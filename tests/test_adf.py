"""Tests for the ADF (Atlassian Document Format) conversion utilities."""

import json

import pytest

from jira_emulator.adf import adf_to_text, is_adf, serialize_adf, text_to_adf


# ---------------------------------------------------------------------------
# is_adf
# ---------------------------------------------------------------------------


class TestIsAdf:
    def test_none(self):
        assert is_adf(None) is False

    def test_plain_string(self):
        assert is_adf("Hello world") is False

    def test_json_but_not_adf(self):
        assert is_adf('{"type": "paragraph"}') is False

    def test_adf_json_string(self):
        adf = json.dumps({"version": 1, "type": "doc", "content": []})
        assert is_adf(adf) is True

    def test_empty_string(self):
        assert is_adf("") is False

    def test_json_array(self):
        assert is_adf("[1, 2, 3]") is False


# ---------------------------------------------------------------------------
# text_to_adf
# ---------------------------------------------------------------------------


class TestTextToAdf:
    def test_none(self):
        assert text_to_adf(None) is None

    def test_plain_text(self):
        result = text_to_adf("Hello world")
        assert result["type"] == "doc"
        assert result["version"] == 1
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "paragraph"
        assert result["content"][0]["content"][0]["text"] == "Hello world"

    def test_multiline_text(self):
        result = text_to_adf("Line 1\nLine 2\nLine 3")
        assert result["type"] == "doc"
        assert len(result["content"]) == 3
        assert result["content"][0]["content"][0]["text"] == "Line 1"
        assert result["content"][1]["content"][0]["text"] == "Line 2"
        assert result["content"][2]["content"][0]["text"] == "Line 3"

    def test_text_with_empty_lines(self):
        result = text_to_adf("Line 1\n\nLine 3")
        assert len(result["content"]) == 3
        # Empty line results in empty paragraph
        assert result["content"][1]["content"] == []

    def test_stored_adf_string(self):
        original = {"version": 1, "type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]},
        ]}
        stored = json.dumps(original)
        result = text_to_adf(stored)
        assert result == original


# ---------------------------------------------------------------------------
# adf_to_text
# ---------------------------------------------------------------------------


class TestAdfToText:
    def test_none(self):
        assert adf_to_text(None) is None

    def test_plain_string(self):
        assert adf_to_text("Hello world") == "Hello world"

    def test_adf_dict(self):
        adf = {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello world"}],
                },
            ],
        }
        assert adf_to_text(adf) == "Hello world"

    def test_adf_multiple_paragraphs(self):
        adf = {
            "version": 1,
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Line 1"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "Line 2"}]},
            ],
        }
        assert adf_to_text(adf) == "Line 1\nLine 2"

    def test_nested_adf_with_marks(self):
        """ADF with inline marks (bold, etc.) should still extract all text."""
        adf = {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hello "},
                        {
                            "type": "text",
                            "text": "bold",
                            "marks": [{"type": "strong"}],
                        },
                        {"type": "text", "text": " world"},
                    ],
                },
            ],
        }
        assert adf_to_text(adf) == "Hello bold world"

    def test_adf_json_string(self):
        adf = {
            "version": 1,
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Test"}]},
            ],
        }
        result = adf_to_text(json.dumps(adf))
        assert result == "Test"

    def test_heading_node(self):
        adf = {
            "version": 1,
            "type": "doc",
            "content": [
                {"type": "heading", "attrs": {"level": 1}, "content": [
                    {"type": "text", "text": "Title"},
                ]},
                {"type": "paragraph", "content": [{"type": "text", "text": "Body"}]},
            ],
        }
        assert adf_to_text(adf) == "Title\nBody"


# ---------------------------------------------------------------------------
# serialize_adf
# ---------------------------------------------------------------------------


class TestSerializeAdf:
    def test_none(self):
        assert serialize_adf(None) is None

    def test_string(self):
        assert serialize_adf("Hello") == "Hello"

    def test_dict(self):
        adf = {"version": 1, "type": "doc", "content": []}
        result = serialize_adf(adf)
        assert isinstance(result, str)
        assert json.loads(result) == adf


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


class TestRoundTrips:
    def test_adf_dict_roundtrip(self):
        """ADF dict -> serialize -> text_to_adf -> same structure."""
        original = {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hello "},
                        {"type": "text", "text": "world", "marks": [{"type": "strong"}]},
                    ],
                },
            ],
        }
        stored = serialize_adf(original)
        restored = text_to_adf(stored)
        assert restored == original

    def test_plain_text_roundtrip(self):
        """Plain text -> text_to_adf -> adf_to_text -> same text."""
        original = "Hello world"
        adf = text_to_adf(original)
        restored = adf_to_text(adf)
        assert restored == original

    def test_multiline_roundtrip(self):
        """Multi-line plain text round-trips correctly."""
        original = "Line 1\nLine 2\nLine 3"
        adf = text_to_adf(original)
        restored = adf_to_text(adf)
        assert restored == original
