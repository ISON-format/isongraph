"""
Schema Generator

Generates ISONGraph schemas from analyzed data.
"""

from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field

from .analyzer import DataAnalyzer, FieldStats, NodeTypeStats, EdgeTypeStats


@dataclass
class FieldSchema:
    """Schema for a single field."""
    name: str
    type: str
    required: bool = True
    description: Optional[str] = None
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    enum: Optional[List[Any]] = None


@dataclass
class NodeTypeSchema:
    """Schema for a node type."""
    name: str
    description: Optional[str] = None
    fields: List[FieldSchema] = field(default_factory=list)


@dataclass
class EdgeTypeSchema:
    """Schema for an edge type."""
    name: str
    description: Optional[str] = None
    source_types: List[str] = field(default_factory=list)
    target_types: List[str] = field(default_factory=list)
    fields: List[FieldSchema] = field(default_factory=list)
    unique: bool = False
    no_self_loop: bool = False


@dataclass
class GraphSchema:
    """Complete graph schema."""
    name: str
    description: Optional[str] = None
    node_types: List[NodeTypeSchema] = field(default_factory=list)
    edge_types: List[EdgeTypeSchema] = field(default_factory=list)


class SchemaGenerator:
    """
    Generates ISONGraph schemas from JSON data.

    Example:
        ```python
        from schema_generator import SchemaGenerator

        data = {
            "nodes": [
                {"type": "person", "id": "1", "name": "Alice", "age": 30},
                {"type": "person", "id": "2", "name": "Bob", "age": 25}
            ],
            "edges": [
                {"rel_type": "KNOWS", "source": {"type": "person", "id": "1"},
                 "target": {"type": "person", "id": "2"}}
            ]
        }

        generator = SchemaGenerator()
        schema = generator.generate(data)
        print(generator.to_python(schema))
        ```
    """

    def __init__(
        self,
        infer_constraints: bool = True,
        infer_enums: bool = True,
        infer_patterns: bool = True,
        strict_mode: bool = False
    ):
        """
        Initialize generator.

        Args:
            infer_constraints: Infer min/max constraints
            infer_enums: Detect enum fields
            infer_patterns: Detect string patterns
            strict_mode: Make all fields required
        """
        self.infer_constraints = infer_constraints
        self.infer_enums = infer_enums
        self.infer_patterns = infer_patterns
        self.strict_mode = strict_mode

    def generate(
        self,
        data: Dict[str, Any],
        name: str = "generated_schema"
    ) -> GraphSchema:
        """
        Generate schema from JSON data.

        Args:
            data: JSON graph data
            name: Schema name

        Returns:
            Generated GraphSchema
        """
        analyzer = DataAnalyzer()
        analyzer.analyze(data)

        schema = GraphSchema(name=name)

        # Generate node type schemas
        for type_name, stats in analyzer.get_node_stats().items():
            node_schema = self._generate_node_schema(type_name, stats)
            schema.node_types.append(node_schema)

        # Generate edge type schemas
        for type_name, stats in analyzer.get_edge_stats().items():
            edge_schema = self._generate_edge_schema(type_name, stats)
            schema.edge_types.append(edge_schema)

        return schema

    def _generate_node_schema(
        self,
        type_name: str,
        stats: NodeTypeStats
    ) -> NodeTypeSchema:
        """Generate schema for a node type."""
        node_schema = NodeTypeSchema(name=type_name)

        for field_name, field_stats in stats.fields.items():
            field_schema = self._generate_field_schema(field_stats)
            node_schema.fields.append(field_schema)

        return node_schema

    def _generate_edge_schema(
        self,
        type_name: str,
        stats: EdgeTypeStats
    ) -> EdgeTypeSchema:
        """Generate schema for an edge type."""
        edge_schema = EdgeTypeSchema(
            name=type_name,
            source_types=list(stats.source_types),
            target_types=list(stats.target_types)
        )

        # Detect self-loop potential
        if stats.source_types == stats.target_types and len(stats.source_types) == 1:
            edge_schema.no_self_loop = True

        for field_name, field_stats in stats.fields.items():
            field_schema = self._generate_field_schema(field_stats)
            edge_schema.fields.append(field_schema)

        return edge_schema

    def _generate_field_schema(self, stats: FieldStats) -> FieldSchema:
        """Generate schema for a field."""
        field_schema = FieldSchema(
            name=stats.name,
            type=stats.primary_type,
            required=stats.required if not self.strict_mode else True
        )

        # Add constraints
        if self.infer_constraints:
            if stats.min_value is not None:
                field_schema.min_value = stats.min_value
            if stats.max_value is not None:
                field_schema.max_value = stats.max_value
            if stats.min_length is not None:
                field_schema.min_length = stats.min_length
            if stats.max_length is not None:
                field_schema.max_length = stats.max_length

        # Add pattern
        if self.infer_patterns and stats.patterns:
            field_schema.pattern = list(stats.patterns)[0]

        # Add enum
        if self.infer_enums and stats.is_enum:
            field_schema.enum = list(stats.unique_values)

        return field_schema

    def to_python(self, schema: GraphSchema) -> str:
        """
        Generate Python code for schema.

        Args:
            schema: GraphSchema to convert

        Returns:
            Python code string
        """
        lines = [
            "from ison_graph.schema import GraphSchema, NodeType, EdgeType",
            "from ison_graph.schema import StringField, IntField, FloatField, BoolField",
            "",
            f"# Schema: {schema.name}",
            "",
        ]

        # Node types
        for node_type in schema.node_types:
            lines.append(f"# Node type: {node_type.name}")
            lines.append(f"{node_type.name}_type = NodeType(\"{node_type.name}\")")

            for field in node_type.fields:
                field_code = self._field_to_python(field)
                lines.append(f"    .field(\"{field.name}\", {field_code})")

            lines.append("")

        # Edge types
        for edge_type in schema.edge_types:
            lines.append(f"# Edge type: {edge_type.name}")
            lines.append(f"{edge_type.name.lower()}_type = EdgeType(\"{edge_type.name}\")")

            for source in edge_type.source_types:
                lines.append(f"    .from_node(\"{source}\")")
            for target in edge_type.target_types:
                lines.append(f"    .to_node(\"{target}\")")

            if edge_type.no_self_loop:
                lines.append("    .no_self_loop()")
            if edge_type.unique:
                lines.append("    .unique()")

            for field in edge_type.fields:
                field_code = self._field_to_python(field)
                lines.append(f"    .field(\"{field.name}\", {field_code})")

            lines.append("")

        # Create schema
        lines.append(f"schema = GraphSchema(\"{schema.name}\")")
        for node_type in schema.node_types:
            lines.append(f"    .node_type({node_type.name}_type)")
        for edge_type in schema.edge_types:
            lines.append(f"    .edge_type({edge_type.name.lower()}_type)")

        return "\n".join(lines)

    def _field_to_python(self, field: FieldSchema) -> str:
        """Convert field schema to Python code."""
        type_map = {
            'string': 'StringField',
            'int': 'IntField',
            'float': 'FloatField',
            'bool': 'BoolField',
        }

        field_type = type_map.get(field.type, 'StringField')
        parts = [f"{field_type}()"]

        if field.required:
            parts.append(".required()")

        if field.min_value is not None:
            parts.append(f".min({field.min_value})")
        if field.max_value is not None:
            parts.append(f".max({field.max_value})")
        if field.min_length is not None:
            parts.append(f".min_length({field.min_length})")
        if field.max_length is not None:
            parts.append(f".max_length({field.max_length})")
        if field.pattern:
            parts.append(f".pattern(\"{field.pattern}\")")
        if field.enum:
            enum_str = ", ".join(repr(v) for v in field.enum)
            parts.append(f".enum([{enum_str}])")

        return "".join(parts)

    def to_dict(self, schema: GraphSchema) -> Dict[str, Any]:
        """
        Convert schema to dictionary format.

        Args:
            schema: GraphSchema to convert

        Returns:
            Dictionary representation
        """
        return {
            "name": schema.name,
            "description": schema.description,
            "node_types": [
                {
                    "name": nt.name,
                    "description": nt.description,
                    "fields": [
                        {
                            "name": f.name,
                            "type": f.type,
                            "required": f.required,
                            "min": f.min_value,
                            "max": f.max_value,
                            "min_length": f.min_length,
                            "max_length": f.max_length,
                            "pattern": f.pattern,
                            "enum": f.enum,
                        }
                        for f in nt.fields
                    ]
                }
                for nt in schema.node_types
            ],
            "edge_types": [
                {
                    "name": et.name,
                    "description": et.description,
                    "source_types": et.source_types,
                    "target_types": et.target_types,
                    "unique": et.unique,
                    "no_self_loop": et.no_self_loop,
                    "fields": [
                        {
                            "name": f.name,
                            "type": f.type,
                            "required": f.required,
                        }
                        for f in et.fields
                    ]
                }
                for et in schema.edge_types
            ]
        }


def generate_schema(
    data: Dict[str, Any],
    name: str = "generated_schema",
    output_format: str = "python"
) -> str:
    """
    Convenience function to generate schema from JSON data.

    Args:
        data: JSON graph data
        name: Schema name
        output_format: "python" or "dict"

    Returns:
        Generated schema as string or dict
    """
    generator = SchemaGenerator()
    schema = generator.generate(data, name)

    if output_format == "python":
        return generator.to_python(schema)
    elif output_format == "dict":
        import json
        return json.dumps(generator.to_dict(schema), indent=2)
    else:
        raise ValueError(f"Unknown format: {output_format}")
