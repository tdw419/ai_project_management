"""
DEPRECATED: This module is superseded by issue_queue.py

GitHub Issues are now the work queue. This SQLite-backed queue
is kept for backwards compatibility only.

Use: from aipm.issue_queue import GitHubIssueQueue
Instead of: from aipm.queue import MultiProjectQueue
"""

import warnings

warnings.warn(
    "aipm.queue is deprecated. Use aipm.issue_queue.GitHubIssueQueue instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .core.queue import PromptQueue  # noqa: F401
