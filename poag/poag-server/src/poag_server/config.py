"""POAG Server configuration using XDG base directories."""

from dataclasses import dataclass
from pathlib import Path

from xdg_base_dirs import xdg_data_home, xdg_state_home


@dataclass
class Home:
    """
    POAG stores state and data in the local filesystem using XDG directories.

    - Data: ~/.local/share/poag/ (sessions database, persistent data)
    - State: ~/.local/state/poag/ (runtime data, ports, pid files)

    To create a sandboxed environment for testing, initialize with custom paths.
    """

    data: Path = xdg_data_home() / "poag"
    state: Path = xdg_state_home() / "poag"

    def __post_init__(self) -> None:
        self.mkdirs()

    @staticmethod
    def sandbox(parent: Path | str) -> "Home":
        """Create a sandboxed Home for testing."""
        if isinstance(parent, str):
            parent = Path(parent)
        return Home(
            data=parent / "share" / "poag",
            state=parent / "state" / "poag"
        )

    def mkdirs(self) -> None:
        """Ensure all directories exist."""
        self.data.mkdir(parents=True, exist_ok=True)
        self.state.mkdir(parents=True, exist_ok=True)

    @property
    def sessions_db(self) -> Path:
        """Path to the sessions SQLite database."""
        return self.data / "sessions.db"

    def set_port(self, port: int) -> None:
        """Store the server port number."""
        (self.state / "port").write_text(str(port))

    def get_port(self) -> int | None:
        """Retrieve the stored server port number."""
        port_file = self.state / "port"
        if port_file.exists():
            return int(port_file.read_text().strip())
        return None

    def set_pid(self, pid: int) -> None:
        """Store the server process ID."""
        (self.state / "pid").write_text(str(pid))

    def get_pid(self) -> int | None:
        """Retrieve the stored server process ID."""
        pid_file = self.state / "pid"
        if pid_file.exists():
            return int(pid_file.read_text().strip())
        return None
