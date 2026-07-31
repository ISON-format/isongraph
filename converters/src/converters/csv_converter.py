"""
CSV Converter

Convert between ISONGraph and CSV files.
Supports separate node and edge CSV files.
"""

import csv
import warnings
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from ison_graph import ISONGraph


class CSVConverter:
    """
    Convert between ISONGraph and CSV format.

    CSV format uses separate files for nodes and edges:
    - nodes.csv: type, id, property1, property2, ...
    - edges.csv: rel_type, source_type, source_id, target_type, target_id, property1, ...

    Example:
        ```python
        from converters import CSVConverter

        # Convert ISONGraph to CSV
        graph = ISONGraph("example")
        graph.add_node("person", "alice", {"name": "Alice"})

        converter = CSVConverter()
        nodes_csv, edges_csv = converter.to_csv(graph)

        # Convert CSV to ISONGraph
        graph2 = converter.from_csv(nodes_csv, edges_csv)
        ```
    """

    def __init__(
        self,
        delimiter: str = ",",
        quotechar: str = '"',
        include_headers: bool = True
    ):
        """
        Initialize converter.

        Args:
            delimiter: CSV field delimiter
            quotechar: Quote character for fields
            include_headers: Whether to include header row
        """
        self.delimiter = delimiter
        self.quotechar = quotechar
        self.include_headers = include_headers

    def to_csv(self, graph: ISONGraph) -> Tuple[str, str]:
        """
        Convert ISONGraph to CSV strings.

        Args:
            graph: ISONGraph instance

        Returns:
            Tuple of (nodes_csv, edges_csv) strings
        """
        nodes_csv = self._nodes_to_csv(graph)
        edges_csv = self._edges_to_csv(graph)
        return nodes_csv, edges_csv

    def _nodes_to_csv(self, graph: ISONGraph) -> str:
        """Convert nodes to CSV."""
        output = StringIO()

        # Collect all property keys
        all_props = set()
        for node in graph.nodes():
            all_props.update(node.properties.keys())
        prop_keys = sorted(all_props)

        # Write CSV
        writer = csv.writer(
            output,
            delimiter=self.delimiter,
            quotechar=self.quotechar,
            quoting=csv.QUOTE_MINIMAL
        )

        if self.include_headers:
            writer.writerow(["type", "id"] + prop_keys)

        for node in graph.nodes():
            row = [node.type, node.id]
            for key in prop_keys:
                value = node.properties.get(key, "")
                row.append(self._serialize_value(value))
            writer.writerow(row)

        return output.getvalue()

    def _edges_to_csv(self, graph: ISONGraph) -> str:
        """Convert edges to CSV."""
        output = StringIO()

        # Collect all property keys
        all_props = set()
        for edge in graph.edges():
            all_props.update(edge.properties.keys())
        prop_keys = sorted(all_props)

        # Write CSV
        writer = csv.writer(
            output,
            delimiter=self.delimiter,
            quotechar=self.quotechar,
            quoting=csv.QUOTE_MINIMAL
        )

        if self.include_headers:
            writer.writerow([
                "rel_type", "source_type", "source_id",
                "target_type", "target_id"
            ] + prop_keys)

        for edge in graph.edges():
            row = [
                edge.rel_type,
                edge.source[0],
                edge.source[1],
                edge.target[0],
                edge.target[1]
            ]
            for key in prop_keys:
                value = edge.properties.get(key, "")
                row.append(self._serialize_value(value))
            writer.writerow(row)

        return output.getvalue()

    def from_csv(
        self,
        nodes_csv: str,
        edges_csv: Optional[str] = None,
        name: str = "imported"
    ) -> ISONGraph:
        """
        Convert CSV strings to ISONGraph.

        Args:
            nodes_csv: CSV string with node data
            edges_csv: Optional CSV string with edge data
            name: Name for the resulting graph

        Returns:
            ISONGraph instance
        """
        graph = ISONGraph(name=name)

        # Parse nodes
        self._parse_nodes_csv(graph, nodes_csv)

        # Parse edges
        if edges_csv:
            self._parse_edges_csv(graph, edges_csv)

        return graph

    def _parse_nodes_csv(self, graph: ISONGraph, csv_string: str) -> None:
        """Parse nodes from CSV."""
        reader = csv.reader(
            StringIO(csv_string),
            delimiter=self.delimiter,
            quotechar=self.quotechar
        )

        rows = list(reader)
        if not rows:
            return

        # Determine if first row is header
        if self.include_headers and rows[0][0] in ("type", "Type", "TYPE"):
            headers = rows[0]
            data_rows = rows[1:]
        else:
            # Assume first two columns are type, id
            headers = ["type", "id"] + [f"prop_{i}" for i in range(len(rows[0]) - 2)]
            data_rows = rows

        for row in data_rows:
            if len(row) < 2:
                continue

            node_type = row[0]
            node_id = row[1]
            properties = {}

            for i, value in enumerate(row[2:], start=2):
                if i < len(headers) and value:
                    prop_name = headers[i]
                    properties[prop_name] = self._parse_value(value)

            graph.add_node(node_type, node_id, **properties)

    def _parse_edges_csv(self, graph: ISONGraph, csv_string: str) -> None:
        """
        Parse edges from CSV.

        ISONGraph is a simple graph: at most one edge per
        (rel_type, source, target) triple. A source CSV with a repeated
        row for the same triple - common in event-log-style exports where
        the same relationship recurs - is not an error; the repeat is
        skipped and a single UserWarning is raised at the end summarizing
        how many rows were dropped, so bulk imports don't silently lose
        data without the caller knowing. To keep what made the repeats
        distinct (e.g. a timestamp per occurrence), pre-aggregate them
        into one row's properties (e.g. a count or list column) before
        conversion.
        """
        reader = csv.reader(
            StringIO(csv_string),
            delimiter=self.delimiter,
            quotechar=self.quotechar
        )

        rows = list(reader)
        if not rows:
            return

        # Determine if first row is header
        if self.include_headers and rows[0][0] in ("rel_type", "type", "relationship"):
            headers = rows[0]
            data_rows = rows[1:]
        else:
            headers = ["rel_type", "source_type", "source_id", "target_type", "target_id"]
            headers += [f"prop_{i}" for i in range(len(rows[0]) - 5)]
            data_rows = rows

        skipped_duplicates = 0

        for row in data_rows:
            if len(row) < 5:
                continue

            rel_type = row[0]
            source = (row[1], row[2])
            target = (row[3], row[4])
            properties = {}

            for i, value in enumerate(row[5:], start=5):
                if i < len(headers) and value:
                    prop_name = headers[i]
                    properties[prop_name] = self._parse_value(value)

            # Ensure nodes exist
            if not graph.has_node(*source):
                graph.add_node(source[0], source[1], {})
            if not graph.has_node(*target):
                graph.add_node(target[0], target[1], {})

            if graph.has_edge(rel_type, source, target):
                skipped_duplicates += 1
                continue

            graph.add_edge(rel_type, source, target, **properties)

        if skipped_duplicates:
            warnings.warn(
                f"CSV import skipped {skipped_duplicates} duplicate edge row(s) "
                f"(ISONGraph is a simple graph: at most one edge per "
                f"(rel_type, source, target) triple). Pre-aggregate repeats "
                f"into one row's properties before conversion to keep that data.",
                stacklevel=2,
            )

    def _serialize_value(self, value: Any) -> str:
        """Serialize value for CSV."""
        if value is None:
            return ""
        elif isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, (list, dict)):
            import json
            return json.dumps(value)
        else:
            return str(value)

    def _parse_value(self, s: str) -> Any:
        """Parse CSV value to Python type."""
        s = s.strip()

        if not s:
            return ""

        # Boolean
        if s.lower() == "true":
            return True
        elif s.lower() == "false":
            return False

        # Number
        try:
            if "." in s:
                return float(s)
            else:
                return int(s)
        except ValueError:
            pass

        # JSON array/object
        if s.startswith('[') or s.startswith('{'):
            try:
                import json
                return json.loads(s)
            except (json.JSONDecodeError, ValueError):
                pass

        return s

    def save(
        self,
        graph: ISONGraph,
        nodes_path: str,
        edges_path: Optional[str] = None
    ) -> None:
        """
        Save ISONGraph to CSV files.

        Args:
            graph: ISONGraph instance
            nodes_path: Output path for nodes CSV
            edges_path: Optional output path for edges CSV
        """
        nodes_csv, edges_csv = self.to_csv(graph)

        Path(nodes_path).write_text(nodes_csv, encoding="utf-8")

        if edges_path:
            Path(edges_path).write_text(edges_csv, encoding="utf-8")

    def load(
        self,
        nodes_path: str,
        edges_path: Optional[str] = None,
        name: Optional[str] = None
    ) -> ISONGraph:
        """
        Load ISONGraph from CSV files.

        Args:
            nodes_path: Input path for nodes CSV
            edges_path: Optional input path for edges CSV
            name: Optional graph name (defaults to filename)

        Returns:
            ISONGraph instance
        """
        nodes_csv = Path(nodes_path).read_text(encoding="utf-8")

        edges_csv = None
        if edges_path and Path(edges_path).exists():
            edges_csv = Path(edges_path).read_text(encoding="utf-8")

        if name is None:
            name = Path(nodes_path).stem

        return self.from_csv(nodes_csv, edges_csv, name)


class Neo4jCSVConverter(CSVConverter):
    """
    CSV converter compatible with Neo4j import format.

    Generates CSV files that can be imported using neo4j-admin import
    or LOAD CSV in Cypher.
    """

    def to_neo4j_csv(self, graph: ISONGraph) -> Tuple[str, str]:
        """
        Convert to Neo4j-compatible CSV format.

        Args:
            graph: ISONGraph instance

        Returns:
            Tuple of (nodes_csv, relationships_csv)
        """
        nodes_csv = self._nodes_to_neo4j_csv(graph)
        rels_csv = self._edges_to_neo4j_csv(graph)
        return nodes_csv, rels_csv

    def _nodes_to_neo4j_csv(self, graph: ISONGraph) -> str:
        """Convert nodes to Neo4j import format."""
        output = StringIO()

        # Collect all property keys
        all_props = set()
        for node in graph.nodes():
            all_props.update(node.properties.keys())
        prop_keys = sorted(all_props)

        writer = csv.writer(output)

        # Neo4j header format: :ID, :LABEL, properties...
        header = [":ID", ":LABEL"] + prop_keys
        writer.writerow(header)

        for node in graph.nodes():
            node_id = f"{node.type}:{node.id}"
            row = [node_id, node.type]
            for key in prop_keys:
                value = node.properties.get(key, "")
                row.append(self._serialize_value(value))
            writer.writerow(row)

        return output.getvalue()

    def _edges_to_neo4j_csv(self, graph: ISONGraph) -> str:
        """Convert edges to Neo4j import format."""
        output = StringIO()

        # Collect all property keys
        all_props = set()
        for edge in graph.edges():
            all_props.update(edge.properties.keys())
        prop_keys = sorted(all_props)

        writer = csv.writer(output)

        # Neo4j header: :START_ID, :END_ID, :TYPE, properties...
        header = [":START_ID", ":END_ID", ":TYPE"] + prop_keys
        writer.writerow(header)

        for edge in graph.edges():
            start_id = f"{edge.source[0]}:{edge.source[1]}"
            end_id = f"{edge.target[0]}:{edge.target[1]}"
            row = [start_id, end_id, edge.rel_type]
            for key in prop_keys:
                value = edge.properties.get(key, "")
                row.append(self._serialize_value(value))
            writer.writerow(row)

        return output.getvalue()
