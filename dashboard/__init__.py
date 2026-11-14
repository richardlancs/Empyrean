"""Dashboard (Person 4): one FastAPI page with the latest warning and recent events."""

from dashboard.server import create_app, register
from dashboard.state import DashboardState

__all__ = ["DashboardState", "create_app", "register"]
