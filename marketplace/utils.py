"""Backwards-compatible estimator import; implementation lives in ai_services.py."""
from .ai_services import get_ai_cost_estimate

__all__ = ['get_ai_cost_estimate']
