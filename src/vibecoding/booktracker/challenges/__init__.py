"""Reading challenges module.

Provides functionality for:
- Creating and managing reading challenges
- Tracking progress toward challenge goals
- Challenge types: books count, pages count, time-based
"""

from .manager import ChallengeManager
from .models import Challenge, ChallengeBook
from .schemas import (
    ChallengeCreate,
    ChallengeUpdate,
    ChallengeResponse,
    ChallengeType,
    ChallengeStatus,
    ChallengeProgress,
)

__all__ = [
    "ChallengeManager",
    "Challenge",
    "ChallengeBook",
    "ChallengeCreate",
    "ChallengeUpdate",
    "ChallengeResponse",
    "ChallengeType",
    "ChallengeStatus",
    "ChallengeProgress",
]
