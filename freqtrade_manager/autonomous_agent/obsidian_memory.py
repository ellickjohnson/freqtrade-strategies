"""
Obsidian Memory Integration - Uses Obsidian vault for persistent agent memory.

This module integrates with the Obsidian vault for persistent agent memory storage
and retrieval. It uses the FilesystemMemoryBackend for actual file operations,
which works standalone without requiring MCP tools.

The vault path is configured via OBSIDIAN_VAULT_PATH environment variable.
Default: /home/ejohnson/Documents/Obsidian Vault

Stores:
- Agent decisions with reasoning chains
- Research findings from external data sources
- Strategy performance analyses
- Market regime observations
- Hyperopt results
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path

from .memory_backend import FilesystemMemoryBackend, SearchResult, get_memory_backend

logger = logging.getLogger(__name__)


class ObsidianMemory:
    """
    Integration with Obsidian vault for persistent agent memory.

    Stores agent decisions, research findings, and insights in Obsidian
    for human-readable persistent memory and searchability.

    Uses FilesystemMemoryBackend for actual file operations, which works
    standalone without requiring MCP tools.
    """

    def __init__(self, vault_path: Optional[str] = None):
        """
        Initialize Obsidian memory integration.

        Args:
            vault_path: Path to Obsidian vault. If None, uses OBSIDIAN_VAULT_PATH
                       environment variable or default path.
        """
        self.backend = get_memory_backend(vault_path)
        self.notes_folder = "Freqtrade Agent"
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Ensure the backend is initialized."""
        if not self._initialized:
            self._initialized = self.backend.ensure_folders()
        return self._initialized

    async def create_note(self, path: str, content: str) -> bool:
        """
        Create a note in Obsidian vault.

        Args:
            path: Relative path within vault
            content: Markdown content

        Returns:
            True if note was created successfully.
        """
        if not self._ensure_initialized():
            logger.error("Memory backend not initialized")
            return False

        return self.backend.create_note(path, content)

    async def search_memory(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Search memory in Obsidian vault.

        Uses filesystem search to find relevant notes.

        Args:
            query: Search query string
            limit: Maximum results

        Returns:
            List of matching notes as dicts.
        """
        if not self._ensure_initialized():
            return []

        results = self.backend.search_notes(query, limit)
        return [r.__dict__ for r in results]

    async def store_decision(self, decision: Dict) -> str:
        """
        Store an agent decision in Obsidian.

        Creates a formatted note with reasoning chain.

        Args:
            decision: Decision dict with id, decision_type, agent_type, etc.

        Returns:
            Path to created note.
        """
        if not self._ensure_initialized():
            return ""

        note_path = f"{self.notes_folder}/Decisions/{decision['id']}.md"
        content = self._format_decision_note(decision)

        success = self.backend.create_note(note_path, content)
        return note_path if success else ""

    async def store_research_finding(self, finding: Dict) -> str:
        """
        Store a research finding in Obsidian.

        Creates a note with source, analysis, and implications.

        Args:
            finding: Finding dict with id, source, title, content, etc.

        Returns:
            Path to created note.
        """
        if not self._ensure_initialized():
            return ""

        finding_id = finding.get('id', datetime.utcnow().strftime('%Y%m%d_%H%M%S'))
        note_path = f"{self.notes_folder}/Research/{finding_id}.md"
        content = self._format_research_note(finding)

        success = self.backend.create_note(note_path, content)
        return note_path if success else ""

    async def store_strategy_analysis(self, analysis: Dict) -> str:
        """
        Store strategy analysis in Obsidian.

        Creates a note with performance metrics and recommendations.

        Args:
            analysis: Analysis dict with strategy_id, metrics, etc.

        Returns:
            Path to created note.
        """
        if not self._ensure_initialized():
            return ""

        strategy_id = analysis.get('strategy_id', 'unknown')
        timestamp = analysis.get('timestamp', datetime.utcnow().isoformat())
        note_path = f"{self.notes_folder}/Analysis/{strategy_id}/{timestamp[:10]}.md"
        content = self._format_analysis_note(analysis)

        success = self.backend.create_note(note_path, content)
        return note_path if success else ""

    async def store_market_regime(self, regime: Dict) -> str:
        """
        Store market regime observation in Obsidian.

        Creates a note with regime type, confidence, and implications.

        Args:
            regime: Regime dict with regime_type, confidence, etc.

        Returns:
            Path to created note.
        """
        if not self._ensure_initialized():
            return ""

        date = regime.get('timestamp', datetime.utcnow().isoformat())[:10]
        note_path = f"{self.notes_folder}/Market Regimes/{date}.md"
        content = self._format_regime_note(regime)

        success = self.backend.create_note(note_path, content)
        return note_path if success else ""

    async def store_hyperopt_result(self, result: Dict) -> str:
        """
        Store hyperopt results in Obsidian.

        Args:
            result: Hyperopt result dict with hyperopt_id, strategy_id, etc.

        Returns:
            Path to created note.
        """
        if not self._ensure_initialized():
            return ""

        hyperopt_id = result.get('hyperopt_id', datetime.utcnow().strftime('%Y%m%d_%H%M%S'))
        note_path = f"{self.notes_folder}/Hyperopt/{hyperopt_id}.md"
        content = self._format_hyperopt_note(result)

        success = self.backend.create_note(note_path, content)
        return note_path if success else ""

    def _format_decision_note(self, decision: Dict) -> str:
        """Format decision as Obsidian note."""
        reasoning = "\n".join([f"  - {step}" for step in decision.get("reasoning_chain", [])])

        status_badge = "✅ Approved" if decision.get("approved_at") else (
            "⏳ Pending" if decision.get("requires_approval") else "✓ Executed"
        )

        # Build frontmatter
        frontmatter = "---\n"
        frontmatter += f"id: {decision.get('id', 'unknown')}\n"
        frontmatter += f"agent_type: {decision.get('agent_type', 'unknown')}\n"
        frontmatter += f"decision_type: {decision.get('decision_type', 'unknown')}\n"
        frontmatter += f"date: {decision.get('created_at', datetime.utcnow().isoformat())}\n"
        frontmatter += f"confidence: {decision.get('confidence', 0):.2f}\n"
        frontmatter += f"requires_approval: {decision.get('requires_approval', False)}\n"
        frontmatter += "---\n\n"

        return f"""{frontmatter}# Agent Decision: {decision['decision_type']}

**Agent:** {decision['agent_type']}
**Decision:** {decision['decision_type']}
**Confidence:** {decision.get('confidence', 0):.0%}
**Time:** {decision.get('created_at', datetime.utcnow().isoformat())}
**Requires Approval:** {'Yes' if decision.get('requires_approval') else 'No'}
**Status:** {status_badge}

## Reasoning Chain

{reasoning}

## Conclusion

{decision.get('conclusion', 'N/A')}

## Context

```json
{json.dumps(decision.get('context', {}), indent=2)}
```

## Outcome

{decision.get('outcome', 'Pending')}

---

#decision #{decision['agent_type']} #{decision['decision_type'].replace('_', '-')}
"""

    def _format_research_note(self, finding: Dict) -> str:
        """Format research finding as Obsidian note."""
        impact = json.dumps(finding.get('impact_assessment', {}), indent=2)
        entities = finding.get('entities', ['market-wide'])
        entities_md = ", ".join([f"[[{e}]]" for e in entities])

        status_badge = "✅ Applied" if finding.get('applied_at') else "⏳ Pending Application"

        # Build frontmatter
        frontmatter = "---\n"
        frontmatter += f"id: {finding.get('id', 'unknown')}\n"
        frontmatter += f"source: {finding.get('source', 'unknown')}\n"
        frontmatter += f"date: {finding.get('created_at', datetime.utcnow().isoformat())}\n"
        frontmatter += f"sentiment: {finding.get('sentiment', 0):.2f}\n"
        frontmatter += f"relevance: {finding.get('relevance', 0):.2f}\n"
        frontmatter += "---\n\n"

        return f"""{frontmatter}# Research Finding: {finding.get('title', 'Untitled')}

**Source:** [[{finding.get('source', 'unknown')}]]
**Type:** {finding.get('finding_type', 'general')}
**Sentiment:** {finding.get('sentiment', 0):.2f}
**Relevance:** {finding.get('relevance', 0):.2f}
**Confidence:** {finding.get('confidence', 0):.0%}
**Time:** {finding.get('created_at', datetime.utcnow().isoformat())}
**Status:** {status_badge}

## Summary

{finding.get('content', '')}

## Impact Assessment

```json
{impact}
```

## Affected Entities

{entities_md}

## Trading Implications

*To be analyzed...*

---

#research #{finding.get('source', 'unknown')} #{finding.get('finding_type', 'general')}
"""

    def _format_analysis_note(self, analysis: Dict) -> str:
        """Format strategy analysis as Obsidian note."""
        metrics = analysis.get('metrics', {})
        issues = analysis.get('issues', [])
        recommendations = analysis.get('recommendations', [])

        issues_md = "\n".join([f"- {i}" for i in issues]) if issues else "None identified"
        recommendations_md = "\n".join([f"- {r}" for r in recommendations]) if recommendations else "No specific recommendations"

        health_score = analysis.get('health_score', 0)
        health_emoji = "🟢" if health_score >= 70 else ("🟡" if health_score >= 40 else "🔴")

        # Build frontmatter
        frontmatter = "---\n"
        frontmatter += f"strategy_id: {analysis['strategy_id']}\n"
        frontmatter += f"health_score: {health_score}\n"
        frontmatter += f"date: {analysis.get('timestamp', datetime.utcnow().isoformat())}\n"
        frontmatter += "---\n\n"

        return f"""{frontmatter}# Strategy Analysis: {analysis.get('strategy_name', analysis['strategy_id'])}

**Strategy ID:** [[{analysis['strategy_id']}]]
**Health Score:** {health_emoji} {health_score:.0f}/100
**Time:** {analysis.get('timestamp', datetime.utcnow().isoformat())}

## Performance Metrics

| Metric | Value |
|--------|-------|
| Win Rate | {metrics.get('win_rate', 0):.1%} |
| Sharpe Ratio | {metrics.get('sharpe_ratio', 0):.2f} |
| Max Drawdown | {metrics.get('max_drawdown', 0):.1%} |
| Profit | {metrics.get('profit_pct', 0):.1f}% |
| Total Trades | {metrics.get('total_trades', 0)} |

## Market Regime

**Type:** {analysis.get('market_regime', {}).get('regime_type', 'unknown')}
**Confidence:** {analysis.get('market_regime', {}).get('confidence', 0):.0%}

## Issues

{issues_md}

## Recommendations

{recommendations_md}

---

#analysis #{analysis['strategy_id']}
"""

    def _format_regime_note(self, regime: Dict) -> str:
        """Format market regime as Obsidian note."""
        affected = ", ".join([f"[[{s}]]" for s in regime.get('affected_strategies', ['all'])])
        recommendations = "\n".join([f"- {r}" for r in regime.get('recommendations', [])])

        regime_type = regime.get('regime_type', 'unknown')
        regime_emoji = {
            'trending_up': '📈',
            'trending_down': '📉',
            'ranging': '↔️',
            'volatile': '⚡',
        }.get(regime_type, '❓')

        # Build frontmatter
        frontmatter = "---\n"
        frontmatter += f"regime_type: {regime_type}\n"
        frontmatter += f"date: {regime.get('timestamp', datetime.utcnow().isoformat())[:10]}\n"
        frontmatter += f"confidence: {regime.get('confidence', 0):.2f}\n"
        frontmatter += "---\n\n"

        return f"""{frontmatter}# Market Regime: {regime_emoji} {regime_type.replace('_', ' ').title()}

**Date:** {regime.get('timestamp', datetime.utcnow().isoformat())[:10]}
**Regime:** {regime_type}
**Confidence:** {regime.get('confidence', 0):.0%}

## Characteristics

```json
{json.dumps(regime.get('characteristics', {}), indent=2)}
```

## Affected Strategies

{affected}

## Trading Recommendations

{recommendations}

---

#market-regime #{regime_type}
"""

    def _format_hyperopt_note(self, result: Dict) -> str:
        """Format hyperopt result as Obsidian note."""
        best_params = result.get('best_params', {})
        metrics = result.get('metrics', {})

        params_md = "\n".join([f"- **{k}:** {v}" for k, v in best_params.items()]) if best_params else "No parameters found"
        metrics_md = "\n".join([f"- **{k}:** {v}" for k, v in metrics.items()]) if metrics else "No metrics available"

        status = result.get('status', 'unknown')
        status_emoji = "✅" if status == 'completed' else ("❌" if status == 'failed' else "🔄")

        # Build frontmatter
        frontmatter = "---\n"
        frontmatter += f"hyperopt_id: {result.get('hyperopt_id', 'unknown')}\n"
        frontmatter += f"strategy_id: {result.get('strategy_id', 'unknown')}\n"
        frontmatter += f"status: {status}\n"
        frontmatter += f"improvement: {result.get('improvement_pct', 0):.1f}\n"
        frontmatter += f"date: {result.get('start_time', datetime.utcnow().isoformat())}\n"
        frontmatter += "---\n\n"

        return f"""{frontmatter}# Hyperopt Results: {result.get('hyperopt_id', 'unknown')[:8]}

**Strategy:** [[{result.get('strategy_id', 'unknown')}]]
**Status:** {status_emoji} {status}
**Time:** {result.get('start_time', 'unknown')}
**Improvement:** {result.get('improvement_pct', 0):.1f}%

## Best Parameters

{params_md}

## Performance Metrics

{metrics_md}

## Reasoning

This hyperopt was run to optimize strategy parameters.
The improvement of {result.get('improvement_pct', 0):.1f}% was achieved over the baseline.

---

#hyperopt #{result.get('strategy_id', 'unknown')[:8]}
"""

    def get_summary(self) -> Dict[str, Any]:
        """Get memory summary from backend."""
        return self.backend.get_summary()

    def list_notes(
        self,
        memory_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List notes in the vault."""
        if not self._ensure_initialized():
            return []
        return self.backend.list_notes(memory_type, limit, offset)

    def read_note(self, path: str) -> Optional[str]:
        """Read a note from the vault."""
        return self.backend.read_note(path)


# Singleton instance
_obsidian_memory: Optional[ObsidianMemory] = None


def get_obsidian_memory(vault_path: Optional[str] = None) -> ObsidianMemory:
    """Get or create Obsidian memory instance."""
    global _obsidian_memory

    if _obsidian_memory is None:
        _obsidian_memory = ObsidianMemory(vault_path)

    return _obsidian_memory


async def store_agent_memory(memory_type: str, data: Dict) -> str:
    """
    Store agent memory in Obsidian.

    This function should be called by agents to persist their memory.

    Args:
        memory_type: Type of memory (decision, research, analysis, regime, hyperopt)
        data: Memory data to store

    Returns:
        Path to created note
    """
    memory = get_obsidian_memory()

    if memory_type == "decision":
        return await memory.store_decision(data)
    elif memory_type == "research":
        return await memory.store_research_finding(data)
    elif memory_type == "analysis":
        return await memory.store_strategy_analysis(data)
    elif memory_type == "regime":
        return await memory.store_market_regime(data)
    elif memory_type == "hyperopt":
        return await memory.store_hyperopt_result(data)
    else:
        raise ValueError(f"Unknown memory type: {memory_type}")


async def search_agent_memory(query: str, limit: int = 20) -> List[Dict]:
    """
    Search agent memory in Obsidian.

    Args:
        query: Search query
        limit: Maximum results

    Returns:
        List of matching notes
    """
    memory = get_obsidian_memory()
    return await memory.search_memory(query, limit)