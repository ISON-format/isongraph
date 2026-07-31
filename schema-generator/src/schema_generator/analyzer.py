"""
Data Analyzer for Schema Generation

Analyzes JSON data to infer types and patterns.
"""

from typing import Any, Dict, List, Optional, Set, Tuple, Union
from dataclasses import dataclass, field
from collections import defaultdict
import re


@dataclass
class FieldStats:
    """Statistics for a field."""
    name: str
    types: Set[str] = field(default_factory=set)
    count: int = 0
    null_count: int = 0
    unique_values: Set[Any] = field(default_factory=set)
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    patterns: Set[str] = field(default_factory=set)

    @property
    def required(self) -> bool:
        """Check if field is required (no nulls)."""
        return self.null_count == 0

    @property
    def primary_type(self) -> str:
        """Get the most common type."""
        # Priority: string > int > float > bool
        type_priority = ['string', 'int', 'float', 'bool', 'null']
        for t in type_priority:
            if t in self.types:
                return t
        return 'any'

    @property
    def is_enum(self) -> bool:
        """Check if field looks like an enum."""
        if 'string' not in self.types:
            return False
        return len(self.unique_values) < min(10, self.count * 0.5) and self.count > 3


@dataclass
class NodeTypeStats:
    """Statistics for a node type."""
    type_name: str
    count: int = 0
    fields: Dict[str, FieldStats] = field(default_factory=dict)


@dataclass
class EdgeTypeStats:
    """Statistics for an edge type."""
    type_name: str
    count: int = 0
    source_types: Set[str] = field(default_factory=set)
    target_types: Set[str] = field(default_factory=set)
    fields: Dict[str, FieldStats] = field(default_factory=dict)


class DataAnalyzer:
    """
    Analyzes JSON graph data to extract schema information.
    """

    def __init__(self):
        self.node_stats: Dict[str, NodeTypeStats] = {}
        self.edge_stats: Dict[str, EdgeTypeStats] = {}

    def analyze(self, data: Dict[str, Any]) -> None:
        """
        Analyze a JSON graph structure.

        Args:
            data: JSON graph with 'nodes' and 'edges' arrays
        """
        # Analyze nodes
        for node in data.get('nodes', []):
            self._analyze_node(node)

        # Analyze edges
        for edge in data.get('edges', []):
            self._analyze_edge(edge)

    def _analyze_node(self, node: Dict[str, Any]) -> None:
        """Analyze a single node."""
        node_type = node.get('type', 'entity')

        if node_type not in self.node_stats:
            self.node_stats[node_type] = NodeTypeStats(type_name=node_type)

        stats = self.node_stats[node_type]
        stats.count += 1

        # Analyze each field
        for key, value in node.items():
            if key == 'type':
                continue

            if key not in stats.fields:
                stats.fields[key] = FieldStats(name=key)

            self._analyze_value(stats.fields[key], value)

    def _analyze_edge(self, edge: Dict[str, Any]) -> None:
        """Analyze a single edge."""
        edge_type = edge.get('rel_type') or edge.get('type', 'RELATED_TO')

        if edge_type not in self.edge_stats:
            self.edge_stats[edge_type] = EdgeTypeStats(type_name=edge_type)

        stats = self.edge_stats[edge_type]
        stats.count += 1

        # Track source/target types
        source = edge.get('source', {})
        target = edge.get('target', {})

        if isinstance(source, dict):
            stats.source_types.add(source.get('type', 'entity'))
        if isinstance(target, dict):
            stats.target_types.add(target.get('type', 'entity'))

        # Analyze properties
        properties = edge.get('properties', {})
        for key, value in properties.items():
            if key not in stats.fields:
                stats.fields[key] = FieldStats(name=key)
            self._analyze_value(stats.fields[key], value)

    def _analyze_value(self, field_stats: FieldStats, value: Any) -> None:
        """Analyze a field value."""
        field_stats.count += 1

        if value is None:
            field_stats.null_count += 1
            field_stats.types.add('null')
            return

        # Determine type
        if isinstance(value, bool):
            field_stats.types.add('bool')
            field_stats.unique_values.add(value)

        elif isinstance(value, int):
            field_stats.types.add('int')
            if len(field_stats.unique_values) < 100:
                field_stats.unique_values.add(value)
            if field_stats.min_value is None or value < field_stats.min_value:
                field_stats.min_value = value
            if field_stats.max_value is None or value > field_stats.max_value:
                field_stats.max_value = value

        elif isinstance(value, float):
            field_stats.types.add('float')
            if field_stats.min_value is None or value < field_stats.min_value:
                field_stats.min_value = value
            if field_stats.max_value is None or value > field_stats.max_value:
                field_stats.max_value = value

        elif isinstance(value, str):
            field_stats.types.add('string')
            if len(field_stats.unique_values) < 100:
                field_stats.unique_values.add(value)

            # Track length
            length = len(value)
            if field_stats.min_length is None or length < field_stats.min_length:
                field_stats.min_length = length
            if field_stats.max_length is None or length > field_stats.max_length:
                field_stats.max_length = length

            # Detect patterns
            pattern = self._detect_pattern(value)
            if pattern:
                field_stats.patterns.add(pattern)

        elif isinstance(value, list):
            field_stats.types.add('array')

        elif isinstance(value, dict):
            field_stats.types.add('object')

    def _detect_pattern(self, value: str) -> Optional[str]:
        """Detect common patterns in string values."""
        patterns = {
            'email': r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$',
            'url': r'^https?://[^\s]+$',
            'uuid': r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            'date': r'^\d{4}-\d{2}-\d{2}$',
            'datetime': r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',
            'phone': r'^\+?[\d\s-]{10,}$',
        }

        for name, pattern in patterns.items():
            if re.match(pattern, value, re.IGNORECASE):
                return name

        return None

    def get_node_stats(self) -> Dict[str, NodeTypeStats]:
        """Get node type statistics."""
        return self.node_stats

    def get_edge_stats(self) -> Dict[str, EdgeTypeStats]:
        """Get edge type statistics."""
        return self.edge_stats

    def summary(self) -> Dict[str, Any]:
        """Get analysis summary."""
        return {
            'node_types': len(self.node_stats),
            'edge_types': len(self.edge_stats),
            'total_nodes': sum(s.count for s in self.node_stats.values()),
            'total_edges': sum(s.count for s in self.edge_stats.values()),
            'node_type_names': list(self.node_stats.keys()),
            'edge_type_names': list(self.edge_stats.keys()),
        }
