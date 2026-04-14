"""
Knowledge Graph - Persistent memory for autonomous agents.

Stores entities, relationships, research findings, and decision history.
Implements memory decay for stale information and semantic search.
"""

import json
import logging
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import uuid

logger = logging.getLogger(__name__)


class EntityType(Enum):
    STRATEGY = "strategy"
    MARKET_REGIME = "market_regime"
    FINDING = "finding"
    DECISION = "decision"
    TRADE = "trade"
    HYPEROPT_RESULT = "hyperopt_result"
    BACKTEST_RESULT = "backtest_result"
    NEWS_EVENT = "news_event"
    SENTIMENT_DATA = "sentiment_data"
    ON_CHAIN_DATA = "on_chain_data"
    PERFORMANCE_METRIC = "performance_metric"


class RelationType(Enum):
    LED_TO = "led_to"
    CAUSED = "caused"
    CORRELATES_WITH = "correlates_with"
    IMPROVES = "improves"
    DEGRADES = "degrades"
    APPLIES_TO = "applies_to"
    DERIVED_FROM = "derived_from"
    SUPERSEDES = "supersedes"
    RELATES_TO = "relates_to"


@dataclass
class Entity:
    """A knowledge graph entity."""
    id: str
    entity_type: EntityType
    data: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    confidence: float = 1.0
    decay_rate: float = 0.01  # Confidence decay per day
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "entity_type": self.entity_type.value,
            "data": self.data,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "confidence": self.confidence,
            "decay_rate": self.decay_rate,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Entity":
        return cls(
            id=data["id"],
            entity_type=EntityType(data["entity_type"]),
            data=data["data"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]),
            confidence=data["confidence"],
            decay_rate=data["decay_rate"],
            tags=data.get("tags", []),
        )


@dataclass
class Relation:
    """A relationship between entities."""
    id: str
    from_entity: str
    to_entity: str
    relation_type: RelationType
    weight: float = 1.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "from_entity": self.from_entity,
            "to_entity": self.to_entity,
            "relation_type": self.relation_type.value,
            "weight": self.weight,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class ResearchFinding:
    """A research finding from external data sources."""
    id: str
    source: str  # 'news', 'sentiment', 'onchain', 'backtest', 'hyperopt'
    finding_type: str
    title: str
    content: str
    sentiment: float  # -1 to 1
    relevance: float  # 0 to 1
    impact_assessment: Dict[str, Any]
    entities: List[str]  # Related strategy/asset IDs
    confidence: float
    created_at: datetime = field(default_factory=datetime.utcnow)
    applied_at: Optional[datetime] = None
    applied_to_strategy: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "source": self.source,
            "finding_type": self.finding_type,
            "title": self.title,
            "content": self.content,
            "sentiment": self.sentiment,
            "relevance": self.relevance,
            "impact_assessment": self.impact_assessment,
            "entities": self.entities,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "applied_to_strategy": self.applied_to_strategy,
            "metadata": self.metadata,
        }


@dataclass
class AgentDecision:
    """A decision made by an autonomous agent."""
    id: str
    agent_type: str  # 'orchestrator', 'research', 'analysis', 'risk', 'strategy'
    decision_type: str
    context: Dict[str, Any]
    reasoning_chain: List[str]
    conclusion: str
    confidence: float
    action_taken: Optional[str] = None
    outcome: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    requires_approval: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "decision_type": self.decision_type,
            "context": self.context,
            "reasoning_chain": self.reasoning_chain,
            "conclusion": self.conclusion,
            "confidence": self.confidence,
            "action_taken": self.action_taken,
            "outcome": self.outcome,
            "created_at": self.created_at.isoformat(),
            "requires_approval": self.requires_approval,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
        }


class KnowledgeGraph:
    """
    SQLite-backed knowledge graph for autonomous agent memory.

    Features:
    - Entity storage with confidence decay
    - Relationship tracking
    - Research finding persistence
    - Decision logging with reasoning chains
    - Semantic search across knowledge
    """

    def __init__(self, db_path: str = "/data/knowledge_graph.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Entities table
        c.execute("""
            CREATE TABLE IF NOT EXISTS kg_entities (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                decay_rate REAL DEFAULT 0.01,
                tags TEXT DEFAULT '[]'
            )
        """)

        # Relations table
        c.execute("""
            CREATE TABLE IF NOT EXISTS kg_relations (
                id TEXT PRIMARY KEY,
                from_entity TEXT NOT NULL,
                to_entity TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            )
        """)

        # Research findings table
        c.execute("""
            CREATE TABLE IF NOT EXISTS research_findings (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                finding_type TEXT NOT NULL,
                title TEXT,
                content TEXT NOT NULL,
                sentiment REAL DEFAULT 0.0,
                relevance REAL DEFAULT 0.5,
                impact_assessment TEXT DEFAULT '{}',
                entities TEXT DEFAULT '[]',
                confidence REAL DEFAULT 0.5,
                created_at TEXT NOT NULL,
                applied_at TEXT,
                applied_to_strategy TEXT,
                metadata TEXT DEFAULT '{}'
            )
        """)

        # Agent decisions table
        c.execute("""
            CREATE TABLE IF NOT EXISTS agent_decisions (
                id TEXT PRIMARY KEY,
                agent_type TEXT NOT NULL,
                decision_type TEXT NOT NULL,
                context TEXT DEFAULT '{}',
                reasoning_chain TEXT DEFAULT '[]',
                conclusion TEXT,
                confidence REAL DEFAULT 0.5,
                action_taken TEXT,
                outcome TEXT,
                created_at TEXT NOT NULL,
                requires_approval INTEGER DEFAULT 0,
                approved_by TEXT,
                approved_at TEXT
            )
        """)

        # Indexes for common queries
        c.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON kg_entities(entity_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_entities_created ON kg_entities(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_relations_from ON kg_relations(from_entity)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_relations_to ON kg_relations(to_entity)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_findings_source ON research_findings(source)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_findings_created ON research_findings(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_decisions_agent ON agent_decisions(agent_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_decisions_created ON agent_decisions(created_at)")

        conn.commit()
        conn.close()

    # ==================== Entity Operations ====================

    def add_entity(self, entity: Entity) -> str:
        """Add or update an entity."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            INSERT OR REPLACE INTO kg_entities
            (id, entity_type, data, created_at, last_accessed, confidence, decay_rate, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entity.id,
            entity.entity_type.value,
            json.dumps(entity.data),
            entity.created_at.isoformat(),
            entity.last_accessed.isoformat(),
            entity.confidence,
            entity.decay_rate,
            json.dumps(entity.tags),
        ))

        conn.commit()
        conn.close()
        return entity.id

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("SELECT * FROM kg_entities WHERE id = ?", (entity_id,))
        row = c.fetchone()
        conn.close()

        if row:
            # Update last_accessed
            self._update_access_time(entity_id)
            return Entity.from_dict(dict(row))
        return None

    def get_entities_by_type(self, entity_type: EntityType, limit: int = 100) -> List[Entity]:
        """Get all entities of a type."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("""
            SELECT * FROM kg_entities
            WHERE entity_type = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (entity_type.value, limit))

        rows = c.fetchall()
        conn.close()

        return [Entity.from_dict(dict(row)) for row in rows]

    def search_entities(self, query: str, entity_type: Optional[EntityType] = None, limit: int = 50) -> List[Entity]:
        """Search entities by content."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        search_pattern = f"%{query}%"

        if entity_type:
            c.execute("""
                SELECT * FROM kg_entities
                WHERE entity_type = ? AND (data LIKE ? OR tags LIKE ?)
                ORDER BY confidence DESC, created_at DESC
                LIMIT ?
            """, (entity_type.value, search_pattern, search_pattern, limit))
        else:
            c.execute("""
                SELECT * FROM kg_entities
                WHERE data LIKE ? OR tags LIKE ?
                ORDER BY confidence DESC, created_at DESC
                LIMIT ?
            """, (search_pattern, search_pattern, limit))

        rows = c.fetchall()
        conn.close()

        return [Entity.from_dict(dict(row)) for row in rows]

    def _update_access_time(self, entity_id: str):
        """Update last_accessed timestamp."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "UPDATE kg_entities SET last_accessed = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), entity_id)
        )
        conn.commit()
        conn.close()

    def decay_entities(self, days_old: int = 30):
        """Apply confidence decay to old entities."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        cutoff = datetime.utcnow() - timedelta(days=days_old)

        # Decay confidence
        c.execute("""
            UPDATE kg_entities
            SET confidence = confidence * (1 - decay_rate)
            WHERE created_at < ? AND confidence > 0.1
        """, (cutoff.isoformat(),))

        # Remove very low confidence entities
        c.execute("DELETE FROM kg_entities WHERE confidence < 0.1")

        conn.commit()
        conn.close()

    # ==================== Relation Operations ====================

    def add_relation(self, relation: Relation) -> str:
        """Add a relationship between entities."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            INSERT OR REPLACE INTO kg_relations
            (id, from_entity, to_entity, relation_type, weight, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            relation.id,
            relation.from_entity,
            relation.to_entity,
            relation.relation_type.value,
            relation.weight,
            relation.created_at.isoformat(),
            json.dumps(relation.metadata),
        ))

        conn.commit()
        conn.close()
        return relation.id

    def get_related_entities(
        self,
        entity_id: str,
        relation_type: Optional[RelationType] = None,
        direction: str = "both"  # "from", "to", "both"
    ) -> List[Tuple[Entity, Relation]]:
        """Get entities related to an entity."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        conditions = []
        params = []

        if direction in ("from", "both"):
            conditions.append("from_entity = ?")
            params.append(entity_id)
        if direction in ("to", "both"):
            conditions.append("to_entity = ?")
            params.append(entity_id)

        query = f"""
            SELECT r.*, e.id as entity_id, e.entity_type, e.data, e.confidence
            FROM kg_relations r
            JOIN kg_entities e ON (e.id = r.from_entity OR e.id = r.to_entity)
            WHERE ({' OR '.join(conditions)}) AND e.id != ?
        """
        params.append(entity_id)

        if relation_type:
            query += " AND r.relation_type = ?"
            params.append(relation_type.value)

        c.execute(query, params)
        rows = c.fetchall()
        conn.close()

        results = []
        for row in rows:
            entity = Entity(
                id=row["entity_id"],
                entity_type=EntityType(row["entity_type"]),
                data=json.loads(row["data"]),
                confidence=row["confidence"],
            )
            relation = Relation(
                id=row["id"],
                from_entity=row["from_entity"],
                to_entity=row["to_entity"],
                relation_type=RelationType(row["relation_type"]),
                weight=row["weight"],
            )
            results.append((entity, relation))

        return results

    # ==================== Research Finding Operations ====================

    def add_finding(self, finding: ResearchFinding) -> str:
        """Add a research finding."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            INSERT INTO research_findings
            (id, source, finding_type, title, content, sentiment, relevance,
             impact_assessment, entities, confidence, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            finding.id,
            finding.source,
            finding.finding_type,
            finding.title,
            finding.content,
            finding.sentiment,
            finding.relevance,
            json.dumps(finding.impact_assessment),
            json.dumps(finding.entities),
            finding.confidence,
            finding.created_at.isoformat(),
            json.dumps(finding.metadata),
        ))

        conn.commit()
        conn.close()
        return finding.id

    def get_findings(
        self,
        source: Optional[str] = None,
        finding_type: Optional[str] = None,
        since: Optional[datetime] = None,
        min_confidence: float = 0.0,
        limit: int = 100
    ) -> List[ResearchFinding]:
        """Get research findings with filters."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        conditions = []
        params = []

        if source:
            conditions.append("source = ?")
            params.append(source)
        if finding_type:
            conditions.append("finding_type = ?")
            params.append(finding_type)
        if since:
            conditions.append("created_at >= ?")
            params.append(since.isoformat())

        conditions.append("confidence >= ?")
        params.append(min_confidence)

        query = f"""
            SELECT * FROM research_findings
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(limit)

        c.execute(query, params)
        rows = c.fetchall()
        conn.close()

        return [self._row_to_finding(row) for row in rows]

    def get_unapplied_findings(self, limit: int = 50) -> List[ResearchFinding]:
        """Get findings that haven't been applied yet."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("""
            SELECT * FROM research_findings
            WHERE applied_at IS NULL
            ORDER BY confidence DESC, created_at DESC
            LIMIT ?
        """, (limit,))

        rows = c.fetchall()
        conn.close()

        return [self._row_to_finding(row) for row in rows]

    def mark_finding_applied(self, finding_id: str, strategy_id: str):
        """Mark a finding as applied to a strategy."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            UPDATE research_findings
            SET applied_at = ?, applied_to_strategy = ?
            WHERE id = ?
        """, (datetime.utcnow().isoformat(), strategy_id, finding_id))

        conn.commit()
        conn.close()

    def _row_to_finding(self, row) -> ResearchFinding:
        """Convert database row to ResearchFinding."""
        return ResearchFinding(
            id=row["id"],
            source=row["source"],
            finding_type=row["finding_type"],
            title=row["title"],
            content=row["content"],
            sentiment=row["sentiment"],
            relevance=row["relevance"],
            impact_assessment=json.loads(row["impact_assessment"]),
            entities=json.loads(row["entities"]),
            confidence=row["confidence"],
            created_at=datetime.fromisoformat(row["created_at"]),
            applied_at=datetime.fromisoformat(row["applied_at"]) if row["applied_at"] else None,
            applied_to_strategy=row["applied_to_strategy"],
            metadata=json.loads(row["metadata"]),
        )

    # ==================== Decision Operations ====================

    def log_decision(self, decision: AgentDecision) -> str:
        """Log an agent decision with reasoning."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            INSERT INTO agent_decisions
            (id, agent_type, decision_type, context, reasoning_chain, conclusion,
             confidence, action_taken, outcome, created_at, requires_approval,
             approved_by, approved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            decision.id,
            decision.agent_type,
            decision.decision_type,
            json.dumps(decision.context),
            json.dumps(decision.reasoning_chain),
            decision.conclusion,
            decision.confidence,
            decision.action_taken,
            decision.outcome,
            decision.created_at.isoformat(),
            1 if decision.requires_approval else 0,
            decision.approved_by,
            decision.approved_at.isoformat() if decision.approved_at else None,
        ))

        conn.commit()
        conn.close()
        return decision.id

    def get_decisions(
        self,
        agent_type: Optional[str] = None,
        decision_type: Optional[str] = None,
        since: Optional[datetime] = None,
        requires_approval: Optional[bool] = None,
        limit: int = 100
    ) -> List[AgentDecision]:
        """Get decisions with filters."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        conditions = []
        params = []

        if agent_type:
            conditions.append("agent_type = ?")
            params.append(agent_type)
        if decision_type:
            conditions.append("decision_type = ?")
            params.append(decision_type)
        if since:
            conditions.append("created_at >= ?")
            params.append(since.isoformat())
        if requires_approval is not None:
            conditions.append("requires_approval = ?")
            params.append(1 if requires_approval else 0)

        query = f"""
            SELECT * FROM agent_decisions
            {f'WHERE {" AND ".join(conditions)}' if conditions else ''}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(limit)

        c.execute(query, params)
        rows = c.fetchall()
        conn.close()

        return [self._row_to_decision(row) for row in rows]

    def get_pending_approvals(self) -> List[AgentDecision]:
        """Get decisions pending approval."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("""
            SELECT * FROM agent_decisions
            WHERE requires_approval = 1 AND approved_at IS NULL
            ORDER BY created_at ASC
        """)

        rows = c.fetchall()
        conn.close()

        return [self._row_to_decision(row) for row in rows]

    def approve_decision(self, decision_id: str, approved_by: str = "user"):
        """Approve a pending decision."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            UPDATE agent_decisions
            SET approved_by = ?, approved_at = ?
            WHERE id = ? AND requires_approval = 1
        """, (approved_by, datetime.utcnow().isoformat(), decision_id))

        conn.commit()
        conn.close()

    def update_decision_outcome(self, decision_id: str, outcome: str):
        """Update the outcome of a decision."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            UPDATE agent_decisions
            SET outcome = ?
            WHERE id = ?
        """, (outcome, decision_id))

        conn.commit()
        conn.close()

    def _row_to_decision(self, row) -> AgentDecision:
        """Convert database row to AgentDecision."""
        return AgentDecision(
            id=row["id"],
            agent_type=row["agent_type"],
            decision_type=row["decision_type"],
            context=json.loads(row["context"]),
            reasoning_chain=json.loads(row["reasoning_chain"]),
            conclusion=row["conclusion"],
            confidence=row["confidence"],
            action_taken=row["action_taken"],
            outcome=row["outcome"],
            created_at=datetime.fromisoformat(row["created_at"]),
            requires_approval=bool(row["requires_approval"]),
            approved_by=row["approved_by"],
            approved_at=datetime.fromisoformat(row["approved_at"]) if row["approved_at"] else None,
        )

    # ==================== Summary & Stats ====================

    def get_summary(self) -> Dict[str, Any]:
        """Get knowledge graph statistics."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM kg_entities")
        entity_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM kg_relations")
        relation_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM research_findings")
        finding_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM research_findings WHERE applied_at IS NULL")
        unapplied_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM agent_decisions")
        decision_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM agent_decisions WHERE requires_approval = 1 AND approved_at IS NULL")
        pending_count = c.fetchone()[0]

        conn.close()

        return {
            "entity_count": entity_count,
            "relation_count": relation_count,
            "finding_count": finding_count,
            "unapplied_findings": unapplied_count,
            "decision_count": decision_count,
            "pending_approvals": pending_count,
        }

    def cleanup_old_data(self, days: int = 90):
        """Remove old, low-value data."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        # Remove old low-confidence entities
        c.execute("""
            DELETE FROM kg_entities
            WHERE created_at < ? AND confidence < 0.3
        """, (cutoff,))

        # Remove old decisions with no outcome
        c.execute("""
            DELETE FROM agent_decisions
            WHERE created_at < ? AND outcome IS NULL AND requires_approval = 0
        """, (cutoff,))

        conn.commit()
        conn.close()