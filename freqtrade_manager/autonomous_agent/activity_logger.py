"""
Activity Logger - Real-time logging for autonomous agent activities.

Provides live activity stream for research, analysis, and other agent actions.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from collections import deque
import threading

logger = logging.getLogger(__name__)


class ActivityType(Enum):
    """Types of activities."""
    RESEARCH_START = "research_start"
    RESEARCH_PROGRESS = "research_progress"
    RESEARCH_FINDING = "research_finding"
    RESEARCH_COMPLETE = "research_complete"
    ANALYSIS_START = "analysis_start"
    ANALYSIS_PROGRESS = "analysis_progress"
    ANALYSIS_COMPLETE = "analysis_complete"
    DECISION_MADE = "decision_made"
    HYPEROPT_START = "hyperopt_start"
    HYPEROPT_PROGRESS = "hyperopt_progress"
    HYPEROPT_EPOCH = "hyperopt_epoch"
    HYPEROPT_COMPLETE = "hyperopt_complete"
    ERROR = "error"
    INFO = "info"


@dataclass
class ActivityEvent:
    """A single activity event."""
    id: str
    activity_type: ActivityType
    agent: str
    title: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    progress: Optional[float] = None  # 0.0 to 1.0 for progress events

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "activity_type": self.activity_type.value,
            "agent": self.agent,
            "title": self.title,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "progress": self.progress,
        }


class ActivityLogger:
    """
    Singleton activity logger for streaming agent activities.

    Stores recent activity events and broadcasts to subscribers.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._events: deque = deque(maxlen=500)  # Keep last 500 events
        self._subscribers: List[Callable] = []
        self._event_counter = 0
        self._lock = threading.Lock()

    def subscribe(self, callback: Callable):
        """Subscribe to activity events."""
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable):
        """Unsubscribe from activity events."""
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def log(
        self,
        activity_type: ActivityType,
        agent: str,
        title: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        progress: Optional[float] = None,
    ) -> ActivityEvent:
        """
        Log an activity event.

        Args:
            activity_type: Type of activity
            agent: Agent that generated this activity
            title: Short title
            message: Detailed message
            details: Optional additional details
            progress: Optional progress value (0.0 to 1.0)

        Returns:
            The created activity event
        """
        with self._lock:
            self._event_counter += 1
            event_id = f"act_{self._event_counter:06d}"

            event = ActivityEvent(
                id=event_id,
                activity_type=activity_type,
                agent=agent,
                title=title,
                message=message,
                details=details or {},
                progress=progress,
            )

            self._events.append(event)

            # Broadcast to subscribers
            event_dict = event.to_dict()
            for callback in self._subscribers:
                try:
                    callback(event_dict)
                except Exception as e:
                    logger.error(f"Activity subscriber error: {e}")

            logger.debug(f"Activity: [{activity_type.value}] {agent}: {title}")
            return event

    def get_recent_events(
        self,
        limit: int = 50,
        agent: Optional[str] = None,
        activity_type: Optional[ActivityType] = None,
        since: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get recent activity events.

        Args:
            limit: Maximum number of events
            agent: Filter by agent
            activity_type: Filter by activity type
            since: Only events after this time

        Returns:
            List of event dictionaries
        """
        with self._lock:
            events = list(self._events)

        # Apply filters
        if agent:
            events = [e for e in events if e.agent == agent]
        if activity_type:
            events = [e for e in events if e.activity_type == activity_type]
        if since:
            events = [e for e in events if e.timestamp > since]

        # Sort by timestamp descending
        events.sort(key=lambda e: e.timestamp, reverse=True)

        # Limit
        events = events[:limit]

        return [e.to_dict() for e in events]

    def get_events_by_research_id(self, research_id: str) -> List[Dict[str, Any]]:
        """Get all events for a specific research run."""
        with self._lock:
            events = [
                e for e in self._events
                if e.details.get("research_id") == research_id
            ]

        events.sort(key=lambda e: e.timestamp)
        return [e.to_dict() for e in events]

    def clear_old_events(self, max_age_hours: int = 24):
        """Clear events older than specified hours."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)

        with self._lock:
            self._events = deque(
                (e for e in self._events if e.timestamp > cutoff),
                maxlen=500
            )


# Convenience functions for common activity types
def log_research_start(
    agent: str,
    research_id: str,
    research_type: str,
    strategy: str,
    hypothesis: str,
) -> ActivityEvent:
    """Log research start event."""
    activity_logger = ActivityLogger()
    return activity_logger.log(
        activity_type=ActivityType.RESEARCH_START,
        agent=agent,
        title=f"Starting {research_type} research",
        message=f"Researching: {hypothesis}",
        details={
            "research_id": research_id,
            "research_type": research_type,
            "strategy": strategy,
            "hypothesis": hypothesis,
        },
        progress=0.0,
    )


def log_research_progress(
    agent: str,
    research_id: str,
    phase: str,
    message: str,
    progress: float,
    details: Optional[Dict] = None,
) -> ActivityEvent:
    """Log research progress event."""
    activity_logger = ActivityLogger()
    full_details = {
        "research_id": research_id,
        "phase": phase,
        **(details or {}),
    }
    return activity_logger.log(
        activity_type=ActivityType.RESEARCH_PROGRESS,
        agent=agent,
        title=f"Research: {phase}",
        message=message,
        details=full_details,
        progress=progress,
    )


def log_research_finding(
    agent: str,
    research_id: str,
    finding_type: str,
    summary: str,
    confidence: float,
) -> ActivityEvent:
    """Log a research finding."""
    activity_logger = ActivityLogger()
    return activity_logger.log(
        activity_type=ActivityType.RESEARCH_FINDING,
        agent=agent,
        title=f"Finding: {finding_type}",
        message=summary,
        details={
            "research_id": research_id,
            "finding_type": finding_type,
            "confidence": confidence,
        },
    )


def log_research_complete(
    agent: str,
    research_id: str,
    result: str,
    improvement: Optional[float] = None,
) -> ActivityEvent:
    """Log research completion."""
    activity_logger = ActivityLogger()
    details = {
        "research_id": research_id,
        "result": result,
    }
    if improvement is not None:
        details["improvement"] = improvement

    return activity_logger.log(
        activity_type=ActivityType.RESEARCH_COMPLETE,
        agent=agent,
        title="Research complete",
        message=result,
        details=details,
        progress=1.0,
    )


def log_hyperopt_epoch(
    agent: str,
    research_id: str,
    epoch: int,
    total_epochs: int,
    best_score: float,
    current_params: Dict,
) -> ActivityEvent:
    """Log hyperopt epoch completion."""
    activity_logger = ActivityLogger()
    return activity_logger.log(
        activity_type=ActivityType.HYPEROPT_EPOCH,
        agent=agent,
        title=f"Epoch {epoch}/{total_epochs}",
        message=f"Best score: {best_score:.4f}",
        details={
            "research_id": research_id,
            "epoch": epoch,
            "total_epochs": total_epochs,
            "best_score": best_score,
            "current_params": current_params,
        },
        progress=epoch / total_epochs,
    )


def log_error(
    agent: str,
    error_type: str,
    message: str,
    details: Optional[Dict] = None,
) -> ActivityEvent:
    """Log an error event."""
    activity_logger = ActivityLogger()
    return activity_logger.log(
        activity_type=ActivityType.ERROR,
        agent=agent,
        title=f"Error: {error_type}",
        message=message,
        details=details or {},
    )