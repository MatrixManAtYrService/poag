"""Session storage using SQLite."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Session:
    """Represents a POAG session."""

    session_id: str
    cwd: str
    pid: int
    counter: int


class SessionStorage:
    """SQLite-based session storage.

    Sessions are identified by a composite key of (cwd, pid) and tracked
    with a counter to allow multiple sessions from the same cwd/pid combination.

    Session IDs follow the format: {cwd}.{pid}.{counter}
    """

    def __init__(self, db_path: Path):
        """Initialize session storage.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    cwd TEXT NOT NULL,
                    pid INTEGER NOT NULL,
                    counter INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cwd_pid
                ON sessions(cwd, pid)
            """)
            conn.commit()

    def create_session(self, cwd: str, pid: int) -> Session:
        """Create a new session for the given cwd and pid.

        If sessions already exist for this cwd/pid combination, the counter
        is incremented. Otherwise, it starts at 1.

        Args:
            cwd: Current working directory
            pid: Process ID

        Returns:
            Session object with the generated session_id
        """
        with sqlite3.connect(self.db_path) as conn:
            # Get the maximum counter for this cwd/pid combination
            cursor = conn.execute(
                "SELECT MAX(counter) FROM sessions WHERE cwd = ? AND pid = ?",
                (cwd, pid)
            )
            result = cursor.fetchone()
            max_counter = result[0] if result[0] is not None else 0

            # Increment counter
            counter = max_counter + 1
            session_id = f"{cwd}.{pid}.{counter}"

            # Insert new session
            conn.execute(
                "INSERT INTO sessions (session_id, cwd, pid, counter) VALUES (?, ?, ?, ?)",
                (session_id, cwd, pid, counter)
            )
            conn.commit()

            return Session(
                session_id=session_id,
                cwd=cwd,
                pid=pid,
                counter=counter
            )

    def get_session(self, session_id: str) -> Session | None:
        """Retrieve a session by its ID.

        Args:
            session_id: The session ID to look up

        Returns:
            Session object if found, None otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT session_id, cwd, pid, counter FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            result = cursor.fetchone()

            if result:
                return Session(
                    session_id=result[0],
                    cwd=result[1],
                    pid=result[2],
                    counter=result[3]
                )
            return None

    def list_sessions(self, cwd: str | None = None, pid: int | None = None) -> list[Session]:
        """List all sessions, optionally filtered by cwd and/or pid.

        Args:
            cwd: Filter by current working directory (optional)
            pid: Filter by process ID (optional)

        Returns:
            List of matching sessions
        """
        query = "SELECT session_id, cwd, pid, counter FROM sessions WHERE 1=1"
        params: list[str | int] = []

        if cwd is not None:
            query += " AND cwd = ?"
            params.append(cwd)

        if pid is not None:
            query += " AND pid = ?"
            params.append(pid)

        query += " ORDER BY created_at DESC"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            return [
                Session(
                    session_id=row[0],
                    cwd=row[1],
                    pid=row[2],
                    counter=row[3]
                )
                for row in cursor.fetchall()
            ]
