"""COLUM - AI Desktop Assistant"""

__version__ = "1.0.0-beta1"
__author__ = "COLUM Team"

from app.config.loader import get_config, Config
from app.utils.logging import setup_logging, get_logger, StructuredLogger

__all__ = [
    "get_config",
    "Config",
    "setup_logging",
    "get_logger",
    "StructuredLogger",
]