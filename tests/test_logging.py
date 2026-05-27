import logging
import pytest

def test_logging(app, caplog):
    logger = logging.getLogger("fenrir")
    caplog.set_level(logging.INFO)
    logger.info("Test Info Message")
    logger.warning("Test Warning Message")

    assert "Test Info Message" in caplog.text
    assert "Test Warning Message" in caplog.text
