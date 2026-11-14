"""Dashboard (Person 4): one FastAPI page with the latest warning and recent events."""

from dashboard.server import Dashboard, create_app, register
from dashboard.state import DashboardState

__all__ = ["Dashboard", "DashboardState", "create_app", "register"]
