"""
Multi-Armed Bandit Policies Package

This package contains implementations of various bandit policies:
- Thompson Sampling: Bayesian approach with Beta distributions
- ε-greedy: Simple exploration-exploitation with fixed exploration rate
- UCB1: Upper Confidence Bound with logarithmic confidence intervals

All policies implement the Policy interface defined in base.py
"""

from .base import Policy, PolicyResult, BasePolicy, PolicyStateManager, get_policy

__all__ = [
    'Policy',
    'PolicyResult', 
    'BasePolicy',
    'PolicyStateManager',
    'get_policy'
]
