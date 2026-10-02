"""Logging for the Lambda entry points.

The Lambda Python runtime only passes WARNING and above by default, which would
hide the INFO lines SPEC §10 asks for (command, tournament, stale flag,
duration). Called once per cold start by each handler, never at import, so
tests keep their logging configuration.
"""

import logging

APP_LOGGER = "cobra_bot"


def configure_logging(level: int = logging.INFO) -> None:
    logging.getLogger(APP_LOGGER).setLevel(level)
