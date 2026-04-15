"""
Risk Agent - Monitors and manages portfolio risk.

Responsibilities:
- Drawdown monitoring
- Position sizing
- Exposure tracking
- VaR calculations
- Circuit breaker triggers
- Risk alerts
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .knowledge_graph import KnowledgeGraph, AgentDecision

logger = logging.getLogger(__name__)


@dataclass
class RiskLimits:
    """Risk limits configuration."""
    max_portfolio_drawdown: float = 15.0  # % of portfolio
    max_position_size_pct: float = 10.0  # % per trade
    max_correlated_positions: int = 3
    max_daily_loss_pct: float = 5.0
    max_strategy_drawdown: float = 20.0  # % per strategy
    var_confidence: float = 0.95
    var_limit_pct: float = 5.0  # Daily VaR limit


@dataclass
class Position:
    """Position information."""
    strategy_id: str
    pair: str
    size: float
    entry_price: float
    current_price: float
    profit_pct: float
    duration_hours: float
    exposure_pct: float  # % of portfolio


@dataclass
class RiskReport:
    """Comprehensive risk assessment."""
    timestamp: str
    portfolio_drawdown: float
    daily_pnl: float
    total_exposure: float
    positions_at_risk: List[Dict]
    var_estimate: float
    risk_score: float  # 0-100
    alerts: List[Dict]
    recommendations: List[str]
    circuit_breaker_triggered: bool
    circuit_breaker_reason: Optional[str] = None


@dataclass
class RiskMetrics:
    """Individual risk metrics."""
    name: str
    value: float
    threshold: float
    status: str  # "ok", "warning", "critical"
    description: str


class RiskAgent:
    """
    Agent that monitors and manages portfolio risk.

    Responsibilities:
    - Monitor drawdown across portfolio
    - Track position exposure
    - Calculate Value at Risk
    - Adjust position sizes dynamically
    - Trigger circuit breakers
    - Generate risk alerts
    """

    def __init__(
        self,
        db_path: str,
        knowledge_graph: KnowledgeGraph,
        config: Optional[RiskLimits] = None,
        notification_callback=None,
    ):
        self.db_path = db_path
        self.kg = knowledge_graph
        self.config = config or RiskLimits()
        self.notification_callback = notification_callback

        self._position_history: List[Dict] = []
        self._last_drawdown: float = 0.0
        self._circuit_breaker_active: bool = False
        self._circuit_breaker_until: Optional[datetime] = None

    async def check_portfolio_risk(
        self,
        strategies: List[Dict],
        portfolio_summary: Dict,
    ) -> Dict[str, Any]:
        """
        Perform comprehensive portfolio risk check.

        Returns a RiskReport with all metrics and recommendations.
        """
        report = RiskReport(
            timestamp=datetime.utcnow().isoformat(),
            portfolio_drawdown=0.0,
            daily_pnl=0.0,
            total_exposure=0.0,
            positions_at_risk=[],
            var_estimate=0.0,
            risk_score=0.0,
            alerts=[],
            recommendations=[],
            circuit_breaker_triggered=False,
        )

        # Get open positions
        positions = self._get_all_positions(strategies)

        # Calculate portfolio drawdown
        report.portfolio_drawdown = self._calculate_portfolio_drawdown(portfolio_summary)

        # Calculate daily P&L
        report.daily_pnl = portfolio_summary.get("daily_pnl", 0)

        # Calculate total exposure
        report.total_exposure = self._calculate_total_exposure(positions, portfolio_summary)

        # Find positions at risk
        report.positions_at_risk = self._identify_risky_positions(positions, portfolio_summary)

        # Calculate VaR
        report.var_estimate = self._calculate_var(strategies)

        # Check circuit breakers
        report.circuit_breaker_triggered, reason = self._check_circuit_breakers(
            report, portfolio_summary
        )
        report.circuit_breaker_reason = reason

        # Calculate risk score
        report.risk_score = self._calculate_risk_score(report)

        # Generate alerts
        report.alerts = self._generate_alerts(report)

        # Generate recommendations
        report.recommendations = self._generate_recommendations(report)

        # Log to knowledge graph
        self._log_risk_check(report)

        return report.to_dict()

    def _get_all_positions(self, strategies: List[Dict]) -> List[Position]:
        """Get all open positions from running strategies."""
        positions = []

        for strategy in strategies:
            if strategy.get("status") != "running":
                continue

            # Get positions from strategy data
            strategy_positions = strategy.get("positions", [])

            for pos_data in strategy_positions:
                position = Position(
                    strategy_id=strategy.get("id"),
                    pair=pos_data.get("pair", ""),
                    size=pos_data.get("size", 0),
                    entry_price=pos_data.get("entry_price", 0),
                    current_price=pos_data.get("current_price", 0),
                    profit_pct=pos_data.get("profit_pct", 0),
                    duration_hours=pos_data.get("duration_hours", 0),
                    exposure_pct=pos_data.get("exposure_pct", 0),
                )
                positions.append(position)

        return positions

    def _calculate_portfolio_drawdown(self, portfolio_summary: Dict) -> float:
        """Calculate current portfolio drawdown."""
        # Get from portfolio summary
        drawdown = portfolio_summary.get("drawdown_pct", 0)

        # Also track from position history
        if "positions_history" in portfolio_summary:
            recent = portfolio_summary["positions_history"][-100:]
            if recent:
                peak = max(p.get("total_value", 0) for p in recent)
                current = recent[-1].get("total_value", 0)
                if peak > 0:
                    drawdown = max(drawdown, (peak - current) / peak * 100)

        return drawdown

    def _calculate_total_exposure(self, positions: List[Position], portfolio_summary: Dict) -> float:
        """Calculate total portfolio exposure."""
        total_value = portfolio_summary.get("total_value", 10000)
        total_exposure = sum(p.size * p.current_price for p in positions)
        return total_exposure / total_value * 100

    def _identify_risky_positions(self, positions: List[Position], portfolio_summary: Dict) -> List[Dict]:
        """Identify positions that exceed risk thresholds."""
        risky = []

        for pos in positions:
            risk_factors = []

            # Check position size
            if pos.exposure_pct > self.config.max_position_size_pct:
                risk_factors.append(f"Position size {pos.exposure_pct:.1f}% exceeds limit")

            # Check drawdown
            if pos.profit_pct < -10:
                risk_factors.append(f"Position loss {pos.profit_pct:.1f}%")

            # Check duration (holding too long)
            if pos.duration_hours > 72:
                risk_factors.append(f"Long duration: {pos.duration_hours:.0f} hours")

            if risk_factors:
                risky.append({
                    "strategy_id": pos.strategy_id,
                    "pair": pos.pair,
                    "profit_pct": pos.profit_pct,
                    "exposure_pct": pos.exposure_pct,
                    "duration_hours": pos.duration_hours,
                    "risk_factors": risk_factors,
                })

        return risky

    def _calculate_var(self, strategies: List[Dict]) -> float:
        """Calculate Value at Risk estimate."""
        # Simplified VaR calculation
        # In production, this would use historical returns distribution

        # Get recent P&L history
        returns = []
        for strategy in strategies:
            pnl_history = strategy.get("pnl_history", [])
            returns.extend(pnl_history)

        if len(returns) < 10:
            return 0.0

        # Calculate VaR at confidence level
        import statistics

        mean_return = statistics.mean(returns)
        std_return = statistics.stdev(returns) if len(returns) > 1 else 0

        # VaR = mean - z * std (for confidence level)
        # For 95% confidence, z = 1.65
        z_score = 1.65 if self.config.var_confidence == 0.95 else 1.96
        var = abs(mean_return - z_score * std_return)

        return min(var, self.config.var_limit_pct)

    def _check_circuit_breakers(self, report: RiskReport, portfolio_summary: Dict) -> tuple:
        """Check if any circuit breakers should be triggered."""
        reasons = []

        # Portfolio drawdown circuit breaker
        if report.portfolio_drawdown > self.config.max_portfolio_drawdown:
            reasons.append(f"Portfolio drawdown {report.portfolio_drawdown:.1f}% exceeds limit {self.config.max_portfolio_drawdown}%")

        # Daily loss circuit breaker
        daily_loss_pct = abs(report.daily_pnl) / max(portfolio_summary.get("total_value", 1), 1) * 100
        if daily_loss_pct > self.config.max_daily_loss_pct:
            reasons.append(f"Daily loss {daily_loss_pct:.1f}% exceeds limit {self.config.max_daily_loss_pct}%")

        # VaR circuit breaker
        if report.var_estimate > self.config.var_limit_pct:
            reasons.append(f"VaR {report.var_estimate:.1f}% exceeds limit {self.config.var_limit_pct}%")

        # Check if already in circuit breaker cooldown
        if self._circuit_breaker_active:
            if self._circuit_breaker_until and datetime.utcnow() < self._circuit_breaker_until:
                return True, f"Circuit breaker active until {self._circuit_breaker_until}"
            else:
                self._circuit_breaker_active = False
                self._circuit_breaker_until = None

        if reasons:
            # Activate circuit breaker for 1 hour
            self._circuit_breaker_active = True
            self._circuit_breaker_until = datetime.utcnow() + timedelta(hours=1)
            return True, "; ".join(reasons)

        return False, None

    def _calculate_risk_score(self, report: RiskReport) -> float:
        """Calculate overall risk score (0-100, higher is riskier)."""
        score = 0.0

        # Drawdown contribution
        if report.portfolio_drawdown > 10:
            score += 40
        elif report.portfolio_drawdown > 5:
            score += 20
        elif report.portfolio_drawdown > 0:
            score += 10

        # Exposure contribution
        if report.total_exposure > 50:
            score += 20
        elif report.total_exposure > 30:
            score += 10

        # Risky positions contribution
        if len(report.positions_at_risk) > 3:
            score += 20
        elif len(report.positions_at_risk) > 0:
            score += 10

        # VaR contribution
        if report.var_estimate > 5:
            score += 20
        elif report.var_estimate > 3:
            score += 10

        return min(100, score)

    def _generate_alerts(self, report: RiskReport) -> List[Dict]:
        """Generate risk alerts based on report."""
        alerts = []

        # Drawdown alert
        if report.portfolio_drawdown > self.config.max_portfolio_drawdown * 0.8:
            alerts.append({
                "level": "critical" if report.portfolio_drawdown >= self.config.max_portfolio_drawdown else "warning",
                "type": "drawdown",
                "message": f"Portfolio drawdown at {report.portfolio_drawdown:.1f}%",
                "threshold": self.config.max_portfolio_drawdown,
                "recommendation": "Consider reducing position sizes",
            })

        # Daily loss alert
        if report.daily_pnl < 0:
            loss_pct = abs(report.daily_pnl) / 100
            if loss_pct > self.config.max_daily_loss_pct * 0.5:
                alerts.append({
                    "level": "warning" if loss_pct < self.config.max_daily_loss_pct else "critical",
                    "type": "daily_loss",
                    "message": f"Daily loss: ${abs(report.daily_pnl):.2f}",
                    "recommendation": "Review open positions",
                })

        # Position risk alerts
        for pos in report.positions_at_risk:
            alerts.append({
                "level": "warning",
                "type": "position_risk",
                "message": f"Risky position: {pos['pair']} ({pos['profit_pct']:.1f}%)",
                "details": pos["risk_factors"],
                "recommendation": "Consider closing or reducing position",
            })

        # VaR alert
        if report.var_estimate > self.config.var_limit_pct * 0.8:
            alerts.append({
                "level": "warning",
                "type": "var",
                "message": f"VaR at {report.var_estimate:.1f}%",
                "threshold": self.config.var_limit_pct,
                "recommendation": "Reduce overall exposure",
            })

        return alerts

    def _generate_recommendations(self, report: RiskReport) -> List[str]:
        """Generate risk management recommendations."""
        recommendations = []

        if report.circuit_breaker_triggered:
            recommendations.append("CRITICAL: Circuit breaker triggered. All new trades paused.")

        if report.portfolio_drawdown > 5:
            recommendations.append(f"Reduce position sizes by {(report.portfolio_drawdown / 10 * 100):.0f}%")

        if report.total_exposure > 40:
            recommendations.append(f"Total exposure at {report.total_exposure:.1f}%. Consider reducing.")

        for pos in report.positions_at_risk:
            if pos["profit_pct"] < -10:
                recommendations.append(f"Close {pos['pair']} position - significant loss")

        if len(report.positions_at_risk) > 2:
            recommendations.append("Multiple risky positions detected. Review all open trades.")

        if report.risk_score > 70:
            recommendations.append("Overall risk HIGH. Consider reducing all positions by 50%.")

        return recommendations

    def _log_risk_check(self, report: RiskReport):
        """Log risk check to knowledge graph."""
        decision = AgentDecision(
            id=f"risk_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            agent_type="risk",
            decision_type="risk_check",
            context={
                "portfolio_drawdown": report.portfolio_drawdown,
                "total_exposure": report.total_exposure,
                "risk_score": report.risk_score,
                "alerts": len(report.alerts),
                "recommendations": report.recommendations,
            },
            reasoning_chain=[
                f"Portfolio drawdown: {report.portfolio_drawdown:.2f}%",
                f"Total exposure: {report.total_exposure:.2f}%",
                f"VaR estimate: {report.var_estimate:.2f}%",
                f"Risk score: {report.risk_score}",
            ],
            conclusion=f"Risk check: {'CRITICAL' if report.circuit_breaker_triggered else 'OK'}",
            confidence=0.95,
        )

        self.kg.log_decision(decision)

    async def get_position_sizing(
        self,
        strategy_id: str,
        pair: str,
        portfolio_value: float,
        current_positions: List[Position],
    ) -> Dict[str, float]:
        """Calculate appropriate position size based on risk limits."""
        # Count correlated positions
        correlated_count = sum(1 for p in current_positions if p.pair == pair)

        # Check exposure limits
        total_exposure = sum(p.exposure_pct for p in current_positions)

        # Calculate max position size
        max_size_pct = self.config.max_position_size_pct

        # Reduce if correlated positions exist
        if correlated_count >= self.config.max_correlated_positions:
            return {
                "allowed": False,
                "reason": f"Too many correlated positions ({correlated_count})",
                "max_size_pct": 0,
            }

        # Reduce if total exposure is high
        if total_exposure > 50:
            max_size_pct *= 0.5  # Reduce by half if exposure is high

        # Calculate dollar amount
        max_size_usd = portfolio_value * (max_size_pct / 100)

        return {
            "allowed": True,
            "max_size_pct": max_size_pct,
            "max_size_usd": max_size_usd,
            "current_exposure": total_exposure,
            "correlated_positions": correlated_count,
        }

    def get_risk_metrics(self) -> List[RiskMetrics]:
        """Get all current risk metrics."""
        return [
            RiskMetrics(
                name="Portfolio Drawdown",
                value=self._last_drawdown,
                threshold=self.config.max_portfolio_drawdown,
                status="critical" if self._last_drawdown >= self.config.max_portfolio_drawdown else "warning" if self._last_drawdown >= self.config.max_portfolio_drawdown * 0.8 else "ok",
                description="Current drawdown as percentage of portfolio",
            ),
            RiskMetrics(
                name="Max Position Size",
                value=self.config.max_position_size_pct,
                threshold=self.config.max_position_size_pct,
                status="ok",
                description="Maximum allowed position size as % of portfolio",
            ),
            RiskMetrics(
                name="VaR Limit",
                value=0.0,  # Would be calculated
                threshold=self.config.var_limit_pct,
                status="ok",
                description="Value at Risk at 95% confidence",
            ),
        ]


# Add to_dict method to RiskReport
def risk_report_to_dict(self) -> Dict:
    return {
        "timestamp": self.timestamp,
        "portfolio_drawdown": self.portfolio_drawdown,
        "daily_pnl": self.daily_pnl,
        "total_exposure": self.total_exposure,
        "positions_at_risk": self.positions_at_risk,
        "var_estimate": self.var_estimate,
        "risk_score": self.risk_score,
        "alerts": self.alerts,
        "recommendations": self.recommendations,
        "circuit_breaker_triggered": self.circuit_breaker_triggered,
        "circuit_breaker_reason": self.circuit_breaker_reason,
    }

RiskReport.to_dict = risk_report_to_dict