"""Shared CLI records. Start Python with -B before library import for no writes."""
from .contracts import Refusal
from .engine import refresh, search, describe, context
__all__ = ['Refusal', 'refresh', 'search', 'describe', 'context']
