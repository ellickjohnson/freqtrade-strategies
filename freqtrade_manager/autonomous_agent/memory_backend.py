"""
Memory Backend - Filesystem-based storage for Obsidian vault.

Provides simple file operations that work standalone (without MCP tools).
The vault path can be configured via OBSIDIAN_VAULT_PATH environment variable.
"""

import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Represents a search result from the memory."""
    path: str
    title: str
    content_snippet: str
    memory_type: str
    created_at: str
    tags: List[str]
    relevance: float
    full_content: Optional[str] = None


class FilesystemMemoryBackend:
    """
    Filesystem backend for Obsidian vault storage.

    Stores agent decisions, research findings, strategy analyses, and market regimes
    as Markdown files in an Obsidian-compatible structure.

    The vault path is configured via OBSIDIAN_VAULT_PATH environment variable,
    defaulting to /data/obsidian_vault if not set.
    """

    def __init__(self, vault_path: Optional[str] = None):
        """
        Initialize the filesystem memory backend.

        Args:
            vault_path: Path to Obsidian vault. If None, uses OBSIDIAN_VAULT_PATH
                       environment variable or default path.
        """
        self.vault_path = Path(
            vault_path or
            os.getenv("OBSIDIAN_VAULT_PATH", "/data/obsidian_vault")
        )
        self.notes_folder = "Freqtrade Agent"
        self._initialized = False

        # Memory type to folder mapping
        self.type_folders = {
            "decision": "Decisions",
            "research": "Research",
            "analysis": "Analysis",
            "regime": "Market Regimes",
            "hyperopt": "Hyperopt",
        }

    def _get_vault_path(self) -> Path:
        """Get the vault path with user home expanded."""
        # Handle ~ in path
        path = str(self.vault_path)
        if path.startswith("~"):
            path = os.path.expanduser(path)
        return Path(path)

    def ensure_folders(self) -> bool:
        """
        Create required folder structure in the vault.

        Returns:
            True if folders exist or were created, False on error.
        """
        try:
            vault = self._get_vault_path()
            base = vault / self.notes_folder

            # Create all type folders
            folders = [base / folder for folder in self.type_folders.values()]
            folders.append(base)  # Also create base folder

            for folder in folders:
                folder.mkdir(parents=True, exist_ok=True)

            self._initialized = True
            logger.info(f"Ensured memory folders in {vault}")
            return True

        except Exception as e:
            logger.error(f"Failed to create memory folders: {e}")
            return False

    def is_available(self) -> bool:
        """
        Check if the vault is available for writing.

        Returns:
            True if the vault directory exists or can be created.
        """
        try:
            vault = self._get_vault_path()
            if vault.exists():
                return True
            # Try to create it
            vault.mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            return False

    def create_note(self, path: str, content: str) -> bool:
        """
        Write a note to the vault.

        Args:
            path: Relative path within vault (e.g., "Freqtrade Agent/Decisions/decision-123.md")
            content: Markdown content of the note

        Returns:
            True if note was created successfully.
        """
        try:
            if not self._initialized:
                self.ensure_folders()

            vault = self._get_vault_path()
            full_path = vault / path

            # Ensure parent directory exists
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Write the note
            full_path.write_text(content, encoding="utf-8")

            logger.debug(f"Created note: {path}")
            return True

        except Exception as e:
            logger.error(f"Failed to create note {path}: {e}")
            return False

    def read_note(self, path: str) -> Optional[str]:
        """
        Read a note from the vault.

        Args:
            path: Relative path within vault

        Returns:
            Note content or None if not found.
        """
        try:
            vault = self._get_vault_path()
            full_path = vault / path

            if not full_path.exists():
                return None

            return full_path.read_text(encoding="utf-8")

        except Exception as e:
            logger.error(f"Failed to read note {path}: {e}")
            return None

    def delete_note(self, path: str) -> bool:
        """
        Delete a note from the vault.

        Args:
            path: Relative path within vault

        Returns:
            True if note was deleted or didn't exist.
        """
        try:
            vault = self._get_vault_path()
            full_path = vault / path

            if full_path.exists():
                full_path.unlink()
                logger.debug(f"Deleted note: {path}")

            return True

        except Exception as e:
            logger.error(f"Failed to delete note {path}: {e}")
            return False

    def search_notes(
        self,
        query: str,
        limit: int = 20,
        memory_types: Optional[List[str]] = None
    ) -> List[SearchResult]:
        """
        Search notes using text matching.

        Searches note titles, content, and tags for the query.

        Args:
            query: Search query string
            limit: Maximum results to return
            memory_types: Optional filter by memory types (decision, research, etc.)

        Returns:
            List of SearchResult objects ordered by relevance.
        """
        try:
            if not self._initialized:
                self.ensure_folders()

            vault = self._get_vault_path()
            base = vault / self.notes_folder

            if not base.exists():
                return []

            results: List[SearchResult] = []
            query_lower = query.lower()
            query_terms = set(query_lower.split())

            # Determine which type folders to search
            type_folders = memory_types if memory_types else list(self.type_folders.keys())

            for memory_type in type_folders:
                folder_name = self.type_folders.get(memory_type)
                if not folder_name:
                    continue

                type_path = base / folder_name
                if not type_path.exists():
                    continue

                # Search all markdown files in this folder
                for note_path in type_path.glob("**/*.md"):
                    result = self._search_note(note_path, query_lower, query_terms, memory_type, vault)
                    if result:
                        results.append(result)

                        if len(results) >= limit * 2:  # Get extra for ranking
                            break

                if len(results) >= limit * 2:
                    break

            # Sort by relevance score
            results.sort(key=lambda r: r.relevance, reverse=True)

            return results[:limit]

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def _search_note(
        self,
        note_path: Path,
        query_lower: str,
        query_terms: set,
        memory_type: str,
        vault: Path
    ) -> Optional[SearchResult]:
        """
        Search a single note for query terms.

        Returns SearchResult if match found, None otherwise.
        """
        try:
            content = note_path.read_text(encoding="utf-8")
            content_lower = content.lower()

            # Calculate relevance score
            relevance = 0.0

            # Check title (first # heading)
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            title = title_match.group(1) if title_match else note_path.stem

            if query_lower in title.lower():
                relevance += 3.0
            for term in query_terms:
                if term in title.lower():
                    relevance += 1.0

            # Check content
            if query_lower in content_lower:
                relevance += 2.0

            # Count term occurrences
            for term in query_terms:
                count = content_lower.count(term)
                relevance += count * 0.1

            # Check tags
            tags = re.findall(r"#(\w+[-\w]*)", content)
            for tag in tags:
                tag_lower = tag.lower()
                if query_lower in tag_lower or tag_lower in query_lower:
                    relevance += 0.5

            # Must have at least one match
            if relevance == 0:
                return None

            # Create snippet (first 200 chars after title)
            snippet_match = re.search(r"^#\s+.+?\n(.{0,200})", content, re.DOTALL)
            snippet = snippet_match.group(1).strip() if snippet_match else content[:200]
            snippet = snippet.replace("\n", " ").strip()[:200]

            # Get created date from frontmatter or file mtime
            created_at = datetime.fromtimestamp(note_path.stat().st_mtime).isoformat()
            frontmatter = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
            if frontmatter:
                fm = frontmatter.group(1)
                date_match = re.search(r"date:\s*(.+)", fm)
                if date_match:
                    created_at = date_match.group(1).strip()

            # Relative path from vault
            rel_path = str(note_path.relative_to(vault))

            return SearchResult(
                path=rel_path,
                title=title,
                content_snippet=snippet,
                memory_type=memory_type,
                created_at=created_at,
                tags=tags,
                relevance=min(relevance, 10.0),  # Cap at 10
            )

        except Exception as e:
            logger.debug(f"Error searching note {note_path}: {e}")
            return None

    def list_notes(
        self,
        memory_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List notes in the vault.

        Args:
            memory_type: Optional filter by type (decision, research, etc.)
            limit: Maximum results
            offset: Offset for pagination

        Returns:
            List of note metadata dicts.
        """
        try:
            if not self._initialized:
                self.ensure_folders()

            vault = self._get_vault_path()
            base = vault / self.notes_folder

            if not base.exists():
                return []

            results: List[Dict[str, Any]] = []

            # Determine folders to search
            if memory_type:
                folders = [self.type_folders.get(memory_type)]
            else:
                folders = list(self.type_folders.values())

            for folder_name in folders:
                if not folder_name:
                    continue

                type_path = base / folder_name
                if not type_path.exists():
                    continue

                for note_path in sorted(
                    type_path.glob("**/*.md"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True
                ):
                    # Get note metadata
                    metadata = self._get_note_metadata(note_path, vault)
                    if metadata:
                        results.append(metadata)

                        if len(results) >= limit + offset:
                            break

                if len(results) >= limit + offset:
                    break

            return results[offset:offset + limit]

        except Exception as e:
            logger.error(f"Failed to list notes: {e}")
            return []

    def _get_note_metadata(self, note_path: Path, vault: Path) -> Optional[Dict[str, Any]]:
        """Extract metadata from a note."""
        try:
            content = note_path.read_text(encoding="utf-8")

            # Extract title
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            title = title_match.group(1) if title_match else note_path.stem

            # Extract tags
            tags = re.findall(r"#(\w+[-\w]*)", content)

            # Get file stats
            stat = note_path.stat()
            created_at = datetime.fromtimestamp(stat.st_mtime).isoformat()

            return {
                "path": str(note_path.relative_to(vault)),
                "title": title,
                "memory_type": self._infer_memory_type(note_path),
                "tags": tags,
                "created_at": created_at,
                "size": stat.st_size,
            }

        except Exception as e:
            logger.debug(f"Error getting note metadata: {e}")
            return None

    def _infer_memory_type(self, note_path: Path) -> str:
        """Infer memory type from note path."""
        for type_name, folder_name in self.type_folders.items():
            if folder_name in str(note_path):
                return type_name
        return "unknown"

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics about stored memory.

        Returns:
            Dict with counts by type, total notes, etc.
        """
        try:
            if not self._initialized:
                self.ensure_folders()

            vault = self._get_vault_path()
            base = vault / self.notes_folder

            if not base.exists():
                return {
                    "available": False,
                    "total_notes": 0,
                    "by_type": {},
                }

            counts = {}
            total = 0
            oldest = None
            newest = None

            for type_name, folder_name in self.type_folders.items():
                type_path = base / folder_name
                if type_path.exists():
                    notes = list(type_path.glob("**/*.md"))
                    counts[type_name] = len(notes)
                    total += len(notes)

                    # Track date range
                    for note in notes:
                        mtime = note.stat().st_mtime
                        if oldest is None or mtime < oldest:
                            oldest = mtime
                        if newest is None or mtime > newest:
                            newest = mtime

            return {
                "available": True,
                "vault_path": str(vault),
                "total_notes": total,
                "by_type": counts,
                "oldest_note": datetime.fromtimestamp(oldest).isoformat() if oldest else None,
                "newest_note": datetime.fromtimestamp(newest).isoformat() if newest else None,
            }

        except Exception as e:
            logger.error(f"Failed to get summary: {e}")
            return {
                "available": False,
                "error": str(e),
                "total_notes": 0,
                "by_type": {},
            }


# Singleton instance
_memory_backend: Optional[FilesystemMemoryBackend] = None


def get_memory_backend(vault_path: Optional[str] = None) -> FilesystemMemoryBackend:
    """Get or create the singleton memory backend instance."""
    global _memory_backend

    if _memory_backend is None:
        _memory_backend = FilesystemMemoryBackend(vault_path)

    return _memory_backend