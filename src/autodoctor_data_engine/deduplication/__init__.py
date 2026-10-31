"""Deduplication layer."""

from .detector import (
    DuplicateGroup,
    StatementRef,
    collect_statements,
    detect_duplicates,
    record_id,
    statement_text,
)

__all__ = [
    "DuplicateGroup",
    "StatementRef",
    "collect_statements",
    "detect_duplicates",
    "record_id",
    "statement_text",
]
