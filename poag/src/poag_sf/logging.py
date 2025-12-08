"""Structured logging configuration for POAG."""

import logging
import sys
from pathlib import Path

import structlog
from rich.console import Console

stderr = Console(stderr=True)


def setup_logging(log_file: Path, serena_log_dir: Path) -> None:
    """Configure structlog for POAG and suppress Serena's verbose logging.

    Args:
        log_file: Path to main POAG log file
        serena_log_dir: Directory for Serena MCP server logs
    """
    # Configure Python's standard logging to suppress Serena's INFO messages
    # Set all Serena loggers to WARNING level
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(serena_log_dir / "serena.log", mode="w")],
    )

    # Explicitly set Serena's loggers to WARNING
    for logger_name in ["serena", "sensai", "solidlsp", "mcp"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=log_file.open("w")),
        cache_logger_on_first_use=True,
    )

    # Log where things are going
    stderr.print(f"[dim]📝 Logs: {log_file}[/dim]")
    stderr.print(f"[dim]📝 Serena logs: {serena_log_dir}[/dim]")


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)
