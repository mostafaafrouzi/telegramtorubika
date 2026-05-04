"""Logical menu sections for reply-keyboard routing (see docs/v2/03-menu-spec.md)."""

from enum import Enum


class MenuSection(str, Enum):
    MAIN = "main"
    PLAN = "plan"
    FILES = "files"
    RUBIKA = "rubika"
    SETTINGS = "settings"
    ADMIN = "admin"
