#!/usr/bin/env python3
"""
ISONQL - Pure Property Graph Query Language for ISONGraph

A declarative query language for property graph operations.

Supported Query Types:
- NODES: Select and filter nodes
- EDGES: Select and filter edges
- TRAVERSE: Graph traversal with patterns
- PATH: Shortest path finding
- COUNT: Count nodes matching criteria
- SUM/AVG/MIN/MAX: Numeric aggregations

Usage:
    from ison_graph import ISONGraph
    from ison_graph.query import QueryEngine

    graph = ISONGraph()
    graph.add_node('person', 'alice', name='Alice', age=30)
    graph.add_node('person', 'bob', name='Bob', age=25)
    graph.add_edge('KNOWS', ('person', 'alice'), ('person', 'bob'), since=2020)

    engine = QueryEngine(graph)

    # Execute ISONQL queries
    result = engine.execute("NODES person WHERE age > 25")
    result = engine.execute("TRAVERSE person:alice -> KNOWS -> person")
    result = engine.execute("PATH person:alice TO person:bob VIA KNOWS")
    result = engine.execute("COUNT person WHERE age > 20")
    result = engine.execute("AVG person.age")

    # Fluent API alternative
    result = (engine.match("person")
        .where("age", ">", 25)
        .order_by("name")
        .limit(10)
        .execute())

Author: Mahesh Vaikri
Version: 1.4.1
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import (
    Any, Dict, List, Optional, Set, Tuple,
    Union, Callable, Iterator
)
from enum import Enum

# Import from parent package - these will be available when used within ison_graph
try:
    from . import ISONGraph, Node, Edge, NodeRef, Direction, Path
except ImportError:
    # Fallback for standalone testing
    from ison_graph import ISONGraph, Node, Edge, NodeRef, Direction, Path

__version__ = "1.4.1"
__author__ = "Mahesh Vaikri"


# =============================================================================
# Enums and Types
# =============================================================================

class Operator(Enum):
    """Query operators for conditions."""
    EQ = "="
    NE = "!="
    GT = ">"
    GE = ">="
    LT = "<"
    LE = "<="
    IN = "IN"
    NOT_IN = "NOT IN"
    CONTAINS = "CONTAINS"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    MATCHES = "MATCHES"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"


class SortOrder(Enum):
    """Sort order for results."""
    ASC = "ASC"
    DESC = "DESC"


class QueryType(Enum):
    """Supported query types."""
    NODES = "NODES"
    EDGES = "EDGES"
    TRAVERSE = "TRAVERSE"
    PATH = "PATH"
    COUNT = "COUNT"
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Condition:
    """A query condition for filtering."""
    field: str
    operator: Operator
    value: Any

    def evaluate(self, properties: Dict[str, Any]) -> bool:
        """Evaluate condition against a properties dictionary."""
        # EXISTS / NOT_EXISTS checks
        if self.operator == Operator.EXISTS:
            return self.field in properties
        if self.operator == Operator.NOT_EXISTS:
            return self.field not in properties

        # Field must exist for other comparisons
        if self.field not in properties:
            return False

        prop_value = properties[self.field]

        # Comparison operators
        if self.operator == Operator.EQ:
            return prop_value == self.value
        elif self.operator == Operator.NE:
            return prop_value != self.value
        elif self.operator == Operator.GT:
            return prop_value > self.value
        elif self.operator == Operator.GE:
            return prop_value >= self.value
        elif self.operator == Operator.LT:
            return prop_value < self.value
        elif self.operator == Operator.LE:
            return prop_value <= self.value
        elif self.operator == Operator.IN:
            return prop_value in self.value
        elif self.operator == Operator.NOT_IN:
            return prop_value not in self.value
        elif self.operator == Operator.CONTAINS:
            return self.value in str(prop_value)
        elif self.operator == Operator.STARTS_WITH:
            return str(prop_value).startswith(self.value)
        elif self.operator == Operator.ENDS_WITH:
            return str(prop_value).endswith(self.value)
        elif self.operator == Operator.MATCHES:
            return bool(re.match(self.value, str(prop_value)))

        return False

    def __repr__(self) -> str:
        return f"{self.field} {self.operator.value} {self.value}"


@dataclass
class QueryResult:
    """Result of a query execution."""
    data: List[Any]
    count: int
    total_count: int
    execution_time_ms: float
    query: str
    query_type: str = ""

    def __repr__(self) -> str:
        return f"QueryResult(count={self.count}, total={self.total_count}, time={self.execution_time_ms:.2f}ms)"

    def __iter__(self):
        """Iterate over result data."""
        return iter(self.data)

    def __len__(self) -> int:
        return self.count

    def first(self) -> Optional[Any]:
        """Get first result or None."""
        return self.data[0] if self.data else None

    def to_list(self) -> List[Any]:
        """Return data as list."""
        return self.data


# =============================================================================
# ISONQL Parser
# =============================================================================

class ISONQLParser:
    """
    Parser for ISONQL (ISON Query Language).

    Supported Syntax:
    - NODES <type> [WHERE <conditions>] [ORDER BY <field> [ASC|DESC]] [LIMIT <n>] [OFFSET <n>]
    - EDGES [<type>] [WHERE <conditions>] [LIMIT <n>]
    - TRAVERSE <type>:<id> -> <rel> -> <target> [MAX <depth>] [LIMIT <n>]
    - PATH <source> TO <target> [VIA <rel>] [MAX <hops>]
    - COUNT <type> [WHERE <conditions>]
    - SUM/AVG/MIN/MAX <type>.<property> [WHERE <conditions>]
    """

    # Keywords recognized by the parser
    KEYWORDS = {
        'NODES', 'EDGES', 'TRAVERSE', 'PATH', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX',
        'WHERE', 'AND', 'OR', 'NOT', 'ORDER', 'BY', 'ASC', 'DESC', 'LIMIT', 'OFFSET',
        'TO', 'VIA', 'RETURN', 'AS', 'IN', 'CONTAINS', 'STARTS_WITH',
        'ENDS_WITH', 'MATCHES', 'EXISTS', 'TRUE', 'FALSE', 'NULL', 'NONE', 'NIL'
    }

    # Operator mappings
    OPERATORS = {
        '=': Operator.EQ,
        '==': Operator.EQ,
        '!=': Operator.NE,
        '<>': Operator.NE,
        '>': Operator.GT,
        '>=': Operator.GE,
        '<': Operator.LT,
        '<=': Operator.LE,
    }

    def __init__(self):
        self._tokens: List[str] = []
        self._pos: int = 0

    def parse(self, query: str) -> Dict[str, Any]:
        """Parse an ISONQL query string into a structured dictionary."""
        self._tokens = self._tokenize(query)
        self._pos = 0

        if not self._tokens:
            raise ValueError("Empty query")

        keyword = self._tokens[0].upper()

        if keyword == 'NODES':
            return self._parse_nodes_query()
        elif keyword == 'EDGES':
            return self._parse_edges_query()
        elif keyword == 'TRAVERSE':
            return self._parse_traverse_query()
        elif keyword == 'PATH':
            return self._parse_path_query()
        elif keyword == 'COUNT':
            return self._parse_count_query()
        elif keyword in ('SUM', 'AVG', 'MIN', 'MAX'):
            return self._parse_aggregation_query(keyword)
        else:
            raise ValueError(f"Unknown query type: {keyword}. "
                           f"Supported: NODES, EDGES, TRAVERSE, PATH, COUNT, SUM, AVG, MIN, MAX")

    def _tokenize(self, query: str) -> List[str]:
        """Tokenize query string into a list of tokens."""
        tokens = []
        i = 0
        query = query.strip()

        while i < len(query):
            # Skip whitespace
            if query[i].isspace():
                i += 1
                continue

            # String literals (single or double quoted)
            if query[i] in '"\'':
                quote = query[i]
                i += 1
                start = i
                while i < len(query) and query[i] != quote:
                    if query[i] == '\\' and i + 1 < len(query):
                        i += 2  # Skip escaped character
                    else:
                        i += 1
                tokens.append(query[start:i])
                i += 1  # Skip closing quote
                continue

            # Multi-character operators
            if i + 1 < len(query):
                two_char = query[i:i+2]
                if two_char in ('==', '!=', '>=', '<=', '<>', '->', '<-', '--'):
                    tokens.append(two_char)
                    i += 2
                    continue

            # Negative number literals (e.g. -5, -3.14)
            if query[i] == '-' and i + 1 < len(query) and query[i + 1].isdigit():
                start = i
                i += 1
                while i < len(query) and (query[i].isdigit() or query[i] == '.'):
                    i += 1
                tokens.append(query[start:i])
                continue

            # Single-character operators and punctuation
            if query[i] in '=<>!(),.*':
                tokens.append(query[i])
                i += 1
                continue

            # Node reference :type:id
            if query[i] == ':':
                start = i
                i += 1
                while i < len(query) and (query[i].isalnum() or query[i] in ':_-'):
                    i += 1
                tokens.append(query[start:i])
                continue

            # Words (identifiers, keywords, numbers, type:id node refs)
            if query[i].isalnum() or query[i] == '_':
                start = i
                while i < len(query):
                    ch = query[i]
                    if ch.isalnum() or ch in '_.-':
                        i += 1
                    elif ch == ':' and i + 1 < len(query) and (
                        query[i + 1].isalnum() or query[i + 1] == '_'
                    ):
                        # Keep type:id references as a single token
                        i += 1
                    else:
                        break
                tokens.append(query[start:i])
                continue

            raise ValueError(
                f"Unexpected character {query[i]!r} in query at position {i}"
            )

        return tokens

    def _current(self) -> Optional[str]:
        """Get current token without advancing."""
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _peek(self, offset: int = 0) -> Optional[str]:
        """Peek at token at specified offset."""
        pos = self._pos + offset
        if pos < len(self._tokens):
            return self._tokens[pos]
        return None

    def _advance(self) -> Optional[str]:
        """Advance position and return current token."""
        token = self._current()
        self._pos += 1
        return token

    def _expect(self, expected: str) -> str:
        """Expect and consume a specific token."""
        token = self._advance()
        if token is None or token.upper() != expected.upper():
            raise ValueError(f"Expected '{expected}', got '{token}'")
        return token

    def _match(self, *expected: str) -> bool:
        """Check if current token matches any of the expected values."""
        current = self._current()
        if current is None:
            return False
        return current.upper() in [e.upper() for e in expected]

    # -------------------------------------------------------------------------
    # Query Parsers
    # -------------------------------------------------------------------------

    def _parse_nodes_query(self) -> Dict[str, Any]:
        """Parse NODES query."""
        self._advance()  # Skip 'NODES'

        result = {
            'type': 'NODES',
            'node_type': None,
            'conditions': [],
            'order_by': None,
            'order_dir': 'ASC',
            'limit': None,
            'offset': None,
            'return_fields': None
        }

        # Node type (optional)
        if self._current() and not self._match('WHERE', 'ORDER', 'LIMIT', 'RETURN'):
            node_type = self._advance()
            # Handle shorthand: person(name="Alice")
            if self._match('('):
                self._advance()  # Skip '('
                result['node_type'] = node_type
                result['conditions'] = self._parse_shorthand_conditions()
            else:
                result['node_type'] = node_type

        # WHERE clause
        if self._match('WHERE'):
            self._advance()
            result['conditions'] = self._merge_condition_sets(
                result['conditions'], self._parse_conditions()
            )

        # ORDER BY clause
        if self._match('ORDER'):
            self._advance()
            self._expect('BY')
            result['order_by'] = self._advance()
            if self._match('ASC', 'DESC'):
                result['order_dir'] = self._advance().upper()

        # LIMIT clause
        if self._match('LIMIT'):
            self._advance()
            result['limit'] = int(self._advance())

        # OFFSET clause
        if self._match('OFFSET'):
            self._advance()
            result['offset'] = int(self._advance())

        # RETURN clause
        if self._match('RETURN'):
            self._advance()
            result['return_fields'] = self._parse_field_list()

        return result

    def _parse_edges_query(self) -> Dict[str, Any]:
        """Parse EDGES query."""
        self._advance()  # Skip 'EDGES'

        result = {
            'type': 'EDGES',
            'rel_type': None,
            'conditions': [],
            'limit': None
        }

        # Edge type (optional)
        if self._current() and not self._match('WHERE', 'LIMIT'):
            result['rel_type'] = self._advance()

        # WHERE clause
        if self._match('WHERE'):
            self._advance()
            result['conditions'] = self._parse_conditions()

        # LIMIT clause
        if self._match('LIMIT'):
            self._advance()
            result['limit'] = int(self._advance())

        return result

    def _parse_traverse_query(self) -> Dict[str, Any]:
        """Parse TRAVERSE query."""
        self._advance()  # Skip 'TRAVERSE'

        result = {
            'type': 'TRAVERSE',
            'start': None,
            'pattern': [],
            'max_depth': None,
            'limit': None
        }

        # Start node: type:id or :type:id
        start_token = self._advance()
        result['start'] = self._parse_node_ref(start_token)

        # Parse traversal pattern: -> REL -> target
        while self._match('->', '<-', '--'):
            direction = self._advance()
            rel_type = self._advance()

            # Expect another direction arrow
            if self._match('->', '<-', '--'):
                dir2 = self._advance()
                target_type = self._advance() if self._current() and not self._match('MAX', 'LIMIT') else '*'
            else:
                target_type = '*'
                dir2 = direction

            result['pattern'].append({
                'direction': self._direction_from_arrows(direction, dir2),
                'rel_type': rel_type,
                'target_type': target_type
            })

        # MAX depth
        if self._match('MAX'):
            self._advance()
            result['max_depth'] = int(self._advance())

        # LIMIT
        if self._match('LIMIT'):
            self._advance()
            result['limit'] = int(self._advance())

        return result

    def _parse_path_query(self) -> Dict[str, Any]:
        """Parse PATH query."""
        self._advance()  # Skip 'PATH'

        result = {
            'type': 'PATH',
            'source': None,
            'target': None,
            'via': None,
            'max_hops': 10
        }

        # Source node
        source_token = self._advance()
        result['source'] = self._parse_node_ref(source_token)

        # TO keyword
        self._expect('TO')

        # Target node
        target_token = self._advance()
        result['target'] = self._parse_node_ref(target_token)

        # VIA relationship type (optional)
        if self._match('VIA'):
            self._advance()
            result['via'] = self._advance()

        # MAX hops
        if self._match('MAX'):
            self._advance()
            result['max_hops'] = int(self._advance())

        return result

    def _parse_count_query(self) -> Dict[str, Any]:
        """Parse COUNT query."""
        self._advance()  # Skip 'COUNT'

        result = {
            'type': 'COUNT',
            'node_type': None,
            'conditions': []
        }

        # Node type
        if self._current() and not self._match('WHERE'):
            result['node_type'] = self._advance()

        # WHERE clause
        if self._match('WHERE'):
            self._advance()
            result['conditions'] = self._parse_conditions()

        return result

    def _parse_aggregation_query(self, agg_type: str) -> Dict[str, Any]:
        """Parse SUM/AVG/MIN/MAX query."""
        self._advance()  # Skip aggregation keyword

        result = {
            'type': agg_type,
            'node_type': None,
            'property': None,
            'conditions': []
        }

        # type.property
        type_prop = self._advance()
        if '.' in type_prop:
            parts = type_prop.split('.', 1)
            result['node_type'] = parts[0]
            result['property'] = parts[1]
        else:
            result['property'] = type_prop

        # WHERE clause
        if self._match('WHERE'):
            self._advance()
            result['conditions'] = self._parse_conditions()

        return result

    # -------------------------------------------------------------------------
    # Condition Parsing
    # -------------------------------------------------------------------------

    def _parse_conditions(self) -> Union[List[Condition], List[List[Condition]]]:
        """Parse WHERE conditions with standard precedence (AND binds tighter than OR).

        The condition sequence is split into OR-groups of AND-ed conditions:
        ``a AND b OR c`` parses as ``(a AND b) OR c``.

        Returns:
            A flat ``List[Condition]`` (all AND-ed) when no OR is present,
            otherwise a ``List[List[Condition]]`` where each inner list is an
            AND-group and the groups are OR-ed together.
        """
        groups: List[List[Condition]] = [[]]

        while True:
            condition = self._parse_single_condition()
            if condition:
                groups[-1].append(condition)

            if self._match('AND'):
                self._advance()
                continue
            elif self._match('OR'):
                self._advance()
                groups.append([])
                continue
            else:
                break

        groups = [group for group in groups if group]
        if not groups:
            return []
        if len(groups) == 1:
            return groups[0]
        return groups

    @staticmethod
    def _merge_condition_sets(
        base: List[Condition],
        new: Union[List[Condition], List[List[Condition]]],
    ) -> Union[List[Condition], List[List[Condition]]]:
        """Merge flat AND-ed conditions with a parsed WHERE result.

        ``base`` (e.g. shorthand conditions) is AND-ed with every OR-group
        of ``new``.
        """
        if not base:
            return new
        if not new:
            return base
        if isinstance(new[0], list):
            return [base + group for group in new]
        return base + new

    def _parse_single_condition(self) -> Optional[Condition]:
        """Parse a single condition."""
        if not self._current():
            return None

        # EXISTS / NOT EXISTS
        if self._match('EXISTS'):
            self._advance()
            field = self._advance()
            return Condition(field, Operator.EXISTS, None)

        if self._match('NOT'):
            self._advance()
            if self._match('EXISTS'):
                self._advance()
                field = self._advance()
                return Condition(field, Operator.NOT_EXISTS, None)

        field = self._advance()
        if not field or field.upper() in self.KEYWORDS:
            self._pos -= 1
            return None

        # Operator
        op_token = self._current()
        if not op_token:
            return None

        op_upper = op_token.upper()

        if op_token in self.OPERATORS:
            self._advance()
            operator = self.OPERATORS[op_token]
        elif op_upper == 'IN':
            self._advance()
            operator = Operator.IN
        elif op_upper == 'CONTAINS':
            self._advance()
            operator = Operator.CONTAINS
        elif op_upper == 'STARTS_WITH':
            self._advance()
            operator = Operator.STARTS_WITH
        elif op_upper == 'ENDS_WITH':
            self._advance()
            operator = Operator.ENDS_WITH
        elif op_upper == 'MATCHES':
            self._advance()
            operator = Operator.MATCHES
        elif op_upper == 'EXISTS':
            self._advance()
            return Condition(field, Operator.EXISTS, None)
        elif op_upper == 'NOT':
            nxt = self._peek(1)
            nxt_upper = nxt.upper() if nxt else ''
            if nxt_upper == 'EXISTS':
                self._advance()
                self._advance()
                return Condition(field, Operator.NOT_EXISTS, None)
            if nxt_upper == 'IN':
                self._advance()
                self._advance()
                operator = Operator.NOT_IN
            else:
                raise ValueError(
                    f"Parse error: expected EXISTS or IN after NOT, got '{nxt}'"
                )
        else:
            raise ValueError(
                f"Parse error: unknown operator '{op_token}' in condition"
            )

        # Value
        value = self._parse_value()

        return Condition(field, operator, value)

    def _parse_value(self) -> Any:
        """Parse a value (string, number, boolean, list)."""
        token = self._current()
        if not token:
            return None

        # List: (val1, val2, ...)
        if token == '(':
            self._advance()
            values = []
            while not self._match(')'):
                if not self._current():
                    raise ValueError("Parse error: unclosed list, expected ')'")
                val = self._parse_single_value()
                if val is not None:
                    values.append(val)
                if self._match(','):
                    self._advance()
            self._advance()  # Skip ')'
            return values

        return self._parse_single_value()

    def _parse_single_value(self) -> Any:
        """Parse a single value."""
        token = self._advance()
        if not token:
            return None

        upper = token.upper()

        # Booleans
        if upper == 'TRUE':
            return True
        if upper == 'FALSE':
            return False

        # Null
        if upper in ('NULL', 'NONE', 'NIL'):
            return None

        # Numbers
        try:
            if '.' in token:
                return float(token)
            return int(token)
        except ValueError:
            pass

        # String (already unquoted by tokenizer)
        return token

    def _parse_shorthand_conditions(self) -> List[Condition]:
        """Parse shorthand conditions: (name="Alice", age=30)"""
        conditions = []

        while not self._match(')'):
            field = self._advance()
            if self._match('='):
                self._advance()
                value = self._parse_single_value()
                conditions.append(Condition(field, Operator.EQ, value))
            if self._match(','):
                self._advance()

        self._advance()  # Skip ')'
        return conditions

    def _parse_field_list(self) -> List[str]:
        """Parse comma-separated field list."""
        fields = []
        while self._current() and not self._match('LIMIT', 'OFFSET', 'ORDER'):
            field = self._advance()
            fields.append(field)
            if self._match(','):
                self._advance()
            else:
                break
        return fields

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _parse_node_ref(self, token: str) -> Tuple[str, Union[int, str]]:
        """Parse node reference: type:id or :type:id"""
        if token.startswith(':'):
            token = token[1:]

        parts = token.split(':')
        if len(parts) >= 2:
            node_type = parts[0]
            node_id = parts[1]
            # Try to convert to int
            try:
                node_id = int(node_id)
            except ValueError:
                pass
            return (node_type, node_id)

        raise ValueError(f"Invalid node reference: {token}. Expected format: type:id")

    def _direction_from_arrows(self, arrow1: str, arrow2: str) -> 'Direction':
        """Determine direction from arrow tokens."""
        if arrow1 == '->' or arrow2 == '->':
            return Direction.OUT
        if arrow1 == '<-' or arrow2 == '<-':
            return Direction.IN
        return Direction.BOTH


# =============================================================================
# Query Engine
# =============================================================================

class QueryEngine:
    """
    ISONQL Query Engine for ISONGraph.

    Executes parsed ISONQL queries against an ISONGraph instance.

    Usage:
        from ison_graph import ISONGraph
        from ison_graph.query import QueryEngine

        graph = ISONGraph()
        graph.add_node('person', 'alice', name='Alice', age=30)
        engine = QueryEngine(graph)

        # String queries
        result = engine.execute("NODES person WHERE age > 25")
        result = engine.execute("TRAVERSE person:alice -> KNOWS -> person")

        # Fluent API
        result = engine.match("person").where("age", ">", 25).execute()
    """

    def __init__(self, graph: ISONGraph):
        """Initialize query engine with a graph instance."""
        self._graph = graph
        self._parser = ISONQLParser()

    @property
    def graph(self) -> ISONGraph:
        """Get the underlying graph."""
        return self._graph

    def execute(self, query: str) -> QueryResult:
        """
        Execute an ISONQL query string.

        Args:
            query: ISONQL query string

        Returns:
            QueryResult with data, count, and execution time

        Raises:
            ValueError: If query syntax is invalid
        """
        start_time = time.time()

        try:
            parsed = self._parser.parse(query)
        except Exception as e:
            raise ValueError(f"Parse error: {e}")

        query_type = parsed['type']

        if query_type == 'NODES':
            data, total = self._execute_nodes(parsed)
        elif query_type == 'EDGES':
            data, total = self._execute_edges(parsed)
        elif query_type == 'TRAVERSE':
            data, total = self._execute_traverse(parsed)
        elif query_type == 'PATH':
            data, total = self._execute_path(parsed)
        elif query_type == 'COUNT':
            data, total = self._execute_count(parsed)
        elif query_type in ('SUM', 'AVG', 'MIN', 'MAX'):
            data, total = self._execute_aggregation(parsed)
        else:
            raise ValueError(f"Unknown query type: {query_type}")

        execution_time = (time.time() - start_time) * 1000

        return QueryResult(
            data=data,
            count=len(data) if isinstance(data, list) else 1,
            total_count=total,
            execution_time_ms=execution_time,
            query=query,
            query_type=query_type
        )

    # -------------------------------------------------------------------------
    # Query Executors
    # -------------------------------------------------------------------------

    def _execute_nodes(self, parsed: Dict) -> Tuple[List[Dict], int]:
        """Execute NODES query."""
        node_type = parsed.get('node_type')
        conditions = parsed.get('conditions', [])
        order_by = parsed.get('order_by')
        order_dir = parsed.get('order_dir', 'ASC')
        limit = parsed.get('limit')
        offset = parsed.get('offset', 0)
        return_fields = parsed.get('return_fields')

        # Get nodes
        nodes = list(self._graph.nodes(node_type))

        # Filter by conditions
        if conditions:
            nodes = [n for n in nodes if self._matches_conditions(n.properties, conditions)]

        total = len(nodes)

        # Sort: nodes missing the field always sort last; values are grouped
        # by type so mixed-type properties never raise a comparison TypeError.
        if order_by:
            reverse = order_dir == 'DESC'
            present = [n for n in nodes if order_by in n.properties]
            missing = [n for n in nodes if order_by not in n.properties]

            def sort_key(node) -> Tuple[str, Any]:
                value = node.properties[order_by]
                if isinstance(value, bool):
                    return ('bool', value)
                if isinstance(value, (int, float)):
                    return ('number', value)
                if isinstance(value, str):
                    return ('str', value)
                return (type(value).__name__, str(value))

            present.sort(key=sort_key, reverse=reverse)
            nodes = present + missing

        # Pagination
        if offset is not None:
            nodes = nodes[offset:]
        if limit is not None:
            nodes = nodes[:limit]

        # Format output
        if return_fields:
            data = [
                {f: n.properties.get(f) for f in return_fields}
                for n in nodes
            ]
        else:
            data = [
                {'type': n.type, 'id': n.id, 'properties': n.properties}
                for n in nodes
            ]

        return data, total

    def _execute_edges(self, parsed: Dict) -> Tuple[List[Dict], int]:
        """Execute EDGES query."""
        rel_type = parsed.get('rel_type')
        conditions = parsed.get('conditions', [])
        limit = parsed.get('limit')

        # Get edges
        edges = list(self._graph.edges(rel_type))

        # Filter by conditions
        if conditions:
            edges = [e for e in edges if self._matches_conditions(e.properties, conditions)]

        total = len(edges)

        # Limit
        if limit is not None:
            edges = edges[:limit]

        data = [
            {
                'rel_type': e.rel_type,
                'source': e.source,
                'target': e.target,
                'properties': e.properties
            }
            for e in edges
        ]

        return data, total

    def _execute_traverse(self, parsed: Dict) -> Tuple[List[Tuple], int]:
        """Execute TRAVERSE query."""
        start = parsed['start']
        pattern = parsed.get('pattern', [])
        max_depth = parsed.get('max_depth')
        limit = parsed.get('limit')

        # Start traversal
        current = {start}
        visited = {start}

        for step in pattern:
            direction = step['direction']
            rel_type = step['rel_type']
            target_type = step.get('target_type', '*')

            next_level = set()
            for node_ref in current:
                neighbors = self._graph.neighbors(node_ref, rel_type, direction)
                for neighbor in neighbors:
                    if neighbor not in visited:
                        if target_type == '*' or neighbor[0] == target_type:
                            next_level.add(neighbor)

            visited.update(next_level)
            current = next_level

            if not current:
                break

        # Apply max_depth by doing additional hops
        if max_depth and max_depth > len(pattern):
            remaining_hops = max_depth - len(pattern)
            last_rel = pattern[-1]['rel_type'] if pattern else None
            last_dir = pattern[-1]['direction'] if pattern else Direction.OUT

            for _ in range(remaining_hops):
                next_level = set()
                for node_ref in current:
                    neighbors = self._graph.neighbors(node_ref, last_rel, last_dir)
                    for neighbor in neighbors:
                        if neighbor not in visited:
                            next_level.add(neighbor)
                visited.update(next_level)
                current.update(next_level)

                if not next_level:
                    break

        result = list(current)
        total = len(result)

        if limit is not None:
            result = result[:limit]

        return result, total

    def _execute_path(self, parsed: Dict) -> Tuple[List[Dict], int]:
        """Execute PATH query."""
        source = parsed['source']
        target = parsed['target']
        via = parsed.get('via')
        max_hops = parsed.get('max_hops', 10)

        path = self._graph.shortest_path(source, target, via, max_hops)

        if path:
            data = [{
                'nodes': path.nodes,
                'edges': [{'rel_type': e.rel_type, 'source': e.source, 'target': e.target} for e in path.edges],
                'length': path.length
            }]
            return data, 1
        else:
            return [], 0

    def _execute_count(self, parsed: Dict) -> Tuple[List[int], int]:
        """Execute COUNT query."""
        node_type = parsed.get('node_type')
        conditions = parsed.get('conditions', [])

        nodes = list(self._graph.nodes(node_type))

        if conditions:
            nodes = [n for n in nodes if self._matches_conditions(n.properties, conditions)]

        count = len(nodes)
        return [count], count

    def _execute_aggregation(self, parsed: Dict) -> Tuple[List[Any], int]:
        """Execute SUM/AVG/MIN/MAX query."""
        agg_type = parsed['type']
        node_type = parsed.get('node_type')
        prop = parsed['property']
        conditions = parsed.get('conditions', [])

        nodes = list(self._graph.nodes(node_type))

        if conditions:
            nodes = [n for n in nodes if self._matches_conditions(n.properties, conditions)]

        # Extract numeric values
        values = [n.properties.get(prop) for n in nodes if prop in n.properties]
        values = [v for v in values if isinstance(v, (int, float))]

        if not values:
            return [None], 0

        if agg_type == 'SUM':
            result = sum(values)
        elif agg_type == 'AVG':
            result = sum(values) / len(values)
        elif agg_type == 'MIN':
            result = min(values)
        elif agg_type == 'MAX':
            result = max(values)
        else:
            result = None

        return [result], len(values)

    def _matches_conditions(
        self,
        properties: Dict[str, Any],
        conditions: Union[List[Condition], List[List[Condition]]],
    ) -> bool:
        """Check if properties match the parsed conditions.

        A flat list of Conditions is AND-ed. A list of lists is an OR of
        AND-groups: at least one group must match fully.
        """
        if not conditions:
            return True
        if isinstance(conditions[0], list):
            return any(
                all(condition.evaluate(properties) for condition in group)
                for group in conditions
            )
        return all(condition.evaluate(properties) for condition in conditions)

    # -------------------------------------------------------------------------
    # Fluent API
    # -------------------------------------------------------------------------

    def match(self, node_type: str) -> 'QueryBuilder':
        """Start a fluent query for nodes of a given type."""
        return QueryBuilder(self, node_type)

    def match_edges(self, rel_type: Optional[str] = None) -> 'EdgeQueryBuilder':
        """Start a fluent query for edges."""
        return EdgeQueryBuilder(self, rel_type)


# =============================================================================
# Fluent Query Builders
# =============================================================================

class QueryBuilder:
    """
    Fluent API for building node queries programmatically.

    Usage:
        result = (engine.match("person")
            .where("age", ">", 25)
            .where("status", "=", "active")
            .order_by("name", "DESC")
            .limit(10)
            .offset(5)
            .return_fields("name", "email")
            .execute())
    """

    def __init__(self, engine: QueryEngine, node_type: str):
        self._engine = engine
        self._node_type = node_type
        self._conditions: List[Condition] = []
        self._order_by: Optional[str] = None
        self._order_dir: str = "ASC"
        self._limit: Optional[int] = None
        self._offset: int = 0
        self._fields: Optional[List[str]] = None

    def where(self, field: str, operator: str, value: Any) -> 'QueryBuilder':
        """Add a WHERE condition."""
        op_map = {
            '=': Operator.EQ, '==': Operator.EQ,
            '!=': Operator.NE, '<>': Operator.NE,
            '>': Operator.GT, '>=': Operator.GE,
            '<': Operator.LT, '<=': Operator.LE,
            'IN': Operator.IN, 'NOT IN': Operator.NOT_IN,
            'CONTAINS': Operator.CONTAINS,
            'STARTS_WITH': Operator.STARTS_WITH,
            'ENDS_WITH': Operator.ENDS_WITH,
            'MATCHES': Operator.MATCHES,
        }
        op = op_map.get(operator.upper())
        if op is None:
            raise ValueError(
                f"Unknown operator: {operator!r}. "
                f"Supported: {', '.join(sorted(op_map))}"
            )
        self._conditions.append(Condition(field, op, value))
        return self

    def where_exists(self, field: str) -> 'QueryBuilder':
        """Add EXISTS condition."""
        self._conditions.append(Condition(field, Operator.EXISTS, None))
        return self

    def where_not_exists(self, field: str) -> 'QueryBuilder':
        """Add NOT EXISTS condition."""
        self._conditions.append(Condition(field, Operator.NOT_EXISTS, None))
        return self

    def order_by(self, field: str, direction: str = "ASC") -> 'QueryBuilder':
        """Set ORDER BY clause."""
        self._order_by = field
        self._order_dir = direction.upper()
        return self

    def limit(self, n: int) -> 'QueryBuilder':
        """Set LIMIT."""
        self._limit = n
        return self

    def offset(self, n: int) -> 'QueryBuilder':
        """Set OFFSET for pagination."""
        self._offset = n
        return self

    def return_fields(self, *fields: str) -> 'QueryBuilder':
        """Set fields to return (projection)."""
        self._fields = list(fields)
        return self

    def execute(self) -> QueryResult:
        """Execute the built query."""
        parsed = {
            'type': 'NODES',
            'node_type': self._node_type,
            'conditions': self._conditions,
            'order_by': self._order_by,
            'order_dir': self._order_dir,
            'limit': self._limit,
            'offset': self._offset,
            'return_fields': self._fields
        }

        start_time = time.time()
        data, total = self._engine._execute_nodes(parsed)
        execution_time = (time.time() - start_time) * 1000

        # Build query string for logging
        query_str = f"NODES {self._node_type}"
        if self._conditions:
            conds = " AND ".join([str(c) for c in self._conditions])
            query_str += f" WHERE {conds}"
        if self._order_by:
            query_str += f" ORDER BY {self._order_by} {self._order_dir}"
        if self._limit:
            query_str += f" LIMIT {self._limit}"

        return QueryResult(
            data=data,
            count=len(data),
            total_count=total,
            execution_time_ms=execution_time,
            query=query_str,
            query_type='NODES'
        )

    def count(self) -> int:
        """Execute count query and return count."""
        parsed = {
            'type': 'COUNT',
            'node_type': self._node_type,
            'conditions': self._conditions
        }
        data, total = self._engine._execute_count(parsed)
        return data[0] if data else 0


class EdgeQueryBuilder:
    """
    Fluent API for building edge queries.

    Usage:
        result = (engine.match_edges("KNOWS")
            .where("since", ">", 2020)
            .limit(10)
            .execute())
    """

    def __init__(self, engine: QueryEngine, rel_type: Optional[str] = None):
        self._engine = engine
        self._rel_type = rel_type
        self._conditions: List[Condition] = []
        self._limit: Optional[int] = None

    def where(self, field: str, operator: str, value: Any) -> 'EdgeQueryBuilder':
        """Add a WHERE condition."""
        op_map = {
            '=': Operator.EQ, '==': Operator.EQ,
            '!=': Operator.NE, '<>': Operator.NE,
            '>': Operator.GT, '>=': Operator.GE,
            '<': Operator.LT, '<=': Operator.LE,
        }
        op = op_map.get(operator.upper())
        if op is None:
            raise ValueError(
                f"Unknown operator: {operator!r}. "
                f"Supported: {', '.join(sorted(op_map))}"
            )
        self._conditions.append(Condition(field, op, value))
        return self

    def limit(self, n: int) -> 'EdgeQueryBuilder':
        """Set LIMIT."""
        self._limit = n
        return self

    def execute(self) -> QueryResult:
        """Execute the built query."""
        parsed = {
            'type': 'EDGES',
            'rel_type': self._rel_type,
            'conditions': self._conditions,
            'limit': self._limit
        }

        start_time = time.time()
        data, total = self._engine._execute_edges(parsed)
        execution_time = (time.time() - start_time) * 1000

        query_str = f"EDGES {self._rel_type or ''}"
        if self._conditions:
            conds = " AND ".join([str(c) for c in self._conditions])
            query_str += f" WHERE {conds}"

        return QueryResult(
            data=data,
            count=len(data),
            total_count=total,
            execution_time_ms=execution_time,
            query=query_str.strip(),
            query_type='EDGES'
        )


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Version
    '__version__',

    # Enums
    'Operator',
    'SortOrder',
    'QueryType',

    # Data Classes
    'Condition',
    'QueryResult',

    # Parser
    'ISONQLParser',

    # Engine
    'QueryEngine',

    # Builders
    'QueryBuilder',
    'EdgeQueryBuilder',
]
