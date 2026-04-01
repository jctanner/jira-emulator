"""Transform a JQL Lark AST into SQLAlchemy filter/order-by expressions.

Usage::

    from jira_emulator.jql.parser import parse_jql
    from jira_emulator.jql.transformer import JQLTransformer

    tree = parse_jql("project = DEMO AND status != Closed ORDER BY created DESC")
    where_clauses, order_clauses = JQLTransformer().transform(tree, current_username="admin")
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import lark
from sqlalchemy import select, and_, or_, not_, exists
from sqlalchemy.sql import func

from jira_emulator.models.issue import Issue
from jira_emulator.models.project import Project
from jira_emulator.models.status import Status
from jira_emulator.models.issue_type import IssueType
from jira_emulator.models.priority import Priority
from jira_emulator.models.user import User
from jira_emulator.models.resolution import Resolution
from jira_emulator.models.label import Label
from jira_emulator.models.component import Component, IssueComponent
from jira_emulator.models.version import Version, IssueFixVersion, IssueAffectsVersion
from jira_emulator.models.comment import Comment
from jira_emulator.models.custom_field import CustomField, IssueCustomFieldValue
from jira_emulator.models.sprint import Sprint, IssueSprint

from jira_emulator.jql.functions import resolve_function

import re


class JQLTransformer:
    """Walk a Lark parse-tree produced by ``parse_jql`` and emit SQLAlchemy
    filter expressions against the ``issues`` table.
    """

    def __init__(self) -> None:
        self._current_username: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transform(
        self,
        tree: lark.Tree,
        current_username: str | None = None,
    ) -> tuple[list, list]:
        """Return ``(where_clauses, order_by_clauses)`` for use with
        ``select(Issue).where(...).order_by(...)``.

        Parameters
        ----------
        tree:
            The AST produced by ``parse_jql()``.
        current_username:
            Username of the authenticated user (for ``currentUser()``).
        """
        self._current_username = current_username

        where_clauses: list = []
        order_by_clauses: list = []

        for child in tree.children:
            if child is None:
                continue
            if isinstance(child, lark.Tree):
                if child.data == "order_by_clause":
                    order_by_clauses = self._process_order_by(child)
                else:
                    clause = self._process_node(child)
                    if clause is not None:
                        where_clauses.append(clause)
            # Token children at top level are ignored

        return where_clauses, order_by_clauses

    # ------------------------------------------------------------------
    # Recursive AST walker
    # ------------------------------------------------------------------

    def _process_node(self, node: lark.Tree):
        """Dispatch on the node's ``data`` attribute."""
        handler_name = f"_handle_{node.data}"
        handler = getattr(self, handler_name, None)
        if handler is not None:
            return handler(node)

        # For expression nodes that just wrap children (or_expr, and_expr, etc.)
        # produced by Lark inlining (?), we should not normally reach here
        # because the grammar uses "?" aliases.  But if we do, process children.
        results = []
        for child in node.children:
            if isinstance(child, lark.Tree):
                r = self._process_node(child)
                if r is not None:
                    results.append(r)
        if len(results) == 1:
            return results[0]
        if results:
            return and_(*results)
        return None

    # ------------------------------------------------------------------
    # Boolean connectives
    # ------------------------------------------------------------------

    def _handle_or_expr(self, node: lark.Tree):
        parts = []
        for child in node.children:
            if isinstance(child, lark.Tree):
                r = self._process_node(child)
                if r is not None:
                    parts.append(r)
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return or_(*parts)

    def _handle_and_expr(self, node: lark.Tree):
        parts = []
        for child in node.children:
            if isinstance(child, lark.Tree):
                r = self._process_node(child)
                if r is not None:
                    parts.append(r)
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return and_(*parts)

    def _handle_not_clause(self, node: lark.Tree):
        inner = None
        for child in node.children:
            if isinstance(child, lark.Tree):
                inner = self._process_node(child)
        if inner is None:
            return None
        return not_(inner)

    def _handle_paren_group(self, node: lark.Tree):
        for child in node.children:
            if isinstance(child, lark.Tree):
                return self._process_node(child)
        return None

    # ------------------------------------------------------------------
    # Clause handlers
    # ------------------------------------------------------------------

    def _handle_comparison_clause(self, node: lark.Tree):
        """``field OP value``"""
        field_name = self._extract_field(node.children[0])
        op = self._extract_op(node.children[1])
        value = self._extract_value(node.children[2])
        return self._build_comparison(field_name, op, value)

    def _handle_in_clause(self, node: lark.Tree):
        """``field IN (v1, v2, ...)``"""
        field_name = self._extract_field(node.children[0])
        # Find the value_list child (skip KW_IN token)
        value_list_node = self._find_child_tree(node, "value_list")
        values = self._extract_value_list(value_list_node)
        return self._build_in(field_name, values, negate=False)

    def _handle_not_in_clause(self, node: lark.Tree):
        """``field NOT IN (v1, v2, ...)``"""
        field_name = self._extract_field(node.children[0])
        # Find the value_list child (skip NOT_IN token)
        value_list_node = self._find_child_tree(node, "value_list")
        values = self._extract_value_list(value_list_node)
        return self._build_in(field_name, values, negate=True)

    def _handle_is_empty_clause(self, node: lark.Tree):
        field_name = self._extract_field(node.children[0])
        return self._build_is_empty(field_name, negate=False)

    def _handle_is_not_empty_clause(self, node: lark.Tree):
        field_name = self._extract_field(node.children[0])
        return self._build_is_empty(field_name, negate=True)

    def _handle_is_null_clause(self, node: lark.Tree):
        field_name = self._extract_field(node.children[0])
        return self._build_is_empty(field_name, negate=False)

    def _handle_is_not_null_clause(self, node: lark.Tree):
        field_name = self._extract_field(node.children[0])
        return self._build_is_empty(field_name, negate=True)

    # ------------------------------------------------------------------
    # Extractors
    # ------------------------------------------------------------------

    @staticmethod
    def _find_child_tree(node: lark.Tree, data_name: str) -> lark.Tree:
        """Find the first child Tree with the given data name."""
        for child in node.children:
            if isinstance(child, lark.Tree) and child.data == data_name:
                return child
        raise ValueError(f"Expected child tree '{data_name}' not found")

    def _extract_field(self, node) -> str:
        """Return the normalised field name string."""
        if isinstance(node, lark.Token):
            return self._normalise_field(str(node))
        if isinstance(node, lark.Tree):
            if node.data == "plain_field":
                return self._normalise_field(str(node.children[0]))
            if node.data == "quoted_field":
                return self._normalise_field(self._unquote(str(node.children[0])))
            if node.data == "cf_field":
                # cf[12345] → "cf[12345]"
                return str(node.children[0]).strip()
        return str(node)

    def _extract_op(self, node) -> str:
        """Return the operator as a normalised string."""
        if isinstance(node, lark.Tree):
            return node.data  # e.g. "op_eq", "op_ne", ...
        return str(node)

    def _extract_value(self, node) -> Any:
        """Resolve a value node to a Python value."""
        if isinstance(node, lark.Token):
            return self._token_to_value(node)

        if isinstance(node, lark.Tree):
            if node.data == "quoted_string":
                return self._unquote(str(node.children[0]))
            if node.data == "unquoted_value":
                return str(node.children[0])
            if node.data == "number_value":
                text = str(node.children[0])
                if "." in text:
                    return float(text)
                return int(text)
            if node.data == "empty_value":
                return None
            if node.data == "null_value":
                return None
            if node.data == "function_call":
                return self._resolve_func(node)
            # Recurse for wrapped trees
            if node.children:
                return self._extract_value(node.children[0])

        return str(node)

    def _extract_value_list(self, node: lark.Tree) -> list:
        """Extract list of values from a ``value_list`` node."""
        values = []
        for child in node.children:
            if isinstance(child, lark.Token):
                # Skip punctuation tokens that aren't meaningful values
                if child.type in ("LPAR", "RPAR", "COMMA", "__ANON_0", "__ANON_1"):
                    continue
                values.append(self._token_to_value(child))
            elif isinstance(child, lark.Tree):
                values.append(self._extract_value(child))
        return values

    def _resolve_func(self, node: lark.Tree):
        """Resolve a function_call node."""
        func_name = str(node.children[0])
        args: list = []
        for child in node.children[1:]:
            if isinstance(child, lark.Tree) and child.data == "func_args":
                for arg_child in child.children:
                    args.append(self._extract_value(arg_child))
        return resolve_function(func_name, args, self._current_username)

    @staticmethod
    def _unquote(s: str) -> str:
        """Remove surrounding quotes and unescape inner characters."""
        if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
            inner = s[1:-1]
            return inner.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")
        return s

    @staticmethod
    def _token_to_value(token: lark.Token):
        if token.type == "SIGNED_NUMBER":
            text = str(token)
            return float(text) if "." in text else int(text)
        if token.type in ("DOUBLE_QUOTED_STRING", "SINGLE_QUOTED_STRING"):
            return JQLTransformer._unquote(str(token))
        if token.type == "EMPTY_KW":
            return None
        if token.type == "NULL_KW":
            return None
        return str(token)

    @staticmethod
    def _normalise_field(name: str) -> str:
        """Normalise a JQL field name to a canonical lowercase form."""
        return name.strip().lower()

    # ------------------------------------------------------------------
    # Field -> Column/Subquery mapping
    # ------------------------------------------------------------------

    # Fields that map to a direct column on Issue
    _DIRECT_COLUMNS = {
        "summary": Issue.summary,
        "description": Issue.description,
        "key": Issue.key,
        "issuekey": Issue.key,
        "created": Issue.created_at,
        "updated": Issue.updated_at,
        "due": Issue.due_date,
        "duedate": Issue.due_date,
    }

    # Fields that are FK lookups: field_name -> (fk_column, lookup_model, lookup_column)
    _LOOKUP_FIELDS: dict[str, tuple] = {
        "project": (Issue.project_id, Project, Project.key),
        "status": (Issue.status_id, Status, Status.name),
        "issuetype": (Issue.issue_type_id, IssueType, IssueType.name),
        "type": (Issue.issue_type_id, IssueType, IssueType.name),
        "priority": (Issue.priority_id, Priority, Priority.name),
        "assignee": (Issue.assignee_id, User, User.username),
        "reporter": (Issue.reporter_id, User, User.username),
        "resolution": (Issue.resolution_id, Resolution, Resolution.name),
    }

    def _get_column(self, field_name: str):
        """Return the SQLAlchemy column for a direct-column field, or None."""
        return self._DIRECT_COLUMNS.get(field_name)

    # ------------------------------------------------------------------
    # Build filter expressions
    # ------------------------------------------------------------------

    def _build_comparison(self, field: str, op: str, value):
        """Build a single comparison clause."""

        # --- Direct column fields ---
        col = self._get_column(field)
        if col is not None:
            return self._apply_op_to_column(col, op, value, field)

        # --- FK lookup fields ---
        lookup = self._LOOKUP_FIELDS.get(field)
        if lookup is not None:
            fk_col, model, lookup_col = lookup
            return self._apply_lookup_op(fk_col, model, lookup_col, op, value, field)

        # --- text (combined summary + description) ---
        if field == "text":
            return self._build_text_search(op, value)

        # --- labels ---
        if field == "labels":
            return self._build_label_clause(op, value)

        # --- component ---
        if field == "component":
            return self._build_component_clause(op, value)

        # --- fixversion ---
        if field in ("fixversion", "fixversions"):
            return self._build_fix_version_clause(op, value)

        # --- affectedversion ---
        if field in ("affectedversion", "affectedversions"):
            return self._build_affects_version_clause(op, value)

        # --- parent ---
        if field == "parent":
            return self._build_parent_clause(op, value)

        # --- statusCategory ---
        if field == "statuscategory":
            return self._build_status_category_clause(op, value)

        # --- comment ---
        if field == "comment":
            return self._build_comment_clause(op, value)

        # --- cf[NNNNN] custom field reference ---
        cf_match = re.match(r"^cf\[(\d+)\]$", field, re.IGNORECASE)
        if cf_match:
            field_id = f"customfield_{cf_match.group(1)}"
            return self._build_custom_field_clause(op, value, field_id)

        # --- customfield_NNNNN ---
        if field.startswith("customfield_"):
            return self._build_custom_field_clause(op, value, field)

        # --- sprint ---
        if field == "sprint":
            return self._build_sprint_clause(op, value)

        raise ValueError(f"Unsupported JQL field: '{field}'")

    # --- Operator application helpers ---

    def _apply_op_to_column(self, col, op: str, value, field: str = ""):
        """Apply *op* to a direct column."""
        if op == "op_eq":
            if value is None:
                return col.is_(None)
            if self._is_text_column(field):
                return func.lower(col) == func.lower(str(value))
            return col == value
        if op == "op_ne":
            if value is None:
                return col.isnot(None)
            if self._is_text_column(field):
                return func.lower(col) != func.lower(str(value))
            return col != value
        if op == "op_contains":
            return col.ilike(f"%{value}%")
        if op == "op_not_contains":
            return ~col.ilike(f"%{value}%")
        if op == "op_gt":
            return col > value
        if op == "op_gte":
            return col >= value
        if op == "op_lt":
            return col < value
        if op == "op_lte":
            return col <= value
        raise ValueError(f"Unsupported operator: {op}")

    @staticmethod
    def _is_text_column(field: str) -> bool:
        return field in ("summary", "description", "key", "issuekey")

    def _apply_lookup_op(self, fk_col, model, lookup_col, op: str, value, field: str):
        """Build a subquery-based filter for FK lookup fields."""
        if value is None:
            # IS NULL / IS EMPTY semantics
            if op in ("op_eq",):
                return fk_col.is_(None)
            if op in ("op_ne",):
                return fk_col.isnot(None)

        if op == "op_eq":
            return fk_col.in_(
                select(model.id).where(func.lower(lookup_col) == func.lower(str(value)))
            )
        if op == "op_ne":
            return ~fk_col.in_(
                select(model.id).where(func.lower(lookup_col) == func.lower(str(value)))
            )
        if op == "op_contains":
            return fk_col.in_(
                select(model.id).where(lookup_col.ilike(f"%{value}%"))
            )
        if op == "op_not_contains":
            return ~fk_col.in_(
                select(model.id).where(lookup_col.ilike(f"%{value}%"))
            )

        raise ValueError(
            f"Operator '{op}' is not supported for lookup field '{field}'"
        )

    # --- text (summary OR description) ---

    def _build_text_search(self, op: str, value):
        if op in ("op_contains", "op_eq"):
            return or_(
                Issue.summary.ilike(f"%{value}%"),
                Issue.description.ilike(f"%{value}%"),
            )
        if op in ("op_not_contains", "op_ne"):
            return and_(
                ~Issue.summary.ilike(f"%{value}%"),
                or_(
                    Issue.description.is_(None),
                    ~Issue.description.ilike(f"%{value}%"),
                ),
            )
        raise ValueError(f"Operator '{op}' is not supported for 'text' field")

    # --- labels ---

    def _build_label_clause(self, op: str, value):
        label_exists = exists(
            select(Label.id).where(
                Label.issue_id == Issue.id,
                func.lower(Label.label) == func.lower(str(value)),
            )
        )
        if op == "op_eq":
            return label_exists
        if op == "op_ne":
            return ~label_exists
        raise ValueError(f"Operator '{op}' is not supported for 'labels' field")

    # --- component ---

    def _build_component_clause(self, op: str, value):
        comp_exists = exists(
            select(IssueComponent.issue_id).where(
                IssueComponent.issue_id == Issue.id,
                IssueComponent.component_id.in_(
                    select(Component.id).where(
                        func.lower(Component.name) == func.lower(str(value))
                    )
                ),
            )
        )
        if op == "op_eq":
            return comp_exists
        if op == "op_ne":
            return ~comp_exists
        raise ValueError(f"Operator '{op}' is not supported for 'component' field")

    # --- fixVersion ---

    def _build_fix_version_clause(self, op: str, value):
        fv_exists = exists(
            select(IssueFixVersion.issue_id).where(
                IssueFixVersion.issue_id == Issue.id,
                IssueFixVersion.version_id.in_(
                    select(Version.id).where(
                        func.lower(Version.name) == func.lower(str(value))
                    )
                ),
            )
        )
        if op == "op_eq":
            return fv_exists
        if op == "op_ne":
            return ~fv_exists
        raise ValueError(
            f"Operator '{op}' is not supported for 'fixVersion' field"
        )

    # --- affectedVersion ---

    def _build_affects_version_clause(self, op: str, value):
        av_exists = exists(
            select(IssueAffectsVersion.issue_id).where(
                IssueAffectsVersion.issue_id == Issue.id,
                IssueAffectsVersion.version_id.in_(
                    select(Version.id).where(
                        func.lower(Version.name) == func.lower(str(value))
                    )
                ),
            )
        )
        if op == "op_eq":
            return av_exists
        if op == "op_ne":
            return ~av_exists
        raise ValueError(
            f"Operator '{op}' is not supported for 'affectedVersion' field"
        )

    # --- parent ---

    def _build_parent_clause(self, op: str, value):
        """``parent = PROJ-123``  ->  look up the parent issue by key."""
        parent_subq = select(Issue.id).where(Issue.key == str(value)).scalar_subquery()
        if op == "op_eq":
            return Issue.parent_id == parent_subq
        if op == "op_ne":
            return Issue.parent_id != parent_subq
        raise ValueError(f"Operator '{op}' is not supported for 'parent' field")

    # --- statusCategory ---

    # Map JQL statusCategory display names to the internal category values
    _STATUS_CATEGORY_MAP: dict[str, str] = {
        "to do": "new",
        "new": "new",
        "in progress": "indeterminate",
        "indeterminate": "indeterminate",
        "done": "done",
        "complete": "done",
    }

    def _resolve_status_category(self, value) -> str:
        """Map a JQL statusCategory value to the internal category string."""
        mapped = self._STATUS_CATEGORY_MAP.get(str(value).lower())
        if mapped is None:
            # Fall back to the raw value lowercased
            return str(value).lower()
        return mapped

    def _build_status_category_clause(self, op: str, value):
        category = self._resolve_status_category(value)
        subq = select(Status.id).where(func.lower(Status.category) == category)
        if op == "op_eq":
            return Issue.status_id.in_(subq)
        if op == "op_ne":
            return ~Issue.status_id.in_(subq)
        raise ValueError(
            f"Operator '{op}' is not supported for 'statusCategory' field"
        )

    # --- comment ---

    def _build_comment_clause(self, op: str, value):
        if op in ("op_contains", "op_eq"):
            return exists(
                select(Comment.id).where(
                    Comment.issue_id == Issue.id,
                    Comment.body.ilike(f"%{value}%"),
                )
            )
        if op in ("op_not_contains", "op_ne"):
            return ~exists(
                select(Comment.id).where(
                    Comment.issue_id == Issue.id,
                    Comment.body.ilike(f"%{value}%"),
                )
            )
        raise ValueError(f"Operator '{op}' is not supported for 'comment' field")

    # --- custom fields (cf[NNNNN] / customfield_NNNNN) ---

    def _build_custom_field_clause(self, op: str, value, field_id: str):
        cf_subq = select(CustomField.id).where(CustomField.field_id == field_id)
        if op == "op_eq":
            return exists(
                select(IssueCustomFieldValue.id).where(
                    IssueCustomFieldValue.issue_id == Issue.id,
                    IssueCustomFieldValue.custom_field_id.in_(cf_subq),
                    func.lower(IssueCustomFieldValue.value_string) == func.lower(str(value)),
                )
            )
        if op == "op_ne":
            return ~exists(
                select(IssueCustomFieldValue.id).where(
                    IssueCustomFieldValue.issue_id == Issue.id,
                    IssueCustomFieldValue.custom_field_id.in_(cf_subq),
                    func.lower(IssueCustomFieldValue.value_string) == func.lower(str(value)),
                )
            )
        if op in ("op_contains",):
            return exists(
                select(IssueCustomFieldValue.id).where(
                    IssueCustomFieldValue.issue_id == Issue.id,
                    IssueCustomFieldValue.custom_field_id.in_(cf_subq),
                    IssueCustomFieldValue.value_string.ilike(f"%{value}%"),
                )
            )
        if op in ("op_not_contains",):
            return ~exists(
                select(IssueCustomFieldValue.id).where(
                    IssueCustomFieldValue.issue_id == Issue.id,
                    IssueCustomFieldValue.custom_field_id.in_(cf_subq),
                    IssueCustomFieldValue.value_string.ilike(f"%{value}%"),
                )
            )
        raise ValueError(
            f"Operator '{op}' is not supported for custom field '{field_id}'"
        )

    # --- sprint ---

    def _build_sprint_clause(self, op: str, value):
        sprint_exists = exists(
            select(IssueSprint.issue_id).where(
                IssueSprint.issue_id == Issue.id,
                IssueSprint.sprint_id.in_(
                    select(Sprint.id).where(
                        func.lower(Sprint.name) == func.lower(str(value))
                    )
                ),
            )
        )
        if op == "op_eq":
            return sprint_exists
        if op == "op_ne":
            return ~sprint_exists
        raise ValueError(f"Operator '{op}' is not supported for 'sprint' field")

    # ------------------------------------------------------------------
    # IN / NOT IN
    # ------------------------------------------------------------------

    def _build_in(self, field: str, values: list, *, negate: bool):
        """Build IN or NOT IN expressions."""

        # Direct columns
        col = self._get_column(field)
        if col is not None:
            str_values = [str(v) for v in values if v is not None]
            has_null = any(v is None for v in values)
            parts = []
            if str_values:
                if self._is_text_column(field):
                    lower_vals = [func.lower(v) for v in str_values]
                    expr = func.lower(col).in_(lower_vals)
                else:
                    expr = col.in_(str_values)
                parts.append(~expr if negate else expr)
            if has_null:
                parts.append(col.isnot(None) if negate else col.is_(None))
            if not parts:
                # Empty list -- no match
                return col.is_(None) if not negate else col.isnot(None)
            return and_(*parts) if negate else or_(*parts)

        # FK lookup fields
        lookup = self._LOOKUP_FIELDS.get(field)
        if lookup is not None:
            fk_col, model, lookup_col = lookup
            str_values = [str(v) for v in values if v is not None]
            has_null = any(v is None for v in values)
            parts = []
            if str_values:
                lower_vals = [func.lower(v) for v in str_values]
                subq = select(model.id).where(func.lower(lookup_col).in_(lower_vals))
                expr = fk_col.in_(subq)
                parts.append(~expr if negate else expr)
            if has_null:
                parts.append(fk_col.isnot(None) if negate else fk_col.is_(None))
            if not parts:
                return fk_col.is_(None) if not negate else fk_col.isnot(None)
            return and_(*parts) if negate else or_(*parts)

        # Labels -- IN means issue has at least one of the labels
        if field == "labels":
            exprs = []
            for v in values:
                e = exists(
                    select(Label.id).where(
                        Label.issue_id == Issue.id,
                        func.lower(Label.label) == func.lower(str(v)),
                    )
                )
                exprs.append(~e if negate else e)
            return and_(*exprs) if negate else or_(*exprs)

        # Component IN
        if field == "component":
            str_values = [str(v) for v in values]
            lower_vals = [func.lower(v) for v in str_values]
            comp_exists = exists(
                select(IssueComponent.issue_id).where(
                    IssueComponent.issue_id == Issue.id,
                    IssueComponent.component_id.in_(
                        select(Component.id).where(
                            func.lower(Component.name).in_(lower_vals)
                        )
                    ),
                )
            )
            return ~comp_exists if negate else comp_exists

        # fixVersion IN
        if field in ("fixversion", "fixversions"):
            str_values = [str(v) for v in values]
            lower_vals = [func.lower(v) for v in str_values]
            fv_exists = exists(
                select(IssueFixVersion.issue_id).where(
                    IssueFixVersion.issue_id == Issue.id,
                    IssueFixVersion.version_id.in_(
                        select(Version.id).where(
                            func.lower(Version.name).in_(lower_vals)
                        )
                    ),
                )
            )
            return ~fv_exists if negate else fv_exists

        # statusCategory IN
        if field == "statuscategory":
            categories = [self._resolve_status_category(v) for v in values]
            subq = select(Status.id).where(func.lower(Status.category).in_(categories))
            expr = Issue.status_id.in_(subq)
            return ~expr if negate else expr

        # sprint IN
        if field == "sprint":
            lower_vals = [func.lower(str(v)) for v in values]
            sprint_exists = exists(
                select(IssueSprint.issue_id).where(
                    IssueSprint.issue_id == Issue.id,
                    IssueSprint.sprint_id.in_(
                        select(Sprint.id).where(
                            func.lower(Sprint.name).in_(lower_vals)
                        )
                    ),
                )
            )
            return ~sprint_exists if negate else sprint_exists

        # cf[NNNNN] IN
        cf_match = re.match(r"^cf\[(\d+)\]$", field, re.IGNORECASE)
        if cf_match:
            field_id = f"customfield_{cf_match.group(1)}"
            return self._build_custom_field_in(field_id, values, negate)

        # customfield_NNNNN IN
        if field.startswith("customfield_"):
            return self._build_custom_field_in(field, values, negate)

        raise ValueError(f"Unsupported JQL field for IN operator: '{field}'")

    def _build_custom_field_in(self, field_id: str, values: list, negate: bool):
        """Build IN / NOT IN for custom field values."""
        cf_subq = select(CustomField.id).where(CustomField.field_id == field_id)
        lower_vals = [func.lower(str(v)) for v in values]
        cf_exists = exists(
            select(IssueCustomFieldValue.id).where(
                IssueCustomFieldValue.issue_id == Issue.id,
                IssueCustomFieldValue.custom_field_id.in_(cf_subq),
                func.lower(IssueCustomFieldValue.value_string).in_(lower_vals),
            )
        )
        return ~cf_exists if negate else cf_exists

    # ------------------------------------------------------------------
    # IS EMPTY / IS NOT EMPTY
    # ------------------------------------------------------------------

    def _build_is_empty(self, field: str, *, negate: bool):
        """Build IS EMPTY / IS NOT EMPTY / IS NULL / IS NOT NULL."""

        # Direct columns
        col = self._get_column(field)
        if col is not None:
            return col.isnot(None) if negate else col.is_(None)

        # FK lookup fields (resolution IS EMPTY -> resolution_id IS NULL)
        lookup = self._LOOKUP_FIELDS.get(field)
        if lookup is not None:
            fk_col = lookup[0]
            return fk_col.isnot(None) if negate else fk_col.is_(None)

        # Labels IS EMPTY -> no labels exist
        if field == "labels":
            label_exists = exists(
                select(Label.id).where(Label.issue_id == Issue.id)
            )
            return label_exists if negate else ~label_exists

        # Component IS EMPTY
        if field == "component":
            comp_exists = exists(
                select(IssueComponent.issue_id).where(
                    IssueComponent.issue_id == Issue.id
                )
            )
            return comp_exists if negate else ~comp_exists

        # fixVersion IS EMPTY
        if field in ("fixversion", "fixversions"):
            fv_exists = exists(
                select(IssueFixVersion.issue_id).where(
                    IssueFixVersion.issue_id == Issue.id
                )
            )
            return fv_exists if negate else ~fv_exists

        # statusCategory IS EMPTY -- status has no category set
        if field == "statuscategory":
            # Check if the issue's status has a null/empty category
            subq = select(Status.id).where(
                Status.id == Issue.status_id,
                or_(Status.category.is_(None), Status.category == ""),
            )
            empty_expr = exists(subq)
            return ~empty_expr if negate else empty_expr

        # sprint IS EMPTY -- issue has no sprint associations
        if field == "sprint":
            sprint_exists = exists(
                select(IssueSprint.issue_id).where(
                    IssueSprint.issue_id == Issue.id
                )
            )
            return sprint_exists if negate else ~sprint_exists

        # cf[NNNNN] IS EMPTY
        cf_match = re.match(r"^cf\[(\d+)\]$", field, re.IGNORECASE)
        if cf_match:
            field_id = f"customfield_{cf_match.group(1)}"
            return self._build_custom_field_is_empty(field_id, negate)

        # customfield_NNNNN IS EMPTY
        if field.startswith("customfield_"):
            return self._build_custom_field_is_empty(field, negate)

        raise ValueError(f"Unsupported JQL field for IS EMPTY: '{field}'")

    def _build_custom_field_is_empty(self, field_id: str, negate: bool):
        """Build IS EMPTY / IS NOT EMPTY for a custom field."""
        cf_subq = select(CustomField.id).where(CustomField.field_id == field_id)
        cf_exists = exists(
            select(IssueCustomFieldValue.id).where(
                IssueCustomFieldValue.issue_id == Issue.id,
                IssueCustomFieldValue.custom_field_id.in_(cf_subq),
                IssueCustomFieldValue.value_string.isnot(None),
            )
        )
        return cf_exists if negate else ~cf_exists

    # ------------------------------------------------------------------
    # ORDER BY
    # ------------------------------------------------------------------

    # Mapping of field names to columns usable in ORDER BY
    _ORDER_BY_COLUMNS: dict[str, Any] = {
        "key": Issue.key,
        "issuekey": Issue.key,
        "summary": Issue.summary,
        "created": Issue.created_at,
        "updated": Issue.updated_at,
        "due": Issue.due_date,
        "duedate": Issue.due_date,
        "priority": Issue.priority_id,
        "status": Issue.status_id,
        "assignee": Issue.assignee_id,
        "reporter": Issue.reporter_id,
        "resolution": Issue.resolution_id,
        "issuetype": Issue.issue_type_id,
        "type": Issue.issue_type_id,
        "project": Issue.project_id,
    }

    def _process_order_by(self, node: lark.Tree) -> list:
        """Process an ``order_by_clause`` node and return a list of
        SQLAlchemy order-by column expressions.
        """
        result = []
        for child in node.children:
            if isinstance(child, lark.Tree) and child.data == "order_by_field":
                field_name = self._extract_field(child.children[0])
                direction = "asc"  # default
                for sub in child.children[1:]:
                    if isinstance(sub, lark.Token):
                        if sub.type == "DESC":
                            direction = "desc"
                        elif sub.type == "ASC":
                            direction = "asc"

                col = self._ORDER_BY_COLUMNS.get(field_name)
                if col is None:
                    raise ValueError(
                        f"Cannot ORDER BY unsupported field: '{field_name}'"
                    )

                if direction == "desc":
                    result.append(col.desc())
                else:
                    result.append(col.asc())

        return result
