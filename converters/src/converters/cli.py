#!/usr/bin/env python3
"""
ISONGraph Format Converter CLI

Command-line tool for converting between ISONGraph and various formats.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from ison_graph import ISONGraph

from .graphml import GraphMLConverter
from .rdf import RDFConverter
from .csv_converter import CSVConverter, Neo4jCSVConverter
from .cypher import CypherConverter
from .dot import DOTConverter


def get_format_from_extension(path: str) -> str:
    """Infer format from file extension."""
    ext = Path(path).suffix.lower()
    format_map = {
        ".ison": "ison",
        ".isonl": "isonl",
        ".json": "json",
        ".graphml": "graphml",
        ".xml": "graphml",
        ".ttl": "turtle",
        ".nt": "ntriples",
        ".rdf": "rdf",
        ".csv": "csv",
        ".cypher": "cypher",
        ".cql": "cypher",
        ".dot": "dot",
        ".gv": "dot",
    }
    return format_map.get(ext, "ison")


def load_graph(path: str, format: Optional[str] = None, name: Optional[str] = None) -> ISONGraph:
    """Load graph from file."""
    if format is None:
        format = get_format_from_extension(path)

    if name is None:
        name = Path(path).stem

    content = Path(path).read_text(encoding="utf-8")

    if format == "ison":
        return ISONGraph.from_ison(content, name=name)
    elif format == "isonl":
        return ISONGraph.from_isonl(content, name=name)
    elif format == "json":
        import json
        data = json.loads(content)
        return ISONGraph.from_dict(data, name=name)
    elif format == "graphml":
        converter = GraphMLConverter()
        return converter.from_graphml(content, name=name)
    elif format in ("turtle", "ttl", "rdf"):
        converter = RDFConverter()
        return converter.from_turtle(content, name=name)
    else:
        raise ValueError(f"Unsupported input format: {format}")


def save_graph(graph: ISONGraph, path: str, format: Optional[str] = None, **options) -> None:
    """Save graph to file."""
    if format is None:
        format = get_format_from_extension(path)

    if format == "ison":
        content = graph.to_ison()
    elif format == "isonl":
        content = graph.to_isonl()
    elif format == "json":
        import json
        content = json.dumps(graph.to_dict(), indent=2)
    elif format == "graphml":
        converter = GraphMLConverter()
        content = converter.to_graphml(graph)
    elif format in ("turtle", "ttl"):
        converter = RDFConverter(base_uri=options.get("base_uri", "http://example.org/"))
        content = converter.to_turtle(graph)
    elif format in ("ntriples", "nt"):
        converter = RDFConverter(base_uri=options.get("base_uri", "http://example.org/"))
        content = converter.to_ntriples(graph)
    elif format == "cypher":
        converter = CypherConverter()
        mode = options.get("mode", "merge")
        if options.get("batch", False):
            content = converter.to_cypher_batch(graph, mode=mode)
        else:
            content = converter.to_cypher(graph, mode=mode)
    elif format == "dot":
        converter = DOTConverter(
            label_property=options.get("label_property", "name"),
            show_properties=options.get("show_properties", False),
        )
        if options.get("clustered", False):
            content = converter.to_dot_clustered(graph)
        else:
            content = converter.to_dot(graph)
    elif format == "csv":
        # CSV requires special handling for nodes/edges
        converter = CSVConverter()
        nodes_csv, edges_csv = converter.to_csv(graph)

        # Write nodes file
        nodes_path = path
        Path(nodes_path).write_text(nodes_csv, encoding="utf-8")

        # Write edges file
        edges_path = str(Path(path).with_suffix("")) + "_edges.csv"
        Path(edges_path).write_text(edges_csv, encoding="utf-8")

        print(f"Wrote nodes to: {nodes_path}")
        print(f"Wrote edges to: {edges_path}")
        return
    else:
        raise ValueError(f"Unsupported output format: {format}")

    Path(path).write_text(content, encoding="utf-8")
    print(f"Wrote {format.upper()} to: {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert between ISONGraph and various graph formats",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Supported formats:
  ison      - ISON format (token-efficient)
  isonl     - ISON Lines (streaming format)
  json      - JSON format
  graphml   - GraphML (XML-based)
  turtle    - RDF Turtle format
  ntriples  - RDF N-Triples format
  csv       - CSV (separate nodes/edges files)
  cypher    - Neo4j Cypher statements
  dot       - Graphviz DOT format

Examples:
  # Convert JSON to ISON
  ison-convert input.json output.ison

  # Convert ISON to GraphML
  ison-convert graph.ison graph.graphml

  # Convert to Cypher with MERGE mode
  ison-convert graph.ison import.cypher --cypher-mode merge

  # Convert to DOT with clustering
  ison-convert graph.ison graph.dot --clustered
        """
    )

    parser.add_argument("input", help="Input file path")
    parser.add_argument("output", help="Output file path")
    parser.add_argument(
        "-i", "--input-format",
        help="Input format (auto-detected from extension if not specified)"
    )
    parser.add_argument(
        "-o", "--output-format",
        help="Output format (auto-detected from extension if not specified)"
    )
    parser.add_argument(
        "-n", "--name",
        help="Graph name (defaults to input filename)"
    )

    # Format-specific options
    parser.add_argument(
        "--base-uri",
        default="http://example.org/",
        help="Base URI for RDF output (default: http://example.org/)"
    )
    parser.add_argument(
        "--cypher-mode",
        choices=["create", "merge"],
        default="merge",
        help="Cypher statement mode (default: merge)"
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Use batched Cypher with UNWIND"
    )
    parser.add_argument(
        "--clustered",
        action="store_true",
        help="Use clustered subgraphs in DOT output"
    )
    parser.add_argument(
        "--label-property",
        default="name",
        help="Property to use as node label in DOT (default: name)"
    )
    parser.add_argument(
        "--show-properties",
        action="store_true",
        help="Show all properties in DOT labels"
    )

    args = parser.parse_args()

    try:
        # Load input graph
        graph = load_graph(
            args.input,
            format=args.input_format,
            name=args.name
        )

        print(f"Loaded graph: {graph.name}")
        print(f"  Nodes: {graph.node_count()}")
        print(f"  Edges: {graph.edge_count()}")

        # Save to output format
        save_graph(
            graph,
            args.output,
            format=args.output_format,
            base_uri=args.base_uri,
            mode=args.cypher_mode,
            batch=args.batch,
            clustered=args.clustered,
            label_property=args.label_property,
            show_properties=args.show_properties,
        )

    except FileNotFoundError as e:
        print(f"Error: File not found - {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
