"""
Autonomous API Integration - Endpoints for autonomous agent control.

Add these routes to freqtrade_manager/main.py
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Global orchestrator instance
orchestrator = None


def setup_autonomous_routes(app, db, manager, ws_server):
    """Setup autonomous agent routes on the FastAPI app."""
    from autonomous_agent import (
        OrchestratorAgent,
        OrchestratorConfig,
        LLMClient,
        LLMConfig,
        LLMProvider,
        KnowledgeGraph,
    )
    from autonomous_agent.hyperopt_executor import HyperoptExecutor, HyperoptConfig
    from autonomous_agent.obsidian_memory import get_obsidian_memory

    global orchestrator

    # Initialize components
    db_path = "/data/dashboard.db"
    kg = KnowledgeGraph(db_path)

    # Configure LLM from environment
    llm_provider_str = os.getenv("LLM_PROVIDER", "ollama").lower()
    llm_provider = LLMProvider.OLLAMA  # default
    if llm_provider_str == "anthropic":
        llm_provider = LLMProvider.ANTHROPIC
    elif llm_provider_str == "openai":
        llm_provider = LLMProvider.OPENAI
    elif llm_provider_str == "ollama":
        llm_provider = LLMProvider.OLLAMA

    llm_model = os.getenv("LLM_MODEL", "qwen3.5:latest" if llm_provider == LLMProvider.OLLAMA else "claude-sonnet-4-6")

    llm_config = LLMConfig(
        provider=llm_provider,
        model=llm_model,
        base_url=os.getenv("OLLAMA_BASE_URL"),
    )
    llm_client = LLMClient(llm_config)
    logger.info(f"LLM configured: provider={llm_provider_str}, model={llm_model}")

    hyperopt_config = HyperoptConfig(
        user_data_dir="/user_data",
    )
    hyperopt_executor = HyperoptExecutor(
        db_path=db_path,
        knowledge_graph=kg,
        config=hyperopt_config,
    )

    orchestrator_config = OrchestratorConfig(
        interval_minutes=5,
        auto_apply_improvements=False,  # Require approval by default
        paper_trading_only=True,
    )

    async def notification_callback(notification: Dict):
        """Send notifications via WebSocket and Slack."""
        try:
            if ws_server:
                await ws_server.broadcast({"type": notification.get("type"), "data": notification})
            if manager and manager.slack:
                await manager.slack.send(notification.get("message", "Autonomous agent notification"))
        except Exception as e:
            logger.error(f"Notification callback failed: {e}")

    orchestrator = OrchestratorAgent(
        db_path=db_path,
        config=orchestrator_config,
        llm_client=llm_client,
        strategy_manager=manager,
        notification_callback=notification_callback,
    )

    # Store hyperopt executor reference
    orchestrator.hyperopt_executor = hyperopt_executor

    # Store Obsidian memory reference
    orchestrator.obsidian_memory = get_obsidian_memory()

    # Auto-start if configured
    # We schedule a delayed start so it runs after the event loop is fully up
    autostart = os.getenv("AUTOSTART_AUTONOMOUS", "true").lower() in ("true", "1", "yes")
    if autostart:
        async def _delayed_autostart():
            await asyncio.sleep(2)  # Wait for full app startup
            if orchestrator and not orchestrator.running:
                asyncio.create_task(orchestrator.start())
                logger.info("Autonomous agent auto-started")
        # Schedule the delayed start using a background thread trick
        # since we're not in an async context at module load time
        orchestrator._autostart_requested = True
        logger.info("Autonomous agent auto-start scheduled")
    else:
        logger.info("Autonomous agent auto-start disabled (AUTOSTART_AUTONOMOUS=false)")

    # ==================== Autonomous Control ====================

    @app.get("/api/autonomous/status")
    async def get_autonomous_status():
        """Get autonomous agent status."""
        try:
            status = orchestrator.get_status()
            return status
        except Exception as e:
            logger.error(f"Error getting autonomous status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/autonomous/start")
    async def start_autonomous():
        """Start autonomous mode."""
        try:
            if orchestrator.running:
                return {"status": "already_running", "message": "Autonomous mode already running"}

            # Start in background
            asyncio.create_task(orchestrator.start())
            return {"status": "started", "message": "Autonomous mode started"}
        except Exception as e:
            logger.error(f"Error starting autonomous mode: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/autonomous/stop")
    async def stop_autonomous():
        """Stop autonomous mode."""
        try:
            orchestrator.stop()
            return {"status": "stopped", "message": "Autonomous mode stopped"}
        except Exception as e:
            logger.error(f"Error stopping autonomous mode: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== Decisions ====================

    @app.get("/api/autonomous/decisions")
    async def get_decisions(
        agent_type: Optional[str] = None,
        decision_type: Optional[str] = None,
        since_hours: int = 24,
        limit: int = 50,
    ):
        """Get recent agent decisions."""
        try:
            since = datetime.utcnow() - timedelta(hours=since_hours)
            decisions = kg.get_decisions(
                agent_type=agent_type,
                decision_type=decision_type,
                since=since,
                limit=limit,
            )
            return {"decisions": [d.to_dict() for d in decisions]}
        except Exception as e:
            logger.error(f"Error getting decisions: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/autonomous/decisions/{decision_id}")
    async def get_decision(decision_id: str):
        """Get a specific decision with full reasoning."""
        try:
            entity = kg.get_entity(decision_id)
            if not entity:
                raise HTTPException(status_code=404, detail="Decision not found")
            return entity.to_dict()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting decision: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== Approvals ====================

    @app.get("/api/autonomous/approvals")
    async def get_pending_approvals():
        """Get decisions pending approval."""
        try:
            pending = kg.get_pending_approvals()
            return {"approvals": [p.to_dict() for p in pending]}
        except Exception as e:
            logger.error(f"Error getting pending approvals: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/autonomous/approvals/{decision_id}/approve")
    async def approve_decision(decision_id: str, reason: Optional[str] = None):
        """Approve a pending decision."""
        try:
            result = await orchestrator.approve_decision(decision_id)
            return result
        except Exception as e:
            logger.error(f"Error approving decision: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/autonomous/approvals/{decision_id}/reject")
    async def reject_decision(decision_id: str, reason: str):
        """Reject a pending decision."""
        try:
            orchestrator.reject_decision(decision_id, reason)
            return {"status": "rejected", "decision_id": decision_id, "reason": reason}
        except Exception as e:
            logger.error(f"Error rejecting decision: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== Research Findings ====================

    @app.get("/api/autonomous/findings")
    async def get_findings(
        source: Optional[str] = None,
        finding_type: Optional[str] = None,
        since_hours: int = 72,
        limit: int = 50,
    ):
        """Get research findings."""
        try:
            since = datetime.utcnow() - timedelta(hours=since_hours)
            findings = kg.get_findings(
                source=source,
                finding_type=finding_type,
                since=since,
                limit=limit,
            )
            return {"findings": [f.to_dict() for f in findings]}
        except Exception as e:
            logger.error(f"Error getting findings: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/autonomous/findings/{finding_id}/apply")
    async def apply_finding(finding_id: str, strategy_id: str):
        """Apply a research finding to a strategy."""
        try:
            kg.mark_finding_applied(finding_id, strategy_id)
            return {"status": "applied", "finding_id": finding_id, "strategy_id": strategy_id}
        except Exception as e:
            logger.error(f"Error applying finding: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== Hyperopt ====================

    @app.post("/api/autonomous/hyperopt")
    async def run_hyperopt(hyperopt_data: dict):
        """Run hyperopt for a strategy."""
        try:
            strategy_id = hyperopt_data.get("strategy_id")
            if not strategy_id:
                raise HTTPException(status_code=400, detail="strategy_id required")

            strategy = await manager.get_strategy_status(strategy_id)
            if not strategy:
                raise HTTPException(status_code=404, detail="Strategy not found")

            result = await orchestrator.hyperopt_executor.run_hyperopt(
                strategy_id=strategy_id,
                strategy_name=strategy.get("name", strategy_id[:8]),
                strategy_file=strategy.get("strategy_file"),
                config_path=strategy.get("config_path"),
                timerange=hyperopt_data.get("timerange", "20240101-"),
                epochs=hyperopt_data.get("epochs", 100),
            )

            return result.to_dict()
        except Exception as e:
            logger.error(f"Error running hyperopt: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/autonomous/hyperopt/status/{hyperopt_id}")
    async def get_hyperopt_status(hyperopt_id: str):
        """Get hyperopt status."""
        try:
            active = orchestrator.hyperopt_executor.get_active_hyperopts()
            if hyperopt_id in active:
                return {"status": "running", "hyperopt_id": hyperopt_id}
            return {"status": "completed", "hyperopt_id": hyperopt_id}
        except Exception as e:
            logger.error(f"Error getting hyperopt status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/autonomous/hyperopt/{hyperopt_id}/cancel")
    async def cancel_hyperopt(hyperopt_id: str):
        """Cancel a running hyperopt."""
        try:
            success = await orchestrator.hyperopt_executor.cancel_hyperopt(hyperopt_id)
            return {"status": "cancelled" if success else "not_found"}
        except Exception as e:
            logger.error(f"Error cancelling hyperopt: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== Strategy Lifecycle ====================

    @app.get("/api/autonomous/strategies/health")
    async def get_strategies_health():
        """Get health assessment for all strategies."""
        try:
            strategies = await manager.get_all_strategies()
            from autonomous_agent.strategy_agent import StrategyAgent

            strategy_agent = StrategyAgent(
                db_path="/data/dashboard.db",
                llm_client=orchestrator.llm,
                knowledge_graph=kg,
                hyperopt_executor=orchestrator.hyperopt_executor,
                strategy_manager=manager,
            )

            health_reports = []
            for strategy in strategies:
                health = await strategy_agent.evaluate_strategy(strategy)
                health_reports.append(health.to_dict())

            return {"strategies": health_reports}
        except Exception as e:
            logger.error(f"Error getting strategies health: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/autonomous/strategies/{strategy_id}/deprecate")
    async def deprecate_strategy(strategy_id: str, reason: str):
        """Deprecate a strategy."""
        try:
            from autonomous_agent.strategy_agent import StrategyAgent

            strategy_agent = StrategyAgent(
                db_path="/data/dashboard.db",
                llm_client=orchestrator.llm,
                knowledge_graph=kg,
                strategy_manager=manager,
            )

            result = await strategy_agent.deprecate_strategy(strategy_id, reason)
            return result
        except Exception as e:
            logger.error(f"Error deprecating strategy: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/autonomous/strategies/{strategy_id}/promote")
    async def promote_strategy(strategy_id: str):
        """Promote a strategy from paper to live."""
        try:
            from autonomous_agent.strategy_agent import StrategyAgent

            strategy_agent = StrategyAgent(
                db_path="/data/dashboard.db",
                llm_client=orchestrator.llm,
                knowledge_graph=kg,
                strategy_manager=manager,
            )

            result = await strategy_agent.promote_strategy(strategy_id)
            return result
        except Exception as e:
            logger.error(f"Error promoting strategy: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== Risk ====================

    @app.get("/api/autonomous/risk")
    async def get_risk_report():
        """Get current portfolio risk report."""
        try:
            strategies = await manager.get_all_strategies()
            portfolio = await manager.get_portfolio_summary()

            from autonomous_agent.risk_agent import RiskAgent

            risk_agent = RiskAgent(
                db_path="/data/dashboard.db",
                knowledge_graph=kg,
            )

            report = await risk_agent.check_portfolio_risk(strategies, portfolio)
            return report
        except Exception as e:
            logger.error(f"Error getting risk report: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== Memory (Obsidian) ====================

    @app.get("/api/autonomous/memory/search")
    async def search_memory(query: str, limit: int = 20):
        """Search agent memory in Obsidian vault."""
        try:
            from autonomous_agent.obsidian_store import search_obsidian_memory
            results = await search_obsidian_memory(query, limit=limit)
            return {"results": results}
        except Exception as e:
            logger.error(f"Error searching memory: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/autonomous/memory/summary")
    async def get_memory_summary():
        """Get memory summary from Obsidian vault."""
        try:
            from autonomous_agent.obsidian_store import get_memory_summary
            summary = get_memory_summary()
            return summary
        except Exception as e:
            logger.error(f"Error getting memory summary: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/autonomous/memory/list")
    async def list_memory_notes(
        memory_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ):
        """List notes in memory vault."""
        try:
            from autonomous_agent.obsidian_store import list_memory_notes
            notes = list_memory_notes(memory_type=memory_type, limit=limit, offset=offset)
            return {"notes": notes}
        except Exception as e:
            logger.error(f"Error listing memory notes: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/autonomous/memory/status")
    async def get_memory_status():
        """Get memory backend status."""
        try:
            from autonomous_agent.memory_backend import get_memory_backend
            backend = get_memory_backend()
            return {
                "available": backend.is_available(),
                "vault_path": str(backend.vault_path),
            }
        except Exception as e:
            logger.error(f"Error getting memory status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== Configuration ====================

    @app.get("/api/autonomous/config")
    async def get_autonomous_config():
        """Get autonomous agent configuration."""
        try:
            return {
                "interval_minutes": orchestrator.config.interval_minutes,
                "auto_apply_improvements": orchestrator.config.auto_apply_improvements,
                "paper_trading_only": orchestrator.config.paper_trading_only,
                "max_portfolio_drawdown": orchestrator.config.max_portfolio_drawdown,
                "max_position_size_pct": orchestrator.config.max_position_size_pct,
                "min_sharpe_ratio": orchestrator.config.min_sharpe_ratio,
                "min_improvement_threshold": orchestrator.config.min_improvement_threshold,
                "llm_model": orchestrator.llm.config.model,
            }
        except Exception as e:
            logger.error(f"Error getting config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.put("/api/autonomous/config")
    async def update_autonomous_config(config: dict):
        """Update autonomous agent configuration."""
        try:
            # Update orchestrator config
            if "interval_minutes" in config:
                orchestrator.config.interval_minutes = config["interval_minutes"]
            if "auto_apply_improvements" in config:
                orchestrator.config.auto_apply_improvements = config["auto_apply_improvements"]
            if "paper_trading_only" in config:
                orchestrator.config.paper_trading_only = config["paper_trading_only"]
            if "max_portfolio_drawdown" in config:
                orchestrator.config.max_portfolio_drawdown = config["max_portfolio_drawdown"]

            return {"status": "updated", "config": config}
        except Exception as e:
            logger.error(f"Error updating config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/autonomous/llm/usage")
    async def get_llm_usage():
        """Get LLM token usage statistics."""
        try:
            usage = orchestrator.llm.get_usage_stats()
            return usage
        except Exception as e:
            logger.error(f"Error getting LLM usage: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== Activity Stream ====================

    @app.get("/api/autonomous/activity")
    async def get_activity(
        limit: int = 50,
        agent: Optional[str] = None,
        activity_type: Optional[str] = None,
        since_hours: float = 24,
    ):
        """Get recent activity events."""
        try:
            from autonomous_agent.activity_logger import ActivityLogger, ActivityType

            activity_logger = ActivityLogger()

            # Parse activity type filter
            type_filter = None
            if activity_type:
                try:
                    type_filter = ActivityType(activity_type)
                except ValueError:
                    pass

            since = datetime.utcnow() - timedelta(hours=since_hours)
            events = activity_logger.get_recent_events(
                limit=limit,
                agent=agent,
                activity_type=type_filter,
                since=since,
            )

            return {"events": events, "total": len(events)}
        except Exception as e:
            logger.error(f"Error getting activity: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/autonomous/activity/{research_id}")
    async def get_research_activity(research_id: str):
        """Get all activity events for a specific research run."""
        try:
            from autonomous_agent.activity_logger import ActivityLogger

            activity_logger = ActivityLogger()
            events = activity_logger.get_events_by_research_id(research_id)

            return {"research_id": research_id, "events": events}
        except Exception as e:
            logger.error(f"Error getting research activity: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/autonomous/activity/test")
    async def create_test_activity():
        """Create a test activity event for debugging."""
        try:
            from autonomous_agent.activity_logger import ActivityLogger, ActivityType

            activity_logger = ActivityLogger()
            event = activity_logger.log(
                activity_type=ActivityType.INFO,
                agent="test",
                title="Test Activity",
                message="This is a test activity event",
                details={"test": True},
            )

            return {"created": event.to_dict()}
        except Exception as e:
            logger.error(f"Error creating test activity: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    logger.info("Autonomous agent routes configured")
    return orchestrator