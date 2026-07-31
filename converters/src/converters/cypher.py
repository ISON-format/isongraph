"""
Neo4j Cypher Converter

Convert ISONGraph to Neo4j Cypher statements for import/export.
"""

from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from ison_graph import ISONGraph


class CypherConverter:
    """
    Convert between ISONGraph and Neo4j Cypher statements.

    Generates Cypher CREATE/MERGE statements for importing graphs
    into Neo4j, and can parse simple Cypher patterns.

    Example:
        ```python
        from converters import CypherConverter

        # Convert ISONGraph to Cypher
        graph = ISONGraph("example")
        graph.add_node("Person", "alice", {"name": "Alice"})

        converter = CypherConverter()
        cypher = converter.to_cypher(graph)
        # Creates: CREATE (n:Person {id: 'alice', name: 'Alice'})

        # Generate MERGE statements (idempotent)
        cypher = converter.to_cypher(graph, mode="merge")
        ```
    """

    def __init__(
        self,
        use_labels: bool = True,
        batch_size: int = 1000
    ):
        """
        Initialize converter.

        Args:
            use_labels: Use node types as Neo4j labels
            batch_size: Batch size for UNWIND statements
        """
        self.use_labels = use_labels
        self.batch_size = batch_size

    def to_cypher(
        self,
        graph: ISONGraph,
        mode: str = "create"
    ) -> str:
        """
        Convert ISONGraph to Cypher statements.

        Args:
            graph: ISONGraph instance
            mode: "create" for CREATE, "merge" for MERGE

        Returns:
            Cypher script string
        """
        lines = []
        lines.append(f"// Generated Cypher for graph: {graph.name}")
        lines.append(f"// Nodes: {graph.node_count()}, Edges: {graph.edge_count()}")
        lines.append("")

        # Generate node statements
        lines.append("// Create nodes")
        for node in graph.nodes():
            stmt = self._node_to_cypher(node, mode)
            lines.append(stmt)

        lines.append("")

        # Generate relationship statements
        lines.append("// Create relationships")
        for edge in graph.edges():
            stmt = self._edge_to_cypher(edge, mode)
            lines.append(stmt)

        return "\n".join(lines)

    def to_cypher_batch(
        self,
        graph: ISONGraph,
        mode: str = "merge"
    ) -> str:
        """
        Convert ISONGraph to batched Cypher using UNWIND.

        More efficient for large graphs.

        Args:
            graph: ISONGraph instance
            mode: "create" or "merge"

        Returns:
            Cypher script with UNWIND batches
        """
        lines = []
        lines.append(f"// Batched Cypher for graph: {graph.name}")
        lines.append("")

        # Group nodes by type
        nodes_by_type = {}
        for node in graph.nodes():
            if node.type not in nodes_by_type:
                nodes_by_type[node.type] = []
            nodes_by_type[node.type].append(node)

        # Generate batched node creation per type
        for node_type, nodes in nodes_by_type.items():
            lines.append(f"// Create {node_type} nodes")
            lines.append(self._nodes_batch_cypher(nodes, node_type, mode))
            lines.append("")

        # Group edges by type
        edges_by_type = {}
        for edge in graph.edges():
            if edge.rel_type not in edges_by_type:
                edges_by_type[edge.rel_type] = []
            edges_by_type[edge.rel_type].append(edge)

        # Generate batched edge creation per type
        for rel_type, edges in edges_by_type.items():
            lines.append(f"// Create {rel_type} relationships")
            lines.append(self._edges_batch_cypher(edges, rel_type, mode))
            lines.append("")

        return "\n".join(lines)

    def to_cypher_apoc(
        self,
        graph: ISONGraph,
        mode: str = "merge"
    ) -> str:
        """
        Generate Cypher using APOC procedures for better performance.

        Requires APOC library installed in Neo4j.

        Args:
            graph: ISONGraph instance
            mode: "create" or "merge"

        Returns:
            Cypher script using APOC
        """
        lines = []
        lines.append("// APOC-based import (requires APOC library)")
        lines.append("")

        # Collect all nodes as data
        node_data = []
        for node in graph.nodes():
            data = {"_type": node.type, "_id": node.id}
            data.update(node.properties)
            node_data.append(data)

        # Generate APOC call for nodes
        if node_data:
            lines.append("// Create nodes using APOC")
            lines.append(f"WITH {self._to_cypher_list(node_data)} AS nodes")
            lines.append("UNWIND nodes AS node")
            if mode == "merge":
                lines.append("CALL apoc.merge.node([node._type], {id: node._id}, node) YIELD node AS n")
            else:
                lines.append("CALL apoc.create.node([node._type], node) YIELD node AS n")
            lines.append("RETURN count(n);")
            lines.append("")

        # Collect all edges as data
        edge_data = []
        for edge in graph.edges():
            data = {
                "_rel_type": edge.rel_type,
                "_source_type": edge.source[0],
                "_source_id": edge.source[1],
                "_target_type": edge.target[0],
                "_target_id": edge.target[1],
            }
            data.update(edge.properties)
            edge_data.append(data)

        # Generate APOC call for edges
        if edge_data:
            lines.append("// Create relationships using APOC")
            lines.append(f"WITH {self._to_cypher_list(edge_data)} AS rels")
            lines.append("UNWIND rels AS rel")
            lines.append("MATCH (a) WHERE a.id = rel._source_id")
            lines.append("MATCH (b) WHERE b.id = rel._target_id")
            if mode == "merge":
                lines.append("CALL apoc.merge.relationship(a, rel._rel_type, {}, rel, b) YIELD rel AS r")
            else:
                lines.append("CALL apoc.create.relationship(a, rel._rel_type, rel, b) YIELD rel AS r")
            lines.append("RETURN count(r);")

        return "\n".join(lines)

    def _node_to_cypher(self, node, mode: str) -> str:
        """Convert single node to Cypher statement."""
        if self.use_labels:
            label = f":{self._escape_label(node.type)}"
        else:
            label = ""

        props = {"id": node.id}
        props.update(node.properties)
        props_str = self._props_to_cypher(props)

        if mode == "merge":
            return f"MERGE (n{label} {{id: {self._to_cypher_value(node.id)}}}) SET n += {props_str};"
        else:
            return f"CREATE (n{label} {props_str});"

    def _edge_to_cypher(self, edge, mode: str) -> str:
        """Convert single edge to Cypher statement."""
        source_label = f":{self._escape_label(edge.source[0])}" if self.use_labels else ""
        target_label = f":{self._escape_label(edge.target[0])}" if self.use_labels else ""
        rel_type = self._escape_label(edge.rel_type)

        source_match = f"(a{source_label} {{id: {self._to_cypher_value(edge.source[1])}}})"
        target_match = f"(b{target_label} {{id: {self._to_cypher_value(edge.target[1])}}})"

        if edge.properties:
            props_str = f" {self._props_to_cypher(edge.properties)}"
        else:
            props_str = ""

        if mode == "merge":
            return f"MATCH {source_match}, {target_match} MERGE (a)-[r:{rel_type}]->(b) SET r += {{{self._props_inline(edge.properties)}}};"
        else:
            return f"MATCH {source_match}, {target_match} CREATE (a)-[:{rel_type}{props_str}]->(b);"

    def _nodes_batch_cypher(
        self,
        nodes: List,
        node_type: str,
        mode: str
    ) -> str:
        """Generate batched node creation."""
        label = f":{self._escape_label(node_type)}" if self.use_labels else ""

        data = []
        for node in nodes:
            item = {"id": node.id}
            item.update(node.properties)
            data.append(item)

        lines = []
        lines.append(f"UNWIND {self._to_cypher_list(data)} AS row")

        if mode == "merge":
            lines.append(f"MERGE (n{label} {{id: row.id}})")
            lines.append("SET n += row")
        else:
            lines.append(f"CREATE (n{label})")
            lines.append("SET n = row")

        lines.append("RETURN count(n);")
        return "\n".join(lines)

    def _edges_batch_cypher(
        self,
        edges: List,
        rel_type: str,
        mode: str
    ) -> str:
        """Generate batched edge creation."""
        data = []
        for edge in edges:
            item = {
                "source_type": edge.source[0],
                "source_id": edge.source[1],
                "target_type": edge.target[0],
                "target_id": edge.target[1],
            }
            item.update(edge.properties)
            data.append(item)

        rel_type_escaped = self._escape_label(rel_type)

        lines = []
        lines.append(f"UNWIND {self._to_cypher_list(data)} AS row")
        lines.append("MATCH (a {id: row.source_id})")
        lines.append("MATCH (b {id: row.target_id})")

        if mode == "merge":
            lines.append(f"MERGE (a)-[r:{rel_type_escaped}]->(b)")
            lines.append("SET r += row")
        else:
            lines.append(f"CREATE (a)-[r:{rel_type_escaped}]->(b)")
            lines.append("SET r = row")

        lines.append("RETURN count(r);")
        return "\n".join(lines)

    def _props_to_cypher(self, props: Dict[str, Any]) -> str:
        """Convert properties dict to Cypher map literal."""
        items = []
        for key, value in props.items():
            items.append(f"{self._escape_key(key)}: {self._to_cypher_value(value)}")
        return "{" + ", ".join(items) + "}"

    def _props_inline(self, props: Dict[str, Any]) -> str:
        """Convert properties to inline format for SET."""
        items = []
        for key, value in props.items():
            items.append(f"{self._escape_key(key)}: {self._to_cypher_value(value)}")
        return ", ".join(items)

    def _to_cypher_value(self, value: Any) -> str:
        """Convert Python value to Cypher literal."""
        if value is None:
            return "null"
        elif isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            return f"'{self._escape_string(value)}'"
        elif isinstance(value, list):
            items = [self._to_cypher_value(v) for v in value]
            return "[" + ", ".join(items) + "]"
        elif isinstance(value, dict):
            return self._props_to_cypher(value)
        else:
            return f"'{self._escape_string(str(value))}'"

    def _to_cypher_list(self, items: List[Dict]) -> str:
        """Convert list of dicts to Cypher list literal."""
        cypher_items = [self._props_to_cypher(item) for item in items]
        return "[" + ", ".join(cypher_items) + "]"

    def _escape_label(self, s: str) -> str:
        """Escape string for use as Neo4j label."""
        # Labels should start with letter and contain alphanumeric/underscore
        s = s.replace(" ", "_").replace("-", "_")
        if s and not s[0].isalpha():
            s = "_" + s
        return s

    def _escape_key(self, s: str) -> str:
        """Escape property key."""
        if s.isidentifier():
            return s
        return f"`{s}`"

    def _escape_string(self, s: str) -> str:
        """Escape string for Cypher."""
        return s.replace("\\", "\\\\").replace("'", "\\'")

    def save(self, graph: ISONGraph, path: str, mode: str = "merge") -> None:
        """
        Save ISONGraph as Cypher script.

        Args:
            graph: ISONGraph instance
            path: Output file path
            mode: "create" or "merge"
        """
        cypher = self.to_cypher(graph, mode)
        Path(path).write_text(cypher, encoding="utf-8")

    def save_batch(self, graph: ISONGraph, path: str, mode: str = "merge") -> None:
        """
        Save ISONGraph as batched Cypher script.

        Args:
            graph: ISONGraph instance
            path: Output file path
            mode: "create" or "merge"
        """
        cypher = self.to_cypher_batch(graph, mode)
        Path(path).write_text(cypher, encoding="utf-8")
