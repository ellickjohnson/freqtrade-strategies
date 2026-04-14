import asyncio
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


class BacktestRunner:
    def __init__(self, freqtrade_path: str = "freqtrade"):
        self.freqtrade_path = freqtrade_path
        self.results_dir = Path("/data/results")
        self.results_dir.mkdir(parents=True, exist_ok=True)

    async def run_backtest(
        self,
        strategy: str,
        config_path: str,
        timerange: str,
        pairs: Optional[List[str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cmd = [
            self.freqtrade_path,
            "backtesting",
            "--config",
            config_path,
            "--strategy",
            strategy,
            "--timerange",
            timerange,
        ]

        if pairs:
            cmd.extend(["--pairs", ",".join(pairs)])

        if params:
            params_file = (
                self.results_dir
                / f"params_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            with open(params_file, "w") as f:
                json.dump(params, f)
            cmd.extend(["--strategy-params", str(params_file)])

        result_file = (
            self.results_dir
            / f"backtest_{strategy}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        cmd.extend(["--export", "trades", "--export-filename", str(result_file)])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                return {
                    "success": False,
                    "error": stderr.decode("utf-8"),
                    "strategy": strategy,
                    "timerange": timerange,
                }

            results = self._parse_backtest_output(stdout.decode("utf-8"))

            if result_file.exists():
                with open(result_file, "r") as f:
                    detailed_results = json.load(f)
                results["detailed"] = detailed_results

            results["success"] = True
            results["strategy"] = strategy
            results["timerange"] = timerange
            results["config_path"] = config_path
            results["timestamp"] = datetime.now().isoformat()

            return results

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "strategy": strategy,
                "timerange": timerange,
            }

    def _parse_backtest_output(self, output: str) -> Dict[str, Any]:
        results = {
            "total_trades": 0,
            "profit_mean": 0.0,
            "profit_total": 0.0,
            "profit_total_abs": 0.0,
            "profit_mean_percent": 0.0,
            "profit_total_percent": 0.0,
            "duration_avg": "0:00",
            "win_rate": 0.0,
            "trades": [],
        }

        try:
            lines = output.split("\n")

            for line in lines:
                if "TOTAL " in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "trades:":
                            results["total_trades"] = int(parts[i + 1])
                        elif "Profit:" in line:
                            profit_parts = line.split("Profit:")
                            if len(profit_parts) > 1:
                                profit_str = profit_parts[1].strip().split()[0]
                                try:
                                    results["profit_total_abs"] = float(
                                        profit_str.replace("$", "")
                                    )
                                except:
                                    pass
                        elif "Avg profit" in line:
                            avg_parts = line.split("Avg profit")
                            if len(avg_parts) > 1:
                                avg_str = avg_parts[1].strip().split()[0]
                                try:
                                    results["profit_mean_percent"] = float(
                                        avg_str.replace("%", "")
                                    )
                                except:
                                    pass
                        elif "Total profit" in line:
                            total_parts = line.split("Total profit")
                            if len(total_parts) > 1:
                                total_str = total_parts[1].strip().split()[0]
                                try:
                                    results["profit_total_percent"] = float(
                                        total_str.replace("%", "")
                                    )
                                except:
                                    pass
                        elif "Win  " in line:
                            win_parts = line.split("Win ")
                            if len(win_parts) > 1:
                                win_str = win_parts[1].strip().split()[0]
                                try:
                                    results["win_rate"] = float(
                                        win_str.replace("%", "")
                                    )
                                except:
                                    pass
        except Exception as e:
            print(f"Error parsing backtest output: {e}")

        return results

    async def run_hyperopt(
        self,
        strategy: str,
        config_path: str,
        timerange: str,
        epochs: int = 100,
        spaces: str = "all",
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cmd = [
            self.freqtrade_path,
            "hyperopt",
            "--config",
            config_path,
            "--strategy",
            strategy,
            "--timerange",
            timerange,
            "--epochs",
            str(epochs),
            "--spaces",
            spaces,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                return {
                    "success": False,
                    "error": stderr.decode("utf-8"),
                    "strategy": strategy,
                }

            best_params = self._parse_hyperopt_output(stdout.decode("utf-8"))

            return {
                "success": True,
                "strategy": strategy,
                "timerange": timerange,
                "epochs": epochs,
                "spaces": spaces,
                "best_params": best_params,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            return {"success": False, "error": str(e), "strategy": strategy}

    def _parse_hyperopt_output(self, output: str) -> Dict[str, Any]:
        params = {}

        try:
            lines = output.split("\n")

            for line in lines:
                if "Best result:" in line or "Objective:" in line:
                    objective_match = line.split("Objective:")
                    if len(objective_match) > 1:
                        try:
                            params["objective"] = float(
                                objective_match[1].strip().split()[0]
                            )
                        except:
                            pass

                if "roi_t" in line.lower() or "stoploss" in line.lower():
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = parts[1].strip()
                        try:
                            params[key] = float(value)
                        except:
                            params[key] = value
        except Exception as e:
            print(f"Error parsing hyperopt output: {e}")

        return params

    async def get_backtest_history(
        self, strategy_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        results = []

        for result_file in sorted(
            self.results_dir.glob("backtest_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]:
            try:
                with open(result_file, "r") as f:
                    data = json.load(f)

                result = {
                    "file": str(result_file),
                    "timestamp": data.get("timestamp"),
                    "strategy": data.get("strategy"),
                    "timerange": data.get("timerange"),
                    "total_trades": data.get("total_trades", 0),
                    "profit_total": data.get("profit_total_abs", 0),
                    "win_rate": data.get("win_rate", 0),
                }

                if strategy_id is None or strategy_id in result_file.stem:
                    results.append(result)
            except Exception as e:
                print(f"Error reading {result_file}: {e}")
                continue

        return results

    async def compare_backtests(self, backtest_ids: List[str]) -> Dict[str, Any]:
        comparison = {"backtests": [], "metrics": {}}

        for backtest_id in backtest_ids:
            result_file = self.results_dir / f"{backtest_id}.json"

            if not result_file.exists():
                continue

            try:
                with open(result_file, "r") as f:
                    data = json.load(f)

                comparison["backtests"].append(
                    {
                        "id": backtest_id,
                        "strategy": data.get("strategy"),
                        "total_trades": data.get("total_trades"),
                        "profit_total": data.get("profit_total_abs"),
                        "win_rate": data.get("win_rate"),
                        "profit_mean": data.get("profit_mean_percent"),
                    }
                )
            except Exception as e:
                print(f"Error reading {result_file}: {e}")

        if comparison["backtests"]:
            comparison["metrics"] = {
                "best_profit": max(
                    comparison["backtests"], key=lambda x: x["profit_total"]
                ),
                "best_win_rate": max(
                    comparison["backtests"], key=lambda x: x["win_rate"]
                ),
                "best_trades": max(
                    comparison["backtests"], key=lambda x: x["total_trades"]
                ),
            }

        return comparison
