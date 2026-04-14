import asyncio
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from db import Database, init_database
from config_parser import ConfigParser
from container_manager import ContainerManager
from backtest_runner import BacktestRunner
from freqai_adapter import FreqAIAdapter
from slack_notifier import SlackNotifier
from websocket_server import WebSocketServer
from manager import FreqtradeManager
from research_orchestrator import ResearchOrchestrator

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/dashboard.db")
CONFIGS_DIR = os.getenv("CONFIGS_DIR", "/configs")
USER_DATA_DIR = os.getenv("USER_DATA_DIR", "/user_data")
MANAGER_PORT = int(os.getenv("MANAGER_PORT", "8765"))
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

db = None
ws_server = None
manager = None
research_orchestrator = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db, ws_server, manager, research_orchestrator

    logger.info("Starting Freqtrade Manager...")

    await init_database(DATABASE_PATH)
    db = Database(DATABASE_PATH)

    config_parser = ConfigParser(configs_dir=CONFIGS_DIR, user_data_dir=USER_DATA_DIR)
    container_manager = None  # Initialize lazily when needed
    backtest_runner = BacktestRunner()
    freqai_adapter = FreqAIAdapter(user_data_dir=USER_DATA_DIR)
    slack_notifier = SlackNotifier(webhook_url=SLACK_WEBHOOK_URL)

    # Try to initialize container manager, but continue if Docker is not available
    try:
        container_manager = ContainerManager()
        # Don't test connection during startup - just create the instance
        logger.info(
            "Container manager initialized (will connect to Docker on first use)"
        )
    except Exception as e:
        logger.warning(f"Could not initialize container manager: {e}")
        container_manager = None

    manager = FreqtradeManager(
        db=db,
        config_parser=config_parser,
        container_manager=container_manager,  # May be None if Docker not available
        backtest_runner=backtest_runner,
        freqai_adapter=freqai_adapter,
        slack_notifier=slack_notifier,
        templates_dir="/templates",
    )

    # Initialize research orchestrator
    research_orchestrator = ResearchOrchestrator(
        db_path=DATABASE_PATH,
        container_manager=container_manager,
        config_parser=config_parser,
        strategy_manager=manager,
    )
    logger.info("Research orchestrator initialized")

    auto_detected = await manager.auto_detect_strategies()
    logger.info(f"Auto-detected {len(auto_detected)} existing strategies")

    ws_server = WebSocketServer(port=MANAGER_PORT)
    ws_server.set_manager(manager)
    ws_server.set_slack(slack_notifier)

    ws_task = asyncio.create_task(ws_server.start())

    logger.info("Freqtrade Manager started successfully")

    yield

    logger.info("Shutting down Freqtrade Manager...")
    ws_task.cancel()
    logger.info("Freqtrade Manager stopped")


app = FastAPI(title="Freqtrade Manager API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "freqtrade-manager"}


@app.get("/api/strategies")
async def get_strategies():
    try:
        strategies = await manager.get_all_strategies()
        return {"strategies": strategies}
    except Exception as e:
        logger.error(f"Error getting strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/strategies")
async def create_strategy(strategy_data: dict):
    try:
        template_id = strategy_data.get("template_id")
        if not template_id:
            raise HTTPException(status_code=400, detail="template_id required")

        strategy_id = await manager.create_strategy_from_template(
            template_id=template_id, customizations=strategy_data
        )

        return {"strategy_id": strategy_id, "status": "created"}
    except ValueError as e:
        logger.error(f"Validation error creating strategy: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating strategy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/strategies/{strategy_id}")
async def get_strategy(strategy_id: str):
    try:
        strategy = await manager.get_strategy_status(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return strategy
    except Exception as e:
        logger.error(f"Error getting strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/strategies/{strategy_id}")
async def update_strategy(strategy_id: str, updates: dict):
    try:
        result = await manager.update_strategy_config(strategy_id, updates)
        return {"success": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str):
    try:
        result = await manager.delete_strategy(strategy_id)
        return {"success": result}
    except Exception as e:
        logger.error(f"Error deleting strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/strategies/{strategy_id}/start")
async def start_strategy(strategy_id: str):
    try:
        result = await manager.start_strategy(strategy_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error starting strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/strategies/{strategy_id}/stop")
async def stop_strategy(strategy_id: str):
    try:
        result = await manager.stop_strategy(strategy_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error stopping strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/strategies/{strategy_id}/restart")
async def restart_strategy(strategy_id: str):
    try:
        await manager.stop_strategy(strategy_id)
        await asyncio.sleep(2)
        result = await manager.start_strategy(strategy_id)
        return result
    except Exception as e:
        logger.error(f"Error restarting strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/strategies/{strategy_id}/logs")
async def get_logs(strategy_id: str, tail: int = 100):
    try:
        logs = await manager.container_manager.get_container_logs(strategy_id, tail)
        return {"logs": logs}
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/strategies/{strategy_id}/trades")
async def get_trades(strategy_id: str, status: str = "all", limit: int = 100):
    try:
        import sqlite3
        from pathlib import Path

        db_path = Path(USER_DATA_DIR) / strategy_id / "tradesv3.dryrun.sqlite"

        if not db_path.exists():
            return {"trades": []}

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        if status == "open":
            query = (
                "SELECT * FROM trades WHERE is_open = 1 ORDER BY open_date DESC LIMIT ?"
            )
        elif status == "closed":
            query = "SELECT * FROM trades WHERE is_open = 0 ORDER BY close_date DESC LIMIT ?"
        else:
            query = (
                "SELECT * FROM trades ORDER BY close_date DESC, open_date DESC LIMIT ?"
            )

        cursor = conn.execute(query, (limit,))
        rows = cursor.fetchall()
        conn.close()

        trades = [dict(row) for row in rows]
        return {"trades": trades}
    except Exception as e:
        logger.error(f"Error getting trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/backtest")
async def run_backtest(backtest_data: dict):
    try:
        strategy_id = backtest_data.get("strategy_id")
        timerange = backtest_data.get("timerange")
        params = backtest_data.get("params", {})

        result = await manager.run_backtest(
            strategy_id=strategy_id, timerange=timerange, params=params
        )

        return result
    except Exception as e:
        logger.error(f"Error running backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/backtest/results")
async def get_backtest_results(strategy_id: str = None, limit: int = 50):
    try:
        results = await manager.backtest_runner.get_backtest_history(
            strategy_id=strategy_id, limit=limit
        )
        return {"results": results}
    except Exception as e:
        logger.error(f"Error getting backtest results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/freqai/status")
async def get_freqai_status(strategy_id: str):
    try:
        status = manager.freqai_adapter.get_latest_model_info(strategy_id)
        return status or {}
    except Exception as e:
        logger.error(f"Error getting FreqAI status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/freqai/insights")
async def get_freqai_insights(strategy_id: str):
    try:
        history = await db.get_freqai_training_history(strategy_id)
        return {"history": history}
    except Exception as e:
        logger.error(f"Error getting FreqAI insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/strategies/{strategy_id}/reasoning")
async def get_strategy_reasoning(strategy_id: str, hours: int = 24, limit: int = 100):
    try:
        from agent_logger import AgentLogger

        logger_instance = AgentLogger(DATABASE_PATH)
        logs = logger_instance.get_recent_reasoning(strategy_id, hours=hours)

        return {"logs": logs[:limit]}
    except Exception as e:
        logger.error(f"Error getting reasoning logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/strategies/{strategy_id}/agent-logs")
async def get_agent_logs(
    strategy_id: str,
    category: str = None,
    level: str = None,
    limit: int = 100,
    offset: int = 0,
):
    try:
        from agent_logger import AgentLogger

        logger_instance = AgentLogger(DATABASE_PATH)
        logs = logger_instance.get_logs(
            strategy_id=strategy_id,
            category=category,
            level=level,
            limit=limit,
            offset=offset,
        )

        return {"logs": logs}
    except Exception as e:
        logger.error(f"Error getting agent logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/freqai/model/{strategy_id}")
async def get_freqai_model(strategy_id: str):
    try:
        from freqai_tracker import FreqAITracker

        tracker = FreqAITracker(DATABASE_PATH)
        status = tracker.get_model_status(strategy_id)

        return status or {}
    except Exception as e:
        logger.error(f"Error getting FreqAI model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/freqai/training/{strategy_id}")
async def get_freqai_training(strategy_id: str):
    try:
        from freqai_tracker import FreqAITracker

        tracker = FreqAITracker(DATABASE_PATH)
        progress = tracker.get_training_progress(strategy_id)

        return progress or {}
    except Exception as e:
        logger.error(f"Error getting FreqAI training: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/freqai/predictions/{strategy_id}")
async def get_freqai_predictions(
    strategy_id: str, limit: int = 100, outcomes: bool = False
):
    try:
        from freqai_tracker import FreqAITracker

        tracker = FreqAITracker(DATABASE_PATH)
        predictions = tracker.get_predictions(
            strategy_id, limit=limit, include_outcomes=outcomes
        )

        return {"predictions": predictions}
    except Exception as e:
        logger.error(f"Error getting FreqAI predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/freqai/performance/{strategy_id}")
async def get_freqai_performance(strategy_id: str):
    try:
        from freqai_tracker import FreqAITracker

        tracker = FreqAITracker(DATABASE_PATH)
        history = tracker.get_model_performance_history(strategy_id)
        accuracy = tracker.get_prediction_accuracy_stats(strategy_id)

        return {"history": history, "accuracy": accuracy}
    except Exception as e:
        logger.error(f"Error getting FreqAI performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/freqai/features/{strategy_id}")
async def get_freqai_features(strategy_id: str):
    try:
        from freqai_tracker import FreqAITracker

        tracker = FreqAITracker(DATABASE_PATH)
        evolution = tracker.get_feature_importance_evolution(strategy_id)

        return {"evolution": evolution}
    except Exception as e:
        logger.error(f"Error getting FreqAI features: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/research/active")
async def get_active_research():
    try:
        from research_tracker import ResearchTracker

        tracker = ResearchTracker(DATABASE_PATH)
        active = tracker.get_active_research()

        return {"active": active}
    except Exception as e:
        logger.error(f"Error getting active research: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/research/history")
async def get_research_history(
    strategy_id: str = None, research_type: str = None, limit: int = 50
):
    try:
        from research_tracker import ResearchTracker

        tracker = ResearchTracker(DATABASE_PATH)
        history = tracker.get_research_history(
            strategy_id=strategy_id, research_type=research_type, limit=limit
        )

        return {"history": history}
    except Exception as e:
        logger.error(f"Error getting research history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/research/summary")
async def get_research_summary(days: int = 30):
    try:
        from research_tracker import ResearchTracker

        tracker = ResearchTracker(DATABASE_PATH)
        summary = tracker.get_research_summary(days=days)

        return summary
    except Exception as e:
        logger.error(f"Error getting research summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/research/discoveries")
async def get_recent_discoveries(limit: int = 10):
    try:
        from research_tracker import ResearchTracker

        tracker = ResearchTracker(DATABASE_PATH)
        discoveries = tracker.get_recent_discoveries(limit=limit)

        return {"discoveries": discoveries}
    except Exception as e:
        logger.error(f"Error getting discoveries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/research/scheduled")
async def get_scheduled_research():
    try:
        from research_tracker import ResearchTracker

        tracker = ResearchTracker(DATABASE_PATH)
        scheduled = tracker.get_scheduled_research()

        return {"scheduled": scheduled}
    except Exception as e:
        logger.error(f"Error getting scheduled research: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/research/start")
async def start_research(research_data: dict):
    try:
        strategy_id = research_data.get("strategy_id")
        strategy_name = research_data.get(
            "strategy_name", strategy_id[:8] if strategy_id else "Unknown"
        )
        research_type = research_data.get("research_type", "hyperopt")
        epochs = research_data.get("epochs", 100)
        timerange = research_data.get("timerange", "20240101-")

        if not strategy_id:
            raise HTTPException(status_code=400, detail="strategy_id required")

        if research_type == "hyperopt":
            research_id = await research_orchestrator.start_hyperopt(
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                timerange=timerange,
                epochs=epochs,
            )
        elif research_type == "backtest_comparison":
            research_id = await research_orchestrator.run_backtest_comparison(
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                timeranges=[timerange],
                configs=[{}],
            )
        elif research_type == "strategy_discovery":
            research_id = await research_orchestrator.discover_strategies(
                timeframe="15m",
                exchanges=["kraken"],
                pairs=["BTC/USDT"],
            )
        else:
            raise HTTPException(
                status_code=400, detail=f"Unknown research type: {research_type}"
            )

        return {"research_id": research_id, "status": "started"}
    except Exception as e:
        logger.error(f"Error starting research: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/research/cancel/{research_id}")
async def cancel_research(research_id: str):
    try:
        success = research_orchestrator.cancel_research(research_id)
        return {"success": success}
    except Exception as e:
        logger.error(f"Error cancelling research: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/research/schedule")
async def schedule_research(schedule_data: dict):
    try:
        strategy_id = schedule_data.get("strategy_id")
        strategy_name = schedule_data.get(
            "strategy_name", strategy_id[:8] if strategy_id else "Unknown"
        )
        research_type = schedule_data.get("research_type", "hyperopt")
        frequency = schedule_data.get("frequency", "weekly")

        schedule_id = await research_orchestrator.schedule_regular_research(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            research_type=research_type,
            frequency=frequency,
        )

        return {"schedule_id": schedule_id, "status": "scheduled"}
    except Exception as e:
        logger.error(f"Error scheduling research: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/research/{research_id}/apply")
async def apply_research_findings(research_id: str):
    try:
        from research_tracker import ResearchTracker

        tracker = ResearchTracker(DATABASE_PATH)

        # Check if already applied
        if tracker.is_applied(research_id):
            raise HTTPException(
                status_code=400, detail="Research findings already applied"
            )

        history = tracker.get_research_history(limit=100)
        research = None
        for r in history:
            if r.get("research_id") == research_id:
                research = r
                break

        if not research:
            raise HTTPException(status_code=404, detail="Research not found")

        if research.get("status") != "completed":
            raise HTTPException(status_code=400, detail="Research not completed yet")

        best_params = research.get("best_params", {})
        if not best_params:
            raise HTTPException(status_code=400, detail="No findings to apply")

        strategy_id = research.get("strategy_id")
        if not strategy_id:
            raise HTTPException(
                status_code=400, detail="No strategy associated with research"
            )

        strategy = await manager.db.get_strategy(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")

        await manager.update_strategy_config(strategy_id, best_params)

        # Mark as applied
        tracker.mark_applied(research_id)

        # Restart if running
        was_running = strategy.get("status") == "running"
        if was_running:
            await manager.stop_strategy(strategy_id)
            await asyncio.sleep(2)
            await manager.start_strategy(strategy_id)

        from agent_logger import AgentLogger, LogCategory, LogLevel

        logger_instance = AgentLogger(DATABASE_PATH)
        logger_instance.log(
            strategy_id=strategy_id,
            strategy_name=strategy.get("name", strategy_id[:8]),
            category=LogCategory.PARAMETER_UPDATE,
            level=LogLevel.INFO,
            title="Research Findings Applied",
            message=f"Applied parameters from research {research_id}",
            reasoning=f"Improvement: {research.get('improvement_pct', 0):.1f}%",
            data={
                "research_id": research_id,
                "params": best_params,
                "improvement": research.get("improvement_pct"),
            },
            impact="high",
            confidence=0.9,
        )

        return {
            "success": True,
            "message": f"Applied parameters: {list(best_params.keys())}",
            "params": best_params,
            "improvement": research.get("improvement_pct"),
            "strategy_restarted": was_running,
        }
    except Exception as e:
        logger.error(f"Error applying research findings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/research/applicable")
async def get_applicable_research(strategy_id: str = None):
    try:
        from research_tracker import ResearchTracker

        tracker = ResearchTracker(DATABASE_PATH)
        applicable = tracker.get_applicable_research(strategy_id=strategy_id)

        return {"applicable": applicable}
    except Exception as e:
        logger.error(f"Error getting applicable research: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/strategies/{strategy_id}/enable-freqai")
async def enable_freqai(strategy_id: str, freqai_config: dict = None):
    try:
        strategy = await manager.db.get_strategy(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")

        config = {
            "use_freqai": True,
            "freqai_model": freqai_config.get("model", "lightgbm")
            if freqai_config
            else "lightgbm",
        }

        if freqai_config:
            if "train_period_days" in freqai_config:
                config["freqai_train_period"] = freqai_config["train_period_days"]
            if "backtest_period_days" in freqai_config:
                config["freqai_backtest_period"] = freqai_config["backtest_period_days"]

        await manager.update_strategy_config(strategy_id, config)

        strategy["use_freqai"] = True
        strategy["freqai_model"] = config["freqai_model"]
        await manager.db.update_strategy(strategy_id, strategy)

        return {
            "success": True,
            "message": f"FreqAI enabled for {strategy_id} with {config['freqai_model']} model",
        }
    except Exception as e:
        logger.error(f"Error enabling FreqAI: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/strategies/{strategy_id}/disable-freqai")
async def disable_freqai(strategy_id: str):
    try:
        strategy = await manager.db.get_strategy(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")

        config = {"use_freqai": False}
        await manager.update_strategy_config(strategy_id, config)

        strategy["use_freqai"] = False
        await manager.db.update_strategy(strategy_id, strategy)

        return {"success": True, "message": f"FreqAI disabled for {strategy_id}"}
    except Exception as e:
        logger.error(f"Error disabling FreqAI: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/settings")
async def get_settings():
    try:
        settings = {
            "auto_research": True,
            "auto_apply_improvements": True,
            "research_frequency": "weekly",
            "min_improvement_threshold": 5.0,
            "max_concurrent_research": 3,
            "freqai_enabled_globally": False,
            "default_freqai_model": "lightgbm",
            "slack_enabled": bool(SLACK_WEBHOOK_URL),
            "container_manager_available": bool(manager.container_manager),
            "base_port": int(os.getenv("BASE_PORT", "7070")),
        }

        return settings
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings")
async def update_settings(settings_data: dict):
    try:
        for key, value in settings_data.items():
            logger.info(f"Setting {key} = {value}")

        return {"success": True, "message": "Settings updated"}
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/portfolio")
async def get_portfolio():
    try:
        summary = await manager.get_portfolio_summary()
        return summary
    except Exception as e:
        logger.error(f"Error getting portfolio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/templates")
async def get_templates():
    try:
        templates = await manager.get_templates()
        return {"templates": templates}
    except Exception as e:
        logger.error(f"Error getting templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/slack/test")
async def test_slack():
    try:
        result = await manager.slack.send(
            "Test notification from Freqtrade Manager",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "✅ *Test Successful*\nFreqtrade Manager is properly configured.",
                    },
                }
            ],
        )
        return {"success": result}
    except Exception as e:
        logger.error(f"Error sending Slack notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Autonomous Agent Routes ====================
# Import and setup autonomous routes
try:
    from autonomous_api import setup_autonomous_routes
    autonomous_orchestrator = setup_autonomous_routes(app, db, manager, ws_server)
    logger.info("Autonomous agent routes configured successfully")
except ImportError as e:
    logger.warning(f"Autonomous agent routes not available: {e}")
    autonomous_orchestrator = None
except Exception as e:
    logger.error(f"Failed to setup autonomous routes: {e}")
    autonomous_orchestrator = None


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
