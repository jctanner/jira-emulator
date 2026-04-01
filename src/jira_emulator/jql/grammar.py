"""Lark EBNF grammar for JQL (Jira Query Language) — Phase 1 subset.

Supports:
- AND / OR boolean connectives (case-insensitive)
- NOT prefix operator
- Parenthesized grouping
- Comparison operators: =, !=, ~, !~, >, >=, <, <=
- Membership operators: IN, NOT IN
- Empty/null operators: IS EMPTY, IS NOT EMPTY, IS NULL, IS NOT NULL
- ORDER BY with multiple fields and ASC/DESC
- Quoted strings, unquoted identifiers (including dotted like RHAIRFE-123),
  numbers (int/float), EMPTY, NULL
- Value lists: (val1, val2, ...)
- Function calls: functionName() or functionName(arg1, arg2)
- Field names: alphanumeric with dots/underscores, cf[12345], quoted names
"""

JQL_GRAMMAR = r"""
    start: query order_by_clause?
         | order_by_clause

    // -------------------------------------------------------------------
    // Boolean expression hierarchy
    // -------------------------------------------------------------------
    ?query: or_expr

    ?or_expr: and_expr (OR and_expr)*
    ?and_expr: not_expr (AND not_expr)*
    ?not_expr: NOT not_expr   -> not_clause
             | atom

    ?atom: "(" or_expr ")"    -> paren_group
         | clause

    // -------------------------------------------------------------------
    // Individual clauses
    // -------------------------------------------------------------------
    clause: field IS_NOT_EMPTY                    -> is_not_empty_clause
          | field IS_EMPTY                        -> is_empty_clause
          | field IS_NOT_NULL                     -> is_not_null_clause
          | field IS_NULL                         -> is_null_clause
          | field NOT_IN value_list               -> not_in_clause
          | field KW_IN value_list                -> in_clause
          | field compare_op value                -> comparison_clause

    compare_op: ">="  -> op_gte
              | "<="  -> op_lte
              | "!="  -> op_ne
              | "!~"  -> op_not_contains
              | "="   -> op_eq
              | "~"   -> op_contains
              | ">"   -> op_gt
              | "<"   -> op_lt

    // -------------------------------------------------------------------
    // Values
    // -------------------------------------------------------------------
    ?value: function_call
          | DOUBLE_QUOTED_STRING  -> quoted_string
          | SINGLE_QUOTED_STRING  -> quoted_string
          | SIGNED_NUMBER         -> number_value
          | EMPTY_KW              -> empty_value
          | NULL_KW               -> null_value
          | UNQUOTED_VALUE        -> unquoted_value

    value_list: "(" value ("," value)* ")"

    function_call: FUNC_NAME "(" func_args? ")"

    func_args: value ("," value)*

    // -------------------------------------------------------------------
    // Field names
    // -------------------------------------------------------------------
    ?field: CF_FIELD               -> cf_field
          | DOUBLE_QUOTED_STRING   -> quoted_field
          | FIELD_NAME             -> plain_field

    // -------------------------------------------------------------------
    // ORDER BY
    // -------------------------------------------------------------------
    order_by_clause: ORDER_BY order_by_field ("," order_by_field)*

    order_by_field: field (ASC | DESC)?

    // -------------------------------------------------------------------
    // Case-insensitive keyword terminals
    //
    // Multi-word keywords must be matched BEFORE single-word variants.
    // The ordering here and priority numbers ensure Lark resolves
    // correctly.
    // -------------------------------------------------------------------
    IS_NOT_EMPTY.4: /IS\s+NOT\s+EMPTY/i
    IS_EMPTY.3: /IS\s+EMPTY/i
    IS_NOT_NULL.4: /IS\s+NOT\s+NULL/i
    IS_NULL.3: /IS\s+NULL/i
    NOT_IN.3: /NOT\s+IN/i
    ORDER_BY.3: /ORDER\s+BY/i

    AND.2: /AND/i
    OR.2: /OR/i
    NOT.2: /NOT/i
    KW_IN.2: /IN/i
    ASC.2: /ASC/i
    DESC.2: /DESC/i

    EMPTY_KW.1: /EMPTY/i
    NULL_KW.1: /NULL/i

    // -------------------------------------------------------------------
    // Lexer terminals
    // -------------------------------------------------------------------

    // Double-quoted strings: handle escaped quotes inside
    DOUBLE_QUOTED_STRING: "\"" /([^"\\]|\\.)*/ "\""

    // Single-quoted strings: handle escaped quotes inside
    SINGLE_QUOTED_STRING: "'" /([^'\\]|\\.)*/ "'"

    // Custom field references: cf[12345]
    CF_FIELD: /cf\[\d+\]/

    // Function name: identifier immediately followed by "("
    // The lookahead (?=\() ensures this only matches when a "(" follows
    FUNC_NAME: /[a-zA-Z_][a-zA-Z0-9_]*(?=\s*\()/

    // Field names: identifiers that may contain dots and underscores
    FIELD_NAME: /[a-zA-Z_][a-zA-Z0-9_.]*/

    // Unquoted value: identifiers that may include letters, digits, hyphens,
    // dots, underscores — broad enough to match project keys like RHAIRFE-123
    UNQUOTED_VALUE: /[a-zA-Z0-9][a-zA-Z0-9._\-]*/

    SIGNED_NUMBER: /[+-]?\d+(\.\d+)?/

    %import common.WS
    %ignore WS
"""
