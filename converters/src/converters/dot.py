"""
DOT/Graphviz Converter

Convert ISONGraph to DOT format for visualization with Graphviz.
"""

from typing import Any, Dict, List, Optional
from pathlib import Path

from ison_graph import ISONGraph


class DOTConverter:
    """
    Convert ISONGraph to DOT format for Graphviz visualization.

    DOT is a graph description language used by Graphviz and other
    visualization tools.

    Example:
        ```python
        from converters import DOTConverter

        graph = ISONGraph("example")
        graph.add_node("person", "alice", {"name": "Alice"})
        graph.add_node("person", "bob", {"name": "Bob"})
        graph.add_edge("KNOWS", ("person", "alice"), ("person", "bob"))

        converter = DOTConverter()
        dot = converter.to_dot(graph)
        # Output:
        # digraph example {
        #   "person:alice" [label="Alice" shape=ellipse];
        #   "person:bob" [label="Bob" shape=ellipse];
        #   "person:alice" -> "person:bob" [label="KNOWS"];
        # }
        ```
    """

    # Default shapes for different node types
    DEFAULT_SHAPES = {
        "person": "ellipse",
        "company": "box",
        "document": "note",
        "concept": "diamond",
        "event": "hexagon",
    }

    # Default colors for different node types
    DEFAULT_COLORS = {
        "person": "#a8d5ba",
        "company": "#f4a460",
        "document": "#87ceeb",
        "concept": "#dda0dd",
        "event": "#f0e68c",
    }

    def __init__(
        self,
        label_property: str = "name",
        show_properties: bool = False,
        rankdir: str = "TB",
        shapes: Optional[Dict[str, str]] = None,
        colors: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize converter.

        Args:
            label_property: Node property to use as label
            show_properties: Include all properties in node label
            rankdir: Graph direction (TB, BT, LR, RL)
            shapes: Custom shapes for node types
            colors: Custom colors for node types
        """
        self.label_property = label_property
        self.show_properties = show_properties
        self.rankdir = rankdir
        self.shapes = {**self.DEFAULT_SHAPES, **(shapes or {})}
        self.colors = {**self.DEFAULT_COLORS, **(colors or {})}

    def to_dot(self, graph: ISONGraph) -> str:
        """
        Convert ISONGraph to DOT format.

        Args:
            graph: ISONGraph instance

        Returns:
            DOT format string
        """
        lines = []

        # Graph header
        graph_type = "digraph" if graph.directed else "graph"
        lines.append(f'{graph_type} "{self._escape(graph.name)}" {{')

        # Graph attributes
        lines.append(f'  rankdir="{self.rankdir}";')
        lines.append('  node [fontname="Helvetica"];')
        lines.append('  edge [fontname="Helvetica"];')
        lines.append("")

        # Generate subgraphs by node type for clustering
        nodes_by_type = {}
        for node in graph.nodes():
            if node.type not in nodes_by_type:
                nodes_by_type[node.type] = []
            nodes_by_type[node.type].append(node)

        # Output nodes grouped by type
        for node_type, nodes in nodes_by_type.items():
            lines.append(f'  // {node_type} nodes')
            for node in nodes:
                node_dot = self._node_to_dot(node)
                lines.append(f"  {node_dot}")
            lines.append("")

        # Output edges
        lines.append("  // Edges")
        edge_connector = " -> " if graph.directed else " -- "
        for edge in graph.edges():
            edge_dot = self._edge_to_dot(edge, edge_connector)
            lines.append(f"  {edge_dot}")

        lines.append("}")

        return "\n".join(lines)

    def to_dot_clustered(self, graph: ISONGraph) -> str:
        """
        Convert ISONGraph to DOT with subgraph clusters by node type.

        Args:
            graph: ISONGraph instance

        Returns:
            DOT format string with clusters
        """
        lines = []

        graph_type = "digraph" if graph.directed else "graph"
        lines.append(f'{graph_type} "{self._escape(graph.name)}" {{')
        lines.append(f'  rankdir="{self.rankdir}";')
        lines.append('  node [fontname="Helvetica"];')
        lines.append('  edge [fontname="Helvetica"];')
        lines.append('  compound=true;')
        lines.append("")

        # Group nodes by type
        nodes_by_type = {}
        for node in graph.nodes():
            if node.type not in nodes_by_type:
                nodes_by_type[node.type] = []
            nodes_by_type[node.type].append(node)

        # Create subgraph clusters
        cluster_idx = 0
        for node_type, nodes in nodes_by_type.items():
            lines.append(f'  subgraph cluster_{cluster_idx} {{')
            lines.append(f'    label="{node_type}";')
            lines.append(f'    style=rounded;')

            color = self.colors.get(node_type, "#cccccc")
            lines.append(f'    bgcolor="{color}22";')
            lines.append("")

            for node in nodes:
                node_dot = self._node_to_dot(node)
                lines.append(f"    {node_dot}")

            lines.append("  }")
            lines.append("")
            cluster_idx += 1

        # Output edges
        lines.append("  // Edges")
        edge_connector = " -> " if graph.directed else " -- "
        for edge in graph.edges():
            edge_dot = self._edge_to_dot(edge, edge_connector)
            lines.append(f"  {edge_dot}")

        lines.append("}")

        return "\n".join(lines)

    def _node_to_dot(self, node) -> str:
        """Convert node to DOT node definition."""
        node_id = self._node_id(node.type, node.id)

        # Determine label
        if self.show_properties:
            label_parts = [f"{node.type}: {node.id}"]
            for key, value in node.properties.items():
                label_parts.append(f"{key}: {value}")
            label = "\\n".join(label_parts)
        else:
            label = node.properties.get(self.label_property, node.id)

        # Get shape and color
        shape = self.shapes.get(node.type, "ellipse")
        color = self.colors.get(node.type, "#cccccc")

        attrs = [
            f'label="{self._escape(str(label))}"',
            f'shape={shape}',
            f'style=filled',
            f'fillcolor="{color}"',
        ]

        return f'"{node_id}" [{" ".join(attrs)}];'

    def _edge_to_dot(self, edge, connector: str) -> str:
        """Convert edge to DOT edge definition."""
        source_id = self._node_id(edge.source[0], edge.source[1])
        target_id = self._node_id(edge.target[0], edge.target[1])

        attrs = [f'label="{self._escape(edge.rel_type)}"']

        if edge.properties:
            if self.show_properties:
                tooltip_parts = [f"{k}: {v}" for k, v in edge.properties.items()]
                attrs.append(f'tooltip="{self._escape(", ".join(tooltip_parts))}"')

        return f'"{source_id}"{connector}"{target_id}" [{" ".join(attrs)}];'

    def _node_id(self, node_type: str, node_id: str) -> str:
        """Generate unique node ID for DOT."""
        return f"{node_type}:{node_id}"

    def _escape(self, s: str) -> str:
        """Escape string for DOT."""
        return (s.replace("\\", "\\\\")
                 .replace('"', '\\"')
                 .replace("\n", "\\n"))

    def save(self, graph: ISONGraph, path: str, clustered: bool = False) -> None:
        """
        Save ISONGraph as DOT file.

        Args:
            graph: ISONGraph instance
            path: Output file path
            clustered: Use clustered output
        """
        if clustered:
            dot = self.to_dot_clustered(graph)
        else:
            dot = self.to_dot(graph)
        Path(path).write_text(dot, encoding="utf-8")

    def save_svg(
        self,
        graph: ISONGraph,
        path: str,
        clustered: bool = False
    ) -> None:
        """
        Save ISONGraph as SVG using Graphviz.

        Requires Graphviz to be installed.

        Args:
            graph: ISONGraph instance
            path: Output SVG file path
            clustered: Use clustered output
        """
        import subprocess

        if clustered:
            dot = self.to_dot_clustered(graph)
        else:
            dot = self.to_dot(graph)

        # Run graphviz dot command
        result = subprocess.run(
            ["dot", "-Tsvg"],
            input=dot,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"Graphviz error: {result.stderr}")

        Path(path).write_text(result.stdout, encoding="utf-8")

    def save_png(
        self,
        graph: ISONGraph,
        path: str,
        clustered: bool = False
    ) -> None:
        """
        Save ISONGraph as PNG using Graphviz.

        Requires Graphviz to be installed.

        Args:
            graph: ISONGraph instance
            path: Output PNG file path
            clustered: Use clustered output
        """
        import subprocess

        if clustered:
            dot = self.to_dot_clustered(graph)
        else:
            dot = self.to_dot(graph)

        # Run graphviz dot command
        result = subprocess.run(
            ["dot", "-Tpng", "-o", path],
            input=dot,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"Graphviz error: {result.stderr}")
