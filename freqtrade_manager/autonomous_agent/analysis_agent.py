"""
Analysis Agent - Evaluates strategy performance and market conditions.

Analyzes:
- Strategy performance metrics
- Market regime detection (with technical indicators)
- Strategy correlations
- Performance attribution
- Improvement opportunities
"""

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .llm_client import LLMClient
from .knowledge_graph import KnowledgeGraph, Entity, EntityType, Relation, RelationType
from .technical_indicators import TechnicalAnalyzer, TechnicalIndicators
from .data_fetcher import get_data_fetcher

logger = logging.getLogger(__name__)


@dataclass
class AnalysisConfig:
    """Configuration for analysis agent."""

    min_trades_for_evaluation: int = 50
    min_sharpe_ratio: float = 0.5
    max_drawdown_threshold: float = 0.15
    correlation_threshold: float = 0.7
    performance_window_days: int = 30


@dataclass
class StrategyPerformance:
    """Performance metrics for a strategy."""

    strategy_id: str
    strategy_name: str
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    avg_trade_duration: float = 0.0
    profit_pct: float = 0.0
    total_profit: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    avg_profit_trade: float = 0.0
    avg_loss_trade: float = 0.0
    expectancy: float = 0.0
    recovery_factor: float = 0.0
    health_score: float = 0.0
    market_regime_correlation: Dict[str, float] = field(default_factory=dict)


@dataclass
class MarketRegime:
    """Current market regime assessment."""

    regime_type: str  # "trending_up", "trending_down", "ranging", "volatile"
    confidence: float
    characteristics: Dict[str, Any]
    affected_strategies: List[str]
    recommendations: List[str]


class AnalysisAgent:
    """
    Agent that analyzes strategy performance and market conditions.

    Responsibilities:
    - Evaluate strategy performance
    - Detect market regime changes (with technical indicators)
    - Calculate strategy correlations
    - Identify improvement opportunities
    - Generate optimization hypotheses
    """

    def __init__(
        self,
        db_path: str,
        llm_client: LLMClient,
        knowledge_graph: KnowledgeGraph,
        strategy_manager=None,
        config: Optional[AnalysisConfig] = None,
    ):
        self.db_path = db_path
        self.llm = llm_client
        self.kg = knowledge_graph
        self.strategy_manager = strategy_manager
        self.config = config or AnalysisConfig()

        # Initialize technical analyzer
        self.technical_analyzer = TechnicalAnalyzer()
        self.data_fetcher = get_data_fetcher(db_path)

    async def analyze_strategies(
        self,
        strategies: List[Dict],
        research_findings: List[Dict],
    ) -> Dict[str, Any]:
        """
        Perform comprehensive analysis of all strategies.

        Returns analysis results including:
        - Performance metrics for each strategy
        - Market regime assessment
        - Correlation analysis
        - Improvement suggestions
        """
        results = {
            "strategies": {},
            "market_regime": None,
            "correlations": {},
            "recommendations": [],
            "generated_at": datetime.utcnow().isoformat(),
        }

        # Analyze each strategy
        for strategy in strategies:
            strategy_id = strategy.get("id")
            try:
                perf = await self._analyze_strategy_performance(strategy)
                results["strategies"][strategy_id] = perf.to_dict()
            except Exception as e:
                logger.error(f"Failed to analyze strategy {strategy_id}: {e}")
                results["strategies"][strategy_id] = {"error": str(e)}

        # Detect market regime
        try:
            regime = await self._detect_market_regime(strategies, research_findings)
            results["market_regime"] = regime.to_dict() if regime else None
        except Exception as e:
            logger.error(f"Failed to detect market regime: {e}")

        # Calculate correlations
        try:
            correlations = self._calculate_correlations(strategies)
            results["correlations"] = correlations
        except Exception as e:
            logger.error(f"Failed to calculate correlations: {e}")

        # Generate recommendations using LLM
        try:
            recommendations = await self._generate_recommendations(
                results["strategies"],
                results["market_regime"],
                research_findings,
            )
            results["recommendations"] = recommendations
        except Exception as e:
            logger.error(f"Failed to generate recommendations: {e}")

        # Store analysis in knowledge graph
        self._store_analysis(results)

        return results

    async def _analyze_strategy_performance(
        self, strategy: Dict
    ) -> StrategyPerformance:
        """Analyze performance metrics for a single strategy."""
        strategy_id = strategy.get("id")
        strategy_name = strategy.get("name", strategy_id[:8])

        perf = StrategyPerformance(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
        )

        # Get trade history from database
        trades = self._get_strategy_trades(strategy_id)

        if not trades:
            perf.health_score = 0.0
            return perf

        perf.total_trades = len(trades)

        # Calculate win rate
        winning_trades = [t for t in trades if t.get("close_profit", 0) > 0]
        perf.win_rate = len(winning_trades) / len(trades) if trades else 0

        # Calculate profit metrics
        profits = [t.get("close_profit", 0) for t in trades]
        perf.total_profit = sum(profits)
        perf.profit_pct = strategy.get("profit_pct", 0)

        winning_profits = [p for p in profits if p > 0]
        losing_profits = [abs(p) for p in profits if p < 0]

        perf.avg_profit_trade = (
            sum(winning_profits) / len(winning_profits) if winning_profits else 0
        )
        perf.avg_loss_trade = (
            sum(losing_profits) / len(losing_profits) if losing_profits else 0
        )

        # Profit factor
        total_wins = sum(winning_profits)
        total_losses = sum(losing_profits)
        perf.profit_factor = (
            total_wins / total_losses if total_losses > 0 else float("inf")
        )

        # Expectancy
        if trades:
            perf.expectancy = (perf.win_rate * perf.avg_profit_trade) - (
                (1 - perf.win_rate) * perf.avg_loss_trade
            )

        # Best/worst trades
        perf.best_trade = max(profits) if profits else 0
        perf.worst_trade = min(profits) if profits else 0

        # Sharpe ratio (simplified)
        if len(profits) > 1:
            avg_profit = sum(profits) / len(profits)
            std_profit = (
                sum((p - avg_profit) ** 2 for p in profits) / len(profits)
            ) ** 0.5
            perf.sharpe_ratio = avg_profit / std_profit if std_profit > 0 else 0

        # Max drawdown
        cumulative = []
        running = 0
        for p in profits:
            running += p
            cumulative.append(running)

        peak = float("-inf")
        max_dd = 0
        for c in cumulative:
            if c > peak:
                peak = c
            dd = (peak - c) / abs(peak) if peak != 0 else 0
            if dd > max_dd:
                max_dd = dd

        perf.max_drawdown = max_dd

        # Recovery factor
        if perf.max_drawdown > 0:
            perf.recovery_factor = perf.total_profit / perf.max_drawdown

        # Calculate health score
        perf.health_score = self._calculate_health_score(perf)

        return perf

    def _get_strategy_trades(self, strategy_id: str, limit: int = 500) -> List[Dict]:
        """Get trade history for a strategy from the Freqtrade trades database."""
        from pathlib import Path

        try:
            trade_db_path = Path(f"/user_data/{strategy_id}/tradesv3.dryrun.sqlite")
            if not trade_db_path.exists():
                trade_db_path = Path(f"/user_data/{strategy_id}/tradesv3.sqlite")

            if not trade_db_path.exists():
                logger.debug(f"No trade database found for {strategy_id}")
                return []

            conn = sqlite3.connect(str(trade_db_path))
            conn.row_factory = sqlite3.Row
            c = conn.cursor()

            c.execute(
                """
                SELECT * FROM trades
                ORDER BY close_date DESC
                LIMIT ?
            """,
                (limit,),
            )

            rows = c.fetchall()
            conn.close()

            return [dict(row) for row in rows]
        except Exception as e:
            logger.warning(f"Could not get trades for {strategy_id}: {e}")
            return []

    def _calculate_health_score(self, perf: StrategyPerformance) -> float:
        """Calculate overall health score for a strategy."""
        score = 100.0

        # Win rate factor
        if perf.win_rate < 0.4:
            score -= 30
        elif perf.win_rate < 0.5:
            score -= 15
        elif perf.win_rate > 0.6:
            score += 10

        # Sharpe ratio factor
        if perf.sharpe_ratio < 0:
            score -= 20
        elif perf.sharpe_ratio < 0.5:
            score -= 10
        elif perf.sharpe_ratio > 1.5:
            score += 10

        # Drawdown factor
        if perf.max_drawdown > 0.2:
            score -= 25
        elif perf.max_drawdown > 0.15:
            score -= 15
        elif perf.max_drawdown > 0.1:
            score -= 5

        # Profit factor factor
        if perf.profit_factor < 1.0:
            score -= 20
        elif perf.profit_factor > 2.0:
            score += 10

        # Trade count confidence
        if perf.total_trades < 50:
            score -= 10
        elif perf.total_trades > 200:
            score += 5

        # Expectancy factor
        if perf.expectancy < 0:
            score -= 15
        elif perf.expectancy > 0:
            score += 5

        return max(0, min(100, score))

    async def _detect_market_regime(
        self, strategies: List[Dict], research_findings: List[Dict]
    ) -> Optional[MarketRegime]:
        """Detect current market regime using technical indicators and LLM analysis."""
        try:
            # Get technical indicators for BTC (primary market signal)
            btc_indicators = await self._get_technical_indicators("BTC/USDT")

            # Gather market data
            market_data = {
                "strategy_performances": {
                    s.get("id"): {
                        "win_rate": s.get("win_rate", 0),
                        "profit_pct": s.get("profit_pct", 0),
                        "sharpe": s.get("sharpe", 0),
                    }
                    for s in strategies
                },
                "research_sentiment": sum(
                    f.get("sentiment", 0) for f in research_findings
                )
                / max(len(research_findings), 1),
                "technical_indicators": {},
            }

            # Add technical indicators if available
            if btc_indicators:
                market_data["technical_indicators"] = {
                    "adx": btc_indicators.adx,
                    "adx_direction": btc_indicators.adx_direction,
                    "atr_percent": btc_indicators.atr_percent,
                    "rsi": btc_indicators.rsi,
                    "rsi_zone": btc_indicators.rsi_zone,
                    "ema_trend": btc_indicators.ema_trend,
                    "trend_strength": btc_indicators.trend_strength,
                    "volatility_regime": btc_indicators.volatility_regime,
                    "momentum_regime": btc_indicators.momentum_regime,
                    "bollinger_position": btc_indicators.bollinger_position,
                    "price_vs_ema": btc_indicators.price_vs_ema,
                }

            # Detect regime from technical indicators (primary)
            technical_regime = None
            if btc_indicators:
                technical_regime = self.technical_analyzer.detect_regime(btc_indicators)

            # If we have technical regime with high confidence, use it
            if technical_regime and technical_regime.get("confidence", 0) >= 0.7:
                logger.info(
                    f"Using technical regime detection: {technical_regime['regime_type']}"
                )
                return MarketRegime(
                    regime_type=technical_regime["regime_type"],
                    confidence=technical_regime["confidence"],
                    characteristics=technical_regime["characteristics"],
                    affected_strategies=technical_regime["affected_strategies"],
                    recommendations=technical_regime["recommendations"],
                )

            # Otherwise, use LLM analysis with technical data as context
            schema = {
                "type": "object",
                "properties": {
                    "regime_type": {
                        "type": "string",
                        "enum": ["trending_up", "trending_down", "ranging", "volatile"],
                    },
                    "confidence": {"type": "number"},
                    "characteristics": {"type": "object"},
                    "affected_strategies": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "recommendations": {"type": "array", "items": {"type": "string"}},
                },
            }

            # Build prompt with technical context
            tech_context = ""
            if btc_indicators:
                tech_context = f"""
Technical Indicators (BTC/USDT):
- ADX: {btc_indicators.adx:.1f} ({btc_indicators.adx_direction}) - Trend strength
- ATR: {btc_indicators.atr_percent:.2f}% - Volatility
- RSI: {btc_indicators.rsi:.1f} ({btc_indicators.rsi_zone}) - Momentum
- EMA Trend: {btc_indicators.ema_trend}
- Trend Strength: {btc_indicators.trend_strength:.0f}/100
- Volatility Regime: {btc_indicators.volatility_regime}
- Momentum Regime: {btc_indicators.momentum_regime}
- Bollinger Position: {btc_indicators.bollinger_position:.2f}
"""

            prompt = f"""Analyze the current market regime based on this data:
{tech_context}
Strategy performances: {json.dumps(market_data["strategy_performances"], indent=2)}
Research sentiment average: {market_data["research_sentiment"]:.2f}

Determine:
1. The current market regime (trending_up, trending_down, ranging, volatile)
2. Confidence level (0-1)
3. Key characteristics of this regime
4. Which strategy types would be affected
5. Recommendations for trading in this regime"""

            result = await self.llm.analyze(
                prompt,
                schema,
                system_prompt="You are a quantitative market analyst specializing in regime detection.",
            )

            if result:
                # Merge technical regime if available
                if technical_regime:
                    result["confidence"] = max(
                        result.get("confidence", 0.5),
                        technical_regime.get("confidence", 0.5),
                    )

                return MarketRegime(
                    regime_type=result.get("regime_type", "ranging"),
                    confidence=result.get("confidence", 0.5),
                    characteristics=result.get("characteristics", {}),
                    affected_strategies=result.get("affected_strategies", []),
                    recommendations=result.get("recommendations", []),
                )
        except Exception as e:
            logger.error(f"Market regime detection failed: {e}")

        return None

    async def _get_technical_indicators(
        self, pair: str = "BTC/USDT", timeframe: str = "1h"
    ) -> Optional[TechnicalIndicators]:
        """Get technical indicators for a trading pair."""
        try:
            # Try async exchange fetch first, fall back to sync (cache/db)
            ohlcv = await self.data_fetcher.get_ohlcv_async(pair, timeframe, limit=200)
            if ohlcv is None:
                ohlcv = self.data_fetcher.get_ohlcv(pair, timeframe, limit=200)

            if ohlcv is None or len(ohlcv) < 50:
                logger.warning(f"Insufficient OHLCV data for {pair}")
                return None

            # Calculate indicators
            indicators = self.technical_analyzer.calculate_indicators(ohlcv, pair)
            return indicators

        except Exception as e:
            logger.error(f"Error getting technical indicators for {pair}: {e}")
            return None

    def _calculate_correlations(self, strategies: List[Dict]) -> Dict[str, float]:
        """Calculate correlation between strategies based on trade history."""
        # Simplified correlation calculation
        correlations = {}

        for i, s1 in enumerate(strategies):
            for s2 in strategies[i + 1 :]:
                # Get trade history for both
                trades1 = self._get_strategy_trades(s1.get("id"), limit=100)
                trades2 = self._get_strategy_trades(s2.get("id"), limit=100)

                if trades1 and trades2:
                    # Calculate correlation coefficient (simplified)
                    corr = self._pearson_correlation(
                        [t.get("close_profit", 0) for t in trades1],
                        [t.get("close_profit", 0) for t in trades2],
                    )
                    key = f"{s1.get('id')[:8]}_{s2.get('id')[:8]}"
                    correlations[key] = round(corr, 3)

        return correlations

    def _pearson_correlation(self, x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient."""
        n = min(len(x), len(y))
        if n < 2:
            return 0.0

        x = x[:n]
        y = y[:n]

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        denom_x = sum((xi - mean_x) ** 2 for xi in x) ** 0.5
        denom_y = sum((yi - mean_y) ** 2 for yi in y) ** 0.5

        if denom_x == 0 or denom_y == 0:
            return 0.0

        return numerator / (denom_x * denom_y)

    async def _generate_recommendations(
        self,
        strategies: Dict[str, Any],
        market_regime: Optional[Dict],
        research_findings: List[Dict],
    ) -> List[Dict]:
        """Generate optimization recommendations using LLM."""
        try:
            schema = {
                "type": "object",
                "properties": {
                    "recommendations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "strategy_id": {"type": "string"},
                                "action": {"type": "string"},
                                "reasoning": {"type": "string"},
                                "confidence": {"type": "number"},
                                "parameters": {"type": "object"},
                            },
                        },
                    }
                },
            }

            prompt = f"""Based on the following analysis, generate optimization recommendations:

Strategy Performances:
{json.dumps({k: v.get("health_score", "N/A") for k, v in strategies.items()}, indent=2)}

Market Regime:
{json.dumps(market_regime, indent=2) if market_regime else "Unknown"}

Recent Research Findings:
{json.dumps([{"title": f.get("title"), "sentiment": f.get("sentiment")} for f in research_findings[:5]], indent=2)}

Generate specific, actionable recommendations for each strategy.
Actions can be: adjust_parameters, run_hyperopt, stop_strategy, reduce_position, increase_position.
Include specific parameter changes when recommending adjustments."""

            result = await self.llm.analyze(
                prompt,
                schema,
                system_prompt="You are a quantitative trading strategy optimizer.",
            )

            return result.get("recommendations", [])
        except Exception as e:
            logger.error(f"Recommendation generation failed: {e}")
            return []

    def _store_analysis(self, results: Dict[str, Any]):
        """Store analysis results in knowledge graph."""
        # Store as entity
        entity = Entity(
            id=f"analysis_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            entity_type=EntityType.FINDING,
            data={
                "type": "strategy_analysis",
                "results": results,
                "strategy_count": len(results.get("strategies", {})),
                "market_regime": (results.get("market_regime") or {}).get(
                    "regime_type"
                ),
            },
            tags=["analysis", "automated"],
        )
        self.kg.add_entity(entity)

        # Store recommendations as separate entities
        for rec in results.get("recommendations", []):
            rec_entity = Entity(
                id=f"rec_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{hash(rec.get('strategy_id', '')) % 10000}",
                entity_type=EntityType.FINDING,
                data={
                    "type": "recommendation",
                    "strategy_id": rec.get("strategy_id"),
                    "action": rec.get("action"),
                    "reasoning": rec.get("reasoning"),
                    "confidence": rec.get("confidence"),
                    "parameters": rec.get("parameters"),
                },
                tags=["recommendation"],
            )
            self.kg.add_entity(rec_entity)

    def get_strategy_health(self, strategy_id: str) -> Dict[str, Any]:
        """Get health assessment for a specific strategy."""
        perf = StrategyPerformance(
            strategy_id=strategy_id,
            strategy_name=strategy_id[:8],
        )

        trades = self._get_strategy_trades(strategy_id)
        if trades:
            perf.total_trades = len(trades)
            perf.win_rate = len(
                [t for t in trades if t.get("close_profit", 0) > 0]
            ) / len(trades)
            profits = [t.get("close_profit", 0) for t in trades]
            perf.total_profit = sum(profits)
            perf.health_score = self._calculate_health_score(perf)

        return {
            "strategy_id": strategy_id,
            "health_score": perf.health_score,
            "metrics": perf.to_dict(),
            "assessment": self._get_health_assessment(perf),
        }

    def _get_health_assessment(self, perf: StrategyPerformance) -> str:
        """Generate human-readable health assessment."""
        if perf.health_score >= 80:
            return "Excellent - Strategy is performing well"
        elif perf.health_score >= 60:
            return "Good - Strategy is profitable with acceptable risk"
        elif perf.health_score >= 40:
            return "Fair - Strategy needs optimization"
        elif perf.health_score >= 20:
            return "Poor - Consider stopping or major adjustments"
        else:
            return "Critical - Strategy should be stopped"


# Add to_dict method to StrategyPerformance
def strategy_performance_to_dict(self) -> Dict:
    return {
        "strategy_id": self.strategy_id,
        "strategy_name": self.strategy_name,
        "total_trades": self.total_trades,
        "win_rate": self.win_rate,
        "profit_factor": self.profit_factor,
        "sharpe_ratio": self.sharpe_ratio,
        "max_drawdown": self.max_drawdown,
        "avg_trade_duration": self.avg_trade_duration,
        "profit_pct": self.profit_pct,
        "total_profit": self.total_profit,
        "best_trade": self.best_trade,
        "worst_trade": self.worst_trade,
        "avg_profit_trade": self.avg_profit_trade,
        "avg_loss_trade": self.avg_loss_trade,
        "expectancy": self.expectancy,
        "recovery_factor": self.recovery_factor,
        "health_score": self.health_score,
        "market_regime_correlation": self.market_regime_correlation,
    }


StrategyPerformance.to_dict = strategy_performance_to_dict


# Add to_dict method to MarketRegime
def market_regime_to_dict(self) -> Dict:
    return {
        "regime_type": self.regime_type,
        "confidence": self.confidence,
        "characteristics": self.characteristics,
        "affected_strategies": self.affected_strategies,
        "recommendations": self.recommendations,
    }


MarketRegime.to_dict = market_regime_to_dict
