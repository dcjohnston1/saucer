"""actions.py — ActionClass abstraction for Saucer/Hana.

Every action Hana can take is registered here with metadata that governs
how it should be treated: whether it can be undone, whether it needs human
review before or after, and whether explicit confirmation is required.

The optional confidence field (0.0–1.0) allows callers to record how
certain Hana was when it decided to take the action. None means unscored.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ActionClass:
    reversible: bool
    reviewable: bool
    confirmation_required: bool
    confidence: Optional[float] = None   # 0.0–1.0; None = not scored
    action_type: str = ''                # machine-readable identifier
    description: str = ''               # human-readable description


# ── Registry ─────────────────────────────────────────────────────────────────

_ACTION_REGISTRY: dict = {}


def register_action(name: str, action: ActionClass) -> None:
    """Register an ActionClass under a given name."""
    _ACTION_REGISTRY[name] = action


def get_action(name: str) -> Optional[ActionClass]:
    """Return the registered ActionClass for name, or None if not registered."""
    return _ACTION_REGISTRY.get(name)


# ── Standard action types ─────────────────────────────────────────────────────

register_action(
    'gmail_draft',
    ActionClass(
        reversible=False,
        reviewable=True,
        confirmation_required=False,
        action_type='gmail_draft',
        description='Create a Gmail draft reply for user review',
    ),
)

register_action(
    'task_add',
    ActionClass(
        reversible=True,
        reviewable=True,
        confirmation_required=False,
        action_type='task_add',
        description='Add a task to the household Google Doc',
    ),
)

register_action(
    'email_dismiss',
    ActionClass(
        reversible=True,
        reviewable=False,
        confirmation_required=False,
        action_type='email_dismiss',
        description='Dismiss an email from the active inbox',
    ),
)
