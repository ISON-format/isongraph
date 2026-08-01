"""
RDF/Turtle Converter

Convert between ISONGraph and RDF (Resource Description Framework) formats.
Supports Turtle, N-Triples, and basic RDF/XML.
"""

from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from urllib.parse import quote, unquote
import re

from ison_graph import ISONGraph


class RDFConverter:
    """
    Convert between ISONGraph and RDF formats.

    RDF (Resource Description Framework) is a standard for semantic web data.
    This converter supports:
    - Turtle (.ttl) - Terse RDF Triple Language
    - N-Triples (.nt) - Line-based RDF format

    Example:
        ```python
        from converters import RDFConverter

        # Convert ISONGraph to Turtle
        graph = ISONGraph("example")
        graph.add_node("person", "alice", {"name": "Alice"})

        converter = RDFConverter(base_uri="http://example.org/")
        turtle = converter.to_turtle(graph)

        # Convert Turtle to ISONGraph
        graph2 = converter.from_turtle(turtle)
        ```
    """

    def __init__(
        self,
        base_uri: str = "http://example.org/",
        include_properties: bool = True
    ):
        """
        Initialize converter.

        Args:
            base_uri: Base URI for generated resources
            include_properties: Whether to include node/edge properties
        """
        self.base_uri = base_uri.rstrip("/") + "/"
        self.include_properties = include_properties

        # Common prefixes
        self.prefixes = {
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "ex": self.base_uri,
        }

    def to_turtle(self, graph: ISONGraph) -> str:
        """
        Convert ISONGraph to Turtle format.

        Args:
            graph: ISONGraph instance

        Returns:
            Turtle format string
        """
        lines = []

        # Add prefixes
        lines.append(f"@prefix rdf: <{self.prefixes['rdf']}> .")
        lines.append(f"@prefix rdfs: <{self.prefixes['rdfs']}> .")
        lines.append(f"@prefix xsd: <{self.prefixes['xsd']}> .")
        lines.append(f"@prefix ex: <{self.base_uri}> .")
        lines.append("")

        # Add nodes with their properties
        for node in graph.nodes():
            node_uri = self._node_to_uri(node.type, node.id)

            # Type statement
            type_uri = f"ex:{self._escape_local(node.type)}"
            lines.append(f"{node_uri} rdf:type {type_uri} ;")

            # ID property
            lines.append(f"    ex:id \"{self._escape_string(node.id)}\" ;")

            # Properties
            if self.include_properties:
                props = list(node.properties.items())
                for i, (prop_name, prop_value) in enumerate(props):
                    prop_uri = f"ex:{self._escape_local(prop_name)}"
                    value_str = self._value_to_turtle(prop_value)
                    separator = " ." if i == len(props) - 1 else " ;"
                    lines.append(f"    {prop_uri} {value_str}{separator}")
            else:
                # Remove trailing semicolon and add period
                if lines[-1].endswith(" ;"):
                    lines[-1] = lines[-1][:-2] + " ."

            lines.append("")

        # Add edges as relationships
        for edge in graph.edges():
            source_uri = self._node_to_uri(edge.source[0], edge.source[1])
            target_uri = self._node_to_uri(edge.target[0], edge.target[1])
            rel_uri = f"ex:{self._escape_local(edge.rel_type)}"

            lines.append(f"{source_uri} {rel_uri} {target_uri} .")

            # Edge properties (as reified statements)
            if self.include_properties and edge.properties:
                stmt_uri = f"ex:stmt_{edge.source[0]}_{edge.source[1]}_{edge.rel_type}_{edge.target[0]}_{edge.target[1]}"
                lines.append(f"{stmt_uri} rdf:type rdf:Statement ;")
                lines.append(f"    rdf:subject {source_uri} ;")
                lines.append(f"    rdf:predicate {rel_uri} ;")
                lines.append(f"    rdf:object {target_uri} ;")

                props = list(edge.properties.items())
                for i, (prop_name, prop_value) in enumerate(props):
                    prop_uri = f"ex:{self._escape_local(prop_name)}"
                    value_str = self._value_to_turtle(prop_value)
                    separator = " ." if i == len(props) - 1 else " ;"
                    lines.append(f"    {prop_uri} {value_str}{separator}")

                lines.append("")

        return "\n".join(lines)

    def to_ntriples(self, graph: ISONGraph) -> str:
        """
        Convert ISONGraph to N-Triples format.

        Args:
            graph: ISONGraph instance

        Returns:
            N-Triples format string
        """
        lines = []

        rdf_type = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"

        # Add nodes
        for node in graph.nodes():
            node_uri = self._node_to_full_uri(node.type, node.id)
            type_uri = f"<{self.base_uri}{self._escape_uri(node.type)}>"

            lines.append(f"{node_uri} {rdf_type} {type_uri} .")

            # ID property
            id_prop = f"<{self.base_uri}id>"
            lines.append(f'{node_uri} {id_prop} "{self._escape_ntriples(node.id)}" .')

            # Properties
            if self.include_properties:
                for prop_name, prop_value in node.properties.items():
                    prop_uri = f"<{self.base_uri}{self._escape_uri(prop_name)}>"
                    value_str = self._value_to_ntriples(prop_value)
                    lines.append(f"{node_uri} {prop_uri} {value_str} .")

        # Add edges
        for edge in graph.edges():
            source_uri = self._node_to_full_uri(edge.source[0], edge.source[1])
            target_uri = self._node_to_full_uri(edge.target[0], edge.target[1])
            rel_uri = f"<{self.base_uri}{self._escape_uri(edge.rel_type)}>"

            lines.append(f"{source_uri} {rel_uri} {target_uri} .")

        return "\n".join(lines)

    def from_turtle(self, turtle_string: str, name: str = "imported") -> ISONGraph:
        """
        Convert Turtle string to ISONGraph.

        This is a basic triple parser, not a full RDF/Turtle implementation:
        it does not understand reified statements (the rdf:Statement /
        rdf:subject / rdf:predicate / rdf:object pattern that to_turtle()
        emits for edges with properties). Turtle produced by to_turtle()
        for edges *without* properties round-trips cleanly; edges *with*
        properties will have their reified statement parsed as extra
        literal nodes/edges rather than folded back into edge properties.

        Args:
            turtle_string: Turtle format string
            name: Name for the resulting graph

        Returns:
            ISONGraph instance
        """
        graph = ISONGraph(name=name)

        # Parse prefixes
        prefixes = {}
        prefix_pattern = re.compile(r'@prefix\s+(\w+):\s*<([^>]+)>\s*\.')
        for match in prefix_pattern.finditer(turtle_string):
            prefixes[match.group(1)] = match.group(2)

        # Simple triple parsing (basic implementation)
        # Remove prefixes and comments
        content = prefix_pattern.sub('', turtle_string)
        content = re.sub(r'#.*$', '', content, flags=re.MULTILINE)

        # Parse subjects with predicates
        subject_pattern = re.compile(
            r'(<[^>]+>|[\w]+:[\w]+)\s+((?:[^.]+\.?\s*)+?)(?=<[^>]+>|[\w]+:[\w]+\s+|$)',
            re.DOTALL
        )

        nodes = {}  # uri -> (type, id, properties)
        edges = []

        for match in subject_pattern.finditer(content):
            subject = self._resolve_uri(match.group(1), prefixes)
            predicates_str = match.group(2).strip()

            # Parse predicate-object pairs
            for line in predicates_str.split(';'):
                line = line.strip()
                if not line or line == '.':
                    continue

                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue

                predicate = self._resolve_uri(parts[0], prefixes)
                obj_str = parts[1].rstrip(' .;')

                # Handle the predicate
                if predicate.endswith('/type') or predicate.endswith('#type'):
                    # rdf:type - defines node type
                    node_type = self._uri_to_local(self._resolve_uri(obj_str, prefixes))
                    node_id = self._uri_to_local(subject)
                    if subject not in nodes:
                        nodes[subject] = [node_type, node_id, {}]
                    else:
                        nodes[subject][0] = node_type
                elif predicate.endswith('/id'):
                    # ID property
                    node_id = self._parse_literal(obj_str)
                    if subject not in nodes:
                        nodes[subject] = ["node", node_id, {}]
                    else:
                        nodes[subject][1] = node_id
                elif obj_str.startswith('<') or ':' in obj_str.split()[0]:
                    # Object is a URI - this is an edge
                    target = self._resolve_uri(obj_str.split()[0], prefixes)
                    rel_type = self._uri_to_local(predicate)
                    edges.append((subject, rel_type, target))
                else:
                    # Literal property
                    if subject not in nodes:
                        nodes[subject] = ["node", self._uri_to_local(subject), {}]
                    prop_name = self._uri_to_local(predicate)
                    prop_value = self._parse_literal(obj_str)
                    nodes[subject][2][prop_name] = prop_value

        # Add nodes to graph
        uri_to_ref = {}
        for uri, (node_type, node_id, properties) in nodes.items():
            graph.add_node(node_type, node_id, **properties)
            uri_to_ref[uri] = (node_type, node_id)

        # Add edges
        for source_uri, rel_type, target_uri in edges:
            if source_uri in uri_to_ref and target_uri in uri_to_ref:
                source = uri_to_ref[source_uri]
                target = uri_to_ref[target_uri]
                if not graph.has_edge(rel_type, source, target):
                    graph.add_edge(rel_type, source, target)

        return graph

    def _node_to_uri(self, node_type: str, node_id: str) -> str:
        """Convert node to prefixed URI."""
        return f"ex:{self._escape_local(node_type)}_{self._escape_local(node_id)}"

    def _node_to_full_uri(self, node_type: str, node_id: str) -> str:
        """Convert node to full URI."""
        return f"<{self.base_uri}{self._escape_uri(node_type)}_{self._escape_uri(node_id)}>"

    def _value_to_turtle(self, value: Any) -> str:
        """Convert Python value to Turtle literal."""
        if isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, int):
            return str(value)
        elif isinstance(value, float):
            return f'"{value}"^^xsd:double'
        else:
            return f'"{self._escape_string(str(value))}"'

    def _value_to_ntriples(self, value: Any) -> str:
        """Convert Python value to N-Triples literal."""
        xsd = "http://www.w3.org/2001/XMLSchema#"
        if isinstance(value, bool):
            return f'"{str(value).lower()}"^^<{xsd}boolean>'
        elif isinstance(value, int):
            return f'"{value}"^^<{xsd}integer>'
        elif isinstance(value, float):
            return f'"{value}"^^<{xsd}double>'
        else:
            return f'"{self._escape_ntriples(str(value))}"'

    def _escape_local(self, s: str) -> str:
        """Escape string for use as local part of prefixed name."""
        return quote(s, safe="")

    def _escape_uri(self, s: str) -> str:
        """Escape string for use in URI."""
        return quote(s, safe="")

    def _escape_string(self, s: str) -> str:
        """Escape string for Turtle literal."""
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    def _escape_ntriples(self, s: str) -> str:
        """Escape string for N-Triples literal."""
        return (s.replace("\\", "\\\\")
                 .replace('"', '\\"')
                 .replace("\n", "\\n")
                 .replace("\r", "\\r")
                 .replace("\t", "\\t"))

    def _resolve_uri(self, uri: str, prefixes: Dict[str, str]) -> str:
        """Resolve prefixed name or full URI to full URI."""
        uri = uri.strip()
        if uri.startswith('<') and uri.endswith('>'):
            return uri[1:-1]
        elif ':' in uri:
            prefix, local = uri.split(':', 1)
            if prefix in prefixes:
                return prefixes[prefix] + local
        return uri

    def _uri_to_local(self, uri: str) -> str:
        """Extract local part from URI."""
        uri = uri.strip('<>')
        # Try to find last / or #
        for sep in ['#', '/']:
            if sep in uri:
                return unquote(uri.rsplit(sep, 1)[-1])
        return unquote(uri)

    def _parse_literal(self, s: str) -> Any:
        """Parse RDF literal to Python value."""
        s = s.strip()

        # Quoted string
        if s.startswith('"'):
            # Find end quote
            end = s.rfind('"')
            if end > 0:
                value = s[1:end]
                # Unescape
                value = value.replace("\\n", "\n").replace("\\\"", '"').replace("\\\\", "\\")

                # Check for datatype
                if "^^" in s[end:]:
                    dtype = s[end:].split("^^")[-1].strip('<>')
                    if "integer" in dtype or "int" in dtype:
                        return int(value)
                    elif "double" in dtype or "float" in dtype:
                        return float(value)
                    elif "boolean" in dtype:
                        return value.lower() == "true"
                return value

        # Unquoted (number or boolean)
        if s.isdigit() or (s.startswith('-') and s[1:].isdigit()):
            return int(s)
        elif s.replace('.', '', 1).isdigit():
            return float(s)
        elif s.lower() in ('true', 'false'):
            return s.lower() == 'true'

        return s

    def save(self, graph: ISONGraph, path: str, format: str = "turtle") -> None:
        """
        Save ISONGraph to RDF file.

        Args:
            graph: ISONGraph instance
            path: Output file path
            format: "turtle" or "ntriples"
        """
        if format == "turtle":
            content = self.to_turtle(graph)
        else:
            content = self.to_ntriples(graph)
        Path(path).write_text(content, encoding="utf-8")

    def load(self, path: str, name: Optional[str] = None) -> ISONGraph:
        """
        Load ISONGraph from RDF file.

        Args:
            path: Input file path
            name: Optional graph name (defaults to filename)

        Returns:
            ISONGraph instance
        """
        content = Path(path).read_text(encoding="utf-8")
        if name is None:
            name = Path(path).stem
        return self.from_turtle(content, name)
