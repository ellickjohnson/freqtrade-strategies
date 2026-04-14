"""
Decision Framework - Types and utilities for agent decisions.

Provides the DecisionEngine and related types for processing
agent decisions and approval workflows.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class DecisionType(Enum):
    """Types of decisions the autonomous agent can make."""
    CREATE_STRATEGY = "create_strategy"
    START_STRATEGY = "start_strategy"
    STOP_STRATEGY = "stop_strategy"
    DEPRECATE_STRATEGY = "deprecate_strategy"
    ADJUST_PARAMETERS = "adjust_parameters"
    RUN_HYPEROPT = "run_hyperopt"
    APPLY_RESEARCH = "apply_research"
    ALERT_USER = "alert_user"


class DecisionStatus(Enum):
    """Status of a decision."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


@dataclass
class Decision:
    """Represents an agent decision."""
    id: str
    decision_type: DecisionType
    agent_type: str
    context: Dict[str, Any]
    reasoning_chain: List[str] = field(default_factory=list)
    confidence: float = 0.5
    requires_approval: bool = True
    status: DecisionStatus = DecisionStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    approved_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    outcome: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert decision to dictionary."""
        return {
            "id": self.id,
            "decision_type": self.decision_type.value,
            "agent_type": self.agent_type,
            "context": self.context,
            "reasoning_chain": self.reasoning_chain,
            "confidence": self.confidence,
            "requires_approval": self.requires_approval,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "outcome": self.outcome,
            "metadata": self.metadata,
        }


class DecisionEngine:
    """
    Engine for processing agent decisions.

    Handles:
    - Decision validation
    - Approval workflow
    - Execution coordination
    - Rollback management
    """

    def __init__(self, db_path: str = "/data/dashboard.db"):
        self.db_path = db_path
        self._pending_approvals: Dict[str, Decision] = {}

    def create_decision(
        self,
        decision_type: DecisionType,
        agent_type: str,
        context: Dict[str, Any],
        reasoning_chain: List[str],
        confidence: float = 0.5,
        requires_approval: bool = True,
    ) -> Decision:
        """Create a new decision."""
        decision_id = f"{decision_type.value}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        decision = Decision(
            id=decision_id,
            decision_type=decision_type,
            agent_type=agent_type,
            context=context,
            reasoning_chain=reasoning_chain,
            confidence=confidence,
            requires_approval=requires_approval,
        )

        if requires_approval:
            self._pending_approvals[decision_id] = decision

        logger.info(f"Created decision: {decision_id} (requires_approval={requires_approval})")
        return decision

    def approve_decision(self, decision_id: str, reason: Optional[str] = None) -> Decision:
        """Approve a pending decision."""
        if decision_id not in self._pending_approvals:
            raise ValueError(f"Decision {decision_id} not found in pending approvals")

        decision = self._pending_approvals[decision_id]
        decision.status = DecisionStatus.APPROVED
        decision.approved_at = datetime.utcnow()

        if reason:
            decision.metadata["approval_reason"] = reason

        del self._pending_approvals[decision_id]
        logger.info(f"Approved decision: {decision_id}")

        return decision

    def reject_decision(self, decision_id: str, reason: str) -> Decision:
        """Reject a pending decision."""
        if decision_id not in self._pending_approvals:
            raise ValueError(f"Decision {decision_id} not found in pending approvals")

        decision = self._pending_approvals[decision_id]
        decision.status = DecisionStatus.REJECTED
        decision.metadata["rejection_reason"] = reason

        del self._pending_approvals[decision_id]
        logger.info(f"Rejected decision: {decision_id}")

        return decision

    def get_pending_approvals(self) -> List[Decision]:
        """Get all decisions pending approval."""
        return list(self._pending_approvals.values())

    def should_auto_approve(self, decision: Decision, auto_approve_threshold: float = 0.8) -> bool:
        """Determine if a decision should be auto-approved."""
        # High confidence decisions that don't require explicit approval
        if not decision.requires_approval:
            return True

        # Auto-approve if confidence is very high
        if decision.confidence >= auto_approve_threshold:
            return True

        return False