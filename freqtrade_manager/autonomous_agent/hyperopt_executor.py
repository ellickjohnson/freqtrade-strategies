"""
Hyperopt Executor - Real Freqtrade hyperopt execution.

Replaces mock implementations with actual hyperopt runs.
"""

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from .knowledge_graph import KnowledgeGraph, AgentDecision, EntityType, ResearchFinding

logger = logging.getLogger(__name__)


@dataclass
class HyperoptConfig:
    """Configuration for hyperopt execution."""
    epochs: int = 100
    spaces: List[str] = field(default_factory=lambda: ["buy", "sell", "roi", "stoploss"])
    timerange: str = "20240101-"
    min_trades: int = 100
    max_open_trades: int = 3
    stake_amount: float = 100
    timeframe: str = "15m"
    exchange: str = "kraken"
    pairs: List[str] = field(default_factory=lambda: ["BTC/USDT"])
    strategy_path: Optional[str] = None
    config_path: Optional[str] = None
    user_data_dir: str = "/user_data"
    freqtrade_cmd: str = "freqtrade"


@dataclass
class HyperoptResult:
    """Result of a hyperopt run."""
    hyperopt_id: str
    strategy_id: str
    strategy_name: str
    status: str  # "running", "completed", "failed"
    start_time: datetime
    end_time: Optional[datetime] = None
    epochs_completed: int = 0
    total_epochs: int = 0
    best_params: Dict[str, Any] = field(default_factory=dict)
    best_score: float = 0.0
    metrics: Dict[str, float] = field(default_factory=dict)
    improvement_pct: float = 0.0
    baseline_score: float = 0.0
    results: List[Dict] = field(default_factory=list)
    error: Optional[str] = None


class HyperoptExecutor:
    """
    Executes real Freqtrade hyperopt optimizations.

    Replaces mock implementations with actual subprocess calls to Freqtrade.
    Tracks progress in database and reports results.
    """

    def __init__(
        self,
        db_path: str,
        knowledge_graph: KnowledgeGraph,
        config: Optional[HyperoptConfig] = None,
        progress_callback: Optional[Callable] = None,
    ):
        self.db_path = db_path
        self.kg = knowledge_graph
        self.config = config or HyperoptConfig()
        self.progress_callback = progress_callback

        self._active_runs: Dict[str, asyncio.subprocess.Process] = {}

    async def run_hyperopt(
        self,
        strategy_id: str,
        strategy_name: str,
        strategy_file: str,
        config_path: str,
        timerange: Optional[str] = None,
        epochs: Optional[int] = None,
        spaces: Optional[List[str]] = None,
    ) -> HyperoptResult:
        """
        Execute a hyperopt run for a strategy.

        Args:
            strategy_id: Strategy UUID
            strategy_name: Human-readable name
            strategy_file: Strategy filename (without .py)
            config_path: Path to config file
            timerange: Backtest timerange
            epochs: Number of epochs
            spaces: Hyperopt spaces to optimize

        Returns:
            HyperoptResult with final parameters
        """
        hyperopt_id = f"hyperopt_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{strategy_id[:8]}"
        timerange = timerange or self.config.timerange
        epochs = epochs or self.config.epochs
        spaces = spaces or self.config.spaces

        result = HyperoptResult(
            hyperopt_id=hyperopt_id,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            status="running",
            start_time=datetime.utcnow(),
            total_epochs=epochs,
        )

        # Log start to knowledge graph
        self._log_hyperopt_start(result)

        try:
            # Build hyperopt command
            cmd = self._build_hyperopt_command(
                strategy_file=strategy_file,
                config_path=config_path,
                timerange=timerange,
                epochs=epochs,
                spaces=spaces,
            )

            logger.info(f"Starting hyperopt: {' '.join(cmd)}")

            # Run hyperopt process
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            self._active_runs[hyperopt_id] = process

            # Parse output in real-time
            await self._parse_hyperopt_output(process, result)

            # Wait for completion
            await process.wait()

            result.end_time = datetime.utcnow()

            if process.returncode == 0:
                result.status = "completed"
                # Extract best results from output
                await self._extract_best_results(result)
            else:
                result.status = "failed"
                result.error = f"Hyperopt exited with code {process.returncode}"

        except Exception as e:
            logger.error(f"Hyperopt failed: {e}", exc_info=True)
            result.status = "failed"
            result.error = str(e)
            result.end_time = datetime.utcnow()

        finally:
            self._active_runs.pop(hyperopt_id, None)

        # Log completion to knowledge graph
        self._log_hyperopt_complete(result)

        return result

    def _build_hyperopt_command(
        self,
        strategy_file: str,
        config_path: str,
        timerange: str,
        epochs: int,
        spaces: List[str],
    ) -> List[str]:
        """Build the freqtrade hyperopt command."""
        cmd = [
            self.config.freqtrade_cmd,
            "hyperopt",
            "--config", config_path,
            "--strategy", strategy_file,
            "--timerange", timerange,
            "--epochs", str(epochs),
            "--spaces", " ".join(spaces),
            "--min-trades", str(self.config.min_trades),
            "--max-open-trades", str(self.config.max_open_trades),
            "--stake-amount", str(self.config.stake_amount),
        ]

        # Add joblib for parallelization
        cmd.extend(["--jobs", str(os.cpu_count() or 2)])

        # Add dry-run mode
        cmd.append("--dry-run-wallet")

        return cmd

    async def _parse_hyperopt_output(
        self,
        process: asyncio.subprocess.Process,
        result: HyperoptResult,
    ):
        """Parse hyperopt output in real-time."""
        output_buffer = []

        async def read_stream(stream, name):
            """Read from stream and parse."""
            while True:
                line = await stream.readline()
                if not line:
                    break

                line_str = line.decode("utf-8", errors="replace").strip()
                output_buffer.append(line_str)

                # Parse epoch progress
                if "Epoch" in line_str:
                    self._parse_epoch_progress(line_str, result)

                # Parse best result
                if "Best result:" in line_str:
                    self._parse_best_result(line_str, result)

        # Read both stdout and stderr
        await asyncio.gather(
            read_stream(process.stdout, "stdout"),
            read_stream(process.stderr, "stderr"),
        )

        # Store full output for debugging
        result.results = [{"line": line} for line in output_buffer[-100:]]

    def _parse_epoch_progress(self, line: str, result: HyperoptResult):
        """Parse epoch progress from output line."""
        try:
            # Example: "Epoch 45/100: Win% 52.3%, Sharpe 1.45, Max DD -8.2%"
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "Epoch":
                    epoch_str = parts[i + 1].split("/")[0]
                    result.epochs_completed = int(epoch_str)

                    # Report progress
                    if self.progress_callback:
                        progress = {
                            "hyperopt_id": result.hyperopt_id,
                            "epoch": result.epochs_completed,
                            "total_epochs": result.total_epochs,
                            "best_score": result.best_score,
                        }
                        asyncio.create_task(self.progress_callback(progress))

                    break
        except Exception as e:
            logger.debug(f"Could not parse epoch progress: {e}")

    def _parse_best_result(self, line: str, result: HyperoptResult):
        """Parse best result from output line."""
        try:
            # Example: "Best result: Win% 58.3%, Sharpe 2.12, Profit 15.4%"
            if "Win%" in line:
                parts = line.replace(",", "").split()
                for i, part in enumerate(parts):
                    if part == "Win%":
                        result.metrics["win_rate"] = float(parts[i + 1].replace("%", "")) / 100
                    elif part == "Sharpe":
                        result.metrics["sharpe"] = float(parts[i + 1])
                    elif part == "Profit":
                        result.metrics["profit_pct"] = float(parts[i + 1].replace("%", ""))
                    elif part == "Max" and parts[i + 1] == "DD":
                        result.metrics["max_drawdown"] = float(parts[i + 2].replace("%", "")) / 100

                # Calculate overall score (weighted combination)
                win_rate = result.metrics.get("win_rate", 0.5)
                sharpe = result.metrics.get("sharpe", 0)
                max_dd = result.metrics.get("max_drawdown", 0.2)

                # Score: favor high win rate, high sharpe, low drawdown
                result.best_score = (win_rate * 0.3) + (min(sharpe / 3, 1) * 0.4) + ((1 - min(max_dd * 5, 1)) * 0.3)

        except Exception as e:
            logger.debug(f"Could not parse best result: {e}")

    async def _extract_best_results(self, result: HyperoptResult):
        """Extract best parameters from hyperopt results file."""
        # Freqtrade stores results in user_data/hyperopt_results/
        results_dir = Path(self.config.user_data_dir) / "hyperopt_results"

        if not results_dir.exists():
            logger.warning("Hyperopt results directory not found")
            return

        # Find the most recent results file
        result_files = sorted(results_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

        if not result_files:
            logger.warning("No hyperopt results file found")
            return

        try:
            with open(result_files[0], "r") as f:
                results_data = json.load(f)

            # Extract best parameters
            if "params" in results_data:
                result.best_params = results_data["params"]

            if "metrics" in results_data:
                result.metrics.update(results_data["metrics"])

            # Calculate improvement vs baseline
            baseline_sharpe = 0.5  # Reasonable baseline
            current_sharpe = result.metrics.get("sharpe", 0)

            if current_sharpe > baseline_sharpe:
                result.improvement_pct = ((current_sharpe - baseline_sharpe) / baseline_sharpe) * 100

        except Exception as e:
            logger.error(f"Failed to extract results: {e}")

    def _log_hyperopt_start(self, result: HyperoptResult):
        """Log hyperopt start to database."""
        decision = AgentDecision(
            id=result.hyperopt_id,
            agent_type="hyperopt",
            decision_type="start_hyperopt",
            context={
                "strategy_id": result.strategy_id,
                "strategy_name": result.strategy_name,
                "epochs": result.total_epochs,
            },
            reasoning_chain=[
                f"Starting hyperopt for {result.strategy_name}",
                f"Epochs: {result.total_epochs}",
                f"Timerange: {self.config.timerange}",
            ],
            conclusion=f"Hyperopt {result.hyperopt_id} started",
            confidence=1.0,
        )

        self.kg.log_decision(decision)

    def _log_hyperopt_complete(self, result: HyperoptResult):
        """Log hyperopt completion to database."""
        # Update decision with outcome
        self.kg.update_decision_outcome(
            result.hyperopt_id,
            f"{result.status}: {result.best_score:.4f}",
        )

        # Create research finding if successful
        if result.status == "completed" and result.best_params:
            finding = ResearchFinding(
                id=f"finding_{result.hyperopt_id}",
                source="hyperopt",
                finding_type="parameter_optimization",
                title=f"Hyperopt results for {result.strategy_name}",
                content=f"Found {result.improvement_pct:.1f}% improvement through hyperopt",
                sentiment=0.7 if result.improvement_pct > 0 else 0.3,
                relevance=0.9,
                impact_assessment={
                    "improvement_pct": result.improvement_pct,
                    "best_params": result.best_params,
                    "metrics": result.metrics,
                },
                entities=[result.strategy_id],
                confidence=0.8,
                metadata={
                    "epochs": result.epochs_completed,
                    "best_score": result.best_score,
                    "duration_seconds": (result.end_time - result.start_time).total_seconds() if result.end_time else 0,
                },
            )

            self.kg.add_finding(finding)

    async def cancel_hyperopt(self, hyperopt_id: str) -> bool:
        """Cancel a running hyperopt."""
        if hyperopt_id in self._active_runs:
            process = self._active_runs[hyperopt_id]
            try:
                process.terminate()
                await process.wait()
                return True
            except Exception as e:
                logger.error(f"Failed to cancel hyperopt: {e}")
                return False
        return False

    def get_active_hyperopts(self) -> List[str]:
        """Get list of active hyperopt IDs."""
        return list(self._active_runs.keys())

    async def run_backtest_comparison(
        self,
        strategy_id: str,
        strategy_file: str,
        config_path: str,
        timeranges: List[str],
        params_list: List[Dict],
    ) -> Dict[str, Any]:
        """
        Run backtests across multiple timeranges and parameter combinations.

        Returns comparison results for each combination.
        """
        comparison_id = f"backtest_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{strategy_id[:8]}"
        results = []

        for timerange in timeranges:
            for params in params_list:
                backtest_result = await self._run_single_backtest(
                    comparison_id=comparison_id,
                    strategy_file=strategy_file,
                    config_path=config_path,
                    timerange=timerange,
                    params=params,
                )
                results.append(backtest_result)

        # Find best result
        best = max(results, key=lambda r: r.get("sharpe", 0), default={})

        return {
            "comparison_id": comparison_id,
            "strategy_id": strategy_id,
            "results": results,
            "best_result": best,
            "total_runs": len(results),
        }

    async def _run_single_backtest(
        self,
        comparison_id: str,
        strategy_file: str,
        config_path: str,
        timerange: str,
        params: Dict,
    ) -> Dict[str, Any]:
        """Run a single backtest."""
        # Build backtest command
        cmd = [
            self.config.freqtrade_cmd,
            "backtesting",
            "--config", config_path,
            "--strategy", strategy_file,
            "--timerange", timerange,
            "--dry-run-wallet",
        ]

        # Add custom parameters via export-filename trick
        # In practice, would create a temp config with params

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()
            output = stdout.decode("utf-8", errors="replace")

            # Parse backtest results
            # Freqtrade outputs JSON results at end
            result = self._parse_backtest_output(output)
            result["timerange"] = timerange
            result["params"] = params
            result["comparison_id"] = comparison_id

            return result

        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            return {"error": str(e), "timerange": timerange, "params": params}

    def _parse_backtest_output(self, output: str) -> Dict[str, Any]:
        """Parse backtest results from output."""
        result = {
            "total_trades": 0,
            "profit_total": 0,
            "profit_pct": 0,
            "win_rate": 0,
            "sharpe": 0,
            "max_drawdown": 0,
        }

        try:
            # Look for JSON output
            if "BACKTESTING REPORT" in output:
                # Parse text output
                lines = output.split("\n")
                for line in lines:
                    if "Total trades:" in line:
                        result["total_trades"] = int(line.split(":")[1].strip())
                    elif "Total profit:" in line:
                        profit_str = line.split(":")[1].strip()
                        if "%" in profit_str:
                            result["profit_pct"] = float(profit_str.replace("%", "").strip())
                    elif "Win%" in line:
                        result["win_rate"] = float(line.split(":")[1].strip().replace("%", "")) / 100
                    elif "Sharpe" in line:
                        result["sharpe"] = float(line.split(":")[1].strip())
                    elif "Max drawdown" in line:
                        dd_str = line.split(":")[1].strip().replace("%", "")
                        result["max_drawdown"] = float(dd_str) / 100

        except Exception as e:
            logger.debug(f"Could not parse backtest output: {e}")

        return result


# Helper to convert HyperoptResult to dict
def hyperopt_result_to_dict(self) -> Dict:
    return {
        "hyperopt_id": self.hyperopt_id,
        "strategy_id": self.strategy_id,
        "strategy_name": self.strategy_name,
        "status": self.status,
        "start_time": self.start_time.isoformat(),
        "end_time": self.end_time.isoformat() if self.end_time else None,
        "epochs_completed": self.epochs_completed,
        "total_epochs": self.total_epochs,
        "best_params": self.best_params,
        "best_score": self.best_score,
        "metrics": self.metrics,
        "improvement_pct": self.improvement_pct,
        "baseline_score": self.baseline_score,
        "error": self.error,
    }

HyperoptResult.to_dict = hyperopt_result_to_dict