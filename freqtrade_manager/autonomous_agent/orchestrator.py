"""
Orchestrator Agent - Main coordination agent for autonomous financial engineering.

This is the central agent that coordinates all sub-agents (Research, Analysis, Risk, Strategy)
and makes portfolio-level decisions.
"""

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

from .llm_client import LLMClient, LLMConfig, LLMProvider
from .knowledge_graph import (
    KnowledgeGraph,
    AgentDecision,
    Entity,
    EntityType,
)
from .activity_logger import ActivityLogger, ActivityType

logger = logging.getLogger(__name__)


class AgentState(Enum):
    IDLE = "idle"
    RESEARCHING = "researching"
    ANALYZING = "analyzing"
    RISK_CHECKING = "risk_checking"
    DECIDING = "deciding"
    EXECUTING = "executing"
    ERROR = "error"


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator agent."""

    interval_minutes: int = 5
    max_concurrent_research: int = 3
    min_improvement_threshold: float = 5.0
    auto_apply_improvements: bool = (
        True  # Auto-apply safe decisions; high-risk ones still require approval
    )
    paper_trading_only: bool = True

    # Risk limits
    max_portfolio_drawdown: float = 15.0
    max_position_size_pct: float = 10.0
    max_correlated_strategies: int = 3

    # Strategy lifecycle
    min_trades_for_evaluation: int = 100
    min_sharpe_ratio: float = 0.5
    strategy_deprecation_threshold: float = -5.0

    # LLM settings
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-6"


@dataclass
class AgentContext:
    """Context passed between agents."""

    timestamp: datetime = field(default_factory=datetime.utcnow)
    strategies: List[Dict] = field(default_factory=list)
    portfolio_summary: Dict = field(default_factory=dict)
    research_findings: List[Dict] = field(default_factory=list)
    analysis_results: Dict = field(default_factory=dict)
    risk_report: Dict = field(default_factory=dict)
    recent_decisions: List[Dict] = field(default_factory=list)
    market_regime: Optional[str] = None
    errors: List[str] = field(default_factory=list)


class OrchestratorAgent:
    """
    Central coordination agent for autonomous financial engineering.

    Responsibilities:
    - Coordinate all sub-agents (Research, Analysis, Risk, Strategy)
    - Prioritize tasks based on urgency and importance
    - Make portfolio-level decisions
    - Log all reasoning and decisions
    - Manage approval workflows
    - Ensure safety limits are respected
    """

    def __init__(
        self,
        db_path: str,
        config: Optional[OrchestratorConfig] = None,
        llm_client: Optional[LLMClient] = None,
        strategy_manager=None,  # FreqtradeManager
        notification_callback: Optional[Callable] = None,
    ):
        self.config = config or OrchestratorConfig()
        self.db_path = db_path
        self.kg = KnowledgeGraph(db_path)
        self.llm = llm_client or LLMClient(
            LLMConfig(
                provider=LLMProvider(self.config.llm_provider)
                if isinstance(self.config.llm_provider, str)
                else self.config.llm_provider,
                model=self.config.llm_model,
            )
        )
        self.strategy_manager = strategy_manager
        self.notification_callback = notification_callback
        self.hyperopt_executor = None

        self.state = AgentState.IDLE
        self.running = False
        self.last_run: Optional[datetime] = None
        self.context = AgentContext()

        # Sub-agents will be initialized lazily
        self._research_agent = None
        self._analysis_agent = None
        self._risk_agent = None
        self._strategy_agent = None
        self.activity = ActivityLogger()

    async def start(self):
        """Start the orchestration loop."""
        if self.running:
            logger.warning("Orchestrator already running")
            return

        self.running = True
        logger.info("Starting orchestrator agent")

        # Ensure existing strategies are running
        await self._ensure_strategies_running()

        while self.running:
            try:
                await self._run_cycle()
            except Exception as e:
                logger.error(f"Orchestration cycle failed: {e}", exc_info=True)
                self.state = AgentState.ERROR
                self.context.errors.append(str(e))
                self.activity.log(
                    ActivityType.ERROR,
                    "OrchestratorAgent",
                    "Orchestration Cycle Failed",
                    str(e),
                    {"error": str(e)},
                )

            # Wait for next cycle
            await asyncio.sleep(self.config.interval_minutes * 60)

    async def _ensure_strategies_running(self):
        """Auto-start any strategies that should be running but have stopped containers."""
        if not self.strategy_manager:
            return

        try:
            strategies = await self.strategy_manager.get_all_strategies()
            for s in strategies:
                if not s.get("enabled"):
                    continue
                if s.get("status") != "running":
                    continue

                stopped_automatically = False
                decisions = self.kg.get_decisions(
                    decision_type="stop_strategy", limit=10
                )
                for d in decisions:
                    if d.outcome and "strategy_stopped" in (d.outcome or ""):
                        if s["id"] in str(d.context):
                            stopped_automatically = True
                            break

                if stopped_automatically:
                    logger.info(
                        f"Skipping auto-start for {s['name']} — was intentionally stopped by orchestrator"
                    )
                    continue

                container_status = (s.get("container_status") or {}).get(
                    "status", "unknown"
                )
                if container_status in ("exited", "dead", "unknown", None):
                    logger.info(
                        f"Auto-starting strategy: {s['name']} (container was {container_status})"
                    )
                    try:
                        await self.strategy_manager.start_strategy(s["id"])
                    except Exception as e:
                        logger.warning(f"Failed to auto-start {s['name']}: {e}")
        except Exception as e:
            logger.warning(f"Strategy auto-start check failed: {e}")

    def stop(self):
        """Stop the orchestration loop."""
        logger.info("Stopping orchestrator agent")
        self.running = False

    async def _run_cycle(self):
        """Execute one orchestration cycle."""
        logger.info("Starting orchestration cycle")
        start_time = datetime.utcnow()

        self.context.errors = []

        self.activity.log(
            ActivityType.INFO,
            "OrchestratorAgent",
            "Orchestration Cycle Started",
            "Starting new analysis cycle — gathering data, running research, and making decisions",
        )

        # 0. Check container health and diagnose problems
        await self._check_container_health()

        # 1. Gather context
        self.state = AgentState.ANALYZING
        await self._gather_context()

        # 2. Run research agent (gathers external data)
        self.state = AgentState.RESEARCHING
        self.activity.log(
            ActivityType.RESEARCH_START,
            "ResearchAgent",
            "Gathering Market Intelligence",
            f"Fetching news, sentiment, macro indicators, and on-chain data for {len(self.context.strategies)} strategies",
            {"strategy_count": len(self.context.strategies)},
            progress=0.0,
        )
        research_findings = await self._run_research_agent()
        self.context.research_findings = research_findings
        self.activity.log(
            ActivityType.RESEARCH_COMPLETE,
            "ResearchAgent",
            f"Research Complete — {len(research_findings)} Findings",
            f"Gathered {len(research_findings)} market intelligence findings from news, sentiment, macro, and on-chain sources",
            {"finding_count": len(research_findings)},
            progress=1.0,
        )

        # 3. Run analysis agent (evaluates strategies)
        self.state = AgentState.ANALYZING
        self.activity.log(
            ActivityType.ANALYSIS_START,
            "AnalysisAgent",
            "Analyzing Strategy Performance",
            f"Evaluating {len(self.context.strategies)} strategies for health, risk, and optimization opportunities",
            {"strategy_count": len(self.context.strategies)},
            progress=0.0,
        )
        analysis_results = await self._run_analysis_agent()
        self.context.analysis_results = analysis_results
        strategy_analyses = analysis_results.get("strategies", {})
        healthy = sum(
            1
            for a in strategy_analyses.values()
            if isinstance(a, dict) and a.get("health_score", 0) > 50
        )
        self.activity.log(
            ActivityType.ANALYSIS_COMPLETE,
            "AnalysisAgent",
            f"Analysis Complete — {healthy}/{len(strategy_analyses)} Healthy",
            f"Analyzed {len(strategy_analyses)} strategies: {healthy} healthy, {len(strategy_analyses) - healthy} need attention",
            {"healthy": healthy, "total": len(strategy_analyses)},
            progress=1.0,
        )

        # 4. Run risk agent (checks risk limits)
        self.state = AgentState.RISK_CHECKING
        risk_report = await self._run_risk_agent()
        self.context.risk_report = risk_report
        risk_level = (
            risk_report.get("overall_risk_level", "unknown")
            if risk_report
            else "unknown"
        )
        self.activity.log(
            ActivityType.INFO,
            "RiskAgent",
            f"Risk Assessment: {risk_level.upper()}",
            f"Portfolio risk check complete. Overall risk level: {risk_level}",
            {"risk_level": risk_level, "report": risk_report},
        )

        # 5. Generate decisions (LLM + stale strategy auto-adjustments)
        self.state = AgentState.DECIDING
        decisions = await self._make_decisions()

        stale_decisions = self._check_stale_strategies()
        if stale_decisions:
            decisions.extend(stale_decisions)
            self.activity.log(
                ActivityType.DECISION_MADE,
                "OrchestratorAgent",
                f"Auto-generated {len(stale_decisions)} Decision(s) for Stale Strategies",
                f"Strategies with 0 trades after multiple cycles — widening parameters",
                {"stale_count": len(stale_decisions)},
            )

        if decisions:
            self.activity.log(
                ActivityType.DECISION_MADE,
                "OrchestratorAgent",
                f"Made {len(decisions)} Decision(s)",
                f"Decisions: {', '.join(d.decision_type for d in decisions)}",
                {
                    "decision_types": [d.decision_type for d in decisions],
                    "confidence_scores": [d.confidence for d in decisions],
                },
            )

        # 6. Execute approved decisions
        self.state = AgentState.EXECUTING
        executed = await self._execute_decisions(decisions)
        if executed:
            actions_str = ", ".join(str(a) for a in executed)
            self.activity.log(
                ActivityType.INFO,
                "OrchestratorAgent",
                f"Executed {len(executed)} Action(s)",
                f"Actions taken: {actions_str}",
                {"actions": executed},
            )

        # 7. Log reasoning
        await self._log_cycle_summary(start_time, executed)

        self.state = AgentState.IDLE
        self.last_run = datetime.utcnow()

    async def _check_container_health(self):
        """Check strategy container health and diagnose problems."""
        if not self.strategy_manager:
            return

        problems = []

        try:
            strategies = await self.strategy_manager.get_all_strategies()

            for s in strategies:
                sid = s.get("id", "?")[:8]
                name = s.get("name", "?")
                status = s.get("status", "?")
                container_status = (s.get("container_status") or {}).get(
                    "status", "none"
                )

                if status == "running" and container_status in ("exited", "dead", None):
                    problems.append(
                        {
                            "strategy_id": sid,
                            "strategy_name": name,
                            "problem": f"Container is {container_status} but strategy status is 'running'",
                            "action": "restart_container",
                        }
                    )
                    logger.warning(
                        f"HEALTH: {name} container {container_status} but marked running - will auto-restart"
                    )

                elif status == "running" and container_status == "running":
                    total_trades = s.get("total_trades", 0)
                    win_rate = s.get("win_rate", 0)
                    logger.info(
                        f"HEALTH: {name} container running | trades={total_trades} | win_rate={win_rate:.1%}"
                    )

                    if total_trades == 0 and self.last_run is not None:
                        hours_running = (
                            datetime.utcnow() - (self.last_run or datetime.utcnow())
                        ).total_seconds() / 3600
                        if hours_running > 0.5:
                            problems.append(
                                {
                                    "strategy_id": sid,
                                    "strategy_name": name,
                                    "problem": f"Running for >30min with 0 trades - entry conditions may be too strict or pairs too few",
                                    "action": "alert_user",
                                }
                            )
                            logger.warning(
                                f"HEALTH: {name} has 0 trades after running - conditions may be too strict"
                            )

                elif status == "stopped":
                    logger.info(f"HEALTH: {name} intentionally stopped")

        except Exception as e:
            logger.error(f"Container health check failed: {e}")

        if problems:
            logger.warning(f"Container health check found {len(problems)} problems")
            for p in problems:
                self.activity.log(
                    ActivityType.ERROR,
                    "OrchestratorAgent",
                    f"Health Alert: {p['strategy_name']}",
                    p["problem"],
                    {"strategy_id": p["strategy_id"], "action": p["action"]},
                )
                if p["action"] == "restart_container":
                    try:
                        await self.strategy_manager.start_strategy(p["strategy_id"])
                        logger.info(f"HEALTH: Auto-restarted {p['strategy_name']}")
                        self.activity.log(
                            ActivityType.INFO,
                            "OrchestratorAgent",
                            f"Restarted {p['strategy_name']}",
                            "Container was down — auto-restarted",
                        )
                    except Exception as e:
                        logger.error(
                            f"HEALTH: Failed to restart {p['strategy_name']}: {e}"
                        )
                        self.activity.log(
                            ActivityType.ERROR,
                            "OrchestratorAgent",
                            f"Failed to restart {p['strategy_name']}",
                            str(e),
                        )

                if self.notification_callback:
                    try:
                        await self.notification_callback(
                            {
                                "type": "health_alert",
                                "message": f"Strategy {p['strategy_name']}: {p['problem']}",
                                "action": p["action"],
                            }
                        )
                    except Exception:
                        pass

    async def _gather_context(self):
        """Gather current context from strategy manager."""
        if not self.strategy_manager:
            logger.warning("No strategy manager connected")
            return

        try:
            # Get all strategies
            strategies = await self.strategy_manager.get_all_strategies()
            self.context.strategies = strategies

            # Get portfolio summary
            portfolio = await self.strategy_manager.get_portfolio_summary()
            self.context.portfolio_summary = portfolio

            # Get recent decisions
            recent = self.kg.get_decisions(
                since=datetime.utcnow() - timedelta(hours=24)
            )
            self.context.recent_decisions = [d.to_dict() for d in recent]

            # Get unapplied research findings
            findings = self.kg.get_unapplied_findings(limit=20)
            self.context.research_findings = [f.to_dict() for f in findings]

        except Exception as e:
            logger.error(f"Failed to gather context: {e}")
            self.context.errors.append(f"Context gathering failed: {e}")

    async def _run_research_agent(self) -> List[Dict]:
        """Run research agent to gather external data."""
        # Import here to avoid circular imports
        from .research_agent import ResearchAgent

        if not self._research_agent:
            self._research_agent = ResearchAgent(
                db_path=self.db_path,
                llm_client=self.llm,
                knowledge_graph=self.kg,
            )

        findings = await self._research_agent.run()
        return findings

    async def _run_analysis_agent(self) -> Dict:
        """Run analysis agent to evaluate strategy performance."""
        from .analysis_agent import AnalysisAgent

        if not self._analysis_agent:
            self._analysis_agent = AnalysisAgent(
                db_path=self.db_path,
                llm_client=self.llm,
                knowledge_graph=self.kg,
                strategy_manager=self.strategy_manager,
            )

        results = await self._analysis_agent.analyze_strategies(
            self.context.strategies,
            self.context.research_findings,
        )
        return results

    async def _run_risk_agent(self) -> Dict:
        """Run risk agent to check portfolio risk."""
        from .risk_agent import RiskAgent

        if not self._risk_agent:
            from .risk_agent import RiskLimits

            risk_config = RiskLimits()
            self._risk_agent = RiskAgent(
                db_path=self.db_path,
                knowledge_graph=self.kg,
                config=risk_config,
            )

        report = await self._risk_agent.check_portfolio_risk(
            self.context.strategies,
            self.context.portfolio_summary,
        )
        return report

    async def _make_decisions(self) -> List[AgentDecision]:
        """Use LLM to make decisions based on context."""
        decisions = []

        context_str = self._build_decision_context()

        strategy_ids = [s.get("id", "?") for s in (self.context.strategies or [])[:5]]
        strategy_names = [
            s.get("name", "?") for s in (self.context.strategies or [])[:5]
        ]
        id_name_pairs = ", ".join(
            f'"{sid}" ({sname})' for sid, sname in zip(strategy_ids, strategy_names)
        )

        valid_decision_types = [
            "adjust_parameters",
            "run_hyperopt",
            "stop_strategy",
            "create_strategy",
            "no_action",
        ]

        decision_schema = {
            "type": "object",
            "properties": {
                "decisions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "decision_type": {
                                "type": "string",
                                "enum": valid_decision_types,
                            },
                            "target": {
                                "type": "string",
                                "description": "Must be one of the strategy IDs listed above",
                            },
                            "parameters": {
                                "type": "object",
                                "description": "For adjust_parameters: rsi_entry_threshold, volume_factor, stoploss, trailing_stop_positive, pairs_to_add, pairs_to_remove. For run_hyperopt: epochs, spaces. For create_strategy: template_id, pairs, exchange.",
                            },
                            "reasoning": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["decision_type", "reasoning", "confidence"],
                    },
                }
            },
            "required": ["decisions"],
        }

        system_prompt = (
            "You are an autonomous trading STRATEGY manager. You manage Freqtrade strategy bots. "
            "You do NOT trade directly — strategies handle trades based on their parameters. "
            "Your job is to review strategy health, research findings, and market conditions, "
            "then decide what PARAMETER CHANGES or STRATEGY ACTIONS to take.\n\n"
            "CRITICAL RULES:\n"
            "- 'target' MUST be a strategy ID (UUID format) from the Strategies list above, NOT a coin name (BTC, ETH) or number.\n"
            "- Do NOT use 'buy' or 'sell' as decision_type — strategies handle trading automatically.\n"
            "- If ALL strategies are new (0 trades) and have NEVER had hyperopt, choose 'run_hyperopt' for at least one.\n"
            "- If a strategy has 0 trades after running, use 'adjust_parameters' to widen entry conditions (e.g., wider RSI thresholds, lower volume requirements, wider stoploss).\n"
            "- DO NOT choose 'no_action' for ALL strategies if any has 0 trades and has never been optimized — at least try run_hyperopt or adjust_parameters.\n"
            "- For 'adjust_parameters', you MUST include a 'parameters' dict with at least one specific change.\n"
            "- Limit to 1-2 decisions per cycle. Quality over quantity.\n"
            "- confidence must be a number between 0.0 and 1.0, NOT a string like 'medium'.\n\n"
            "DECISION TYPES:\n"
            "1. adjust_parameters - Change a strategy's trading parameters. REQUIRES target (strategy ID) and parameters dict.\n"
            "   Valid parameters: rsi_entry_threshold (20-60), volume_factor (0.5-3.0), stoploss (-0.01 to -0.15),\n"
            '   trailing_stop_positive (0.005-0.05), minimal_roi (dict like {"0": 0.015, "10": 0.01}),\n'
            '   pairs_to_add (list like ["XRP/USDT"]), pairs_to_remove (list)\n'
            '2. run_hyperopt - Run parameter optimization. REQUIRES target (strategy ID), parameters: {epochs: 50-200, spaces: ["buy","sell","roi","stoploss"]}\n'
            "   Use this for strategies that have NEVER been hyperopt'd (Hyperopt: never) or have been running poorly.\n"
            "3. stop_strategy - Stop a poorly performing strategy. REQUIRES target (strategy ID).\n"
            "4. create_strategy - Create a new strategy. REQUIRES parameters: {template_id: 'string', pairs: ['BTC/USDT',...], exchange: 'kraken'}\n"
            "5. no_action - Do nothing this cycle. Use ONLY when all strategies are healthy and have been recently optimized."
        )

        prompt = (
            context_str
            + f"\n\n## Valid Strategy IDs\n{id_name_pairs}\n\n"
            + "Based on the context above, decide what actions to take. "
            + "If any strategy has 0 trades and hasn't been hyperopt'd, prefer 'run_hyperopt'. "
            + "If a strategy has 0 trades after running, prefer 'adjust_parameters' to widen entries. "
            + 'Respond with JSON: {"decisions": [{"decision_type": "adjust_parameters", "target": "<strategy_id>", "parameters": {...}, "reasoning": "...", "confidence": 0.7}]}\n\n'
            + "Only choose 'no_action' if all strategies have trades and are performing within acceptable ranges."
        )

        try:
            llm_available = await self.llm.is_available()
            if not llm_available:
                logger.warning("LLM unavailable — skipping LLM-driven decisions")
            else:
                response = await self.llm.analyze(
                    prompt=prompt,
                    schema=decision_schema,
                    system_prompt=system_prompt,
                )

                if response and "decisions" in response:
                    logger.info(f"LLM returned {len(response['decisions'])} decisions")
                else:
                    logger.info(
                        f"LLM returned no valid decisions (response keys: {list(response.keys()) if response else 'None'})"
                    )

                if response and "decisions" in response:
                    for decision_data in response["decisions"][:2]:
                        auto_approve_types = {"hold", "no_action", "wait", "monitor"}
                        needs_approval = (
                            decision_data.get("requires_approval", True)
                            and decision_data.get("decision_type", "").lower()
                            not in auto_approve_types
                        )
                        decision = AgentDecision(
                            id=f"dec_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{decision_data['decision_type']}",
                            agent_type="orchestrator",
                            decision_type=decision_data["decision_type"],
                            context={
                                "strategies": [
                                    s["id"] for s in self.context.strategies
                                ],
                                "portfolio": self.context.portfolio_summary,
                                "research_findings": [
                                    f["id"] for f in self.context.research_findings
                                ],
                            },
                            reasoning_chain=[decision_data.get("reasoning", "")],
                            conclusion=decision_data["reasoning"],
                            confidence=self._parse_confidence(
                                decision_data.get("confidence", 0.5)
                            ),
                            requires_approval=needs_approval,
                            action_taken=None,
                        )

                        decision.metadata = {
                            "priority": decision_data.get("priority", "medium")
                        }
                        if "target" in decision_data:
                            decision.metadata["target"] = decision_data["target"]
                        if "parameters" in decision_data:
                            decision.metadata["parameters"] = decision_data[
                                "parameters"
                            ]

                        decisions.append(decision)
                        self.kg.log_decision(decision)

        except Exception as e:
            logger.error(f"Decision generation failed: {e}", exc_info=True)
            self.context.errors.append(f"Decision generation failed: {e}")

        # Validate and fix decisions
        validated = self._validate_decisions(decisions)

        # If no strategies are running, create one proactively
        active_strategies = [
            s
            for s in self.context.strategies
            if s.get("enabled") and s.get("status") == "running"
        ]
        if not active_strategies and self.strategy_manager:
            template = self._select_strategy_template()
            if template:
                logger.info(f"No active strategies — creating {template} proactively")
                decision = AgentDecision(
                    id=f"dec_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_create_{template}",
                    agent_type="orchestrator",
                    decision_type="create_strategy",
                    context={
                        "reason": "No active strategies — auto-creating to begin trading"
                    },
                    reasoning_chain=[
                        "No active strategies detected",
                        f"Selected template: {template}",
                        "Creating in dry_run mode",
                    ],
                    conclusion=f"Create {template} strategy to start paper trading",
                    confidence=0.8,
                    requires_approval=False,
                    action_taken=None,
                )
                decision.metadata = {
                    "priority": "high",
                    "target": template,
                    "parameters": {"template_id": template, "dry_run": True},
                }
                validated.append(decision)
                self.kg.log_decision(decision)

        return validated

    def _select_strategy_template(self) -> str:
        """Select the best strategy template based on current market regime."""
        # Default to scalping for range-bound markets
        # Use analysis results if available
        regime = "ranging"  # safe default
        if self.context.analysis_results and isinstance(
            self.context.analysis_results, dict
        ):
            regime_data = self.context.analysis_results.get("market_regime", {})
            if isinstance(regime_data, dict):
                regime = regime_data.get(
                    "regime_type", regime_data.get("regime", "ranging")
                )

        template_map = {
            "trending_up": "breakout_momentum",
            "trending_down": "grid_dca",
            "ranging": "scalping_quick",
            "volatile": "oscillator_confluence",
            "ranging_slow": "swing_dca",
        }
        return template_map.get(regime, "scalping_quick")

    async def _run_quick_backtest(
        self, strategy_file: str, config_path: str, timerange: str = "20250101-20250401"
    ) -> Optional[Dict]:
        """Run a quick backtest via freqtrade subprocess. Returns metrics or None on failure."""
        cmd = [
            "freqtrade",
            "backtesting",
            "--strategy",
            strategy_file,
            "--config",
            config_path,
            "--timerange",
            timerange,
            "--export",
            "none",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            if proc.returncode != 0:
                logger.warning(
                    f"Backtest failed for {strategy_file}: {stderr.decode()[:500]}"
                )
                return None

            for line in stdout.decode().split("\n"):
                if "TOTAL" in line or "Profit" in line:
                    logger.info(f"Backtest output: {line.strip()}")

            result_file = config_path.replace(".json", "_backtest_results.json")
            try:
                with open(result_file, "r") as f:
                    results = json.load(f)
                strategy_results = results.get("strategy", {}).get(strategy_file, {})
                if strategy_results:
                    return {
                        "profit_total_pct": strategy_results.get("profit_total_pct", 0),
                        "sharpe": strategy_results.get("sharpe", 0),
                        "total_trades": strategy_results.get("total_trades", 0),
                        "win_rate": strategy_results.get("winning_trades", 0)
                        / max(strategy_results.get("total_trades", 1), 1),
                    }
            except Exception:
                pass

            return {
                "profit_total_pct": 0,
                "sharpe": 0,
                "total_trades": 0,
                "win_rate": 0,
            }
        except asyncio.TimeoutError:
            logger.warning(f"Backtest timed out for {strategy_file}")
            return None
        except Exception as e:
            logger.warning(f"Backtest error for {strategy_file}: {e}")
            return None

    def _check_stale_strategies(self) -> List[AgentDecision]:
        """Detect strategies running with 0 trades for too long and auto-generate parameter adjustments."""
        stale_decisions = []

        if not self.strategy_manager or not self.context.strategies:
            return stale_decisions

        for s in self.context.strategies:
            sid = s.get("id", "")
            name = s.get("name", "")
            status = s.get("status", "")
            total_trades = s.get("total_trades", 0) or 0
            container_status = (s.get("container_status") or {}).get("status", "")

            if status != "running" or container_status != "running":
                continue

            if total_trades > 0:
                continue

            recent = self.kg.get_decisions(
                decision_type="adjust_parameters",
                since=datetime.utcnow() - timedelta(hours=12),
                limit=100,
            )
            already_adjusted = any(
                d.metadata.get("target", "") == sid
                or str(d.context.get("strategies", [])).find(sid) >= 0
                for d in recent
            )
            if already_adjusted:
                continue

            widening_params = {}
            strategy_file = s.get("strategy_file", "").lower()
            if "scalping" in strategy_file:
                widening_params = {
                    "stoploss": -0.03,
                    "minimal_roi": {"0": 0.015, "10": 0.01},
                }
            elif "grid" in strategy_file or "dca" in strategy_file:
                widening_params = {
                    "stoploss": -0.10,
                }
            elif "breakout" in strategy_file or "momentum" in strategy_file:
                widening_params = {
                    "stoploss": -0.05,
                }
            else:
                widening_params = {"stoploss": -0.05}

            decision = AgentDecision(
                id=f"dec_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_stale_{sid[:8]}",
                agent_type="orchestrator",
                decision_type="adjust_parameters",
                context={
                    "reason": f"Strategy {name} has 0 trades — auto-widening parameters to encourage entries",
                    "strategy_id": sid,
                    "strategy_name": name,
                    "total_trades": total_trades,
                },
                reasoning_chain=[
                    f"Strategy {name} (0 trades) detected as stale",
                    "Widening entry/exit parameters to encourage trading activity",
                    f"Applying: {widening_params}",
                ],
                conclusion=f"Auto-widen parameters for stale strategy {name}",
                confidence=0.7,
                requires_approval=False,
            )
            decision.metadata = {
                "priority": "high",
                "target": sid,
                "parameters": widening_params,
            }
            stale_decisions.append(decision)
            self.kg.log_decision(decision)

        return stale_decisions

    async def _execute_decisions(self, decisions: List[AgentDecision]) -> List[Dict]:
        """Execute decisions with safety guardrails."""
        # In paper trading mode, only destructive actions require approval
        REQUIRES_APPROVAL_TYPES = {"stop_strategy", "deprecate_strategy"}

        executed = []

        for decision in decisions:
            try:
                # Check if this decision type requires human approval
                needs_approval = decision.decision_type in REQUIRES_APPROVAL_TYPES
                if needs_approval:
                    logger.info(
                        f"Decision {decision.id} ({decision.decision_type}) requires approval"
                    )
                    self.activity.log(
                        ActivityType.INFO,
                        "OrchestratorAgent",
                        f"Approval Required: {decision.decision_type}",
                        f"Decision: {decision.conclusion or decision.reasoning_chain[-1] if decision.reasoning_chain else 'N/A'}",
                        {
                            "decision_id": decision.id,
                            "decision_type": decision.decision_type,
                        },
                    )
                    executed.append(
                        {
                            "decision": decision.to_dict(),
                            "status": "pending_approval",
                            "message": f"Action requires approval: {decision.decision_type}",
                        }
                    )
                    if self.notification_callback:
                        await self.notification_callback(
                            {
                                "type": "approval_required",
                                "decision": decision.to_dict(),
                            }
                        )
                    continue

                # Map LLM decision types to valid types (small models may not follow schema exactly)
                type_aliases = {
                    "buy": "adjust_parameters",
                    "sell": "adjust_parameters",
                    "hold": "no_action",
                    "wait": "no_action",
                    "optimize": "run_hyperopt",
                    "backtest": "run_hyperopt",
                    "new_strategy": "create_strategy",
                    "start": "create_strategy",
                    "close": "stop_strategy",
                    "kill": "deprecate_strategy",
                    "rebalance": "adjust_parameters",
                    "adjust_position": "adjust_parameters",
                }
                if decision.decision_type in type_aliases:
                    original_type = decision.decision_type
                    decision.decision_type = type_aliases[original_type]
                    logger.info(
                        f"Mapped decision type '{original_type}' -> '{decision.decision_type}'"
                    )

                # Execute the decision
                result = await self._execute_single_decision(decision)
                executed.append(result)

            except Exception as e:
                logger.error(f"Failed to execute decision {decision.id}: {e}")
                executed.append(
                    {
                        "decision": decision.to_dict(),
                        "status": "error",
                        "error": str(e),
                    }
                )

        return executed

    async def _execute_single_decision(self, decision: AgentDecision) -> Dict:
        """Execute a single decision."""
        if not self.strategy_manager:
            return {
                "decision": decision.to_dict(),
                "status": "error",
                "error": "No strategy manager",
            }

        decision_type = decision.decision_type
        target = self._resolve_target(
            decision.metadata.get("target", "")
        ) or decision.metadata.get("target", "")
        params = decision.metadata.get("parameters", {})

        try:
            if decision_type == "adjust_parameters":
                # Update strategy parameters
                result = await self.strategy_manager.update_strategy_config(
                    target, params
                )
                self.kg.update_decision_outcome(decision.id, "parameters_adjusted")
                self.activity.log(
                    ActivityType.INFO,
                    "OrchestratorAgent",
                    f"Parameters Adjusted: {target[:8]}",
                    f"Changed: {', '.join(f'{k}={v}' for k, v in params.items())}",
                    {"target": target, "parameters": params},
                )
                return {
                    "decision": decision.to_dict(),
                    "status": "success",
                    "action": "parameters_adjusted",
                    "target": target,
                    "parameters": params,
                }

            elif decision_type == "run_hyperopt":
                if self.hyperopt_executor:
                    from .hyperopt_executor import HyperoptConfig

                    strategy_info = None
                    if self.strategy_manager:
                        strategies = await self.strategy_manager.get_all_strategies()
                        for s in strategies:
                            if s.get("id") == target:
                                strategy_info = s
                                break

                    if strategy_info:
                        hyperopt_config = HyperoptConfig(
                            epochs=params.get("epochs", 100),
                            spaces=params.get(
                                "spaces", ["buy", "sell", "roi", "stoploss"]
                            ),
                            timerange=params.get("timerange", "20240101-"),
                            strategy_path=strategy_info.get("strategy_file", ""),
                            config_path=strategy_info.get("config_path", ""),
                        )
                        asyncio.create_task(
                            self.hyperopt_executor.run_hyperopt(
                                strategy_id=target,
                                strategy_name=strategy_info.get("name", ""),
                                strategy_file=strategy_info.get("strategy_file", ""),
                                config_path=strategy_info.get("config_path", ""),
                                epochs=params.get("epochs", 100),
                                spaces=params.get(
                                    "spaces", ["buy", "sell", "roi", "stoploss"]
                                ),
                                timerange=params.get("timerange", "20240101-"),
                            )
                        )
                        self.kg.update_decision_outcome(
                            decision.id, "hyperopt_scheduled"
                        )
                        self.activity.log(
                            ActivityType.INFO,
                            "OrchestratorAgent",
                            f"Hyperopt Scheduled: {target[:8]}",
                            f"Epochs: {params.get('epochs', 100)}, Spaces: {params.get('spaces', [])}",
                            {"target": target, "params": params},
                        )
                        return {
                            "decision": decision.to_dict(),
                            "status": "success",
                            "action": "hyperopt_scheduled",
                        }
                    else:
                        self.kg.update_decision_outcome(
                            decision.id, "hyperopt_failed_no_strategy"
                        )
                        return {
                            "decision": decision.to_dict(),
                            "status": "error",
                            "action": "hyperopt_failed_no_strategy",
                            "error": f"Strategy {target} not found",
                        }
                else:
                    self.kg.update_decision_outcome(
                        decision.id, "hyperopt_skipped_no_executor"
                    )
                    self.activity.log(
                        ActivityType.INFO,
                        "OrchestratorAgent",
                        "Hyperopt Skipped",
                        "No hyperopt executor available",
                    )
                    return {
                        "decision": decision.to_dict(),
                        "status": "skipped",
                        "action": "hyperopt_skipped_no_executor",
                    }

            elif decision_type == "apply_research":
                finding_id = params.get("finding_id")
                applied_params = {}
                if finding_id:
                    findings = self.kg.get_findings(limit=200)
                    finding = None
                    for f in findings:
                        if f.id == finding_id:
                            finding = f
                            break
                    if finding:
                        best_params = (finding.impact_assessment or {}).get(
                            "best_params", {}
                        )
                        trading_implications = (finding.impact_assessment or {}).get(
                            "trading_implications", {}
                        )
                        params_to_apply = {}
                        if best_params:
                            params_to_apply.update(best_params)
                        if trading_implications:
                            for key in (
                                "stoploss",
                                "trailing_stop_positive",
                                "max_open_trades",
                                "stake_amount",
                            ):
                                if key in trading_implications:
                                    params_to_apply[key] = trading_implications[key]
                        if params_to_apply and target and self.strategy_manager:
                            await self.strategy_manager.update_strategy_config(
                                target, params_to_apply
                            )
                            applied_params = params_to_apply
                    self.kg.mark_finding_applied(finding_id, target or "")
                self.kg.update_decision_outcome(decision.id, "research_applied")
                self.activity.log(
                    ActivityType.INFO,
                    "OrchestratorAgent",
                    f"Research Applied: {finding_id[:8] if finding_id else 'N/A'}",
                    f"Applied {len(applied_params)} parameters to {target[:8] if target else 'N/A'}",
                    {
                        "finding_id": finding_id,
                        "target": target,
                        "params": applied_params,
                    },
                )
                return {
                    "decision": decision.to_dict(),
                    "status": "success",
                    "action": "research_applied",
                    "params_applied": applied_params,
                }

            elif decision_type == "create_strategy":
                # Create new strategy (paper trading only — backtest validation optional)
                template_id = params.get("template_id")
                if template_id:
                    strategy_id = (
                        await self.strategy_manager.create_strategy_from_template(
                            template_id, params
                        )
                    )
                    self.activity.log(
                        ActivityType.INFO,
                        "OrchestratorAgent",
                        f"Strategy Created: {template_id}",
                        f"New strategy from template {template_id} (dry_run=True)",
                        {"template_id": template_id, "strategy_id": strategy_id},
                    )
                self.kg.update_decision_outcome(decision.id, "strategy_created")
                return {
                    "decision": decision.to_dict(),
                    "status": "success",
                    "action": "strategy_created",
                }

            elif decision_type == "stop_strategy":
                # Stop strategy
                await self.strategy_manager.stop_strategy(target)
                self.kg.update_decision_outcome(decision.id, "strategy_stopped")
                return {
                    "decision": decision.to_dict(),
                    "status": "success",
                    "action": "strategy_stopped",
                }

            elif decision_type == "deprecate_strategy":
                # Deprecate poor performer
                await self.strategy_manager.delete_strategy(target)
                self.kg.update_decision_outcome(decision.id, "strategy_deprecated")
                return {
                    "decision": decision.to_dict(),
                    "status": "success",
                    "action": "strategy_deprecated",
                }

            elif decision_type == "alert_user":
                # Send notification
                if self.notification_callback:
                    await self.notification_callback(
                        {
                            "type": "alert",
                            "message": params.get("message", "Alert from orchestrator"),
                            "decision": decision.to_dict(),
                        }
                    )
                self.kg.update_decision_outcome(decision.id, "user_alerted")
                return {
                    "decision": decision.to_dict(),
                    "status": "success",
                    "action": "user_alerted",
                }

            elif decision_type == "no_action":
                self.kg.update_decision_outcome(decision.id, "no_action_taken")
                return {
                    "decision": decision.to_dict(),
                    "status": "success",
                    "action": "no_action",
                }

            else:
                return {
                    "decision": decision.to_dict(),
                    "status": "error",
                    "error": f"Unknown decision type: {decision_type}",
                }

        except Exception as e:
            self.kg.update_decision_outcome(decision.id, f"error: {e}")
            return {"decision": decision.to_dict(), "status": "error", "error": str(e)}

    @staticmethod
    def _parse_confidence(value) -> float:
        """Parse confidence from LLM output, handling non-numeric values."""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            low_map = {"low": 0.3, "medium": 0.5, "high": 0.7, "very_high": 0.9}
            return low_map.get(value.lower().replace(" ", "_"), 0.5)
        return 0.5

    def _build_decision_context(self) -> str:
        """Build rich context string for LLM decision-making with real strategy IDs and metrics."""
        context_parts = []

        context_parts.append(
            "You are an autonomous crypto TRADING STRATEGY manager. You manage Freqtrade strategies "
            "that execute trades automatically. You adjust strategy PARAMETERS, run optimizations, "
            "start/stop strategies, or create new ones. You do NOT place trades directly."
        )

        ps = self.context.portfolio_summary or {}
        context_parts.append("\n## Portfolio")
        if isinstance(ps, dict):
            total_pnl = ps.get("total_pnl", 0)
            total_trades = ps.get("total_trades", 0)
            win_rate = ps.get("win_rate", 0)
            context_parts.append(f"- Total P&L: ${total_pnl:.2f}")
            context_parts.append(f"- Total Trades: {total_trades}")
            context_parts.append(f"- Win Rate: {win_rate:.1%}")
            context_parts.append(
                f"- Active Strategies: {ps.get('strategies_active', 0)}"
            )
        else:
            context_parts.append(str(ps)[:300])

        if self.context.strategies:
            context_parts.append(
                "\n## Current Strategies (use these EXACT IDs as 'target')"
            )
            for s in self.context.strategies:
                sid = s.get("id", "?")
                name = s.get("name", "Unknown")
                status = s.get("status", "?")
                wr = s.get("win_rate", 0) or 0
                sharpe = s.get("sharpe", 0) or 0
                profit_pct = s.get("profit_pct", 0) or 0
                total_trades = s.get("total_trades", 0) or 0
                max_dd = s.get("max_drawdown", 0) or 0
                pairs = s.get("pairs", [])
                if isinstance(pairs, str):
                    try:
                        import json as _json

                        pairs = _json.loads(pairs)
                    except Exception:
                        pairs = [pairs]
                pairs_str = ", ".join(str(p) for p in (pairs or [])[:5])
                if pairs and len(pairs) > 5:
                    pairs_str += f" +{len(pairs) - 5} more"

                hyperopt_status = "never"
                recent_hyperopt = self.kg.get_decisions(
                    decision_type="run_hyperopt",
                    since=datetime.utcnow() - timedelta(days=7),
                    limit=50,
                )
                for d in recent_hyperopt:
                    target_id = (d.metadata or {}).get("target", "")
                    if target_id == sid:
                        outcome = d.outcome or ""
                        if "scheduled" in outcome or "success" in outcome:
                            hyperopt_status = "recent"
                            break
                if hyperopt_status == "never":
                    all_hyperopt = self.kg.get_decisions(
                        decision_type="run_hyperopt",
                        limit=200,
                    )
                    for d in all_hyperopt:
                        target_id = (d.metadata or {}).get("target", "")
                        if target_id == sid:
                            hyperopt_status = "past"
                            break

                health = (
                    "new_0_trades"
                    if total_trades == 0
                    else ("healthy" if wr > 0.5 else "underperforming")
                )
                context_parts.append(
                    f"- ID: {sid}  Name: {name}  Status: {status}  "
                    f"Trades: {total_trades}  WinRate: {wr:.1%}  "
                    f"Sharpe: {sharpe:.2f}  P&L: {profit_pct:.2f}%  "
                    f"MaxDD: {max_dd:.1%}  Health: {health}  "
                    f"Hyperopt: {hyperopt_status}  Pairs: [{pairs_str}]"
                )

        if self.context.research_findings:
            context_parts.append("\n## Research Findings → Actionable Parameters")
            context_parts.append(
                "IMPORTANT: For each finding below, translate the market signal into concrete parameter changes "
                "for the relevant strategy. Example translations:\n"
                "- Bearish sentiment → widen stoploss (e.g., -0.03 to -0.05), reduce stake_amount\n"
                "- Bullish sentiment → tighten take-profit (minimal_roi lower), increase max_open_trades\n"
                "- High volatility → widen stoploss, add trailing stop, reduce stake_amount\n"
                "- Ranging market → use narrower RSI thresholds (rsi_entry 40→45), add DCA parameters\n"
                "- On-chain bullish → tighten stoploss to lock in profits (e.g., -0.03 to -0.02)\n"
            )
            for f in self.context.research_findings[:5]:
                src = f.get("source", "?")
                title = f.get("title", "")[:80]
                sentiment = f.get("sentiment", "")
                conf = f.get("confidence", "")
                content = f.get("content", "")[:200]
                impact = f.get("impact_assessment", {})
                trading = ""
                if isinstance(impact, dict):
                    ti = impact.get("trading_implications", "")
                    if ti:
                        trading = f" | Implications: {str(ti)[:150]}"
                sent_str = f" (sentiment: {sentiment})" if sentiment else ""
                conf_str = f" [conf: {conf}]" if conf else ""
                context_parts.append(f"- [{src}] {title}{sent_str}{conf_str}{trading}")
                if content:
                    context_parts.append(f"  Detail: {content}")

        if self.context.risk_report:
            context_parts.append("\n## Risk Assessment")
            rr = self.context.risk_report
            if isinstance(rr, dict):
                score = rr.get("overall_risk_score", rr.get("risk_score", "?"))
                level = rr.get("risk_level", "?")
                context_parts.append(f"- Risk Score: {score}  Level: {level}")
                alerts = rr.get("alerts", [])
                if alerts:
                    for a in alerts[:3]:
                        context_parts.append(f"- Alert: {str(a)[:100]}")

        if self.context.analysis_results and isinstance(
            self.context.analysis_results, dict
        ):
            context_parts.append("\n## Strategy Analysis")
            ar = self.context.analysis_results
            regime = ar.get("market_regime", {})
            if isinstance(regime, dict):
                context_parts.append(
                    f"- Market Regime: {regime.get('regime_type', regime.get('regime', '?'))}"
                )
                context_parts.append(
                    f"- Regime Confidence: {regime.get('confidence', '?')}"
                )
            recs = ar.get("recommendations", [])
            if recs:
                context_parts.append("- Analysis Recommendations:")
                for r in recs[:3]:
                    context_parts.append(f"  * {str(r)[:120]}")
            strategy_analyses = ar.get("strategies", {})
            for sid, analysis in strategy_analyses.items():
                if isinstance(analysis, dict):
                    hs = analysis.get("health_score", "?")
                    wr = analysis.get("win_rate", "?")
                    context_parts.append(
                        f"- Strategy {sid[:8]}: health={hs}, win_rate={wr}"
                    )

        if self.context.recent_decisions:
            context_parts.append("\n## Recent Decisions (learn from these)")
            for dec in self.context.recent_decisions[-5:]:
                dtype = dec.get("decision_type", "?")
                target = dec.get("target", "?")
                outcome = dec.get("outcome", "unknown")
                conc = dec.get("conclusion", "")[:80]
                context_parts.append(
                    f"- {dtype} -> {target}: {conc} [outcome: {outcome}]"
                )

        if self.context.errors:
            context_parts.append("\n## Current Errors")
            for error in self.context.errors[:3]:
                context_parts.append(f"- {str(error)[:150]}")

        return "\n".join(context_parts)

    def _validate_decisions(
        self, decisions: List[AgentDecision]
    ) -> List[AgentDecision]:
        """Validate and fix LLM decisions: resolve targets, strip invalid types, enforce constraints."""
        valid_types = {
            "adjust_parameters",
            "run_hyperopt",
            "stop_strategy",
            "create_strategy",
            "no_action",
            "alert_user",
            "apply_research",
            "deprecate_strategy",
        }
        rejected_types = {"buy", "sell", "rebalance", "adjust_position", "hold", "wait"}
        validated = []

        for decision in decisions:
            dtype = decision.decision_type.lower()

            # Map rejected types to valid ones
            if dtype in rejected_types:
                if dtype in {"buy", "sell", "rebalance", "adjust_position"}:
                    logger.warning(
                        f"Mapping '{dtype}' -> 'adjust_parameters' for decision {decision.id}"
                    )
                    decision.decision_type = "adjust_parameters"
                    dtype = "adjust_parameters"
                    decision.reasoning_chain.append(
                        f"(Auto-mapped from '{dtype}' to 'adjust_parameters')"
                    )
                elif dtype in {"hold", "wait"}:
                    decision.decision_type = "no_action"
                    dtype = "no_action"
                    decision.requires_approval = False
                    logger.info(
                        f"Mapping '{dtype}' -> 'no_action' for decision {decision.id}"
                    )

            if dtype not in valid_types:
                logger.warning(
                    f"Rejecting unknown decision type '{dtype}' for {decision.id}"
                )
                self.activity.log(
                    ActivityType.ERROR,
                    "OrchestratorAgent",
                    f"Rejected Unknown Decision Type: {dtype}",
                    f"The LLM generated an invalid decision type '{dtype}'. Skipping.",
                    {"decision_id": decision.id, "decision_type": dtype},
                )
                continue

            # Resolve target to a real strategy ID
            if decision.decision_type not in {
                "no_action",
                "create_strategy",
                "alert_user",
            }:
                target = decision.metadata.get("target", "")
                resolved = self._resolve_target(target)
                if resolved:
                    decision.metadata["target"] = resolved
                    logger.info(f"Resolved target '{target}' -> '{resolved}'")
                else:
                    logger.warning(
                        f"Could not resolve target '{target}' for decision {decision.id} "
                        f"(decision_type={decision.decision_type}). Skipping."
                    )
                    self.activity.log(
                        ActivityType.ERROR,
                        "OrchestratorAgent",
                        f"Invalid Target: '{target}'",
                        f"Decision {decision.decision_type} referenced target '{target}' which doesn't match any strategy. Skipping.",
                        {"decision_id": decision.id, "target": target},
                    )
                    continue

            # Require non-empty parameters for adjust_parameters
            if decision.decision_type == "adjust_parameters":
                params = decision.metadata.get("parameters", {})
                if not params or (isinstance(params, dict) and len(params) == 0):
                    logger.warning(
                        f"Skipping adjust_parameters decision {decision.id} with empty parameters"
                    )
                    self.activity.log(
                        ActivityType.ERROR,
                        "OrchestratorAgent",
                        "Skipped: Empty Parameters",
                        f"adjust_parameters decision has no parameters specified. Skipping.",
                        {"decision_id": decision.id},
                    )
                    continue

                # Auto-mark matching research findings as applied
                target_id = decision.metadata.get("target", "")
                if target_id and self.context.research_findings:
                    for finding in self.context.research_findings[:5]:
                        f_id = finding.get("id", "")
                        if f_id:
                            self.kg.mark_finding_applied(f_id, target_id)

            validated.append(decision)

        return validated

    def _resolve_target(self, target: str) -> Optional[str]:
        """Resolve a target string to a real strategy ID.

        Handles: exact UUID, strategy name, coin/pair name, partial match.
        """
        if not target or not self.context.strategies:
            return None

        # Exact match on ID
        for s in self.context.strategies:
            if s.get("id") == str(target):
                return s["id"]

        # Match on name (case-insensitive)
        target_lower = str(target).lower().strip()
        for s in self.context.strategies:
            name = s.get("name", "").lower()
            if name and name == target_lower:
                return s["id"]
            if name and target_lower in name:
                return s["id"]

        # Match on coin/pair (e.g., "BTC" matches strategy trading "BTC/USDT")
        coin = target_lower.replace("/usdt", "").replace("/usd", "").replace("/btc", "")
        for s in self.context.strategies:
            pairs = s.get("pairs", [])
            if isinstance(pairs, str):
                try:
                    import json as _json

                    pairs = _json.loads(pairs)
                except Exception:
                    pairs = [pairs]
            if pairs:
                for pair in pairs:
                    pair_str = str(pair).lower()
                    if coin in pair_str:
                        return s["id"]

        # If only one strategy, use it regardless
        if len(self.context.strategies) == 1:
            logger.info(
                f"Only one strategy — resolving '{target}' to {self.context.strategies[0]['id']}"
            )
            return self.context.strategies[0]["id"]

        return None

    async def _log_cycle_summary(self, start_time: datetime, executed: List[Dict]):
        """Log summary of orchestration cycle."""
        summary = {
            "cycle_start": start_time.isoformat(),
            "cycle_end": datetime.utcnow().isoformat(),
            "duration_seconds": (datetime.utcnow() - start_time).total_seconds(),
            "state": self.state.value,
            "strategies_analyzed": len(self.context.strategies),
            "research_findings": len(self.context.research_findings),
            "decisions_made": len(executed),
            "decisions_pending": len(
                [e for e in executed if e.get("status") == "pending_approval"]
            ),
            "decisions_executed": len(
                [e for e in executed if e.get("status") == "success"]
            ),
            "errors": len(self.context.errors),
        }

        logger.info(f"Orchestration cycle summary: {json.dumps(summary, indent=2)}")

        # Create decision entity for cycle
        cycle_entity = Entity(
            id=f"cycle_{start_time.strftime('%Y%m%d_%H%M%S')}",
            entity_type=EntityType.DECISION,
            data=summary,
            tags=["orchestration_cycle"],
        )
        self.kg.add_entity(cycle_entity)

    def get_status(self) -> Dict:
        """Get current orchestrator status."""
        return {
            "running": self.running,
            "state": self.state.value,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "config": {
                "interval_minutes": self.config.interval_minutes,
                "paper_trading_only": self.config.paper_trading_only,
                "auto_apply_improvements": self.config.auto_apply_improvements,
            },
            "knowledge_graph": self.kg.get_summary(),
            "pending_approvals": len(self.kg.get_pending_approvals()),
        }

    async def approve_decision(self, decision_id: str, approved_by: str = "user"):
        """Approve a pending decision."""
        self.kg.approve_decision(decision_id, approved_by)

        # Re-execute the approved decision
        decision = self.kg.get_entity(decision_id)
        if decision:
            result = await self._execute_single_decision(
                AgentDecision(
                    id=decision_id,
                    agent_type="orchestrator",
                    decision_type=decision.data.get("decision_type"),
                    context=decision.data.get("context", {}),
                    reasoning_chain=decision.data.get("reasoning_chain", []),
                    conclusion=decision.data.get("conclusion", ""),
                    confidence=decision.confidence,
                    metadata=decision.data.get("metadata", {}),
                    requires_approval=False,  # Already approved
                )
            )
            return result

        return {"status": "error", "error": "Decision not found"}

    def reject_decision(self, decision_id: str, reason: str):
        """Reject a pending decision."""
        self.kg.update_decision_outcome(decision_id, f"rejected: {reason}")
