"""Reachy — self-hosted B2B prospecting and outreach application."""

__version__ = "2.0.0"

from .config import ReachyConfig
from .db import Database

__all__ = ["ReachyConfig", "Database", "__version__"]
