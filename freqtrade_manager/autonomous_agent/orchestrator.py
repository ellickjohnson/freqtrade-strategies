"""
Orchestrator Agent - Main coordination agent for autonomous financial engineering.

This is the central agent that coordinates all sub-agents (Research, Analysis, Risk, Strategy)
and makes portfolio-level decisions.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

from .llm_client import LLMClient, LLMConfig, LLMProvider
from .knowledge_graph import (
    KnowledgeGraph,
    AgentDecision,
    EntityType,
    RelationType,
    Entity,
    Relation,
)

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
    auto_apply_improvements: bool = True  # Auto-apply safe decisions; high-risk ones still require approval
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
        strategy_manager = None,  # FreqtradeManager
        notification_callback: Optional[Callable] = None,
    ):
        self.config = config or OrchestratorConfig()
        self.db_path = db_path
        self.kg = KnowledgeGraph(db_path)
        self.llm = llm_client or LLMClient(LLMConfig(
            provider=LLMProvider(self.config.llm_provider) if isinstance(self.config.llm_provider, str) else self.config.llm_provider,
            model=self.config.llm_model,
        ))
        self.strategy_manager = strategy_manager
        self.notification_callback = notification_callback

        self.state = AgentState.IDLE
        self.running = False
        self.last_run: Optional[datetime] = None
        self.context = AgentContext()

        # Sub-agents will be initialized lazily
        self._research_agent = None
        self._analysis_agent = None
        self._risk_agent = None
        self._strategy_agent = None

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

            # Wait for next cycle
            await asyncio.sleep(self.config.interval_minutes * 60)

    async def _ensure_strategies_running(self):
        """Auto-start any strategies that should be running but have stopped containers."""
        if not self.strategy_manager:
            return

        try:
            strategies = await self.strategy_manager.get_all_strategies()
            for s in strategies:
                if s.get("enabled") and s.get("status") == "running":
                    container_status = (s.get("container_status") or {}).get("status", "unknown")
                    if container_status in ("exited", "dead", "unknown", None):
                        logger.info(f"Auto-starting strategy: {s['name']} (container was {container_status})")
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

        # 1. Gather context
        self.state = AgentState.ANALYZING
        await self._gather_context()

        # 2. Run research agent (gathers external data)
        self.state = AgentState.RESEARCHING
        research_findings = await self._run_research_agent()
        self.context.research_findings = research_findings

        # 3. Run analysis agent (evaluates strategies)
        self.state = AgentState.ANALYZING
        analysis_results = await self._run_analysis_agent()
        self.context.analysis_results = analysis_results

        # 4. Run risk agent (checks risk limits)
        self.state = AgentState.RISK_CHECKING
        risk_report = await self._run_risk_agent()
        self.context.risk_report = risk_report

        # 5. Generate decisions
        self.state = AgentState.DECIDING
        decisions = await self._make_decisions()

        # 6. Execute approved decisions
        self.state = AgentState.EXECUTING
        executed = await self._execute_decisions(decisions)

        # 7. Log reasoning
        await self._log_cycle_summary(start_time, executed)

        self.state = AgentState.IDLE
        self.last_run = datetime.utcnow()

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
            recent = self.kg.get_decisions(since=datetime.utcnow() - timedelta(hours=24))
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

        # Build decision context
        context_str = self._build_decision_context()

        # Define decision schema
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
                                "enum": [
                                    "adjust_parameters",
                                    "run_hyperopt",
                                    "apply_research",
                                    "create_strategy",
                                    "stop_strategy",
                                    "deprecate_strategy",
                                    "alert_user",
                                    "no_action",
                                ]
                            },
                            "target": {"type": "string"},
                            "parameters": {"type": "object"},
                            "reasoning": {"type": "string"},
                            "confidence": {"type": "number"},
                            "requires_approval": {"type": "boolean"},
                            "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                        },
                        "required": ["decision_type", "reasoning", "confidence"],
                    }
                }
            },
            "required": ["decisions"]
        }

        try:
            response = await self.llm.analyze(
                prompt=context_str + "\n\nRespond with JSON: {\"decisions\": [{\"decision_type\": \"...\", \"reasoning\": \"...\", \"confidence\": 0.5, \"target\": \"...\", \"parameters\": {}}]}",
                schema=decision_schema,
                system_prompt="You are an autonomous trading agent. Respond ONLY with valid JSON matching the schema. No markdown, no explanation, just the JSON object.",
            )

            if response and "decisions" in response:
                logger.info(f"LLM returned {len(response['decisions'])} decisions")
            else:
                logger.info(f"LLM returned no valid decisions (response keys: {list(response.keys()) if response else 'None'})")

            if response and "decisions" in response:
                for decision_data in response["decisions"]:
                    decision = AgentDecision(
                        id=f"dec_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{decision_data['decision_type']}",
                        agent_type="orchestrator",
                        decision_type=decision_data["decision_type"],
                        context={
                            "strategies": [s["id"] for s in self.context.strategies],
                            "portfolio": self.context.portfolio_summary,
                            "research_findings": [f["id"] for f in self.context.research_findings],
                        },
                        reasoning_chain=[decision_data.get("reasoning", "")],
                        conclusion=decision_data["reasoning"],
                        confidence=decision_data.get("confidence", 0.5),
                        requires_approval=decision_data.get("requires_approval", True),
                        action_taken=None,
                    )

                    # Store priority in metadata
                    decision.metadata = {"priority": decision_data.get("priority", "medium")}
                    if "target" in decision_data:
                        decision.metadata["target"] = decision_data["target"]
                    if "parameters" in decision_data:
                        decision.metadata["parameters"] = decision_data["parameters"]

                    decisions.append(decision)
                    self.kg.log_decision(decision)

        except Exception as e:
            logger.error(f"Decision generation failed: {e}")
            self.context.errors.append(f"Decision generation failed: {e}")

        # If no strategies are running, create one proactively
        active_strategies = [s for s in self.context.strategies if s.get("enabled") and s.get("status") == "running"]
        if not active_strategies and self.strategy_manager:
            template = self._select_strategy_template()
            if template:
                logger.info(f"No active strategies — creating {template} proactively")
                decision = AgentDecision(
                    id=f"dec_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_create_{template}",
                    agent_type="orchestrator",
                    decision_type="create_strategy",
                    context={"reason": "No active strategies — auto-creating to begin trading"},
                    reasoning_chain=["No active strategies detected", f"Selected template: {template}", "Creating in dry_run mode"],
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
                decisions.append(decision)
                self.kg.log_decision(decision)

        return decisions

    def _select_strategy_template(self) -> str:
        """Select the best strategy template based on current market regime."""
        # Default to scalping for range-bound markets
        # Use analysis results if available
        regime = "ranging"  # safe default
        if self.context.analysis_results and isinstance(self.context.analysis_results, dict):
            regime_data = self.context.analysis_results.get("market_regime", {})
            if isinstance(regime_data, dict):
                regime = regime_data.get("regime_type", regime_data.get("regime", "ranging"))

        template_map = {
            "trending_up": "breakout_momentum",
            "trending_down": "grid_dca",
            "ranging": "scalping_quick",
            "volatile": "oscillator_confluence",
        }
        return template_map.get(regime, "scalping_quick")

    async def _execute_decisions(self, decisions: List[AgentDecision]) -> List[Dict]:
        """Execute decisions with safety guardrails."""
        # Decision types that can be auto-applied (low risk)
        AUTO_APPLY_TYPES = {"adjust_parameters", "run_hyperopt", "apply_research", "create_strategy", "alert_user"}
        # Decision types that always require approval (high risk)
        REQUIRES_APPROVAL_TYPES = {"stop_strategy", "deprecate_strategy"}

        executed = []

        for decision in decisions:
            try:
                # Check if this decision type requires human approval
                needs_approval = decision.decision_type in REQUIRES_APPROVAL_TYPES
                if needs_approval:
                    logger.info(f"Decision {decision.id} ({decision.decision_type}) requires approval")
                    executed.append({
                        "decision": decision.to_dict(),
                        "status": "pending_approval",
                        "message": f"Action requires approval: {decision.decision_type}",
                    })
                    if self.notification_callback:
                        await self.notification_callback({
                            "type": "approval_required",
                            "decision": decision.to_dict(),
                        })
                    continue

                # Map LLM decision types to valid types (small models may not follow schema exactly)
                type_aliases = {
                    "buy": "adjust_parameters", "sell": "adjust_parameters",
                    "hold": "no_action", "wait": "no_action",
                    "optimize": "run_hyperopt", "backtest": "run_hyperopt",
                    "new_strategy": "create_strategy", "start": "create_strategy",
                    "close": "stop_strategy", "kill": "deprecate_strategy",
                }
                if decision.decision_type in type_aliases:
                    original_type = decision.decision_type
                    decision.decision_type = type_aliases[original_type]
                    logger.info(f"Mapped decision type '{original_type}' -> '{decision.decision_type}'")

                # Execute the decision
                result = await self._execute_single_decision(decision)
                executed.append(result)

            except Exception as e:
                logger.error(f"Failed to execute decision {decision.id}: {e}")
                executed.append({
                    "decision": decision.to_dict(),
                    "status": "error",
                    "error": str(e),
                })

        return executed

    async def _execute_single_decision(self, decision: AgentDecision) -> Dict:
        """Execute a single decision."""
        if not self.strategy_manager:
            return {"decision": decision.to_dict(), "status": "error", "error": "No strategy manager"}

        decision_type = decision.decision_type
        target = decision.metadata.get("target")
        params = decision.metadata.get("parameters", {})

        try:
            if decision_type == "adjust_parameters":
                # Update strategy parameters
                await self.strategy_manager.update_strategy_config(target, params)
                self.kg.update_decision_outcome(decision.id, "parameters_adjusted")
                return {"decision": decision.to_dict(), "status": "success", "action": "parameters_adjusted"}

            elif decision_type == "run_hyperopt":
                # Schedule hyperopt via HyperoptExecutor
                if hasattr(self, 'hyperopt_executor') and self.hyperopt_executor:
                    from .hyperopt_executor import HyperoptConfig
                    hyperopt_config = HyperoptConfig(
                        epochs=params.get("epochs", 100),
                        spaces=params.get("spaces", ["buy", "sell", "roi", "stoploss"]),
                        timerange=params.get("timerange", "20240101-"),
                        strategy_path=target,
                        config_path=params.get("config_path"),
                    )
                    asyncio.create_task(self.hyperopt_executor.run_hyperopt(hyperopt_config))
                    self.kg.update_decision_outcome(decision.id, "hyperopt_scheduled")
                    return {"decision": decision.to_dict(), "status": "success", "action": "hyperopt_scheduled"}
                else:
                    self.kg.update_decision_outcome(decision.id, "hyperopt_skipped_no_executor")
                    return {"decision": decision.to_dict(), "status": "skipped", "action": "hyperopt_skipped_no_executor"}

            elif decision_type == "apply_research":
                # Apply research findings
                finding_id = params.get("finding_id")
                if finding_id:
                    self.kg.mark_finding_applied(finding_id, target)
                self.kg.update_decision_outcome(decision.id, "research_applied")
                return {"decision": decision.to_dict(), "status": "success", "action": "research_applied"}

            elif decision_type == "create_strategy":
                # Create new strategy
                template_id = params.get("template_id")
                if template_id:
                    await self.strategy_manager.create_strategy_from_template(template_id, params)
                self.kg.update_decision_outcome(decision.id, "strategy_created")
                return {"decision": decision.to_dict(), "status": "success", "action": "strategy_created"}

            elif decision_type == "stop_strategy":
                # Stop strategy
                await self.strategy_manager.stop_strategy(target)
                self.kg.update_decision_outcome(decision.id, "strategy_stopped")
                return {"decision": decision.to_dict(), "status": "success", "action": "strategy_stopped"}

            elif decision_type == "deprecate_strategy":
                # Deprecate poor performer
                await self.strategy_manager.delete_strategy(target)
                self.kg.update_decision_outcome(decision.id, "strategy_deprecated")
                return {"decision": decision.to_dict(), "status": "success", "action": "strategy_deprecated"}

            elif decision_type == "alert_user":
                # Send notification
                if self.notification_callback:
                    await self.notification_callback({
                        "type": "alert",
                        "message": params.get("message", "Alert from orchestrator"),
                        "decision": decision.to_dict(),
                    })
                self.kg.update_decision_outcome(decision.id, "user_alerted")
                return {"decision": decision.to_dict(), "status": "success", "action": "user_alerted"}

            elif decision_type == "no_action":
                self.kg.update_decision_outcome(decision.id, "no_action_taken")
                return {"decision": decision.to_dict(), "status": "success", "action": "no_action"}

            else:
                return {"decision": decision.to_dict(), "status": "error", "error": f"Unknown decision type: {decision_type}"}

        except Exception as e:
            self.kg.update_decision_outcome(decision.id, f"error: {e}")
            return {"decision": decision.to_dict(), "status": "error", "error": str(e)}

    def _build_decision_context(self) -> str:
        """Build compact context string for LLM decision-making (optimized for small models)."""
        context_parts = []

        # Portfolio summary - compact key metrics only
        ps = self.context.portfolio_summary or {}
        context_parts.append("## Portfolio")
        if isinstance(ps, dict):
            for k in ["total_value", "total_pnl", "pnl_pct", "open_positions"]:
                if k in ps:
                    context_parts.append(f"- {k}: {ps[k]}")
        else:
            context_parts.append(str(ps)[:200])

        # Strategy statuses - one line each
        if self.context.strategies:
            context_parts.append("\n## Strategies")
            for s in self.context.strategies[:5]:
                name = s.get('name', s.get('id', '?')[:8])
                status = s.get('status', '?')
                wr = s.get('win_rate', 'N/A')
                sharpe = s.get('sharpe', 'N/A')
                context_parts.append(f"- {name}: {status}, WR={wr}, Sharpe={sharpe}")

        # Research findings - top 3, one line each
        if self.context.research_findings:
            context_parts.append("\n## Research")
            for f in self.context.research_findings[:3]:
                src = f.get('source', '?')
                title = f.get('title', '')[:60]
                context_parts.append(f"- [{src}] {title}")

        # Risk assessment - compact summary
        if self.context.risk_report:
            context_parts.append("\n## Risk")
            rr = self.context.risk_report
            if isinstance(rr, dict):
                score = rr.get('overall_risk_score', rr.get('risk_score', '?'))
                level = rr.get('risk_level', '?')
                context_parts.append(f"- Score: {score}, Level: {level}")
                alerts = rr.get('alerts', [])
                if alerts:
                    for a in alerts[:3]:
                        context_parts.append(f"- Alert: {str(a)[:80]}")
            else:
                context_parts.append(str(rr)[:200])

        # Analysis results - regime + key metrics only
        if self.context.analysis_results:
            context_parts.append("\n## Analysis")
            ar = self.context.analysis_results
            if isinstance(ar, dict):
                regime = ar.get('regime', ar.get('market_regime', {}))
                if isinstance(regime, dict):
                    context_parts.append(f"- Regime: {regime.get('type', regime.get('regime', '?'))}")
                    context_parts.append(f"- Confidence: {regime.get('confidence', '?')}")
                recs = ar.get('recommendations', [])
                if recs:
                    for r in recs[:2]:
                        context_parts.append(f"- Rec: {str(r)[:80]}")
            else:
                context_parts.append(str(ar)[:200])

        # Recent decisions - last 3 with outcomes
        if self.context.recent_decisions:
            context_parts.append("\n## Recent Decisions")
            for dec in self.context.recent_decisions[-3:]:
                dtype = dec.get('decision_type', '?')
                conc = dec.get('conclusion', '')[:60]
                outcome = (dec.get('outcome') or '')[:40]
                outcome_str = f" -> {outcome}" if outcome else ""
                context_parts.append(f"- {dtype}: {conc}{outcome_str}")

        # Errors - last 2
        if self.context.errors:
            context_parts.append("\n## Errors")
            for error in self.context.errors[:2]:
                context_parts.append(f"- {str(error)[:80]}")

        return "\n".join(context_parts)

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
            "decisions_pending": len([e for e in executed if e.get("status") == "pending_approval"]),
            "decisions_executed": len([e for e in executed if e.get("status") == "success"]),
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
            result = await self._execute_single_decision(AgentDecision(
                id=decision_id,
                agent_type="orchestrator",
                decision_type=decision.data.get("decision_type"),
                context=decision.data.get("context", {}),
                reasoning_chain=decision.data.get("reasoning_chain", []),
                conclusion=decision.data.get("conclusion", ""),
                confidence=decision.confidence,
                metadata=decision.data.get("metadata", {}),
                requires_approval=False,  # Already approved
            ))
            return result

        return {"status": "error", "error": "Decision not found"}

    def reject_decision(self, decision_id: str, reason: str):
        """Reject a pending decision."""
        self.kg.update_decision_outcome(decision_id, f"rejected: {reason}")