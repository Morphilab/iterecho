from __future__ import annotations

import logging as stdlib_logging
from collections.abc import Iterator

import pytest

from iterecho.utils import logging as log_module


@pytest.fixture(autouse=True)
def remember_logging_state() -> Iterator[None]:
    """Save the root logger so each test can rebuild it and leave no trace."""
    root = stdlib_logging.getLogger()
    old_flag = log_module._LOG_INITIALIZED
    old_handlers = list(root.handlers)
    old_level = root.level
    yield
    root.handlers.clear()
    root.handlers.extend(old_handlers)
    root.setLevel(old_level)
    log_module._LOG_INITIALIZED = old_flag


def fresh_setup(**kwargs: bool) -> None:
    """Empty the root logger, then run `setup_logging` on a blank slate.

    `setup_logging` only installs its handlers when the root logger has none,
    so the handlers pytest attaches to every test must be removed first.
    """
    stdlib_logging.getLogger().handlers.clear()
    log_module._LOG_INITIALIZED = False
    log_module.setup_logging(**kwargs)


class TestSetupLogging:
    def test_default_is_info_on_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        fresh_setup()
        assert stdlib_logging.getLogger().level == stdlib_logging.INFO

        stdlib_logging.getLogger("IterEcho.demo").info("plain info message")
        captured = capsys.readouterr()
        assert "INFO - plain info message" in captured.out
        assert "plain info message" not in captured.err

    def test_quiet_raises_level_and_routes_to_stderr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fresh_setup(quiet=True)
        assert stdlib_logging.getLogger().level == stdlib_logging.WARNING

        logger = stdlib_logging.getLogger("IterEcho.demo")
        logger.info("hidden info")
        logger.warning("visible warning")
        captured = capsys.readouterr()
        assert "hidden info" not in captured.out
        assert "visible warning" in captured.err

    def test_verbose_enables_debug_with_timestamps(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fresh_setup(verbose=True)
        assert stdlib_logging.getLogger().level == stdlib_logging.DEBUG

        stdlib_logging.getLogger("IterEcho.demo").debug("debug detail")
        captured = capsys.readouterr()
        assert "IterEcho.demo - DEBUG - debug detail" in captured.out

    def test_iterecho_debug_env_enables_debug_without_flag(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("ITERECHO_DEBUG", "1")
        fresh_setup()
        assert stdlib_logging.getLogger().level == stdlib_logging.DEBUG

        stdlib_logging.getLogger("IterEcho.demo").debug("from env var")
        captured = capsys.readouterr()
        assert "from env var" in captured.out

    def test_second_call_switches_existing_handlers_to_verbose_format(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fresh_setup()
        log_module.setup_logging(verbose=True)
        root = stdlib_logging.getLogger()
        assert root.level == stdlib_logging.DEBUG
        assert len(root.handlers) == 2

        stdlib_logging.getLogger("IterEcho.demo").debug("after re-init")
        captured = capsys.readouterr()
        # asctime appears only in the verbose format
        assert " - IterEcho.demo - DEBUG - after re-init" in captured.out

    def test_second_call_keeps_plain_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        fresh_setup(verbose=True)
        log_module.setup_logging()
        assert stdlib_logging.getLogger().level == stdlib_logging.INFO

        stdlib_logging.getLogger("IterEcho.demo").info("plain again")
        captured = capsys.readouterr()
        assert "INFO - plain again" in captured.out
        assert " - INFO - plain again" not in captured.out
