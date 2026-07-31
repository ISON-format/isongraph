"""
Schema Formatter

Formats schemas to various output formats.
"""

from typing import Any, Dict, Optional
import json

from .generator import GraphSchema, NodeTypeSchema, EdgeTypeSchema, FieldSchema


class SchemaFormatter:
    """
    Formats ISONGraph schemas to various output formats.
    """

    @staticmethod
    def to_python(schema: GraphSchema) -> str:
        """Generate Python code for ISONGraphantic."""
        lines = [
            '"""',
            f"Auto-generated schema: {schema.name}",
            '"""',
            "",
            "from ison_graph.schema import GraphSchema, NodeType, EdgeType",
            "from ison_graph.schema import StringField, IntField, FloatField, BoolField",
            "",
        ]

        # Node types
        for node_type in schema.node_types:
            lines.extend(SchemaFormatter._node_type_to_python(node_type))
            lines.append("")

        # Edge types
        for edge_type in schema.edge_types:
            lines.extend(SchemaFormatter._edge_type_to_python(edge_type))
            lines.append("")

        # Create schema
        lines.append(f'schema = GraphSchema("{schema.name}")')
        for node_type in schema.node_types:
            lines.append(f"    .node_type({node_type.name}_type)")
        for edge_type in schema.edge_types:
            lines.append(f"    .edge_type({edge_type.name.lower()}_type)")

        lines.append("")
        lines.append("")
        lines.append("def validate(graph):")
        lines.append("    return schema.validate(graph)")

        return "\n".join(lines)

    @staticmethod
    def _node_type_to_python(node_type: NodeTypeSchema) -> list:
        """Convert node type to Python code."""
        lines = [f'{node_type.name}_type = NodeType("{node_type.name}")']

        for field in node_type.fields:
            field_code = SchemaFormatter._field_to_python(field)
            lines.append(f'    .field("{field.name}", {field_code})')

        return lines

    @staticmethod
    def _edge_type_to_python(edge_type: EdgeTypeSchema) -> list:
        """Convert edge type to Python code."""
        lines = [f'{edge_type.name.lower()}_type = EdgeType("{edge_type.name}")']

        for source in edge_type.source_types:
            lines.append(f'    .from_node("{source}")')
        for target in edge_type.target_types:
            lines.append(f'    .to_node("{target}")')

        if edge_type.no_self_loop:
            lines.append("    .no_self_loop()")
        if edge_type.unique:
            lines.append("    .unique()")

        for field in edge_type.fields:
            field_code = SchemaFormatter._field_to_python(field)
            lines.append(f'    .field("{field.name}", {field_code})')

        return lines

    @staticmethod
    def _field_to_python(field: FieldSchema) -> str:
        """Convert field to Python code."""
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
            parts.append(f'.pattern("{field.pattern}")')
        if field.enum:
            enum_str = ", ".join(repr(v) for v in field.enum)
            parts.append(f".enum([{enum_str}])")

        return "".join(parts)

    @staticmethod
    def to_typescript(schema: GraphSchema) -> str:
        """Generate TypeScript code."""
        lines = [
            "/**",
            f" * Auto-generated schema: {schema.name}",
            " */",
            "",
            'import { GraphSchema, NodeType, EdgeType, StringField, IntField, FloatField, BoolField } from "ison-graph-ts";',
            "",
        ]

        # Node types
        for node_type in schema.node_types:
            lines.extend(SchemaFormatter._node_type_to_ts(node_type))
            lines.append("")

        # Edge types
        for edge_type in schema.edge_types:
            lines.extend(SchemaFormatter._edge_type_to_ts(edge_type))
            lines.append("")

        # Create schema
        lines.append(f'export const schema = new GraphSchema("{schema.name}")')
        for node_type in schema.node_types:
            lines.append(f"  .nodeType({node_type.name}Type)")
        for edge_type in schema.edge_types:
            lines.append(f"  .edgeType({edge_type.name.lower()}Type);")

        return "\n".join(lines)

    @staticmethod
    def _node_type_to_ts(node_type: NodeTypeSchema) -> list:
        """Convert node type to TypeScript."""
        lines = [f'const {node_type.name}Type = new NodeType("{node_type.name}")']

        for field in node_type.fields:
            field_code = SchemaFormatter._field_to_ts(field)
            lines.append(f'  .field("{field.name}", {field_code})')

        lines[-1] += ";"
        return lines

    @staticmethod
    def _edge_type_to_ts(edge_type: EdgeTypeSchema) -> list:
        """Convert edge type to TypeScript."""
        lines = [f'const {edge_type.name.lower()}Type = new EdgeType("{edge_type.name}")']

        for source in edge_type.source_types:
            lines.append(f'  .fromNode("{source}")')
        for target in edge_type.target_types:
            lines.append(f'  .toNode("{target}")')

        if edge_type.no_self_loop:
            lines.append("  .noSelfLoop()")
        if edge_type.unique:
            lines.append("  .unique()")

        lines[-1] += ";"
        return lines

    @staticmethod
    def _field_to_ts(field: FieldSchema) -> str:
        """Convert field to TypeScript."""
        type_map = {
            'string': 'stringField',
            'int': 'intField',
            'float': 'floatField',
            'bool': 'boolField',
        }

        field_type = type_map.get(field.type, 'stringField')
        parts = [f"{field_type}()"]

        if field.required:
            parts.append(".required()")
        if field.min_value is not None:
            parts.append(f".min({field.min_value})")
        if field.max_value is not None:
            parts.append(f".max({field.max_value})")
        if field.max_length is not None:
            parts.append(f".maxLength({field.max_length})")

        return "".join(parts)

    @staticmethod
    def to_json(schema: GraphSchema) -> str:
        """Generate JSON schema."""
        result = {
            "$schema": "https://isongraph.io/schema/v1",
            "name": schema.name,
            "description": schema.description,
            "nodeTypes": {},
            "edgeTypes": {},
        }

        for node_type in schema.node_types:
            result["nodeTypes"][node_type.name] = {
                "fields": {
                    f.name: SchemaFormatter._field_to_json(f)
                    for f in node_type.fields
                }
            }

        for edge_type in schema.edge_types:
            result["edgeTypes"][edge_type.name] = {
                "sourceTypes": edge_type.source_types,
                "targetTypes": edge_type.target_types,
                "constraints": {
                    "unique": edge_type.unique,
                    "noSelfLoop": edge_type.no_self_loop,
                },
                "fields": {
                    f.name: SchemaFormatter._field_to_json(f)
                    for f in edge_type.fields
                }
            }

        return json.dumps(result, indent=2)

    @staticmethod
    def _field_to_json(field: FieldSchema) -> Dict[str, Any]:
        """Convert field to JSON schema format."""
        result = {
            "type": field.type,
            "required": field.required,
        }

        if field.min_value is not None:
            result["min"] = field.min_value
        if field.max_value is not None:
            result["max"] = field.max_value
        if field.min_length is not None:
            result["minLength"] = field.min_length
        if field.max_length is not None:
            result["maxLength"] = field.max_length
        if field.pattern:
            result["pattern"] = field.pattern
        if field.enum:
            result["enum"] = field.enum

        return result

    @staticmethod
    def to_ison_schema(schema: GraphSchema) -> str:
        """Generate ISON schema format."""
        lines = [
            f"schema.graph {schema.name}",
            "",
        ]

        for node_type in schema.node_types:
            lines.append(f"schema.node {node_type.name}")
            for field in node_type.fields:
                constraints = []
                if field.required:
                    constraints.append("required")
                if field.max_length:
                    constraints.append(f"max_length={field.max_length}")
                if field.min_value is not None:
                    constraints.append(f"min={field.min_value}")
                if field.max_value is not None:
                    constraints.append(f"max={field.max_value}")

                constraint_str = " ".join(constraints)
                lines.append(f"  {field.name} {field.type} {constraint_str}".rstrip())
            lines.append("")

        for edge_type in schema.edge_types:
            lines.append(f"schema.edge {edge_type.name}")
            lines.append(f"  from {' '.join(edge_type.source_types)}")
            lines.append(f"  to {' '.join(edge_type.target_types)}")
            if edge_type.no_self_loop:
                lines.append("  no_self_loop")
            if edge_type.unique:
                lines.append("  unique")
            for field in edge_type.fields:
                lines.append(f"  {field.name} {field.type}")
            lines.append("")

        return "\n".join(lines)
