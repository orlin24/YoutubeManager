"""Permission levels for AI tools.

HIGH_RISK tools never execute directly - they always create an approval request.
"""
from __future__ import annotations

from enum import IntEnum


class PermissionLevel(IntEnum):
    READ = 1
    WRITE = 2
    HIGH_RISK = 3


class PermissionGate:
    """Grants a set of levels; HIGH_RISK is never granted implicitly."""

    def __init__(self, granted: set[PermissionLevel] | None = None):
        self.granted = granted or {PermissionLevel.READ, PermissionLevel.WRITE}

    def can(self, level: PermissionLevel) -> bool:
        return level in self.granted

    def check_tool(self, level: PermissionLevel) -> bool:
        return self.can(level)
