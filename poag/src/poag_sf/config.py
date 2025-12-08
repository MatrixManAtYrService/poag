"""POAG-SF unified configuration using XDG base directories."""

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel
from xdg_base_dirs import xdg_config_home, xdg_state_home


class PoagConfig(BaseModel):
    """Configuration settings for POAG-SF."""

    # Placeholder for future config options
    pass


@dataclass
class Home:
    """
    POAG stores state and configuration data in the local filesystem using XDG directories.

    - Configuration: ~/.config/poag/ (user preferences, settings)
    - State: ~/.local/state/poag/ (runtime data, logs)

    To create a sandboxed environment for testing, initialize with custom paths.
    """

    config: Path = xdg_config_home() / "poag"
    state: Path = xdg_state_home() / "poag"

    def __post_init__(self) -> None:
        self.mkdirs()

    @staticmethod
    def sandbox(parent: Path | str) -> "Home":
        """Create a sandboxed Home for testing."""
        if isinstance(parent, str):
            parent = Path(parent)
        return Home(config=parent / "config" / "poag", state=parent / "state" / "poag")

    def mkdirs(self) -> None:
        """Ensure all directories exist."""
        self.config.mkdir(parents=True, exist_ok=True)
        self.state.mkdir(parents=True, exist_ok=True)

    def load_config(self) -> PoagConfig:
        """Load configuration from poag.json, creating default if it doesn't exist."""
        import json

        config_file = self.config / "poag.json"

        if config_file.exists():
            try:
                config_data = json.loads(config_file.read_text())
                return PoagConfig.model_validate(config_data)
            except (json.JSONDecodeError, ValueError):
                # If config is corrupted, fall back to default
                pass

        # Create default config
        default_config = PoagConfig()
        self.save_config(default_config)
        return default_config

    def save_config(self, config: PoagConfig) -> None:
        """Save configuration to poag.json."""
        config_file = self.config / "poag.json"
        config_file.write_text(config.model_dump_json(indent=2))

    def get_log_file(self) -> Path:
        """Get the path to the current log file (overwrites each run)."""
        return self.state / "poag.log"

    def get_serena_log_dir(self) -> Path:
        """Get directory for Serena MCP server logs."""
        serena_log_dir = self.state / "serena"
        serena_log_dir.mkdir(parents=True, exist_ok=True)
        return serena_log_dir
