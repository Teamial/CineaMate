"""
Scheduler package for movie recommender system
"""

# Import from the main scheduler module
import sys
import os

# Add the parent directory to the path to import the main scheduler
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    from backend.scheduler import get_scheduler
except ImportError:
    # Fallback if the import fails
    get_scheduler = None

from .guardrails_scheduler import setup_guardrails_scheduler, get_guardrails_scheduler, manual_guardrail_check, manual_rollback

__all__ = [
    'get_scheduler',
    'setup_guardrails_scheduler',
    'get_guardrails_scheduler', 
    'manual_guardrail_check',
    'manual_rollback'
]
