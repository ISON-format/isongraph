#!/usr/bin/env python3
"""
ISONGraph - A Token-Efficient Graph Store

A file-based, in-memory graph store built on ISON format.
Supports property graphs, multi-hop traversal, and path finding.

Usage:
    from ison_graph import ISONGraph, NodeRef

    # Create a graph
    graph = ISONGraph()

    # Add nodes
    graph.add_node('person', 1, name='Alice', age=30)
    graph.add_node('person', 2, name='Bob', age=25)
    graph.add_node('company', 100, name='Acme')

    # Add edges
    graph.add_edge('KNOWS', ('person', 1), ('person', 2), since=2020)
    graph.add_edge('WORKS_AT', ('person', 1), ('company', 100), role='Engineer')

    # Traverse
    friends = graph.neighbors(('person', 1), 'KNOWS')
    fof = graph.multi_hop(('person', 1), 'KNOWS', hops=2)

    # Path finding
    path = graph.shortest_path(('person', 1), ('person', 3))

    # Persistence
    graph.save('social.isong')
    graph = ISONGraph.load('social.isong')

Author: Mahesh Vaikri
Version: 1.4.1
"""

from __future__ import annotations

import math
import re
import warnings
from dataclasses import dataclass, field
from typing import (
    Any, Dict, List, Optional, Set, Tuple,
    Iterator, Callable, Union, Generator
)
from pathlib import Path as FilePath
from collections import defaultdict
from enum import Enum

# Import from ison-py
from ison_parser import (
    Document, Block, Reference,
    loads, dumps, load, dump,
    loads_isonl, dumps_isonl,
    dumps_canonical, dumps_canonical_isonl
)

__version__ = "1.4.1"
__author__ = "Mahesh Vaikri"


# =============================================================================
# Type Aliases
# =============================================================================

NodeRef = Tuple[str, Union[int, str]]  # (type, id) e.g., ('person', 1)
EdgeKey = Tuple[str, NodeRef, NodeRef]  # (rel_type, source, target)

# Simple graphs identify an edge by the triple above; ison_graph.multigraph
# appends an integer occurrence key. Storage and errors are shared, so they
# are typed against whichever form the graph in hand uses.
MultiEdgeKey = Tuple[str, NodeRef, NodeRef, int]
AnyEdgeKey = Union[EdgeKey, MultiEdgeKey]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Node:
    """Represents a graph node with properties"""
    type: str
    id: Union[int, str]
    properties: Dict[str, Any] = field(default_factory=dict)

    @property
    def ref(self) -> NodeRef:
        """Get node reference tuple"""
        return (self.type, self.id)

    def to_ison_ref(self) -> str:
        """Convert to ISON reference string"""
        return f":{self.type}:{self.id}"

    def __hash__(self) -> int:
        return hash(self.ref)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Node):
            return self.ref == other.ref
        return False

    def __repr__(self) -> str:
        return f"Node({self.type}:{self.id}, {self.properties})"


@dataclass
class Edge:
    """Represents a graph edge with properties"""
    rel_type: str
    source: NodeRef
    target: NodeRef
    properties: Dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> EdgeKey:
        """Get edge key tuple"""
        return (self.rel_type, self.source, self.target)

    def __hash__(self) -> int:
        return hash(self.key)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Edge):
            return self.key == other.key
        return False

    def __repr__(self) -> str:
        return f"Edge({self.source} -[{self.rel_type}]-> {self.target})"


@dataclass
class Path:
    """Represents a path through the graph"""
    nodes: List[NodeRef]
    edges: List[Edge]

    @property
    def length(self) -> int:
        """Number of hops in the path"""
        return len(self.edges)

    @property
    def start(self) -> NodeRef:
        """Starting node"""
        return self.nodes[0] if self.nodes else None

    @property
    def end(self) -> NodeRef:
        """Ending node"""
        return self.nodes[-1] if self.nodes else None

    def __repr__(self) -> str:
        path_str = " -> ".join([f":{n[0]}:{n[1]}" for n in self.nodes])
        return f"Path({path_str})"


class Direction(Enum):
    """Edge traversal direction"""
    OUT = "out"
    IN = "in"
    BOTH = "both"


# =============================================================================
# Graph Errors
# =============================================================================

class GraphError(Exception):
    """Base exception for graph errors"""
    pass


class NodeNotFoundError(GraphError):
    """Node does not exist in graph"""
    def __init__(self, node_ref: NodeRef):
        self.node_ref = node_ref
        super().__init__(f"Node not found: :{node_ref[0]}:{node_ref[1]}")


class EdgeNotFoundError(GraphError):
    """Edge does not exist in graph"""
    def __init__(self, edge_key: AnyEdgeKey):
        self.edge_key = edge_key
        super().__init__(f"Edge not found: {edge_key}")


class DuplicateNodeError(GraphError):
    """Node already exists"""
    def __init__(self, node_ref: NodeRef):
        self.node_ref = node_ref
        super().__init__(f"Node already exists: :{node_ref[0]}:{node_ref[1]}")


class DuplicateEdgeError(GraphError):
    """Edge already exists"""
    def __init__(self, edge_key: AnyEdgeKey):
        self.edge_key = edge_key
        super().__init__(f"Edge already exists: {edge_key}")


class InvalidIdentifierError(GraphError):
    """A node type, node id, or relationship type is not representable.

    Node and relationship types become ISON block names; node ids appear
    both as values and inside ``:type:id`` references, which have no
    quoting syntax at all. So an identifier containing whitespace, ':' or
    '|' cannot be written and read back - it either fails to parse or
    parses as different data.

    Mirrors ison-py's own name rules so the failure lands at construction,
    where the offending value is still visible, rather than at
    serialization time or, worse, silently on reload.
    """

    #: Illegal anywhere. Whitespace splits a row or header; ':' delimits
    #: references; '|' delimits ISONL columns.
    FORBIDDEN = (' ', '\t', '\n', '\r', ':', '|')

    #: Additionally illegal in a block name, which ISONL cannot quote.
    BLOCK_FORBIDDEN = FORBIDDEN + ('"', '\\')

    def __init__(self, kind: str, value: str, reason: Optional[str] = None):
        self.kind = kind
        self.value = value
        super().__init__(
            f"{kind} {value!r} is not representable: " + (
                reason or (
                    "it must not be empty or contain whitespace, ':' or '|'"
                    + (", '\"' or '\\'" if 'type' in kind.lower() else "")
                )
            )
        )


class InvalidPropertyNameError(GraphError):
    """A property name has no unambiguous ISON encoding.

    Property names are emitted as ISON field names, and the format applies
    quoting rules to values but not to names. A name containing a space
    splits into two fields on reload, one containing ':' has the remainder
    consumed as a type annotation, and '|', '"' or a backslash breaks
    ISONL. All of these lose data silently, so they are refused here where
    the mistake is still visible.

    '.' is refused for a different reason: it is a working ISON feature
    rather than a gap. ``a.b`` is a dot path, so a flat property is written
    out as ``null`` by the canonical writer and comes back nested through
    the legacy one. ISONGraph properties are flat, so it opts out of the
    feature instead of silently reshaping or dropping data.

    A leading '#' is refused because a field line starting with '#' is read
    as a whole-line comment: the header disappears, the first data row is
    taken as the header, and the entire block is lost without an error.
    Only the first character matters - ``a#b`` round-trips fine - but field
    order is chosen by the canonical writer's sort, not by the caller, and
    '#' sorts ahead of letters, so any such name can end up line-initial.
    """

    #: Whitespace, ':', '|', '"' and '\' match what the ISONL writer
    #: already rejects - the stricter of the two forms, and the direction
    #: the format is heading. '.' is ISONGraph's own dot-path opt-out.
    INVALID_CHARS = (' ', '\t', '\n', '\r', ':', '|', '"', '\\', '.')

    #: Rejected only in first position; see the class docstring.
    INVALID_PREFIXES = ('#',)

    def __init__(self, kind: str, name: str):
        self.kind = kind
        self.name = name
        super().__init__(
            f"{kind} name {name!r} cannot be encoded: property names must "
            f"not be empty, start with '#' (read as a comment, losing the "
            f"whole block), or contain whitespace, ':', '|', '\"', '\\' or "
            f"'.' (a dot path would not survive the round trip)."
        )


class InvalidPropertyValueError(GraphError):
    """A property value cannot survive a serialization round trip.

    ISON has no spelling for a non-finite float: ``nan`` and ``inf`` are
    written bare and read back as the *strings* ``"nan"`` and ``"inf"``, so
    the value changes type silently. Refused here, where the mistake is
    still visible, rather than discovered on reload.
    """

    def __init__(self, kind: str, name: str, value: Any):
        self.kind = kind
        self.name = name
        self.value = value
        super().__init__(
            f"{kind} {name!r} = {value!r} cannot be encoded: a float must "
            f"be finite (NaN and infinity are read back as strings)."
        )


# =============================================================================
# Format markers
# =============================================================================

#: Written by ison_graph.multigraph.MultiGraph into its serialized output.
#: ISONGraph refuses to load anything carrying it: a multigraph holds
#: parallel edges that a simple graph cannot represent, and loading it here
#: would drop them.
MULTIGRAPH_FORMAT = "ison-graph-multigraph-v1"

_MULTIGRAPH_REJECTION = (
    f"This is a {MULTIGRAPH_FORMAT} document, which may contain multiple "
    f"edges per (rel_type, source, target) triple. ISONGraph is a simple "
    f"graph and would silently drop them - load it with "
    f"ison_graph.multigraph.MultiGraph instead."
)


#: The canonical decimal spelling of an integer id: an optional sign and
#: ASCII digits. ``str.isdigit()`` is not this - it misses the sign, so a
#: negative integer id came back from a reference as the string "-1", and
#: it accepts Unicode digits that ``int()`` then refuses.
_INT_TEXT = re.compile(r"-?[0-9]+")


def _ref_id(text: str) -> Union[int, str]:
    """The id an unquoted reference/pattern spells, when no node settles it."""
    return int(text) if _INT_TEXT.fullmatch(text) else text


def _resolve_ref(graph: "ISONGraph", ref: Reference) -> NodeRef:
    """Turn an ISON reference into the NodeRef the graph actually holds.

    ``:person:1`` carries no type information, so the id could be the
    string "1" or the int 1 and the reference looks identical either way.
    Guessing from the text alone silently breaks graphs with string ids
    that happen to be numeric, so resolve against the loaded nodes and only
    fall back to guessing when neither form is present.
    """
    if graph.has_node(ref.type, ref.id):
        return (ref.type, ref.id)
    guess = _ref_id(ref.id)
    return (ref.type, guess)


def _declared_directed(doc: Document) -> Optional[bool]:
    """Read ``meta.graph.directed`` if the document carries it, else None."""
    for block in doc.blocks:
        if block.kind == "meta" and block.name == "graph":
            for row in block.rows:
                if "directed" in row:
                    return bool(row["directed"])
    return None


def _reject_if_multigraph(doc: Document) -> None:
    """Raise if a parsed document is marked as a multigraph."""
    for block in doc.blocks:
        if block.kind == "meta" and block.name == "graph":
            for row in block.rows:
                if row.get("format") == MULTIGRAPH_FORMAT:
                    raise ValueError(_MULTIGRAPH_REJECTION)


# =============================================================================
# ISONGraph - Main Graph Class
# =============================================================================

class ISONGraph:
    """
    In-memory property graph store with ISON persistence.

    Features:
    - Property graph model (nodes and edges with properties)
    - Multiple node types and relationship types
    - O(1) node lookup by (type, id)
    - Multi-hop traversal
    - Shortest path finding (BFS)
    - All paths finding (DFS)
    - ISON/ISONL persistence
    """

    def __init__(self, name: str = "graph", directed: bool = True):
        """
        Initialize an empty graph.

        Args:
            name: Graph name (used in serialization)
            directed: Whether edges are directed (default: True)
        """
        self.name = name
        self.directed = directed

        # Node storage: {type: {id: Node}}
        self._nodes: Dict[str, Dict[Union[int, str], Node]] = defaultdict(dict)

        # Edge storage: {rel_type: [Edge]}
        self._edges: Dict[str, List[Edge]] = defaultdict(list)

        # Index: outgoing edges per node
        self._out_edges: Dict[NodeRef, List[Edge]] = defaultdict(list)

        # Index: incoming edges per node
        self._in_edges: Dict[NodeRef, List[Edge]] = defaultdict(list)

        # Edge uniqueness set
        self._edge_set: Set[AnyEdgeKey] = set()

    # =========================================================================
    # Node Operations
    # =========================================================================

    @staticmethod
    def _check_identifier(kind: str, value: Any) -> None:
        """Reject ':' or '|' in a node type, node id, or relationship type.

        Both characters are structurally significant to the wire format
        (':' delimits ``:type:id`` references, '|' delimits ISONL columns);
        allowing them here would build a graph that throws on
        to_ison()/to_isonl() round-trip instead of failing at construction.
        """
        s = str(value)
        # Types and relationship types become block names, which ISONL
        # additionally cannot quote; ids only have to survive a reference.
        forbidden = (InvalidIdentifierError.BLOCK_FORBIDDEN
                     if 'type' in kind.lower()
                     else InvalidIdentifierError.FORBIDDEN)
        if not s or any(ch in s for ch in forbidden):
            raise InvalidIdentifierError(kind, s)

    @staticmethod
    def _check_property_names(kind: str, properties: Dict[str, Any]) -> None:
        """Reject property names that cannot survive a serialization round trip.

        Names become ISON field names, which the format does not quote; see
        :class:`InvalidPropertyNameError` for what each character does.
        """
        bad = InvalidPropertyNameError.INVALID_CHARS
        prefixes = InvalidPropertyNameError.INVALID_PREFIXES
        for name in properties:
            if not name or name.startswith(prefixes) or any(ch in name for ch in bad):
                raise InvalidPropertyNameError(kind, name)

    @staticmethod
    def _check_property_values(kind: str, properties: Dict[str, Any]) -> None:
        """Reject property values that change type on a round trip.

        Only non-finite floats today; see :class:`InvalidPropertyValueError`.
        """
        for name, value in properties.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise InvalidPropertyValueError(kind, name, value)

    @staticmethod
    def _check_node_id_type(node_id: Any) -> None:
        """A node id is a string or a signed integer, nothing else.

        A reference has no quoting and no type marker, so ``:p:1.5`` and
        ``:p:True`` have nothing to resolve against: the id column writes
        them as ``1.5`` / ``true`` and every edge to the node fails on
        reload. Numeric normalization (``1`` vs ``1.0`` vs ``1e0``) would
        otherwise leak into reference syntax, so floats are refused even
        when integral.
        """
        if isinstance(node_id, bool) or not isinstance(node_id, (int, str)):
            raise InvalidIdentifierError(
                'Node id', repr(node_id),
                f"a node id must be a str or int, not {type(node_id).__name__}",
            )

    def add_node(
        self,
        node_type: str,
        node_id: Union[int, str],
        **properties: Any
    ) -> Node:
        """
        Add a node to the graph.

        Args:
            node_type: Type of node (e.g., 'person', 'company')
            node_id: Unique ID within the type
            **properties: Node properties

        Returns:
            The created Node

        Raises:
            InvalidIdentifierError: If node_type or node_id contains ':' or
                '|', or node_id is not a str or int
            InvalidPropertyValueError: If a property is a non-finite float
            DuplicateNodeError: If node already exists
        """
        self._check_identifier('Node type', node_type)
        self._check_node_id_type(node_id)
        self._check_identifier('Node id', node_id)
        self._check_property_names('Node property', properties)
        self._check_property_values('Node property', properties)

        if node_id in self._nodes[node_type]:
            raise DuplicateNodeError((node_type, node_id))

        # An id column distinguishes 1 from "1" by quoting, but a reference
        # cannot: both write as ':p:1'. Two nodes whose ids differ only by
        # type are therefore addressable in memory and indistinguishable on
        # the wire, and reloading collapses them - so refuse the second.
        if isinstance(node_id, str) and _INT_TEXT.fullmatch(node_id):
            twin: Union[int, str] = int(node_id)
        elif isinstance(node_id, int):
            twin = str(node_id)
        else:
            twin = node_id
        if twin != node_id and twin in self._nodes[node_type]:
            raise DuplicateNodeError((node_type, node_id))

        node = Node(type=node_type, id=node_id, properties=properties)
        self._nodes[node_type][node_id] = node
        return node

    def get_node(self, node_type: str, node_id: Union[int, str]) -> Node:
        """
        Get a node by type and ID.

        Args:
            node_type: Type of node
            node_id: Node ID

        Returns:
            The Node

        Raises:
            NodeNotFoundError: If node doesn't exist
        """
        if node_type not in self._nodes or node_id not in self._nodes[node_type]:
            raise NodeNotFoundError((node_type, node_id))
        return self._nodes[node_type][node_id]

    def get_node_by_ref(self, ref: NodeRef) -> Node:
        """Get node by reference tuple"""
        return self.get_node(ref[0], ref[1])

    def has_node(self, node_type: str, node_id: Union[int, str]) -> bool:
        """Check if node exists"""
        return node_type in self._nodes and node_id in self._nodes[node_type]

    def remove_node(self, node_type: str, node_id: Union[int, str]) -> None:
        """
        Remove a node and all its edges.

        Args:
            node_type: Type of node
            node_id: Node ID

        Raises:
            NodeNotFoundError: If node doesn't exist
        """
        ref = (node_type, node_id)
        if not self.has_node(node_type, node_id):
            raise NodeNotFoundError(ref)

        # Remove all edges connected to this node
        edges_to_remove = list(self._out_edges[ref]) + list(self._in_edges[ref])
        for edge in edges_to_remove:
            self._remove_edge_internal(edge)

        # Remove node
        del self._nodes[node_type][node_id]
        if not self._nodes[node_type]:
            del self._nodes[node_type]

    def update_node(
        self,
        node_type: str,
        node_id: Union[int, str],
        **properties: Any
    ) -> Node:
        """Update node properties"""
        self._check_property_names('Node property', properties)
        self._check_property_values('Node property', properties)
        node = self.get_node(node_type, node_id)
        node.properties.update(properties)
        return node

    def nodes(self, node_type: Optional[str] = None) -> Iterator[Node]:
        """
        Iterate over nodes.

        Args:
            node_type: Filter by type (optional)

        Yields:
            Node objects
        """
        if node_type:
            if node_type in self._nodes:
                yield from self._nodes[node_type].values()
        else:
            for type_nodes in self._nodes.values():
                yield from type_nodes.values()

    def node_count(self, node_type: Optional[str] = None) -> int:
        """Count nodes, optionally filtered by type"""
        if node_type:
            return len(self._nodes.get(node_type, {}))
        return sum(len(nodes) for nodes in self._nodes.values())

    def node_types(self) -> List[str]:
        """Get all node types in the graph"""
        return list(self._nodes.keys())

    # =========================================================================
    # Edge Operations
    # =========================================================================

    def add_edge(
        self,
        rel_type: str,
        source: NodeRef,
        target: NodeRef,
        **properties: Any
    ) -> Edge:
        """
        Add an edge to the graph.

        Args:
            rel_type: Relationship type (e.g., 'KNOWS', 'WORKS_AT')
            source: Source node reference (type, id)
            target: Target node reference (type, id)
            **properties: Edge properties

        Returns:
            The created Edge

        Raises:
            InvalidIdentifierError: If rel_type contains ':' or '|'
            InvalidPropertyValueError: If a property is a non-finite float
            NodeNotFoundError: If source or target node doesn't exist
            DuplicateEdgeError: If edge already exists
        """
        self._check_identifier('Relationship type', rel_type)
        self._check_property_names('Edge property', properties)
        self._check_property_values('Edge property', properties)

        # Validate nodes exist
        if not self.has_node(source[0], source[1]):
            raise NodeNotFoundError(source)
        if not self.has_node(target[0], target[1]):
            raise NodeNotFoundError(target)

        edge_key = (rel_type, source, target)
        if edge_key in self._edge_set:
            raise DuplicateEdgeError(edge_key)

        edge = Edge(rel_type=rel_type, source=source, target=target, properties=properties)

        # Add to storage
        self._edges[rel_type].append(edge)
        self._out_edges[source].append(edge)
        self._in_edges[target].append(edge)
        self._edge_set.add(edge_key)

        # For undirected graphs, add reverse edge
        if not self.directed:
            reverse_key = (rel_type, target, source)
            if reverse_key not in self._edge_set:
                reverse_edge = Edge(
                    rel_type=rel_type,
                    source=target,
                    target=source,
                    properties=properties
                )
                self._edges[rel_type].append(reverse_edge)
                self._out_edges[target].append(reverse_edge)
                self._in_edges[source].append(reverse_edge)
                self._edge_set.add(reverse_key)

        return edge

    def _remove_edge_internal(self, edge: Edge) -> None:
        """Internal method to remove an edge"""
        if edge.key in self._edge_set:
            self._edge_set.remove(edge.key)
            self._edges[edge.rel_type].remove(edge)
            self._out_edges[edge.source].remove(edge)
            self._in_edges[edge.target].remove(edge)

    def remove_edge(
        self,
        rel_type: str,
        source: NodeRef,
        target: NodeRef
    ) -> None:
        """Remove an edge from the graph.

        On undirected graphs the auto-created reverse edge is removed too.
        """
        edge_key = (rel_type, source, target)
        if edge_key not in self._edge_set:
            raise EdgeNotFoundError(edge_key)

        keys_to_remove = [edge_key]
        if not self.directed:
            reverse_key = (rel_type, target, source)
            if reverse_key != edge_key and reverse_key in self._edge_set:
                keys_to_remove.append(reverse_key)

        for key in keys_to_remove:
            for edge in self._edges[rel_type]:
                if edge.key == key:
                    self._remove_edge_internal(edge)
                    break

    def has_edge(
        self,
        rel_type: str,
        source: NodeRef,
        target: NodeRef
    ) -> bool:
        """Check if edge exists"""
        return (rel_type, source, target) in self._edge_set

    def get_edge(
        self,
        rel_type: str,
        source: NodeRef,
        target: NodeRef
    ) -> Edge:
        """Get an edge by its components"""
        edge_key = (rel_type, source, target)
        if edge_key not in self._edge_set:
            raise EdgeNotFoundError(edge_key)

        for edge in self._edges[rel_type]:
            if edge.key == edge_key:
                return edge
        raise EdgeNotFoundError(edge_key)

    def edges(
        self,
        rel_type: Optional[str] = None,
        source: Optional[NodeRef] = None,
        target: Optional[NodeRef] = None
    ) -> Iterator[Edge]:
        """
        Iterate over edges with optional filters.

        Args:
            rel_type: Filter by relationship type
            source: Filter by source node
            target: Filter by target node

        Yields:
            Edge objects
        """
        if source:
            edge_list = self._out_edges.get(source, [])
        elif target:
            edge_list = self._in_edges.get(target, [])
        elif rel_type:
            edge_list = self._edges.get(rel_type, [])
        else:
            edge_list = [e for edges in self._edges.values() for e in edges]

        for edge in edge_list:
            if rel_type and edge.rel_type != rel_type:
                continue
            if source and edge.source != source:
                continue
            if target and edge.target != target:
                continue
            yield edge

    def edge_count(self, rel_type: Optional[str] = None) -> int:
        """Count edges, optionally filtered by type"""
        if rel_type:
            return len(self._edges.get(rel_type, []))
        return len(self._edge_set)

    def edge_types(self) -> List[str]:
        """Get all edge/relationship types in the graph"""
        return list(self._edges.keys())

    # =========================================================================
    # Traversal Operations
    # =========================================================================

    def neighbors(
        self,
        node_ref: NodeRef,
        rel_type: Optional[str] = None,
        direction: Direction = Direction.OUT
    ) -> List[NodeRef]:
        """
        Get neighboring nodes.

        Args:
            node_ref: Starting node reference
            rel_type: Filter by relationship type (optional)
            direction: OUT (default), IN, or BOTH

        Returns:
            List of neighbor node references
        """
        neighbors = []

        if direction in (Direction.OUT, Direction.BOTH):
            for edge in self._out_edges.get(node_ref, []):
                if rel_type is None or edge.rel_type == rel_type:
                    neighbors.append(edge.target)

        if direction in (Direction.IN, Direction.BOTH):
            for edge in self._in_edges.get(node_ref, []):
                if rel_type is None or edge.rel_type == rel_type:
                    neighbors.append(edge.source)

        return neighbors

    def multi_hop(
        self,
        start: NodeRef,
        rel_type: Optional[str] = None,
        hops: int = 1,
        direction: Direction = Direction.OUT
    ) -> List[NodeRef]:
        """
        Get nodes N hops away.

        Args:
            start: Starting node reference
            rel_type: Relationship type to follow (optional, any if None)
            hops: Number of hops (default: 1)
            direction: Traversal direction

        Returns:
            List of nodes exactly N hops away
        """
        if hops < 1:
            return [start]

        current = {start}
        visited = {start}

        for _ in range(hops):
            next_level = set()
            for node in current:
                for neighbor in self.neighbors(node, rel_type, direction):
                    if neighbor not in visited:
                        next_level.add(neighbor)
            visited.update(next_level)
            current = next_level

        return list(current)

    def multi_hop_range(
        self,
        start: NodeRef,
        rel_type: Optional[str] = None,
        min_hops: int = 1,
        max_hops: int = 3,
        direction: Direction = Direction.OUT
    ) -> List[NodeRef]:
        """
        Get nodes within a range of hops.

        Args:
            start: Starting node
            rel_type: Relationship type (optional)
            min_hops: Minimum hops (inclusive)
            max_hops: Maximum hops (inclusive)
            direction: Traversal direction

        Returns:
            List of nodes within hop range
        """
        result = set()
        current = {start}
        visited = {start}

        for hop in range(1, max_hops + 1):
            next_level = set()
            for node in current:
                for neighbor in self.neighbors(node, rel_type, direction):
                    if neighbor not in visited:
                        next_level.add(neighbor)
                        if hop >= min_hops:
                            result.add(neighbor)
            visited.update(next_level)
            current = next_level

            if not current:
                break

        return list(result)

    def traverse(
        self,
        start: NodeRef,
        pattern: List[Tuple[str, Direction]],
        filter_fn: Optional[Callable[[Node], bool]] = None
    ) -> List[NodeRef]:
        """
        Traverse graph following a pattern of relationship types.

        Args:
            start: Starting node
            pattern: List of (rel_type, direction) tuples defining the path
            filter_fn: Optional filter function applied at each step

        Returns:
            List of nodes reached after following the pattern

        Example:
            # Find companies where friends work
            graph.traverse(
                ('person', 1),
                [('KNOWS', Direction.OUT), ('WORKS_AT', Direction.OUT)]
            )
        """
        current = {start}

        for rel_type, direction in pattern:
            next_level = set()
            for node_ref in current:
                neighbors = self.neighbors(node_ref, rel_type, direction)
                for neighbor in neighbors:
                    if filter_fn is None:
                        next_level.add(neighbor)
                    else:
                        node = self.get_node_by_ref(neighbor)
                        if filter_fn(node):
                            next_level.add(neighbor)
            current = next_level
            if not current:
                break

        return list(current)

    # =========================================================================
    # Path Finding
    # =========================================================================

    def shortest_path(
        self,
        start: NodeRef,
        end: NodeRef,
        rel_type: Optional[str] = None,
        max_hops: int = 10,
        direction: Direction = Direction.OUT
    ) -> Optional[Path]:
        """
        Find shortest path between two nodes using BFS.

        Args:
            start: Starting node
            end: Target node
            rel_type: Relationship type to follow (optional)
            max_hops: Maximum path length
            direction: Traversal direction

        Returns:
            Path object or None if no path exists
        """
        if start == end:
            return Path(nodes=[start], edges=[])

        # BFS with path tracking
        queue = [(start, [start], [])]
        visited = {start}

        while queue:
            current, path_nodes, path_edges = queue.pop(0)

            # A path with N nodes has N-1 hops; expanding adds one more hop,
            # so only expand when the resulting path stays within max_hops.
            if len(path_nodes) > max_hops:
                continue

            for edge in self._out_edges.get(current, []) if direction != Direction.IN else []:
                if rel_type and edge.rel_type != rel_type:
                    continue
                if edge.target == end:
                    return Path(
                        nodes=path_nodes + [edge.target],
                        edges=path_edges + [edge]
                    )
                if edge.target not in visited:
                    visited.add(edge.target)
                    queue.append((
                        edge.target,
                        path_nodes + [edge.target],
                        path_edges + [edge]
                    ))

            if direction in (Direction.IN, Direction.BOTH):
                for edge in self._in_edges.get(current, []):
                    if rel_type and edge.rel_type != rel_type:
                        continue
                    if edge.source == end:
                        return Path(
                            nodes=path_nodes + [edge.source],
                            edges=path_edges + [edge]
                        )
                    if edge.source not in visited:
                        visited.add(edge.source)
                        queue.append((
                            edge.source,
                            path_nodes + [edge.source],
                            path_edges + [edge]
                        ))

        return None

    def all_paths(
        self,
        start: NodeRef,
        end: NodeRef,
        rel_type: Optional[str] = None,
        max_hops: int = 5,
        direction: Direction = Direction.OUT
    ) -> List[Path]:
        """
        Find all paths between two nodes using DFS.

        Args:
            start: Starting node
            end: Target node
            rel_type: Relationship type (optional)
            max_hops: Maximum path length
            direction: Traversal direction

        Returns:
            List of all valid paths
        """
        paths: List[Path] = []

        def edges_from(node: NodeRef) -> List[Edge]:
            edges_to_follow: List[Edge] = []
            if direction in (Direction.OUT, Direction.BOTH):
                edges_to_follow.extend(self._out_edges.get(node, []))
            if direction in (Direction.IN, Direction.BOTH):
                edges_to_follow.extend(
                    Edge(e.rel_type, e.target, e.source, e.properties)
                    for e in self._in_edges.get(node, [])
                )
            if rel_type:
                edges_to_follow = [e for e in edges_to_follow if e.rel_type == rel_type]
            return edges_to_follow

        if start == end:
            return [Path(nodes=[start], edges=[])]

        # Iterative DFS with backtracking: one edge-iterator frame per node
        # on the current path, so deep graphs cannot overflow the call stack.
        path_nodes: List[NodeRef] = [start]
        path_edges: List[Edge] = []
        visited: Set[NodeRef] = {start}
        stack: List[Iterator[Edge]] = [iter(edges_from(start))]

        while stack:
            edge = next(stack[-1], None)
            if edge is None:
                # Frame exhausted: backtrack (never pop the start node)
                stack.pop()
                if path_edges:
                    visited.remove(path_nodes.pop())
                    path_edges.pop()
                continue

            next_node = edge.target
            if next_node in visited:
                continue

            visited.add(next_node)
            path_nodes.append(next_node)
            path_edges.append(edge)

            if len(path_nodes) > max_hops + 1:
                # Path too long: undo this step
                visited.remove(path_nodes.pop())
                path_edges.pop()
                continue

            if next_node == end:
                paths.append(Path(nodes=list(path_nodes), edges=list(path_edges)))
                visited.remove(path_nodes.pop())
                path_edges.pop()
                continue

            stack.append(iter(edges_from(next_node)))

        return paths

    def path_exists(
        self,
        start: NodeRef,
        end: NodeRef,
        rel_type: Optional[str] = None,
        max_hops: int = 10
    ) -> bool:
        """Check if a path exists between two nodes"""
        return self.shortest_path(start, end, rel_type, max_hops) is not None

    # =========================================================================
    # Graph Analysis
    # =========================================================================

    def in_degree(self, node_ref: NodeRef) -> int:
        """Count incoming edges"""
        return len(self._in_edges.get(node_ref, []))

    def out_degree(self, node_ref: NodeRef) -> int:
        """Count outgoing edges"""
        return len(self._out_edges.get(node_ref, []))

    def degree(self, node_ref: NodeRef) -> int:
        """Total degree (in + out for directed, unique edges for undirected)"""
        if self.directed:
            return self.in_degree(node_ref) + self.out_degree(node_ref)
        else:
            # For undirected, count unique edges
            edges = set()
            for e in self._out_edges.get(node_ref, []):
                edges.add(frozenset([e.source, e.target]))
            for e in self._in_edges.get(node_ref, []):
                edges.add(frozenset([e.source, e.target]))
            return len(edges)

    def is_connected(self) -> bool:
        """Check if graph is connected (all nodes reachable from any node)"""
        all_nodes = list(self.nodes())
        if not all_nodes:
            return True

        start = all_nodes[0].ref
        visited = {start}
        queue = [start]

        while queue:
            current = queue.pop(0)
            for neighbor in self.neighbors(current, direction=Direction.BOTH):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return len(visited) == len(all_nodes)

    def has_cycle(self, rel_type: Optional[str] = None) -> bool:
        """
        Check if graph has cycles.

        For directed graphs, checks for directed cycles (iterative DFS with a
        recursion stack). For undirected graphs, uses standard undirected
        cycle detection: DFS that tracks the parent node it arrived from, so
        the auto-created reverse edge is not mistaken for a cycle.
        """
        if self.directed:
            return self._has_cycle_directed(rel_type)
        return self._has_cycle_undirected(rel_type)

    def _has_cycle_directed(self, rel_type: Optional[str]) -> bool:
        """Directed cycle detection using an explicit DFS stack."""
        visited: Set[NodeRef] = set()

        for node in self.nodes():
            start = node.ref
            if start in visited:
                continue

            rec_stack: Set[NodeRef] = {start}
            visited.add(start)
            stack: List[Tuple[NodeRef, Iterator[NodeRef]]] = [
                (start, iter(self.neighbors(start, rel_type)))
            ]

            while stack:
                current, neighbors_iter = stack[-1]
                neighbor = next(neighbors_iter, None)
                if neighbor is None:
                    stack.pop()
                    rec_stack.discard(current)
                    continue
                if neighbor in rec_stack:
                    return True
                if neighbor not in visited:
                    visited.add(neighbor)
                    rec_stack.add(neighbor)
                    stack.append((neighbor, iter(self.neighbors(neighbor, rel_type))))

        return False

    def _has_cycle_undirected(self, rel_type: Optional[str]) -> bool:
        """Undirected cycle detection: iterative DFS tracking the parent node."""
        visited: Set[NodeRef] = set()

        for node in self.nodes():
            start = node.ref
            if start in visited:
                continue

            visited.add(start)
            stack: List[Tuple[NodeRef, Optional[NodeRef], Iterator[NodeRef]]] = [
                (start, None, iter(self.neighbors(start, rel_type)))
            ]

            while stack:
                current, parent, neighbors_iter = stack[-1]
                neighbor = next(neighbors_iter, None)
                if neighbor is None:
                    stack.pop()
                    continue
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(
                        (neighbor, current, iter(self.neighbors(neighbor, rel_type)))
                    )
                elif neighbor != parent:
                    # Reached an already-visited node via a new edge -> cycle
                    return True

        return False

    def connected_components(self) -> List[Set[NodeRef]]:
        """Get all connected components"""
        visited = set()
        components = []

        for node in self.nodes():
            if node.ref not in visited:
                component = set()
                queue = [node.ref]

                while queue:
                    current = queue.pop(0)
                    if current not in visited:
                        visited.add(current)
                        component.add(current)
                        for neighbor in self.neighbors(current, direction=Direction.BOTH):
                            if neighbor not in visited:
                                queue.append(neighbor)

                components.append(component)

        return components

    # =========================================================================
    # Serialization (ISON/ISONL)
    # =========================================================================

    def _document(self) -> Document:
        """Build the ISON Document this graph serializes to.

        ISONGraph decides *what* to emit - which blocks, which rows, which
        columns - and hands every byte-level decision to ison_parser's
        canonical writer: quoting, escaping, delimiters, column layout, and
        the final block and row order.

        This used to be hand-rolled here, which meant ISON syntax had two
        implementations per language that had to agree forever. They did
        not: the id column was written unquoted, so a node id containing a
        space produced output that would not reparse, while the same graph
        went through the canonical writer intact.
        """
        blocks = []

        # Directedness is graph semantics, not a presentation choice: an
        # undirected graph that reloads as directed silently changes
        # traversal, degree and cycle results, and its two mirror rows
        # become two distinct edges. Written only when it departs from the
        # default so that every directed graph keeps the bytes it had.
        if not self.directed:
            blocks.append(Block(
                kind="meta",
                name="graph",
                fields=["directed"],
                rows=[{"directed": False}],
            ))

        for node_type in sorted(self._nodes.keys()):
            nodes = list(self._nodes[node_type].values())
            if not nodes:
                continue

            prop_keys = sorted({k for n in nodes for k in n.properties})
            blocks.append(Block(
                kind="nodes",
                name=node_type,
                fields=["id"] + prop_keys,
                rows=[
                    {"id": n.id, **{k: n.properties.get(k) for k in prop_keys}}
                    for n in nodes
                ],
            ))

        for rel_type in sorted(self._edges.keys()):
            edges = self._edges[rel_type]
            if not edges:
                continue

            prop_keys = sorted({k for e in edges for k in e.properties})
            blocks.append(Block(
                kind="edges",
                name=rel_type,
                fields=["source", "target"] + prop_keys,
                rows=[
                    {
                        "source": Reference(id=str(e.source[1]), type=e.source[0]),
                        "target": Reference(id=str(e.target[1]), type=e.target[0]),
                        **{k: e.properties.get(k) for k in prop_keys},
                    }
                    for e in edges
                ],
            ))

        return Document(blocks=blocks)

    def to_ison(self) -> str:
        """
        Serialize graph to canonical ISON (ISONCS).

        Format:
            nodes.{type}
            id {property_fields...}
            {id} {property_values...}

            edges.{rel_type}
            source target {property_fields...}
            {source_ref} {target_ref} {property_values...}

        Output is canonical: the same logical graph always serializes to
        the same bytes regardless of construction order, which is what
        makes it safe for content addressing or prompt caching. Block, row
        and column order are the canonical writer's, not ISONGraph's.
        """
        return dumps_canonical(self._document())

    def to_isonl(self) -> str:
        """
        Serialize graph to canonical ISONL streaming format.

        Row order matches :meth:`to_ison` - see there for the guarantee.
        """
        return dumps_canonical_isonl(self._document())

    def save(self, path: Union[str, FilePath], format: str = "auto") -> None:
        """
        Save graph to file.

        Args:
            path: Output file path
            format: 'ison', 'isonl', or 'auto' (detect from extension)
        """
        path = FilePath(path)

        if format == "auto":
            format = "isonl" if path.suffix == ".isonl" else "ison"

        if format == "isonl":
            content = self.to_isonl()
        else:
            content = self.to_ison()

        path.write_text(content, encoding="utf-8")

    @classmethod
    def from_ison(cls, text: str, name: str = "graph") -> 'ISONGraph':
        """
        Parse graph from ISON format.

        Args:
            text: ISON formatted string
            name: Graph name

        Returns:
            ISONGraph instance
        """
        return cls._build(loads(text), name)

    @classmethod
    def from_isonl(cls, text: str, name: str = "graph") -> 'ISONGraph':
        """Parse graph from ISONL format"""
        return cls._build(loads_isonl(text), name)

    @classmethod
    def _build(cls, doc: Document, name: str) -> 'ISONGraph':
        """Shared block walk for from_ison/from_isonl."""
        _reject_if_multigraph(doc)

        directed = _declared_directed(doc)
        graph = cls(name=name, directed=True if directed is None else directed)

        # Nodes first regardless of block order - the canonical writer sorts
        # blocks by name, which puts 'edges' ahead of 'nodes'.
        for block in doc.blocks:
            if block.kind == "nodes":
                node_type = block.name
                for row in block.rows:
                    node_id = row.get("id")
                    props = {k: v for k, v in row.items() if k != "id"}
                    graph.add_node(node_type, node_id, **props)

        for block in doc.blocks:
            if block.kind == "edges":
                rel_type = block.name
                for row in block.rows:
                    source = row.get("source")
                    target = row.get("target")
                    props = {k: v for k, v in row.items() if k not in ("source", "target")}

                    # Convert Reference objects to tuples
                    if isinstance(source, Reference):
                        source = _resolve_ref(graph, source)
                    if isinstance(target, Reference):
                        target = _resolve_ref(graph, target)

                    # An undirected graph serializes both an edge and the
                    # mirror it auto-created; re-adding the mirror would
                    # collide, so skip anything already reconstructed. A
                    # directed graph keeps raising on a genuine duplicate.
                    if not graph.directed and graph.has_edge(rel_type, source, target):
                        continue
                    graph.add_edge(rel_type, source, target, **props)

        return graph

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize graph to dictionary/JSON format.

        Returns:
            Dictionary with 'name', 'directed', 'nodes', and 'edges' keys
        """
        result = {
            "name": self.name,
            "directed": self.directed,
            "nodes": [],
            "edges": []
        }

        # Serialize nodes
        for node in self.nodes():
            node_dict = {
                "type": node.type,
                "id": node.id,
                **node.properties
            }
            result["nodes"].append(node_dict)

        # Serialize edges
        for edge in self.edges():
            edge_dict = {
                "rel_type": edge.rel_type,
                "source": {"type": edge.source[0], "id": edge.source[1]},
                "target": {"type": edge.target[0], "id": edge.target[1]},
                "properties": edge.properties
            }
            result["edges"].append(edge_dict)

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any], name: Optional[str] = None) -> 'ISONGraph':
        """
        Parse graph from dictionary/JSON format.

        Args:
            data: Dictionary with 'nodes' and 'edges' keys
            name: Graph name (uses data['name'] if not provided)

        Returns:
            ISONGraph instance
        """
        if data.get("format") == MULTIGRAPH_FORMAT:
            raise ValueError(_MULTIGRAPH_REJECTION)

        graph_name = name or data.get("name", "graph")
        directed = data.get("directed", True)
        graph = cls(name=graph_name, directed=directed)

        # Parse nodes
        for node_data in data.get("nodes", []):
            node_type = node_data.get("type", "entity")
            node_id = node_data.get("id")
            # Remaining fields are properties
            props = {k: v for k, v in node_data.items() if k not in ("type", "id")}
            graph.add_node(node_type, node_id, **props)

        # Parse edges. ISONGraph is a simple graph: at most one edge per
        # (rel_type, source, target) triple. A source dict/JSON payload
        # with a repeated edge entry for the same triple - common when
        # converting from an event-log-style export - is not an error;
        # the repeat is skipped and a single UserWarning summarizes how
        # many entries were dropped. To keep what made the repeats
        # distinct, pre-aggregate them into one entry's properties before
        # calling from_dict().
        skipped_duplicates = 0
        for edge_data in data.get("edges", []):
            rel_type = edge_data.get("rel_type", edge_data.get("type", "RELATED_TO"))

            # Handle source/target as dict or tuple
            source = edge_data.get("source")
            target = edge_data.get("target")

            if isinstance(source, dict):
                source = (source.get("type", "entity"), source.get("id"))
            if isinstance(target, dict):
                target = (target.get("type", "entity"), target.get("id"))

            props = edge_data.get("properties", {})
            # Also support inline properties
            for k, v in edge_data.items():
                if k not in ("rel_type", "type", "source", "target", "properties"):
                    props[k] = v

            if graph.has_edge(rel_type, source, target):
                skipped_duplicates += 1
                continue

            graph.add_edge(rel_type, source, target, **props)

        if skipped_duplicates:
            warnings.warn(
                f"from_dict() skipped {skipped_duplicates} duplicate edge "
                f"entr{'y' if skipped_duplicates == 1 else 'ies'} (ISONGraph "
                f"is a simple graph: at most one edge per "
                f"(rel_type, source, target) triple). Pre-aggregate repeats "
                f"into one entry's properties before conversion to keep "
                f"that data.",
                stacklevel=2,
            )

        return graph

    @classmethod
    def load(cls, path: Union[str, FilePath], format: str = "auto") -> 'ISONGraph':
        """
        Load graph from file.

        Args:
            path: Input file path
            format: 'ison', 'isonl', or 'auto'

        Returns:
            ISONGraph instance
        """
        path = FilePath(path)
        text = path.read_text(encoding="utf-8")

        if format == "auto":
            format = "isonl" if path.suffix == ".isonl" else "ison"

        name = path.stem

        if format == "isonl":
            return cls.from_isonl(text, name)
        return cls.from_ison(text, name)

    @classmethod
    def parse(cls, text: str, name: str = "graph") -> 'ISONGraph':
        """Alias for from_ison"""
        return cls.from_ison(text, name)

    # =========================================================================
    # Query Interface (Fluent API)
    # =========================================================================

    def start(self, node_ref: NodeRef) -> 'GraphTraversal':
        """
        Start a fluent traversal from a node.

        Example:
            graph.start(('person', 1)) \\
                .hop('KNOWS') \\
                .hop('WORKS_AT') \\
                .collect()
        """
        return GraphTraversal(self, node_ref)

    def query(self, pattern: str) -> List[NodeRef]:
        """
        Execute a simple pattern query.

        Pattern syntax:
            :type:id -[:REL]-> :type:id
            :type:id -[:REL*N]-> *  (N hops)
            :type:id -[:REL*1..3]-> *  (1-3 hops)

        Example:
            graph.query(":person:1 -[:KNOWS*2]-> *")
        """
        # Simple pattern parsing
        pattern = pattern.strip()

        # Match: :type:id -[:REL*N]-> *
        hop_match = re.match(
            r':(\w+):(-?\w+)\s*-\[:(\w+)\*(\d+)\]->\s*\*',
            pattern
        )
        if hop_match:
            node_type, node_id, rel_type, hops = hop_match.groups()
            return self.multi_hop((node_type, _ref_id(node_id)), rel_type, int(hops))

        # Match: :type:id -[:REL*N..M]-> *
        range_match = re.match(
            r':(\w+):(-?\w+)\s*-\[:(\w+)\*(\d+)\.\.(\d+)\]->\s*\*',
            pattern
        )
        if range_match:
            node_type, node_id, rel_type, min_h, max_h = range_match.groups()
            return self.multi_hop_range(
                (node_type, _ref_id(node_id)), rel_type,
                int(min_h), int(max_h)
            )

        # Match: :type:id -[:REL]-> *
        simple_match = re.match(
            r':(\w+):(-?\w+)\s*-\[:(\w+)\]->\s*\*',
            pattern
        )
        if simple_match:
            node_type, node_id, rel_type = simple_match.groups()
            return self.neighbors((node_type, _ref_id(node_id)), rel_type)

        raise ValueError(f"Invalid query pattern: {pattern}")

    def __repr__(self) -> str:
        return f"ISONGraph(name={self.name}, nodes={self.node_count()}, edges={self.edge_count()})"


# =============================================================================
# Fluent Traversal API
# =============================================================================

class GraphTraversal:
    """Fluent API for graph traversal"""

    def __init__(self, graph: ISONGraph, start: NodeRef):
        self._graph = graph
        self._current: Set[NodeRef] = {start}
        self._visited: Set[NodeRef] = {start}

    def hop(
        self,
        rel_type: Optional[str] = None,
        direction: Direction = Direction.OUT,
        where: Optional[Callable[[Node], bool]] = None
    ) -> 'GraphTraversal':
        """
        Traverse one hop following edges.

        Args:
            rel_type: Relationship type (optional, any if None)
            direction: Traversal direction
            where: Filter function for nodes

        Returns:
            Self for chaining
        """
        next_level = set()

        for node_ref in self._current:
            neighbors = self._graph.neighbors(node_ref, rel_type, direction)
            for neighbor in neighbors:
                if neighbor not in self._visited:
                    if where is None:
                        next_level.add(neighbor)
                    else:
                        node = self._graph.get_node_by_ref(neighbor)
                        if where(node):
                            next_level.add(neighbor)

        self._visited.update(next_level)
        self._current = next_level
        return self

    def hops(
        self,
        n: int,
        rel_type: Optional[str] = None,
        direction: Direction = Direction.OUT
    ) -> 'GraphTraversal':
        """Traverse N hops"""
        for _ in range(n):
            self.hop(rel_type, direction)
        return self

    def filter(self, fn: Callable[[Node], bool]) -> 'GraphTraversal':
        """Filter current nodes"""
        self._current = {
            ref for ref in self._current
            if fn(self._graph.get_node_by_ref(ref))
        }
        return self

    def collect(self) -> List[NodeRef]:
        """Return current nodes as list"""
        return list(self._current)

    def collect_nodes(self) -> List[Node]:
        """Return current nodes as Node objects"""
        return [self._graph.get_node_by_ref(ref) for ref in self._current]

    def count(self) -> int:
        """Count current nodes"""
        return len(self._current)

    def first(self) -> Optional[NodeRef]:
        """Get first node or None"""
        return next(iter(self._current), None)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Version
    '__version__',

    # Core Classes
    'ISONGraph',
    'Node',
    'Edge',
    'Path',
    'GraphTraversal',

    # Types
    'NodeRef',
    'EdgeKey',
    'Direction',

    # Errors
    'GraphError',
    'NodeNotFoundError',
    'EdgeNotFoundError',
    'DuplicateNodeError',
    'DuplicateEdgeError',
    'InvalidIdentifierError',
    'InvalidPropertyNameError',
    'InvalidPropertyValueError',

    # Format markers
    'MULTIGRAPH_FORMAT',

    # Submodules
    'query',
    'schema',
    'multigraph',
    'structural',
]


# =============================================================================
# Submodule Imports (Lazy)
# =============================================================================

_LAZY_SUBMODULES = frozenset({'query', 'schema', 'multigraph', 'structural'})


def __getattr__(name: str):
    """Lazy import for submodules.

    importlib rather than `from . import <name>`: that form probes the
    package with hasattr first, which calls this function again for the same
    name and recurses until the stack runs out. Caching in globals() means a
    submodule resolves here once and is a plain attribute afterwards.
    """
    if name in _LAZY_SUBMODULES:
        import importlib

        module = importlib.import_module(f'.{name}', __name__)
        globals()[name] = module
        return module
    raise AttributeError(f"module 'ison_graph' has no attribute '{name}'")
