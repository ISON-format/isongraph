"""
GraphML Converter

Convert between ISONGraph and GraphML format.
GraphML is an XML-based file format for graphs.
"""

import warnings
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from ison_graph import ISONGraph


class GraphMLConverter:
    """
    Convert between ISONGraph and GraphML format.

    GraphML is a comprehensive XML-based format that supports:
    - Node and edge attributes
    - Directed and undirected graphs
    - Hierarchical graphs
    - Hypergraphs

    Example:
        ```python
        from converters import GraphMLConverter

        # Convert ISONGraph to GraphML
        graph = ISONGraph("example")
        graph.add_node("person", "alice", {"name": "Alice"})

        converter = GraphMLConverter()
        graphml = converter.to_graphml(graph)

        # Convert GraphML to ISONGraph
        graph2 = converter.from_graphml(graphml)
        ```
    """

    GRAPHML_NS = "http://graphml.graphdrawing.org/xmlns"
    XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

    def __init__(self, include_properties: bool = True):
        """
        Initialize converter.

        Args:
            include_properties: Whether to include node/edge properties
        """
        self.include_properties = include_properties

    def to_graphml(self, graph: ISONGraph) -> str:
        """
        Convert ISONGraph to GraphML string.

        Args:
            graph: ISONGraph instance

        Returns:
            GraphML XML string
        """
        # Create root element
        root = ET.Element("graphml")
        root.set("xmlns", self.GRAPHML_NS)
        root.set("xmlns:xsi", self.XSI_NS)
        root.set("xsi:schemaLocation",
                 f"{self.GRAPHML_NS} http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd")

        # Collect all property keys
        node_keys = self._collect_node_keys(graph)
        edge_keys = self._collect_edge_keys(graph)

        # Add key definitions
        for key_name, key_type in node_keys.items():
            key_elem = ET.SubElement(root, "key")
            key_elem.set("id", f"n_{key_name}")
            key_elem.set("for", "node")
            key_elem.set("attr.name", key_name)
            key_elem.set("attr.type", key_type)

        for key_name, key_type in edge_keys.items():
            key_elem = ET.SubElement(root, "key")
            key_elem.set("id", f"e_{key_name}")
            key_elem.set("for", "edge")
            key_elem.set("attr.name", key_name)
            key_elem.set("attr.type", key_type)

        # Add special keys for node type and edge type
        type_key = ET.SubElement(root, "key")
        type_key.set("id", "node_type")
        type_key.set("for", "node")
        type_key.set("attr.name", "type")
        type_key.set("attr.type", "string")

        rel_key = ET.SubElement(root, "key")
        rel_key.set("id", "edge_type")
        rel_key.set("for", "edge")
        rel_key.set("attr.name", "rel_type")
        rel_key.set("attr.type", "string")

        # Create graph element
        graph_elem = ET.SubElement(root, "graph")
        graph_elem.set("id", graph.name)
        graph_elem.set("edgedefault", "directed" if graph.directed else "undirected")

        # Add nodes
        for node in graph.nodes():
            node_elem = ET.SubElement(graph_elem, "node")
            node_elem.set("id", f"{node.type}:{node.id}")

            # Add node type
            data_elem = ET.SubElement(node_elem, "data")
            data_elem.set("key", "node_type")
            data_elem.text = node.type

            # Add properties
            if self.include_properties:
                for prop_name, prop_value in node.properties.items():
                    data_elem = ET.SubElement(node_elem, "data")
                    data_elem.set("key", f"n_{prop_name}")
                    data_elem.text = str(prop_value)

        # Add edges
        edge_id = 0
        for edge in graph.edges():
            edge_elem = ET.SubElement(graph_elem, "edge")
            edge_elem.set("id", f"e{edge_id}")
            edge_elem.set("source", f"{edge.source[0]}:{edge.source[1]}")
            edge_elem.set("target", f"{edge.target[0]}:{edge.target[1]}")

            # Add edge type
            data_elem = ET.SubElement(edge_elem, "data")
            data_elem.set("key", "edge_type")
            data_elem.text = edge.rel_type

            # Add properties
            if self.include_properties:
                for prop_name, prop_value in edge.properties.items():
                    data_elem = ET.SubElement(edge_elem, "data")
                    data_elem.set("key", f"e_{prop_name}")
                    data_elem.text = str(prop_value)

            edge_id += 1

        # Pretty print
        xml_string = ET.tostring(root, encoding="unicode")
        return minidom.parseString(xml_string).toprettyxml(indent="  ")

    def from_graphml(self, graphml_string: str, name: str = "imported") -> ISONGraph:
        """
        Convert GraphML string to ISONGraph.

        Args:
            graphml_string: GraphML XML string
            name: Name for the resulting graph

        Returns:
            ISONGraph instance
        """
        root = ET.fromstring(graphml_string)
        ns = {"gml": self.GRAPHML_NS}

        # Parse key definitions
        keys = {}
        for key_elem in root.findall("gml:key", ns) or root.findall("key"):
            key_id = key_elem.get("id")
            key_name = key_elem.get("attr.name")
            key_for = key_elem.get("for")
            key_type = key_elem.get("attr.type", "string")
            keys[key_id] = {"name": key_name, "for": key_for, "type": key_type}

        # Find graph element
        graph_elem = root.find("gml:graph", ns)
        if graph_elem is None:
            graph_elem = root.find("graph")
        if graph_elem is None:
            raise ValueError("No graph element found in GraphML")

        # Create ISONGraph
        directed = graph_elem.get("edgedefault", "directed") == "directed"
        graph = ISONGraph(name=name, directed=directed)

        # Parse nodes
        for node_elem in graph_elem.findall("gml:node", ns) or graph_elem.findall("node"):
            node_id = node_elem.get("id")
            properties = {}
            node_type = "node"

            for data_elem in node_elem.findall("gml:data", ns) or node_elem.findall("data"):
                key_id = data_elem.get("key")
                value = data_elem.text or ""

                if key_id == "node_type":
                    node_type = value
                elif key_id in keys:
                    prop_name = keys[key_id]["name"]
                    prop_type = keys[key_id]["type"]
                    properties[prop_name] = self._convert_value(value, prop_type)
                else:
                    # Use key_id as property name
                    properties[key_id] = value

            # Parse node_id if it contains type
            if ":" in node_id:
                parts = node_id.split(":", 1)
                node_type = parts[0]
                node_id = parts[1]

            graph.add_node(node_type, node_id, **properties)

        # Parse edges.
        #
        # ISONGraph is a simple graph: at most one edge per
        # (rel_type, source, target) triple. GraphML natively allows
        # parallel edges (it's just a list of <edge> elements with no
        # uniqueness constraint), so a repeat is not an error here - it's
        # skipped and a single UserWarning summarizes how many were
        # dropped. To keep what made the repeats distinct, pre-aggregate
        # them into one <edge>'s properties before conversion.
        skipped_duplicates = 0
        for edge_elem in graph_elem.findall("gml:edge", ns) or graph_elem.findall("edge"):
            source_id = edge_elem.get("source")
            target_id = edge_elem.get("target")
            properties = {}
            rel_type = "RELATED_TO"

            for data_elem in edge_elem.findall("gml:data", ns) or edge_elem.findall("data"):
                key_id = data_elem.get("key")
                value = data_elem.text or ""

                if key_id == "edge_type":
                    rel_type = value
                elif key_id in keys:
                    prop_name = keys[key_id]["name"]
                    prop_type = keys[key_id]["type"]
                    properties[prop_name] = self._convert_value(value, prop_type)
                else:
                    properties[key_id] = value

            # Parse source and target
            source = self._parse_node_ref(source_id)
            target = self._parse_node_ref(target_id)

            if graph.has_edge(rel_type, source, target):
                skipped_duplicates += 1
                continue

            graph.add_edge(rel_type, source, target, **properties)

        if skipped_duplicates:
            warnings.warn(
                f"GraphML import skipped {skipped_duplicates} duplicate edge "
                f"element(s) (ISONGraph is a simple graph: at most one edge "
                f"per (rel_type, source, target) triple). Pre-aggregate "
                f"repeats into one edge's properties before conversion to "
                f"keep that data.",
                stacklevel=2,
            )

        return graph

    def _collect_node_keys(self, graph: ISONGraph) -> Dict[str, str]:
        """Collect all unique node property keys and their types."""
        keys = {}
        for node in graph.nodes():
            for prop_name, prop_value in node.properties.items():
                if prop_name not in keys:
                    keys[prop_name] = self._get_graphml_type(prop_value)
        return keys

    def _collect_edge_keys(self, graph: ISONGraph) -> Dict[str, str]:
        """Collect all unique edge property keys and their types."""
        keys = {}
        for edge in graph.edges():
            for prop_name, prop_value in edge.properties.items():
                if prop_name not in keys:
                    keys[prop_name] = self._get_graphml_type(prop_value)
        return keys

    def _get_graphml_type(self, value: Any) -> str:
        """Get GraphML type for a Python value."""
        if isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "int"
        elif isinstance(value, float):
            return "double"
        else:
            return "string"

    def _convert_value(self, value: str, type_name: str) -> Any:
        """Convert string value to appropriate Python type."""
        if type_name == "int":
            return int(value)
        elif type_name == "double" or type_name == "float":
            return float(value)
        elif type_name == "boolean":
            return value.lower() in ("true", "1", "yes")
        else:
            return value

    def _parse_node_ref(self, node_id: str) -> Tuple[str, str]:
        """Parse node reference from GraphML ID."""
        if ":" in node_id:
            parts = node_id.split(":", 1)
            return (parts[0], parts[1])
        return ("node", node_id)

    def save(self, graph: ISONGraph, path: str) -> None:
        """
        Save ISONGraph to GraphML file.

        Args:
            graph: ISONGraph instance
            path: Output file path
        """
        graphml = self.to_graphml(graph)
        Path(path).write_text(graphml, encoding="utf-8")

    def load(self, path: str, name: Optional[str] = None) -> ISONGraph:
        """
        Load ISONGraph from GraphML file.

        Args:
            path: Input file path
            name: Optional graph name (defaults to filename)

        Returns:
            ISONGraph instance
        """
        graphml = Path(path).read_text(encoding="utf-8")
        if name is None:
            name = Path(path).stem
        return self.from_graphml(graphml, name)
