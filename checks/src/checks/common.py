"""Common utilities for running checks."""

import os
import subprocess
from pathlib import Path


def detect_git_changes(paths: list[Path]) -> tuple[str, str]:
    """Get git status before and after for given paths.

    Returns:
        Tuple of (status_before, status_after) as strings
    """
    try:
        cmd = ["git", "status", "--porcelain"] + [str(p) for p in paths]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout, result.stdout
    except Exception:
        return "", ""


def run_check(
    name: str,
    description: str,
    command: list[str],
    paths: list[Path],
    verbose: bool = False,
    verbose_command: list[str] | None = None,
    check_git_changes: bool = False,
) -> int:
    """Run a check command and report results.

    Args:
        name: Check name
        description: Human-readable description
        command: Command to run as list of strings
        paths: Paths to check
        verbose: Whether to show verbose output
        verbose_command: Optional different command for verbose mode.
                        If None, uses command (assumes tool supports --verbose)
        check_git_changes: Whether to detect and report file changes

    Returns:
        Exit code from the command
    """
    print(f"🔍 Running {description}...")
    if verbose:
        print("(verbose mode)")
    print()

    # Get git status before if requested
    status_before = ""
    if check_git_changes:
        status_before, _ = detect_git_changes(paths)

    # Choose which command to run
    cmd_to_run = verbose_command if verbose and verbose_command else command

    # Build full command with paths
    full_command = cmd_to_run + [str(p) for p in paths]

    # Run the command
    result = subprocess.run(full_command, check=False)
    exit_code = result.returncode

    # Check git status after if requested
    if check_git_changes:
        _, status_after = detect_git_changes(paths)

        if status_before != status_after:
            print()
            print(f"📝 Files were modified by {name}:")
            subprocess.run(
                ["git", "diff", "--stat"] + [str(p) for p in paths],
                check=False,
            )

            is_ci = os.environ.get("CI", "0") == "1"
            if is_ci:
                print()
                print("❌ Files were out of date in CI!")
                print(f"To fix this, run '{name}' locally and commit the changes.")
                return 1
            print()
            print("✅ Files have been updated")
            print("💡 Consider committing these changes")
        else:
            print(f"✅ No changes made by {name}")

    return exit_code


def resolve_paths(paths: list[str] | None) -> list[Path]:
    """Resolve path arguments, defaulting to common Python directories.

    Args:
        paths: List of path strings, or None to use defaults

    Returns:
        List of Path objects that exist
    """
    if paths:
        return [Path(p) for p in paths if Path(p).exists()]

    # Default to common Python directories
    defaults = ["src", "tests"]
    return [Path(p) for p in defaults if Path(p).exists()]
