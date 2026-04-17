import asyncio
import json
import os
from typing import Dict, Any, Set, Optional
from datetime import datetime
from websockets.server import serve
from websockets.client import WebSocketClientProtocol


class WebSocketServer:
    def __init__(self, port: int = 8765, host: str = "0.0.0.0"):
        self.port = port
        self.host = host
        self.clients: Set[WebSocketClientProtocol] = set()
        self.manager = None
        self.slack = None

    def set_manager(self, manager):
        self.manager = manager

    def set_slack(self, slack):
        self.slack = slack

    async def register_client(self, websocket: WebSocketClientProtocol):
        self.clients.add(websocket)
        await self.send_to_client(
            websocket,
            {
                "event": "connected",
                "data": {"message": "WebSocket connection established"},
                "timestamp": datetime.now().isoformat(),
            },
        )

    async def unregister_client(self, websocket: WebSocketClientProtocol):
        self.clients.discard(websocket)

    async def send_to_client(
        self, websocket: WebSocketClientProtocol, message: Dict[str, Any]
    ):
        try:
            await websocket.send(json.dumps(message))
        except Exception as e:
            print(f"Error sending to client: {e}")

    async def broadcast(self, event: str, data: Dict[str, Any]):
        if not self.clients:
            return

        message = {
            "event": event,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        }

        await asyncio.gather(
            *[self.send_to_client(client, message) for client in self.clients],
            return_exceptions=True,
        )

    async def handle_command(
        self, command: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not self.manager:
            return {"error": "Manager not initialized"}

        try:
            if command == "start_strategy":
                strategy_id = data.get("strategy_id")
                result = await self.manager.start_strategy(strategy_id)
                return {"success": True, "result": result}

            elif command == "stop_strategy":
                strategy_id = data.get("strategy_id")
                result = await self.manager.stop_strategy(strategy_id)
                return {"success": True, "result": result}

            elif command == "restart_strategy":
                strategy_id = data.get("strategy_id")
                result = await self.manager.restart_strategy(strategy_id)
                return {"success": True, "result": result}

            elif command == "get_status":
                strategy_id = data.get("strategy_id")
                status = await self.manager.get_strategy_status(strategy_id)
                return {"success": True, "status": status}

            elif command == "get_all_strategies":
                strategies = await self.manager.get_all_strategies()
                return {"success": True, "strategies": strategies}

            elif command == "run_backtest":
                result = await self.manager.run_backtest(
                    strategy_id=data.get("strategy_id"),
                    timerange=data.get("timerange"),
                    params=data.get("params"),
                )
                return {"success": True, "result": result}

            elif command == "update_config":
                strategy_id = data.get("strategy_id")
                config = data.get("config")
                result = await self.manager.update_strategy_config(strategy_id, config)
                return {"success": True, "result": result}

            else:
                return {"error": f"Unknown command: {command}"}

        except Exception as e:
            return {"error": str(e)}

    async def message_handler(self, websocket: WebSocketClientProtocol, path: str):
        await self.register_client(websocket)

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    command = data.get("command")
                    payload = data.get("data", {})

                    response = await self.handle_command(command, payload)
                    await self.send_to_client(
                        websocket,
                        {"event": "response", "command": command, "data": response},
                    )

                except json.JSONDecodeError:
                    await self.send_to_client(
                        websocket,
                        {"event": "error", "data": {"message": "Invalid JSON"}},
                    )

                except Exception as e:
                    await self.send_to_client(
                        websocket, {"event": "error", "data": {"message": str(e)}}
                    )

        finally:
            await self.unregister_client(websocket)

    async def start(self):
        print(f"Starting WebSocket server on {self.host}:{self.port}")

        async with serve(self.message_handler, self.host, self.port):
            await asyncio.Future()

    def get_client_count(self) -> int:
        return len(self.clients)


class TradeMonitor:
    def __init__(self, ws_server: WebSocketServer, user_data_dir: str = "/user_data"):
        self.ws_server = ws_server
        self.user_data_dir = user_data_dir
        self.monitored_strategies: Set[str] = set()

    async def start_monitoring(self, strategy_id: str):
        self.monitored_strategies.add(strategy_id)
        asyncio.create_task(self._monitor_trades(strategy_id))

    async def stop_monitoring(self, strategy_id: str):
        self.monitored_strategies.discard(strategy_id)

    async def _monitor_trades(self, strategy_id: str):
        import sqlite3
        from pathlib import Path

        db_path = Path(self.user_data_dir) / strategy_id / "tradesv3.dryrun.sqlite"

        if not db_path.exists():
            return

        last_trade_count = 0

        while strategy_id in self.monitored_strategies:
            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.execute("SELECT COUNT(*) FROM trades")
                current_count = cursor.fetchone()[0]

                if current_count > last_trade_count:
                    cursor = conn.execute(
                        """
                        SELECT pair, open_rate, close_rate, close_profit_abs, 
                               open_date, close_date, is_open, exit_reason
                        FROM trades 
                        ORDER BY id DESC 
                        LIMIT ?
                    """,
                        (current_count - last_trade_count,),
                    )

                    new_trades = cursor.fetchall()

                    for trade in new_trades:
                        is_open = trade[6] == 1
                        pnl = trade[3] if trade[3] is not None else 0.0

                        if is_open:
                            reason = "Strategy entry conditions met"
                        else:
                            reason = trade[7] or "Strategy exit signal"

                        await self.ws_server.broadcast(
                            "trade",
                            {
                                "strategy_id": strategy_id,
                                "pair": trade[0],
                                "open_rate": trade[1],
                                "close_rate": trade[2],
                                "profit_abs": trade[3],
                                "open_date": trade[4],
                                "close_date": trade[5],
                                "is_open": is_open,
                                "exit_reason": reason,
                                "profit_pct": (
                                    (trade[2] - trade[1]) / trade[1] * 100
                                    if trade[1] is not None and trade[1] > 0
                                    else 0
                                ),
                            },
                        )

                        if self.ws_server.slack:
                            await self.ws_server.slack.send_trade_alert(
                                strategy_name=strategy_id[:8],
                                action="sell" if not is_open else "buy",
                                pair=trade[0],
                                price=trade[1] if is_open else (trade[2] or trade[1]),
                                reason=reason,
                                pnl=None if is_open else pnl,
                            )

                    last_trade_count = current_count

                conn.close()

            except Exception as e:
                print(f"Error monitoring trades for {strategy_id}: {e}")

            await asyncio.sleep(5)


class LogStreamer:
    def __init__(self, ws_server: WebSocketServer, user_data_dir: str = "/user_data"):
        self.ws_server = ws_server
        self.user_data_dir = user_data_dir
        self.log_streams: Dict[str, asyncio.Task] = {}

    async def start_streaming(self, strategy_id: str):
        if strategy_id in self.log_streams:
            return

        task = asyncio.create_task(self._stream_logs(strategy_id))
        self.log_streams[strategy_id] = task

    async def stop_streaming(self, strategy_id: str):
        if strategy_id in self.log_streams:
            self.log_streams[strategy_id].cancel()
            del self.log_streams[strategy_id]

    async def _stream_logs(self, strategy_id: str):
        log_path = Path(self.user_data_dir) / strategy_id / "bot.log"

        try:
            with open(log_path, "r") as f:
                f.seek(0, 2)

                while True:
                    line = f.readline()

                    if not line:
                        await asyncio.sleep(0.1)
                        continue

                    await self.ws_server.broadcast(
                        "log",
                        {
                            "strategy_id": strategy_id,
                            "message": line.strip(),
                            "timestamp": datetime.now().isoformat(),
                        },
                    )

        except Exception as e:
            print(f"Error streaming logs for {strategy_id}: {e}")

        finally:
            if strategy_id in self.log_streams:
                del self.log_streams[strategy_id]


from pathlib import Path
