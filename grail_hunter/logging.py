"""Structured logging configuration using structlog."""

import logging
import sys

import structlog


def setup_logging(debug: bool = False) -> None:
    """
    Configure structlog for the application.

    Args:
        debug: Enable debug level logging
    """
    # Set log level
    log_level = logging.DEBUG if debug else logging.INFO

    # Configure structlog processors
    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ExtraAdder(),
    ]

    # Development: colored console output
    # Production: JSON output
    if sys.stderr.isatty():
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True)
        ]
    else:
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer()
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a logger instance."""
    return structlog.get_logger(name)
