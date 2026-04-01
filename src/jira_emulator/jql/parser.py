"""JQL parser — thin wrapper around a Lark grammar.

Usage::

    from jira_emulator.jql.parser import parse_jql

    tree = parse_jql('project = DEMO AND status = Open ORDER BY created DESC')
"""

from __future__ import annotations

import lark
from lark import Lark

from jira_emulator.jql.grammar import JQL_GRAMMAR

# Singleton Lark parser instance — Earley can handle the ambiguity of
# keywords appearing as values.
_parser = Lark(
    JQL_GRAMMAR,
    parser="earley",
    start="start",
    ambiguity="resolve",
)


def parse_jql(jql_string: str) -> lark.Tree:
    """Parse a JQL string and return the Lark AST tree.

    Raises ``ValueError`` with a descriptive message on parse failure.
    """
    if not jql_string or not jql_string.strip():
        raise ValueError("JQL query string must not be empty")

    try:
        return _parser.parse(jql_string)
    except lark.exceptions.LarkError as exc:
        raise ValueError(f"Invalid JQL: {exc}") from exc
