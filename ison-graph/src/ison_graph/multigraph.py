"""
MultiGraph - parallel edges with stable keys.

``ISONGraph`` is a simple graph: at most one edge per
``(rel_type, source, target)`` triple. ``MultiGraph`` lifts that to
``(rel_type, source, target, key)``, so the same relationship can be
recorded more than once between the same pair of nodes - different time
ranges, different provenance, different weights - without inventing
synthetic relation types.

    from ison_graph.multigraph import MultiGraph

    mg = MultiGraph()
    mg.add_node('person', 1, name='Alice')
    mg.add_node('person', 2, name='Bob')

    mg.add_edge('KNOWS', ('person', 1), ('person', 2), since=2015)  # key=0
    mg.add_edge('KNOWS', ('person', 1), ('person', 2), since=2020)  # key=1

    mg.neighbors(('person', 1), 'KNOWS')   # queried by the real rel_type
    mg.edges_between(('person', 1), ('person', 2), 'KNOWS')  # [(0, e), (1, e)]

The relation type stays exactly what the caller passed - no ``r_<encoded>_0``
rewriting - and ``key`` defaults to 0 so a single edge looks identical to
the simple-graph case.

Serialized output carries an explicit ``meta.graph`` marker
(``ison-graph-multigraph-v1``). ``ISONGraph`` refuses to load a file
bearing that marker rather than silently dropping the parallel edges.

Experimental in 1.3.0: the on-disk format is Python-only until the other
ISONGraph ports implement it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, cast

from ison_parser import (
    Block,
    Document,
    Reference,
    dumps_canonical,
    dumps_canonical_isonl,
    loads,
    loads_isonl,
)

from . import (
    MULTIGRAPH_FORMAT,
    Edge,
    EdgeNotFoundError,
    DuplicateEdgeError,
    GraphError,
    ISONGraph,
    NodeNotFoundError,
    NodeRef,
)

#: (rel_type, source, target, key)
MultiEdgeKey = Tuple[str, NodeRef, NodeRef, int]


class InvalidEdgeKeyError(GraphError):
    """An edge key was not a non-negative integer."""

    def __init__(self, key: Any):
        self.key = key
        super().__init__(
            f"Edge key must be a non-negative int, got {key!r} "
            f"({type(key).__name__})."
        )


@dataclass(eq=False)
class MultiEdge(Edge):
    """An edge carrying a stable integer key.

    ``key`` widens the identity tuple to four elements. Everything the
    base graph does with ``edge.key`` - uniqueness, removal, lookup -
    then distinguishes parallel edges without any further changes.

    .. warning::
       This is a deliberately incompatible subtype. On the base ``Edge``,
       ``.key`` is the ``(rel_type, source, target)`` identity tuple; here
       it is the integer occurrence key, and the identity tuple moves to
       :attr:`edge_key`. Code written against ``Edge`` that reads ``.key``
       as an identity will silently see an int instead. Use
       :attr:`edge_key` for identity and :attr:`edge_id` for the integer
       in code that must work with both.
    """

    # Deliberately narrows the base class's identity-tuple property to the
    # integer occurrence key; see the class docstring.
    key: int = 0  # type: ignore[assignment]

    @property
    def edge_key(self) -> MultiEdgeKey:
        """Full identity: ``(rel_type, source, target, key)``."""
        return (self.rel_type, self.source, self.target, self.key)

    @property
    def edge_id(self) -> int:
        """The integer occurrence key, under a name that means the same
        thing on both ``Edge`` and ``MultiEdge`` consumers."""
        return self.key

    def __hash__(self) -> int:
        return hash(self.edge_key)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, MultiEdge):
            return self.edge_key == other.edge_key
        return False

    def __repr__(self) -> str:
        return f"MultiEdge({self.source} -[{self.rel_type}#{self.key}]-> {self.target})"


class MultiGraph(ISONGraph):
    """Property graph allowing parallel edges, keyed by ``(rel_type, source, target, key)``.

    Iteration order is insertion order (``edges()``, ``neighbors()``),
    which ISON-Cache relies on to keep relation order stable. Serialized
    output is still canonically sorted, matching ISONGraph's byte-identity
    guarantee.
    """

    #: Read by ProtectedGraph to decide whether ``key=`` is a structural
    #: argument here or a property trying to use a reserved name.
    _supports_edge_keys = True

    def __init__(self, name: str = "graph", directed: bool = True):
        super().__init__(name=name, directed=directed)
        # triple -> {key: edge}, insertion-ordered. Without this, key
        # assignment and per-triple lookup scan the whole edge set, making
        # bulk loading quadratic.
        self._triple_edges: Dict[
            Tuple[str, NodeRef, NodeRef], Dict[int, MultiEdge]
        ] = {}
        # triple -> next key to hand out. Kept as a counter rather than
        # recomputed with max(), which would make loading n parallel edges
        # onto one triple quadratic.
        self._next_keys: Dict[Tuple[str, NodeRef, NodeRef], int] = {}

    def _next_key(self, rel_type: str, source: NodeRef, target: NodeRef) -> int:
        """Next key for a triple - 0 for the first edge.

        Keys are monotonic, so removing an edge does not free its key for
        reuse. Removing *every* edge on a triple resets the counter.
        """
        return self._next_keys.get((rel_type, source, target), 0)

    def _index(self, edge: MultiEdge) -> None:
        triple = (edge.rel_type, edge.source, edge.target)
        self._triple_edges.setdefault(triple, {})[edge.key] = edge
        self._next_keys[triple] = max(self._next_keys.get(triple, 0), edge.key + 1)

    def _deindex(self, edge: MultiEdge) -> None:
        triple = (edge.rel_type, edge.source, edge.target)
        siblings = self._triple_edges.get(triple)
        if siblings is not None:
            siblings.pop(edge.key, None)
            # Dropping the empty entry is what lets keys restart at 0.
            if not siblings:
                del self._triple_edges[triple]
                del self._next_keys[triple]

    def add_edge(
        self,
        rel_type: str,
        source: NodeRef,
        target: NodeRef,
        key: Optional[int] = None,
        **properties: Any,
    ) -> MultiEdge:
        """Add an edge, allowing parallel edges between the same pair.

        Args:
            rel_type: Relationship type, stored verbatim.
            source: Source node reference (type, id)
            target: Target node reference (type, id)
            key: Stable edge key. Defaults to 0 for the first edge on a
                triple, then the next unused integer. Must be a
                non-negative int (``bool`` is not accepted).
            **properties: Edge properties

        Raises:
            InvalidIdentifierError: If rel_type contains ':' or '|'
            InvalidEdgeKeyError: If key is not a non-negative int
            NodeNotFoundError: If source or target node doesn't exist
            DuplicateEdgeError: If this exact (rel_type, source, target, key)
                already exists

        Every check runs before any index is touched, so a rejected edge
        leaves the graph exactly as it was.
        """
        self._check_identifier('Relationship type', rel_type)
        self._check_property_names('Edge property', properties)

        if key is not None and (isinstance(key, bool) or not isinstance(key, int)
                                or key < 0):
            raise InvalidEdgeKeyError(key)

        if not self.has_node(source[0], source[1]):
            raise NodeNotFoundError(source)
        if not self.has_node(target[0], target[1]):
            raise NodeNotFoundError(target)

        if key is None:
            key = self._next_key(rel_type, source, target)

        edge_key = (rel_type, source, target, key)
        if edge_key in self._edge_set:
            raise DuplicateEdgeError(edge_key)

        edge = MultiEdge(
            rel_type=rel_type,
            source=source,
            target=target,
            properties=properties,
            key=key,
        )

        self._edges[rel_type].append(edge)
        self._out_edges[source].append(edge)
        self._in_edges[target].append(edge)
        self._edge_set.add(edge_key)
        self._index(edge)

        if not self.directed:
            reverse_key = (rel_type, target, source, key)
            if reverse_key not in self._edge_set:
                reverse_edge = MultiEdge(
                    rel_type=rel_type,
                    source=target,
                    target=source,
                    properties=properties,
                    key=key,
                )
                self._edges[rel_type].append(reverse_edge)
                self._out_edges[target].append(reverse_edge)
                self._in_edges[source].append(reverse_edge)
                self._edge_set.add(reverse_key)
                self._index(reverse_edge)

        return edge

    def _remove_edge_internal(self, edge: Edge) -> None:
        """Drop one edge from every index.

        Overridden because the base version keys off ``edge.key``, which on
        a MultiEdge is the integer key rather than the identity tuple -
        without this, ``remove_node()`` would leave dangling edges behind.
        """
        identity = getattr(edge, "edge_key", edge.key)
        if identity in self._edge_set:
            self._edge_set.remove(identity)
            self._edges[edge.rel_type].remove(edge)
            self._out_edges[edge.source].remove(edge)
            self._in_edges[edge.target].remove(edge)
            self._deindex(cast(MultiEdge, edge))

    def has_edge(
        self,
        rel_type: str,
        source: NodeRef,
        target: NodeRef,
        key: Optional[int] = None,
    ) -> bool:
        """Check whether an edge exists.

        With ``key=None`` this asks "is there *any* edge on this triple",
        which is what traversal-shaped code wants. Pass a key to test one
        specific parallel edge.
        """
        if key is not None:
            return (rel_type, source, target, key) in self._edge_set
        return (rel_type, source, target) in self._triple_edges

    def get_edge(
        self,
        rel_type: str,
        source: NodeRef,
        target: NodeRef,
        key: int = 0,
    ) -> MultiEdge:
        """Get one edge by its full key. Defaults to key 0."""
        edge = self._triple_edges.get((rel_type, source, target), {}).get(key)
        if edge is None:
            raise EdgeNotFoundError((rel_type, source, target, key))
        return edge

    def edges_between(
        self,
        source: NodeRef,
        target: NodeRef,
        rel_type: Optional[str] = None,
    ) -> List[Tuple[int, MultiEdge]]:
        """All parallel edges between two nodes, in insertion order.

        Returns:
            List of ``(key, edge)`` pairs.
        """
        rel_types = [rel_type] if rel_type is not None else list(self._edges.keys())
        result: List[Tuple[int, MultiEdge]] = []
        for rt in rel_types:
            result.extend(self._triple_edges.get((rt, source, target), {}).items())
        return result

    def remove_edge(
        self,
        rel_type: str,
        source: NodeRef,
        target: NodeRef,
        key: Optional[int] = None,
    ) -> None:
        """Remove an edge.

        With ``key=None`` every parallel edge on the triple is removed;
        pass a key to remove just one. On undirected graphs the mirrored
        edge goes with it.
        """
        if not self.has_edge(rel_type, source, target, key):
            raise EdgeNotFoundError(
                (rel_type, source, target) if key is None
                else (rel_type, source, target, key)
            )

        if key is None:
            keys = list(self._triple_edges[(rel_type, source, target)])
        else:
            keys = [key]

        for k in keys:
            doomed = [self._triple_edges[(rel_type, source, target)][k]]
            if not self.directed:
                mirror = self._triple_edges.get((rel_type, target, source), {}).get(k)
                if mirror is not None:
                    doomed.append(mirror)
            for edge in doomed:
                self._remove_edge_internal(edge)

    # =========================================================================
    # Serialization
    # =========================================================================

    def _sorted_edges(self, rel_type: str) -> List[MultiEdge]:
        return sorted(
            cast(List[MultiEdge], self._edges[rel_type]),
            key=lambda e: (e.source[0], str(e.source[1]),
                           e.target[0], str(e.target[1]), e.key),
        )

    def _document(self) -> Document:
        """Build the ISON Document this graph serializes to.

        MultiGraph decides *ordering* here - which blocks, which rows, in
        what sequence - and leaves every byte-level decision (quoting,
        escaping, delimiters, column layout) to ison_parser's canonical
        writer. That is the ISONCS split: one emitter per language, so
        byte-identity is a property of the format rather than something
        each graph port re-derives.

        Rows are pre-sorted to keep output canonical on ison-py 1.0.4, whose
        canonical writer orders rows by their first column alone and breaks
        ties in the order given - so without this, two graphs holding the
        same edges would serialize differently depending on insertion order.

        A later ison-py sorts on the full field tuple, which makes this
        redundant (verified: three construction orders give one output with
        the pre-sort disabled). It stays until that release ships and the
        dependency floor rises, because dropping it early would make
        ISONGraph non-canonical on every installable ison-py.
        """
        blocks = [Block(
            kind="meta",
            name="graph",
            fields=["format", "version", "directed"],
            rows=[{
                "format": MULTIGRAPH_FORMAT,
                "version": 1,
                # Without this an undirected graph reloads as directed and
                # silently changes traversal and mutation semantics.
                "directed": self.directed,
            }],
        )]

        for node_type in sorted(self._nodes.keys()):
            nodes = sorted(self._nodes[node_type].values(), key=lambda n: str(n.id))
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
            edges = self._sorted_edges(rel_type)
            if not edges:
                continue

            prop_keys = sorted({k for e in edges for k in e.properties})
            blocks.append(Block(
                kind="edges",
                name=rel_type,
                fields=["source", "target", "key"] + prop_keys,
                rows=[
                    {
                        "source": Reference(id=str(e.source[1]), type=e.source[0]),
                        "target": Reference(id=str(e.target[1]), type=e.target[0]),
                        "key": e.key,
                        **{k: e.properties.get(k) for k in prop_keys},
                    }
                    for e in edges
                ],
            ))

        return Document(blocks=blocks)

    def to_ison(self) -> str:
        """Serialize to canonical ISON (ISONCS)."""
        return dumps_canonical(self._document())

    def to_isonl(self) -> str:
        """Serialize to canonical ISONL (ISONCS)."""
        return dumps_canonical_isonl(self._document())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a dict carrying the multigraph format marker."""
        result: Dict[str, Any] = {
            "format": MULTIGRAPH_FORMAT,
            "name": self.name,
            "directed": self.directed,
            "nodes": [],
            "edges": [],
        }

        for node in self.nodes():
            result["nodes"].append({"type": node.type, "id": node.id, **node.properties})

        for edge in self.edges():
            result["edges"].append({
                "rel_type": edge.rel_type,
                "source": {"type": edge.source[0], "id": edge.source[1]},
                "target": {"type": edge.target[0], "id": edge.target[1]},
                "key": edge.key,
                "properties": edge.properties,
            })

        return result

    @classmethod
    def _build(cls, doc: Any, name: str) -> "MultiGraph":
        """Shared block walk for from_ison/from_isonl."""
        directed = True
        for block in doc.blocks:
            if block.kind == "meta" and block.name == "graph":
                for row in block.rows:
                    if "directed" in row:
                        directed = bool(row["directed"])

        graph = cls(name=name, directed=directed)

        # Nodes first regardless of block order - the canonical writer
        # sorts blocks by name, which puts 'edges' before 'nodes'.
        for block in doc.blocks:
            if block.kind == "nodes":
                for row in block.rows:
                    props = {k: v for k, v in row.items() if k != "id"}
                    graph.add_node(block.name, row.get("id"), **props)

        for block in doc.blocks:
            if block.kind == "edges":
                for row in block.rows:
                    source = row.get("source")
                    target = row.get("target")
                    props = {
                        k: v for k, v in row.items()
                        if k not in ("source", "target", "key")
                    }

                    if isinstance(source, Reference):
                        source = (source.type,
                                  int(source.id) if source.id.isdigit() else source.id)
                    if isinstance(target, Reference):
                        target = (target.type,
                                  int(target.id) if target.id.isdigit() else target.id)

                    key = int(row.get("key", 0))
                    # An undirected graph serializes both an edge and the
                    # mirror it auto-created; re-adding the mirror would
                    # collide, so skip anything already reconstructed.
                    if graph.has_edge(block.name, source, target, key):
                        continue
                    graph.add_edge(block.name, source, target, key=key, **props)

        return graph

    @classmethod
    def from_ison(cls, text: str, name: str = "graph") -> "MultiGraph":
        """Parse a multigraph from ISON."""
        return cls._build(loads(text), name)

    @classmethod
    def from_isonl(cls, text: str, name: str = "graph") -> "MultiGraph":
        """Parse a multigraph from ISONL."""
        return cls._build(loads_isonl(text), name)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], name: Optional[str] = None) -> "MultiGraph":
        """Parse a multigraph from a dict.

        Accepts payloads without the format marker (a plain simple-graph
        dict is a valid multigraph where every key is 0), but rejects a
        marker naming a format this version doesn't implement.
        """
        fmt = data.get("format")
        if fmt is not None and fmt != MULTIGRAPH_FORMAT:
            raise ValueError(
                f"Cannot load format {fmt!r} as a MultiGraph "
                f"(expected {MULTIGRAPH_FORMAT!r})."
            )

        graph = cls(name=name or data.get("name", "graph"),
                    directed=data.get("directed", True))

        for node_data in data.get("nodes", []):
            props = {k: v for k, v in node_data.items() if k not in ("type", "id")}
            graph.add_node(node_data.get("type", "entity"), node_data.get("id"), **props)

        for edge_data in data.get("edges", []):
            rel_type = edge_data.get("rel_type", edge_data.get("type", "RELATED_TO"))

            source = edge_data.get("source")
            target = edge_data.get("target")
            if isinstance(source, dict):
                source = (source.get("type", "entity"), source.get("id"))
            if isinstance(target, dict):
                target = (target.get("type", "entity"), target.get("id"))

            props = dict(edge_data.get("properties", {}))
            for k, v in edge_data.items():
                if k not in ("rel_type", "type", "source", "target", "properties", "key"):
                    props[k] = v

            key = edge_data.get("key")
            # Skip the mirror an undirected graph already reconstructed.
            if key is not None and graph.has_edge(rel_type, source, target, key):
                continue
            graph.add_edge(rel_type, source, target, key=key, **props)

        return graph


__all__ = ["MultiGraph", "MultiEdge", "MultiEdgeKey", "MULTIGRAPH_FORMAT"]
