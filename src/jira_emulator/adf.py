"""Atlassian Document Format (ADF) conversion utilities.

ADF is the JSON document structure used by Jira API v3 for rich-text fields
such as ``description`` and comment ``body``.  These helpers convert between
plain text, stored ADF JSON strings, and ADF dicts so that the emulator can
serve both v2 (plain text) and v3 (ADF) responses from the same stored data.
"""

from __future__ import annotations

import json


# Block-level node types that should be followed by a newline when
# extracting plain text.
_BLOCK_TYPES = frozenset({
    "paragraph", "heading", "blockquote", "codeBlock",
    "rule", "mediaSingle", "mediaGroup", "decisionList",
    "taskList", "bulletList", "orderedList", "listItem",
    "table", "tableRow", "tableCell", "tableHeader",
    "panel", "expand",
})


def is_adf(value: str | None) -> bool:
    """Return ``True`` if *value* is a JSON string encoding an ADF document.

    An ADF document is a JSON object with ``"type": "doc"`` at the root.
    """
    if value is None:
        return False
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(parsed, dict) and parsed.get("type") == "doc"


def text_to_adf(text: str | None) -> dict | None:
    """Convert a stored text value to an ADF dict.

    * If *text* is ``None``, returns ``None``.
    * If *text* is already an ADF JSON string, parse and return the dict.
    * Otherwise treat it as plain text: split on newlines and wrap each line
      in an ADF paragraph node.
    """
    if text is None:
        return None

    if is_adf(text):
        return json.loads(text)

    # Wrap plain text in ADF paragraphs
    lines = text.split("\n")
    content = []
    for line in lines:
        if line:
            content.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": line}],
            })
        else:
            # Empty line → empty paragraph
            content.append({"type": "paragraph", "content": []})

    return {"version": 1, "type": "doc", "content": content}


def adf_to_text(adf: dict | str | None) -> str | None:
    """Extract plain text from an ADF structure.

    * If *adf* is ``None``, returns ``None``.
    * If *adf* is a string that is *not* ADF, return it as-is (already
      plain text).
    * If *adf* is a string that *is* ADF, parse it first.
    * Recursively walks the node tree, concatenating ``text`` values and
      inserting newlines after block-level nodes.
    """
    if adf is None:
        return None

    if isinstance(adf, str):
        if not is_adf(adf):
            return adf
        adf = json.loads(adf)

    parts: list[str] = []
    _walk_nodes(adf, parts)

    # Join and strip trailing whitespace / excessive newlines
    result = "".join(parts).strip("\n")
    return result


def _walk_nodes(node: dict, parts: list[str]) -> None:
    """Recursively extract text from an ADF node tree."""
    if node.get("type") == "text":
        parts.append(node.get("text", ""))
        return

    if node.get("type") == "hardBreak":
        parts.append("\n")
        return

    for child in node.get("content", []):
        _walk_nodes(child, parts)

    if node.get("type") in _BLOCK_TYPES:
        parts.append("\n")


def adf_to_markdown(adf: dict | str | None) -> str | None:
    """Convert an ADF structure to Markdown.

    Like ``adf_to_text`` but preserves formatting as Markdown syntax so that
    a Markdown renderer (e.g. ``marked.js``) can display bold, italic, links,
    headings, etc.
    """
    if adf is None:
        return None

    if isinstance(adf, str):
        if not is_adf(adf):
            return adf
        adf = json.loads(adf)

    parts: list[str] = []
    _walk_nodes_md(adf, parts)
    return "".join(parts).strip("\n")


def _walk_nodes_md(node: dict, parts: list[str]) -> None:
    """Recursively convert ADF nodes to Markdown."""
    node_type = node.get("type")

    if node_type == "text":
        text = node.get("text", "")
        marks = node.get("marks", [])
        for mark in marks:
            mt = mark.get("type")
            if mt == "strong":
                text = f"**{text}**"
            elif mt == "em":
                text = f"*{text}*"
            elif mt == "code":
                text = f"`{text}`"
            elif mt == "link":
                href = mark.get("attrs", {}).get("href", "")
                text = f"[{text}]({href})"
            elif mt == "strike":
                text = f"~~{text}~~"
        parts.append(text)
        return

    if node_type == "hardBreak":
        parts.append("  \n")
        return

    if node_type == "rule":
        parts.append("\n---\n")
        return

    if node_type == "heading":
        level = node.get("attrs", {}).get("level", 1)
        parts.append("#" * level + " ")
        for child in node.get("content", []):
            _walk_nodes_md(child, parts)
        parts.append("\n")
        return

    if node_type == "codeBlock":
        lang = node.get("attrs", {}).get("language", "")
        parts.append(f"```{lang}\n")
        for child in node.get("content", []):
            _walk_nodes_md(child, parts)
        parts.append("\n```\n")
        return

    if node_type == "blockquote":
        inner: list[str] = []
        for child in node.get("content", []):
            _walk_nodes_md(child, inner)
        quoted = "".join(inner).strip("\n")
        for line in quoted.split("\n"):
            parts.append(f"> {line}\n")
        return

    if node_type == "bulletList":
        for child in node.get("content", []):
            parts.append("- ")
            inner = []
            for grandchild in child.get("content", []):
                _walk_nodes_md(grandchild, inner)
            parts.append("".join(inner).strip("\n"))
            parts.append("\n")
        return

    if node_type == "orderedList":
        for i, child in enumerate(node.get("content", []), 1):
            parts.append(f"{i}. ")
            inner = []
            for grandchild in child.get("content", []):
                _walk_nodes_md(grandchild, inner)
            parts.append("".join(inner).strip("\n"))
            parts.append("\n")
        return

    # Default: recurse into children
    for child in node.get("content", []):
        _walk_nodes_md(child, parts)

    if node_type in _BLOCK_TYPES:
        parts.append("\n")


def serialize_adf(value: str | dict | None) -> str | None:
    """Prepare a description / body value for database storage.

    * ``dict`` (ADF object from a v3 client) → JSON string
    * ``str`` → stored as-is (plain text or already-serialized ADF)
    * ``None`` → ``None``
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return json.dumps(value)
    return value
