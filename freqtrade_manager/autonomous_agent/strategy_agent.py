"""
Strategy Agent - Manages strategy lifecycle and optimization.

Responsibilities:
- Create new strategies from templates
- Run hyperopt optimizations
- Deprecate poor performers
- Apply research findings
- Manage strategy lifecycle
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from .llm_client import LLMClient
from .knowledge_graph import KnowledgeGraph, AgentDecision, EntityType
from .hyperopt_executor import HyperoptExecutor, HyperoptConfig

logger = logging.getLogger(__name__)


class StrategyState(Enum):
    DRAFT = "draft"
    BACKTESTING = "backtesting"
    PAPER_TRADING = "paper_trading"
    LIVE = "live"
    DEPRECATED = "deprecated"


@dataclass
class StrategyHealth:
    """Health assessment for a strategy."""

    strategy_id: str
    strategy_name: str
    state: StrategyState
    health_score: float
    total_trades: int
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    profit_pct: float
    days_running: int
    last_trade: Optional[datetime] = None
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class StrategyConfig:
    """Configuration for strategy management."""

    # Lifecycle thresholds
    min_trades_for_evaluation: int = 100
    min_sharpe_ratio: float = 0.5
    max_drawdown_threshold: float = 0.20
    min_uptime_days: int = 7
    deprecation_threshold: float = -10.0  # % loss
    promotion_threshold: float = 5.0  # % gain

    # Paper trading
    paper_trading_duration_days: int = 30
    paper_trading_min_trades: int = 50

    # Optimization
    auto_hyperopt: bool = True
    hyperopt_frequency_days: int = 7
    min_improvement_for_apply: float = 3.0


class StrategyAgent:
    """
    Agent that manages strategy lifecycle and optimization.

    Responsibilities:
    - Evaluate strategy health
    - Create new strategies
    - Run hyperopt optimizations
    - Promote/demote strategies
    - Apply research findings
    - Manage deprecation
    """

    def __init__(
        self,
        db_path: str,
        llm_client: LLMClient,
        knowledge_graph: KnowledgeGraph,
        hyperopt_executor: Optional[HyperoptExecutor] = None,
        strategy_manager=None,
        config: Optional[StrategyConfig] = None,
    ):
        self.db_path = db_path
        self.llm = llm_client
        self.kg = knowledge_graph
        self.hyperopt_executor = hyperopt_executor
        self.strategy_manager = strategy_manager
        self.config = config or StrategyConfig()

    async def evaluate_strategy(self, strategy: Dict) -> StrategyHealth:
        """
        Evaluate health of a strategy.

        Returns StrategyHealth with issues and recommendations.
        """
        strategy_id = strategy.get("id")
        strategy_name = strategy.get("name", strategy_id[:8])

        # Get performance data
        perf = strategy.get("performance", {})
        trades = strategy.get("trades", [])

        health = StrategyHealth(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            state=StrategyState(strategy.get("status", "stopped")),
            health_score=0.0,
            total_trades=len(trades),
            win_rate=perf.get("win_rate", 0),
            sharpe_ratio=perf.get("sharpe", 0),
            max_drawdown=perf.get("max_drawdown", 0),
            profit_pct=perf.get("profit_pct", 0),
            days_running=0,
        )

        # Calculate days running
        if strategy.get("started_at"):
            started = datetime.fromisoformat(strategy["started_at"])
            health.days_running = (datetime.utcnow() - started).days

        # Calculate health score
        health.health_score = self._calculate_health_score(health)

        # Identify issues
        health.issues = self._identify_issues(health)

        # Generate recommendations
        health.recommendations = await self._generate_recommendations(health, strategy)

        return health

    def _calculate_health_score(self, health: StrategyHealth) -> float:
        """Calculate overall health score for strategy."""
        score = 100.0

        # Win rate factor
        if health.win_rate < 0.4:
            score -= 30
        elif health.win_rate < 0.5:
            score -= 15
        elif health.win_rate > 0.6:
            score += 10

        # Sharpe ratio factor
        if health.sharpe_ratio < 0:
            score -= 25
        elif health.sharpe_ratio < 0.5:
            score -= 10
        elif health.sharpe_ratio > 1.5:
            score += 15

        # Drawdown factor
        if health.max_drawdown > 0.2:
            score -= 30
        elif health.max_drawdown > 0.15:
            score -= 20
        elif health.max_drawdown > 0.1:
            score -= 10

        # Profit factor
        if health.profit_pct < -10:
            score -= 30
        elif health.profit_pct < 0:
            score -= 15
        elif health.profit_pct > 10:
            score += 15

        # Trade count confidence
        if health.total_trades < 50:
            score -= 15  # Low confidence
        elif health.total_trades < 100:
            score -= 5
        elif health.total_trades > 200:
            score += 5  # High confidence

        # Days running factor
        if health.days_running < 7:
            score -= 10  # Too early to judge

        return max(0, min(100, score))

    def _identify_issues(self, health: StrategyHealth) -> List[str]:
        """Identify issues with the strategy."""
        issues = []

        # Performance issues
        if health.win_rate < 0.4:
            issues.append(f"Low win rate: {health.win_rate:.1%}")
        if health.sharpe_ratio < 0:
            issues.append(f"Negative Sharpe ratio: {health.sharpe_ratio:.2f}")
        if health.max_drawdown > 0.2:
            issues.append(f"High drawdown: {health.max_drawdown:.1%}")
        if health.profit_pct < -10:
            issues.append(f"Significant loss: {health.profit_pct:.1f}%")

        # Trade count issues
        if health.total_trades < 30:
            issues.append(f"Insufficient trades: {health.total_trades}")
        elif health.total_trades > 1000:
            issues.append(f"Over-trading: {health.total_trades} trades")

        # State issues
        if health.state == StrategyState.DRAFT:
            issues.append("Strategy not started")
        if health.state == StrategyState.DEPRECATED:
            issues.append("Strategy is deprecated")

        return issues

    async def _generate_recommendations(
        self, health: StrategyHealth, strategy: Dict
    ) -> List[str]:
        """Generate recommendations for the strategy."""
        recommendations = []

        # Performance-based recommendations
        if health.health_score < 30:
            recommendations.append("Consider stopping strategy - health score critical")
            recommendations.append("Run hyperopt to find better parameters")
        elif health.health_score < 50:
            recommendations.append("Monitor closely - consider optimization")
            recommendations.append("Reduce position size")
        elif health.health_score > 80:
            recommendations.append(
                "Strategy performing well - consider increasing allocation"
            )

        # State-based recommendations
        if health.state == StrategyState.PAPER_TRADING:
            if (
                health.total_trades > self.config.paper_trading_min_trades
                and health.days_running > self.config.paper_trading_duration_days
            ):
                if health.health_score > 60:
                    recommendations.append("Ready for promotion to live trading")
                else:
                    recommendations.append(
                        "Extend paper trading - performance below threshold"
                    )

        # Research-based recommendations
        unapplied_findings = self.kg.get_unapplied_findings(limit=5)
        if unapplied_findings:
            recommendations.append(
                f"{len(unapplied_findings)} research findings pending application"
            )

        # Hyperopt recommendations
        if self.config.auto_hyperopt:
            last_hyperopt = strategy.get("last_hyperopt_at")
            if last_hyperopt:
                last_hyperopt_date = datetime.fromisoformat(last_hyperopt)
                days_since_hyperopt = (datetime.utcnow() - last_hyperopt_date).days
                if days_since_hyperopt > self.config.hyperopt_frequency_days:
                    recommendations.append(
                        f"Due for hyperopt (last run {days_since_hyperopt} days ago)"
                    )

        return recommendations

    async def create_strategy(
        self,
        template_id: str,
        name: str,
        pairs: List[str],
        custom_params: Optional[Dict] = None,
        start_paper: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a new strategy from template.

        Args:
            template_id: Template to use
            name: Strategy name
            pairs: Trading pairs
            custom_params: Custom parameters
            start_paper: Whether to start in paper trading mode

        Returns:
            Created strategy info
        """
        if not self.strategy_manager:
            raise ValueError("Strategy manager not available")

        # Create strategy
        strategy_id = await self.strategy_manager.create_strategy_from_template(
            template_id=template_id,
            customizations={
                "name": name,
                "pairs": pairs,
                **(custom_params or {}),
                "dry_run": start_paper,
            },
        )

        # Log creation
        decision = AgentDecision(
            id=f"create_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{strategy_id[:8]}",
            agent_type="strategy",
            decision_type="create_strategy",
            context={
                "template_id": template_id,
                "name": name,
                "pairs": pairs,
                "custom_params": custom_params,
                "paper_trading": start_paper,
            },
            reasoning_chain=[
                f"Creating strategy from template {template_id}",
                f"Name: {name}, Pairs: {pairs}",
                f"Mode: {'paper' if start_paper else 'live'}",
            ],
            conclusion=f"Strategy {strategy_id} created",
            confidence=1.0,
            metadata={"strategy_id": strategy_id},
        )

        self.kg.log_decision(decision)

        return {
            "strategy_id": strategy_id,
            "name": name,
            "template_id": template_id,
            "pairs": pairs,
            "status": "created",
        }

    async def run_hyperopt(
        self,
        strategy_id: str,
        epochs: int = 100,
        timerange: str = "20240101-",
    ) -> Dict[str, Any]:
        """
        Run hyperopt for a strategy.

        Args:
            strategy_id: Strategy to optimize
            epochs: Number of epochs
            timerange: Backtest timerange

        Returns:
            Hyperopt result
        """
        if not self.strategy_manager:
            raise ValueError("Strategy manager not available")

        # Get strategy info
        strategy = await self.strategy_manager.get_strategy_status(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        strategy_file = strategy.get("strategy_file")
        config_path = strategy.get("config_path")

        if not self.hyperopt_executor:
            raise ValueError("Hyperopt executor not available")

        # Run hyperopt
        result = await self.hyperopt_executor.run_hyperopt(
            strategy_id=strategy_id,
            strategy_name=strategy.get("name", strategy_id[:8]),
            strategy_file=strategy_file,
            config_path=config_path,
            timerange=timerange,
            epochs=epochs,
        )

        return result.to_dict()

    async def apply_hyperopt_results(
        self,
        strategy_id: str,
        hyperopt_id: str,
        require_approval: bool = True,
    ) -> Dict[str, Any]:
        """
        Apply hyperopt results to strategy.

        Args:
            strategy_id: Strategy to update
            hyperopt_id: Hyperopt result to apply
            require_approval: Whether to require approval

        Returns:
            Application result
        """
        # Get hyperopt result
        # In production, this would query from database
        finding = None
        for f in self.kg.get_findings(source="hyperopt", limit=10):
            if hyperopt_id in f.id:
                finding = f
                break

        if not finding:
            raise ValueError(f"Hyperopt result {hyperopt_id} not found")

        best_params = finding.impact_assessment.get("best_params", {})
        improvement = finding.impact_assessment.get("improvement_pct", 0)

        if improvement < self.config.min_improvement_for_apply:
            return {
                "status": "rejected",
                "reason": f"Improvement {improvement:.1f}% below threshold {self.config.min_improvement_for_apply}%",
            }

        # Create decision for approval if required
        if require_approval:
            decision = AgentDecision(
                id=f"apply_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{strategy_id[:8]}",
                agent_type="strategy",
                decision_type="apply_hyperopt",
                context={
                    "strategy_id": strategy_id,
                    "hyperopt_id": hyperopt_id,
                    "improvement_pct": improvement,
                },
                reasoning_chain=[
                    f"Hyperopt found {improvement:.1f}% improvement",
                    f"Best params: {json.dumps(best_params, indent=2)}",
                    f"Applicable to strategy {strategy_id}",
                ],
                conclusion=f"Apply hyperopt results to {strategy_id}",
                confidence=0.8 + (improvement / 100) * 0.2,
                requires_approval=True,
                metadata={
                    "best_params": best_params,
                    "improvement": improvement,
                },
            )

            self.kg.log_decision(decision)

            return {
                "status": "pending_approval",
                "decision_id": decision.id,
                "improvement": improvement,
                "params": best_params,
            }

        # Apply immediately if not requiring approval
        if self.strategy_manager:
            await self.strategy_manager.update_strategy_config(strategy_id, best_params)

        # Mark finding as applied
        self.kg.mark_finding_applied(finding.id, strategy_id)

        return {
            "status": "applied",
            "improvement": improvement,
            "params": best_params,
        }

    async def deprecate_strategy(
        self,
        strategy_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """
        Deprecate a poorly performing strategy.

        Args:
            strategy_id: Strategy to deprecate
            reason: Deprecation reason

        Returns:
            Deprecation result
        """
        if not self.strategy_manager:
            raise ValueError("Strategy manager not available")

        # Stop the strategy
        try:
            await self.strategy_manager.stop_strategy(strategy_id)
        except Exception as e:
            logger.warning(f"Failed to stop strategy: {e}")

        # Log deprecation
        decision = AgentDecision(
            id=f"deprecate_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{strategy_id[:8]}",
            agent_type="strategy",
            decision_type="deprecate_strategy",
            context={
                "strategy_id": strategy_id,
                "reason": reason,
            },
            reasoning_chain=[
                "Strategy health score below threshold",
                f"Reason: {reason}",
                "Deprecating to protect capital",
            ],
            conclusion=f"Strategy {strategy_id} deprecated",
            confidence=0.9,
            requires_approval=False,
        )

        self.kg.log_decision(decision)

        return {
            "status": "deprecated",
            "strategy_id": strategy_id,
            "reason": reason,
        }

    async def promote_strategy(
        self,
        strategy_id: str,
    ) -> Dict[str, Any]:
        """
        Promote a strategy from paper trading to live.

        Args:
            strategy_id: Strategy to promote

        Returns:
            Promotion result
        """
        if not self.strategy_manager:
            raise ValueError("Strategy manager not available")

        # Get strategy status
        strategy = await self.strategy_manager.get_strategy_status(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        # Check promotion criteria
        health = await self.evaluate_strategy(strategy)

        if health.health_score < self.config.promotion_threshold * 10:
            return {
                "status": "rejected",
                "reason": f"Health score {health.health_score} below threshold",
            }

        if health.total_trades < self.config.paper_trading_min_trades:
            return {
                "status": "rejected",
                "reason": f"Insufficient trades: {health.total_trades}",
            }

        if health.days_running < self.config.paper_trading_duration_days:
            return {
                "status": "rejected",
                "reason": f"Insufficient paper trading duration: {health.days_running} days",
            }

        # Update strategy config to live mode
        await self.strategy_manager.update_strategy_config(
            strategy_id, {"dry_run": False}
        )

        # Log promotion
        decision = AgentDecision(
            id=f"promote_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{strategy_id[:8]}",
            agent_type="strategy",
            decision_type="promote_strategy",
            context={
                "strategy_id": strategy_id,
                "health_score": health.health_score,
                "total_trades": health.total_trades,
                "days_running": health.days_running,
            },
            reasoning_chain=[
                f"Health score: {health.health_score}",
                f"Total trades: {health.total_trades}",
                f"Days running: {health.days_running}",
                "All promotion criteria met",
            ],
            conclusion=f"Strategy {strategy_id} promoted to live",
            confidence=0.85,
            requires_approval=True,  # Require approval for live promotion
        )

        self.kg.log_decision(decision)

        return {
            "status": "pending_approval",
            "decision_id": decision.id,
            "health_score": health.health_score,
        }

    def get_lifecycle_recommendations(self, strategies: List[Dict]) -> List[Dict]:
        """Get lifecycle recommendations for all strategies."""
        recommendations = []

        for strategy in strategies:
            health = self.evaluate_strategy_sync(strategy)

            if health.health_score < 30:
                recommendations.append(
                    {
                        "strategy_id": strategy.get("id"),
                        "action": "deprecate",
                        "reason": f"Health score {health.health_score} - critical",
                        "priority": "high",
                    }
                )
            elif health.health_score > 80 and strategy.get("status") == "paper_trading":
                recommendations.append(
                    {
                        "strategy_id": strategy.get("id"),
                        "action": "promote",
                        "reason": f"Health score {health.health_score} - ready for live",
                        "priority": "medium",
                    }
                )

            if strategy.get("status") == "running":
                last_hyperopt = strategy.get("last_hyperopt_at")
                if last_hyperopt:
                    days_since = (
                        datetime.utcnow() - datetime.fromisoformat(last_hyperopt)
                    ).days
                    if days_since > self.config.hyperopt_frequency_days:
                        recommendations.append(
                            {
                                "strategy_id": strategy.get("id"),
                                "action": "hyperopt",
                                "reason": f"Last hyperopt {days_since} days ago",
                                "priority": "low",
                            }
                        )

        return recommendations

    def evaluate_strategy_sync(self, strategy: Dict) -> StrategyHealth:
        """Synchronous version of evaluate_strategy."""
        # Simplified synchronous evaluation
        strategy_id = strategy.get("id")
        perf = strategy.get("performance", {})

        health = StrategyHealth(
            strategy_id=strategy_id,
            strategy_name=strategy.get("name", strategy_id[:8]),
            state=StrategyState(strategy.get("status", "stopped")),
            health_score=self._calculate_health_score(
                StrategyHealth(
                    strategy_id=strategy_id,
                    strategy_name=strategy.get("name", strategy_id[:8]),
                    state=StrategyState(strategy.get("status", "stopped")),
                    health_score=0,
                    total_trades=len(strategy.get("trades", [])),
                    win_rate=perf.get("win_rate", 0),
                    sharpe_ratio=perf.get("sharpe", 0),
                    max_drawdown=perf.get("max_drawdown", 0),
                    profit_pct=perf.get("profit_pct", 0),
                    days_running=0,
                )
            ),
            total_trades=len(strategy.get("trades", [])),
            win_rate=perf.get("win_rate", 0),
            sharpe_ratio=perf.get("sharpe", 0),
            max_drawdown=perf.get("max_drawdown", 0),
            profit_pct=perf.get("profit_pct", 0),
            days_running=0,
        )

        return health


# Add to_dict method to StrategyHealth
def strategy_health_to_dict(self) -> Dict:
    return {
        "strategy_id": self.strategy_id,
        "strategy_name": self.strategy_name,
        "state": self.state.value,
        "health_score": self.health_score,
        "total_trades": self.total_trades,
        "win_rate": self.win_rate,
        "sharpe_ratio": self.sharpe_ratio,
        "max_drawdown": self.max_drawdown,
        "profit_pct": self.profit_pct,
        "days_running": self.days_running,
        "issues": self.issues,
        "recommendations": self.recommendations,
    }


StrategyHealth.to_dict = strategy_health_to_dict
