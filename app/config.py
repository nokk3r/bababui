import logging
import os
from pathlib import Path

APP_VERSION = "0.5.0"
DATA_DIR = Path(os.environ.get("DATA_DIR", "data")).resolve()
XRAY_BIN = os.environ.get("XRAY_BIN", "xray")
HYSTERIA_BIN = os.environ.get("HYSTERIA_BIN", "hysteria")
SPEEDTEST_BIN = os.environ.get("SPEEDTEST_BIN", "speedtest-go")
WEB_PASSWORD = os.environ.get("WEB_PASSWORD", "")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _log_level() -> int:
    raw = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    level = _LOG_LEVELS.get(raw)
    if level is None:
        allowed = ", ".join(_LOG_LEVELS)
        raise RuntimeError(f"LOG_LEVEL={raw!r} is not one of: {allowed}")
    return level


LOG_LEVEL = _log_level()
