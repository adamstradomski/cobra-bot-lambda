import logging
from collections.abc import Iterator

import pytest

from cobra_bot.handlers.logging_setup import APP_LOGGER, configure_logging


@pytest.fixture(autouse=True)
def lambda_like_levels() -> Iterator[None]:
    """Root and app loggers at WARNING, as in the Lambda runtime; restored after."""
    root, app = logging.getLogger(), logging.getLogger(APP_LOGGER)
    before = (root.level, app.level)
    root.setLevel(logging.WARNING)
    app.setLevel(logging.NOTSET)
    yield
    root.setLevel(before[0])
    app.setLevel(before[1])


def _info_reaches_handlers(caplog: pytest.LogCaptureFixture) -> bool:
    caplog.clear()
    logging.getLogger("cobra_bot.commands").info("command=standings")
    return "command=standings" in caplog.text


def test_info_is_dropped_by_default(caplog: pytest.LogCaptureFixture) -> None:
    assert not _info_reaches_handlers(caplog)


def test_app_loggers_pass_info_after_configuring(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """docs/spec/architecture.md logs command, tournament and duration at INFO."""
    configure_logging()

    assert _info_reaches_handlers(caplog)


def test_other_loggers_are_left_alone() -> None:
    configure_logging()

    assert logging.getLogger().level == logging.WARNING
    assert logging.getLogger("botocore").getEffectiveLevel() == logging.WARNING
