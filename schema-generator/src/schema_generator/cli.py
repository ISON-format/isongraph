#!/usr/bin/env python3
"""
ISONGraph Schema Generator CLI

Generate schemas from JSON graph data.

Usage:
    python -m schema_generator input.json -o schema.py
    python -m schema_generator input.json --format typescript -o schema.ts
    cat data.json | python -m schema_generator - --format json
"""

import argparse
import json
import sys
from pathlib import Path

from .generator import SchemaGenerator
from .formatter import SchemaFormatter


def main():
    parser = argparse.ArgumentParser(
        description="Generate ISONGraph schemas from JSON data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate Python schema
    python -m schema_generator graph.json -o schema.py

    # Generate TypeScript schema
    python -m schema_generator graph.json --format typescript -o schema.ts

    # Generate JSON schema to stdout
    python -m schema_generator graph.json --format json

    # Read from stdin
    cat graph.json | python -m schema_generator -
"""
    )

    parser.add_argument(
        "input",
        help="Input JSON file path or '-' for stdin"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (stdout if not specified)"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["python", "typescript", "json", "ison"],
        default="python",
        help="Output format (default: python)"
    )
    parser.add_argument(
        "-n", "--name",
        default="generated_schema",
        help="Schema name (default: generated_schema)"
    )
    parser.add_argument(
        "--no-constraints",
        action="store_true",
        help="Don't infer min/max constraints"
    )
    parser.add_argument(
        "--no-enums",
        action="store_true",
        help="Don't detect enum fields"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Make all fields required"
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Show data analysis instead of generating schema"
    )

    args = parser.parse_args()

    # Read input
    if args.input == "-":
        data = json.load(sys.stdin)
    else:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Error: File not found: {args.input}", file=sys.stderr)
            sys.exit(1)

        with input_path.open() as f:
            data = json.load(f)

    # Create generator
    generator = SchemaGenerator(
        infer_constraints=not args.no_constraints,
        infer_enums=not args.no_enums,
        strict_mode=args.strict
    )

    # Analyze mode
    if args.analyze:
        from .analyzer import DataAnalyzer
        analyzer = DataAnalyzer()
        analyzer.analyze(data)

        print("Data Analysis Summary")
        print("=" * 40)
        summary = analyzer.summary()
        print(f"Node Types: {summary['node_types']}")
        print(f"Edge Types: {summary['edge_types']}")
        print(f"Total Nodes: {summary['total_nodes']}")
        print(f"Total Edges: {summary['total_edges']}")
        print()

        print("Node Types:")
        for type_name, stats in analyzer.get_node_stats().items():
            print(f"  {type_name} ({stats.count} nodes)")
            for field_name, field_stats in stats.fields.items():
                req = "required" if field_stats.required else "optional"
                print(f"    {field_name}: {field_stats.primary_type} ({req})")
        print()

        print("Edge Types:")
        for type_name, stats in analyzer.get_edge_stats().items():
            sources = ", ".join(stats.source_types)
            targets = ", ".join(stats.target_types)
            print(f"  {type_name} ({stats.count} edges)")
            print(f"    {sources} -> {targets}")

        return

    # Generate schema
    schema = generator.generate(data, args.name)

    # Format output
    if args.format == "python":
        output = SchemaFormatter.to_python(schema)
    elif args.format == "typescript":
        output = SchemaFormatter.to_typescript(schema)
    elif args.format == "json":
        output = SchemaFormatter.to_json(schema)
    elif args.format == "ison":
        output = SchemaFormatter.to_ison_schema(schema)
    else:
        output = SchemaFormatter.to_python(schema)

    # Write output
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output)
        print(f"Schema written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
