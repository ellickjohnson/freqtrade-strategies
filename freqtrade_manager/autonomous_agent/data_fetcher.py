"""
Data Fetcher - Fetch market data for technical analysis.

Provides OHLCV data from freqtrade database, exchange APIs (via ccxt),
or cached data with graceful fallback.
"""

import asyncio
import os
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class DataFetcher:
    """
    Fetch market data for technical analysis.

    Tries to get OHLCV data from:
    1. Freqtrade strategy databases (if running)
    2. Exchange APIs via ccxt (public endpoints, no auth needed)
    3. Cached/stored data (fallback)
    """

    def __init__(
        self,
        db_path: str = "/data/dashboard.db",
        user_data_dir: str = "/user_data",
        exchange_id: Optional[str] = None,
        exchange_api_key: Optional[str] = None,
        exchange_api_secret: Optional[str] = None,
    ):
        self.db_path = Path(db_path)
        self.user_data_dir = Path(user_data_dir)
        self.exchange_id = exchange_id or os.getenv("EXCHANGE_ID", "binance")
        self.exchange_api_key = exchange_api_key
        self.exchange_api_secret = exchange_api_secret
        self._cache: Dict[str, Tuple[np.ndarray, datetime]] = {}
        self._cache_ttl = timedelta(hours=1)
        self._ccxt_exchange = None
        self._ccxt_lock = asyncio.Lock()

    def _get_ccxt_exchange(self):
        """Lazily initialize ccxt exchange instance."""
        if self._ccxt_exchange is not None:
            return self._ccxt_exchange

        try:
            import ccxt.async_support as ccxt_async

            exchange_class = getattr(ccxt_async, self.exchange_id, None)
            if exchange_class is None:
                logger.warning(f"Unknown exchange: {self.exchange_id}")
                return None

            config = {
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
            if self.exchange_api_key:
                config["apiKey"] = self.exchange_api_key
            if self.exchange_api_secret:
                config["secret"] = self.exchange_api_secret

            self._ccxt_exchange = exchange_class(config)
            logger.info(f"Initialized ccxt exchange: {self.exchange_id}")
            return self._ccxt_exchange

        except ImportError:
            logger.warning("ccxt not installed — exchange OHLCV fetching unavailable. Install: pip install ccxt")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize ccxt exchange: {e}")
            return None

    def get_ohlcv(
        self,
        pair: str = "BTC/USDT",
        timeframe: str = "1h",
        limit: int = 200,
        exchange: str = "binance"
    ) -> Optional[np.ndarray]:
        """
        Get OHLCV data for a trading pair (synchronous wrapper).

        Args:
            pair: Trading pair (e.g., "BTC/USDT")
            timeframe: Timeframe (e.g., "1h", "4h", "1d")
            limit: Number of candles to fetch
            exchange: Exchange name

        Returns:
            numpy array with shape (n, 5) containing [open, high, low, close, volume]
            or None if data not available.
        """
        # Check cache
        cache_key = f"{pair}_{timeframe}"
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if datetime.utcnow() - timestamp < self._cache_ttl:
                return data[-limit:]

        # Try to get from freqtrade database
        data = self._get_from_freqtrade_db(pair, timeframe, limit)
        if data is not None and len(data) >= limit:
            self._cache[cache_key] = (data, datetime.utcnow())
            return data[-limit:]

        # Try to get from exchange API (sync fallback — uses cache or None)
        exchange_data = self._get_from_exchange_sync(pair, timeframe, limit, exchange)
        if exchange_data is not None and len(exchange_data) >= limit:
            self._cache[cache_key] = (exchange_data, datetime.utcnow())
            return exchange_data[-limit:]

        # Return cached data if available (even if stale)
        if cache_key in self._cache:
            logger.warning(f"Using stale cache for {pair}")
            return self._cache[cache_key][0][-limit:]

        logger.warning(f"No OHLCV data available for {pair}")
        return None

    async def get_ohlcv_async(
        self,
        pair: str = "BTC/USDT",
        timeframe: str = "1h",
        limit: int = 200,
    ) -> Optional[np.ndarray]:
        """
        Get OHLCV data asynchronously (uses ccxt for exchange data).

        Args:
            pair: Trading pair
            timeframe: Timeframe
            limit: Number of candles

        Returns:
            numpy array with shape (n, 5) or None
        """
        cache_key = f"{pair}_{timeframe}"
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if datetime.utcnow() - timestamp < self._cache_ttl:
                return data[-limit:]

        # Try freqtrade DB first (fast, local)
        data = self._get_from_freqtrade_db(pair, timeframe, limit)
        if data is not None and len(data) >= limit:
            self._cache[cache_key] = (data, datetime.utcnow())
            return data[-limit:]

        # Try exchange via ccxt (async)
        data = await self._get_from_exchange_async(pair, timeframe, limit)
        if data is not None and len(data) >= limit:
            self._cache[cache_key] = (data, datetime.utcnow())
            return data[-limit:]

        # Stale cache fallback
        if cache_key in self._cache:
            logger.warning(f"Using stale cache for {pair}")
            return self._cache[cache_key][0][-limit:]

        return None

    async def _get_from_exchange_async(
        self,
        pair: str,
        timeframe: str,
        limit: int,
    ) -> Optional[np.ndarray]:
        """Fetch OHLCV from exchange via ccxt async."""
        async with self._ccxt_lock:
            exchange = self._get_ccxt_exchange()
            if exchange is None:
                return None

            try:
                ohlcv = await exchange.fetch_ohlcv(pair, timeframe, limit=limit)
                if not ohlcv:
                    return None

                # ccxt returns [[timestamp, open, high, low, close, volume], ...]
                data = np.array([
                    [candle[1], candle[2], candle[3], candle[4], candle[5]]
                    for candle in ohlcv
                    if len(candle) >= 6
                ], dtype=np.float64)

                logger.info(f"Fetched {len(data)} candles for {pair} from {self.exchange_id}")
                return data if len(data) > 0 else None

            except Exception as e:
                logger.error(f"ccxt fetch_ohlcv failed for {pair}: {e}")
                return None

    def _get_from_exchange_sync(
        self,
        pair: str,
        timeframe: str,
        limit: int,
        exchange: str
    ) -> Optional[np.ndarray]:
        """Sync wrapper — returns None, use async version instead."""
        logger.debug(f"Use get_ohlcv_async() for exchange data; sync path unavailable for {pair}")
        return None

    def _get_from_freqtrade_db(
        self,
        pair: str,
        timeframe: str,
        limit: int
    ) -> Optional[np.ndarray]:
        """Try to get OHLCV from freqtrade strategy databases."""
        try:
            db_files = list(self.user_data_dir.glob("**/*.sqlite"))

            for db_file in db_files:
                try:
                    conn = sqlite3.connect(str(db_file))
                    cursor = conn.cursor()

                    cursor.execute("""
                        SELECT name FROM sqlite_master
                        WHERE type='table' AND name LIKE '%pair%'
                    """)
                    tables = cursor.fetchall()

                    if not tables:
                        conn.close()
                        continue

                    for table_name in [t[0] for t in tables]:
                        try:
                            cursor.execute(f"""
                                SELECT * FROM {table_name}
                                WHERE pair = ? OR pair LIKE ?
                                ORDER BY date DESC LIMIT ?
                            """, (pair, f"%{pair.split('/')[0]}%", limit * 2))

                            rows = cursor.fetchall()
                            if rows:
                                ohlcv = self._parse_db_rows(rows, timeframe)
                                if ohlcv is not None and len(ohlcv) >= limit:
                                    conn.close()
                                    return ohlcv

                        except sqlite3.OperationalError:
                            continue

                    conn.close()

                except Exception as e:
                    logger.debug(f"Error reading {db_file}: {e}")
                    continue

            return None

        except Exception as e:
            logger.error(f"Error fetching from freqtrade DB: {e}")
            return None

    def _parse_db_rows(
        self,
        rows: List[Tuple],
        timeframe: str
    ) -> Optional[np.ndarray]:
        """Parse database rows into OHLCV array."""
        try:
            if not rows:
                return None

            first_row = rows[0]
            num_cols = len(first_row)

            if num_cols >= 6:
                ohlcv = []
                for row in rows:
                    try:
                        open_price = row[-5] if num_cols >= 6 else row[1]
                        high_price = row[-4] if num_cols >= 6 else row[2]
                        low_price = row[-3] if num_cols >= 6 else row[3]
                        close_price = row[-2] if num_cols >= 6 else row[4]
                        volume = row[-1] if num_cols >= 6 else row[5]

                        ohlcv.append([
                            float(open_price),
                            float(high_price),
                            float(low_price),
                            float(close_price),
                            float(volume),
                        ])
                    except (ValueError, TypeError, IndexError):
                        continue

                if ohlcv:
                    return np.array(ohlcv)

            return None

        except Exception as e:
            logger.error(f"Error parsing DB rows: {e}")
            return None

    def get_current_price(self, pair: str = "BTC/USDT") -> Optional[float]:
        """Get current price for a pair (from cache or last close)."""
        data = self.get_ohlcv(pair, "1h", limit=1)
        if data is not None and len(data) > 0:
            return float(data[-1, 3])
        return None

    def get_multiple_pairs(
        self,
        pairs: List[str],
        timeframe: str = "1h",
        limit: int = 200
    ) -> Dict[str, Optional[np.ndarray]]:
        """Get OHLCV for multiple pairs."""
        results = {}
        for pair in pairs:
            results[pair] = self.get_ohlcv(pair, timeframe, limit)
        return results

    async def close(self):
        """Clean up ccxt exchange connection."""
        if self._ccxt_exchange is not None:
            try:
                await self._ccxt_exchange.close()
            except Exception:
                pass
            self._ccxt_exchange = None


# Singleton instance
_data_fetcher: Optional[DataFetcher] = None


def get_data_fetcher(
    db_path: str = "/data/dashboard.db",
    user_data_dir: str = "/user_data"
) -> DataFetcher:
    """Get or create the singleton DataFetcher instance."""
    global _data_fetcher

    if _data_fetcher is None:
        _data_fetcher = DataFetcher(db_path, user_data_dir)

    return _data_fetcher