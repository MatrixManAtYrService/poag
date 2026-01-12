"""CLI commands for code quality checks."""

from typing import Annotated

import typer

from checks.common import resolve_paths, run_check


def _ruff_check(
    paths: Annotated[
        list[str] | None,
        typer.Argument(help="Paths to check (defaults to src/ and tests/)"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show verbose output"),
    ] = False,
) -> None:
    """Python linting with ruff (auto-fix enabled)."""
    resolved_paths = resolve_paths(paths)

    if not resolved_paths:
        print("❌ No valid paths to check")
        raise typer.Exit(1)

    # For ruff, we use the same command but add --verbose flag
    # This is the "pass-through" approach
    base_command = ["ruff", "check", "--fix", "--unsafe-fixes", "--exit-non-zero-on-fix"]
    verbose_command = base_command + ["--verbose"]

    exit_code = run_check(
        name="ruff-check",
        description="Python linting with ruff (auto-fix enabled)",
        command=base_command,
        paths=resolved_paths,
        verbose=verbose,
        verbose_command=verbose_command,
        check_git_changes=True,
    )

    raise typer.Exit(exit_code)


def ruff_check() -> None:
    """CLI entry point for ruff check."""
    typer.run(_ruff_check)


def _ruff_format(
    paths: Annotated[
        list[str] | None,
        typer.Argument(help="Paths to format (defaults to src/ and tests/)"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show verbose output"),
    ] = False,
) -> None:
    """Python formatting with ruff (auto-format enabled)."""
    resolved_paths = resolve_paths(paths)

    if not resolved_paths:
        print("❌ No valid paths to format")
        raise typer.Exit(1)

    # For ruff format, we use the same command but add --verbose flag
    base_command = ["ruff", "format"]
    verbose_command = base_command + ["--verbose"]

    exit_code = run_check(
        name="ruff-format",
        description="Python formatting with ruff (auto-format enabled)",
        command=base_command,
        paths=resolved_paths,
        verbose=verbose,
        verbose_command=verbose_command,
        check_git_changes=True,
    )

    raise typer.Exit(exit_code)


def ruff_format() -> None:
    """CLI entry point for ruff format."""
    typer.run(_ruff_format)


def _ty_check(
    paths: Annotated[
        list[str] | None,
        typer.Argument(help="Paths to type check (defaults to src/ and tests/)"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show verbose output"),
    ] = False,
) -> None:
    """Python type checking with ty."""
    resolved_paths = resolve_paths(paths)

    if not resolved_paths:
        print("❌ No valid paths to check")
        raise typer.Exit(1)

    # For ty, we use the same command but add --verbose flag
    base_command = ["ty", "check"]
    verbose_command = base_command + ["--verbose"]

    exit_code = run_check(
        name="ty",
        description="Python type checking with ty",
        command=base_command,
        paths=resolved_paths,
        verbose=verbose,
        verbose_command=verbose_command,
        check_git_changes=False,  # ty doesn't modify files
    )

    raise typer.Exit(exit_code)


def ty_check() -> None:
    """CLI entry point for ty type checking."""
    typer.run(_ty_check)
