"""Checkpoint management for persistent agent state."""

import json
from pathlib import Path
from typing import Dict

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from poag_sf.config import Home


class CheckpointManager:
    """Manages LangGraph checkpoints for subflake agents."""

    def __init__(self, home: Home | None = None):
        if home is None:
            home = Home()
        self.home = home
        self.checkpoint_dir = home.state / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.checkpoint_dir / "metadata.json"

    def get_checkpoint_path(self, subflake_name: str) -> str:
        """Get the database path for a specific subflake's checkpointer.

        Args:
            subflake_name: Name of the subflake

        Returns:
            Path to the SQLite database as a string
        """
        db_path = self.checkpoint_dir / f"{subflake_name}.db"
        return str(db_path)

    def is_initialized(self, subflake_name: str, project_root: Path) -> bool:
        """Check if a subflake agent has been initialized.

        Args:
            subflake_name: Name of the subflake
            project_root: Project root path (for cache invalidation)

        Returns:
            True if initialized, False otherwise
        """
        metadata = self._load_metadata()
        key = f"{project_root}:{subflake_name}"
        return key in metadata

    def mark_initialized(self, subflake_name: str, project_root: Path) -> None:
        """Mark a subflake agent as initialized.

        Args:
            subflake_name: Name of the subflake
            project_root: Project root path
        """
        metadata = self._load_metadata()
        key = f"{project_root}:{subflake_name}"
        metadata[key] = True
        self._save_metadata(metadata)

    def get_thread_id(self, subflake_name: str, project_root: Path) -> str:
        """Get a consistent thread ID for a subflake agent.

        Args:
            subflake_name: Name of the subflake
            project_root: Project root path

        Returns:
            Thread ID string
        """
        return f"{project_root}:{subflake_name}"

    def _load_metadata(self) -> Dict[str, bool]:
        """Load checkpoint metadata from disk."""
        if self.metadata_file.exists():
            try:
                return json.loads(self.metadata_file.read_text())
            except (json.JSONDecodeError, ValueError):
                return {}
        return {}

    def _save_metadata(self, metadata: Dict[str, bool]) -> None:
        """Save checkpoint metadata to disk."""
        self.metadata_file.write_text(json.dumps(metadata, indent=2))
