"""Shared Jira issue-description content-limit validation."""

from __future__ import annotations

from jira_emulator.adf import adf_to_text, serialize_adf
from jira_emulator.config import get_settings
from jira_emulator.exceptions import DescriptionContentLimitExceededError


def normalized_description_text(value: str | dict | None) -> str:
    """Return the logical text Jira counts for an issue description.

    ADF input is serialized exactly as it is stored, then normalized through
    the same ADF-to-text conversion used for v2 responses. Plain text remains
    plain text. The returned string is measured in Python logical characters,
    which is the emulator's representation of Jira's text-field character
    unit.
    """
    return adf_to_text(serialize_adf(value)) or ""


def validate_description(value: str | dict | None) -> None:
    """Reject a description whose normalized logical text exceeds the limit."""
    settings = get_settings()
    normalized = normalized_description_text(value)
    if len(normalized) > settings.DESCRIPTION_MAX_LENGTH:
        raise DescriptionContentLimitExceededError(settings.DESCRIPTION_MAX_LENGTH, len(normalized))


def validate_description_update_ops(update_ops: dict | None) -> None:
    """Validate every description value supplied through Jira update ops."""
    if not update_ops or "description" not in update_ops:
        return
    for operation in update_ops["description"]:
        if isinstance(operation, dict) and "set" in operation:
            validate_description(operation["set"])
