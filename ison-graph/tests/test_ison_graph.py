#!/usr/bin/env python3
"""
Tests for ison-graph package
"""

import pytest
import ison_graph
from ison_graph import (
    ISONGraph, Node, Edge, Path, Direction,
    NodeNotFoundError, EdgeNotFoundError,
    DuplicateNodeError, DuplicateEdgeError,
    InvalidIdentifierError,
    InvalidPropertyNameError,
    InvalidPropertyValueError,
)


def test_submodule_version_tracks_package_release():
    """Public package and query module must report the same release."""
    import importlib

    query_module = importlib.import_module("ison_graph.query")
    assert query_module.__version__ == ison_graph.__version__


# =============================================================================
# Identifier Validation Tests
#
# ':' and '|' are structurally significant to the wire format ('type:id'
# references, ISONL columns); allowing them in a node type, node id, or
# relationship type builds a graph that throws on to_ison()/to_isonl()
# round-trip instead of failing loudly at construction. Reproduced live
# before this fix: add_node('a:b', '1') -> to_ison() -> from_ison() raised
# NodeNotFoundError; add_node('rel|type', '1') -> to_isonl() -> from_isonl()
# raised ISONSyntaxError ("expected 3 sections, got 4").
# =============================================================================

class TestIdentifierValidation:
    @pytest.mark.parametrize("bad", ["a:b", "a|b", ":", "|"])
    def test_add_node_rejects_bad_type(self, bad):
        graph = ISONGraph()
        with pytest.raises(InvalidIdentifierError):
            graph.add_node(bad, "1")

    @pytest.mark.parametrize("bad", ["a:b", "a|b"])
    def test_add_node_rejects_bad_id(self, bad):
        graph = ISONGraph()
        with pytest.raises(InvalidIdentifierError):
            graph.add_node("person", bad)

    @pytest.mark.parametrize("bad", ["a:b", "a|b"])
    def test_add_edge_rejects_bad_rel_type(self, bad):
        graph = ISONGraph()
        graph.add_node("person", 1)
        graph.add_node("person", 2)
        with pytest.raises(InvalidIdentifierError):
            graph.add_edge(bad, ("person", 1), ("person", 2))

    @pytest.mark.parametrize("bad", ["a b", "a\tb", "a\nb", ""])
    def test_unrepresentable_identifiers_are_rejected(self, bad):
        """Whitespace and empty used to be accepted and then blow up on
        round trip: ':a b:1' splits mid-reference, and an id column holding
        'a b' reparses as two values. Rejected at construction instead."""
        graph = ISONGraph()
        with pytest.raises(InvalidIdentifierError):
            graph.add_node(bad, "1")
        with pytest.raises(InvalidIdentifierError):
            graph.add_node("p", bad)

    @pytest.mark.parametrize("bad", ['a"b', "a\\b"])
    def test_block_name_only_restrictions(self, bad):
        """ISONL cannot quote a block name, so types are stricter than ids."""
        graph = ISONGraph()
        with pytest.raises(InvalidIdentifierError):
            graph.add_node(bad, "1")
        graph.add_node("p", bad)  # fine as an id - it is a value, not a name

    def test_valid_identifiers_still_allowed(self):
        # Hyphens, dots, '#', quotes-in-ids and unicode all round-trip.
        graph = ISONGraph()
        graph.add_node("a-type", "an-id-1")
        graph.add_node("b.c", "#2")
        graph.add_node("über", "3")
        edge = graph.add_edge("SHARES_BORDER_WITH", ("a-type", "an-id-1"), ("b.c", "#2"))
        assert edge.rel_type == "SHARES_BORDER_WITH"

        restored = ISONGraph.from_ison(graph.to_ison())
        assert restored.node_count() == 3
        assert restored.edge_count() == 1

    def test_no_longer_crashes_on_ison_roundtrip(self):
        # This previously raised NodeNotFoundError on from_ison(), not at
        # add_node() time - the actual bug this validation closes.
        graph = ISONGraph()
        with pytest.raises(InvalidIdentifierError):
            graph.add_node("a:b", "1")

    def test_no_longer_crashes_on_isonl_roundtrip(self):
        graph = ISONGraph()
        with pytest.raises(InvalidIdentifierError):
            graph.add_node("rel|type", "1")


# =============================================================================
# Node Tests
# =============================================================================

class TestTypePreservation:
    """Quoting is the type marker: bare 42 is an int, "42" is a string.
    That holds for property values and node ids alike."""

    @pytest.mark.parametrize("value", [
        42, "42", 1.5, "1.5", True, "true", None, "null", "hello", "",
    ])
    def test_property_values_keep_their_type(self, value):
        graph = ISONGraph()
        graph.add_node("p", 1, v=value)
        back = ISONGraph.from_ison(graph.to_ison()).get_node("p", 1).properties["v"]
        assert back == value and type(back) is type(value)

    @pytest.mark.parametrize("ids", [[1, 2], ["1", "2"], [1, "a"]])
    def test_node_ids_keep_their_type(self, ids):
        graph = ISONGraph()
        for i in ids:
            graph.add_node("p", i)
        graph.add_edge("K", ("p", ids[0]), ("p", ids[1]))

        restored = ISONGraph.from_ison(graph.to_ison())
        assert sorted(((n.id, type(n.id).__name__) for n in restored.nodes()),
                      key=lambda x: str(x[0])) == sorted(
                          ((i, type(i).__name__) for i in ids), key=lambda x: str(x[0]))
        edge = next(iter(restored.edges()))
        assert edge.source == ("p", ids[0]) and edge.target == ("p", ids[1])

    def test_ids_differing_only_by_type_are_refused(self):
        """A reference cannot carry a type: 1 and "1" both write ':p:1'.
        The id column could tell them apart, the reference cannot, so a
        graph holding both reloads with the edges collapsed onto one node.
        Refused at construction instead."""
        graph = ISONGraph()
        graph.add_node("p", 1)
        with pytest.raises(DuplicateNodeError, match=":p:1"):
            graph.add_node("p", "1")

        reverse = ISONGraph()
        reverse.add_node("p", "1")
        with pytest.raises(DuplicateNodeError):
            reverse.add_node("p", 1)

    def test_only_the_colliding_form_is_refused(self):
        graph = ISONGraph()
        graph.add_node("p", 1)
        graph.add_node("p", 2)
        graph.add_node("p", "a")
        graph.add_node("q", "1")   # different type, no collision
        assert graph.node_count() == 4


class TestPropertyNameValidation:
    """Property names become ISON field names, which the format does not
    quote. An unencodable name corrupts silently on reload, so it is
    refused at construction instead."""

    @pytest.mark.parametrize("bad", [
        "first name", "a:b", "a|b", 'a"b', "a\\b", "a\tb", "a\nb", "",
    ])
    def test_illegal_node_property_names_are_rejected(self, bad):
        graph = ISONGraph()
        with pytest.raises(InvalidPropertyNameError):
            graph.add_node("p", 1, **{bad: "v"})

    @pytest.mark.parametrize("bad", ["first name", "a:b", "a|b", ""])
    def test_illegal_edge_property_names_are_rejected(self, bad):
        graph = ISONGraph()
        graph.add_node("p", 1)
        graph.add_node("p", 2)
        with pytest.raises(InvalidPropertyNameError):
            graph.add_edge("K", ("p", 1), ("p", 2), **{bad: "v"})

    @pytest.mark.parametrize("ok", [
        "name", "first_name", "firstName", "a-b", "n1", "über",
    ])
    def test_legal_property_names_survive_a_round_trip(self, ok):
        graph = ISONGraph()
        graph.add_node("p", 1, **{ok: "v"})
        restored = ISONGraph.from_ison(graph.to_ison())
        assert restored.get_node("p", 1).properties[ok] == "v"

    def test_rejected_property_leaves_no_node_behind(self):
        graph = ISONGraph()
        with pytest.raises(InvalidPropertyNameError):
            graph.add_node("p", 1, **{"first name": "v"})
        assert graph.has_node("p", 1) is False

    def test_names_that_used_to_corrupt_silently(self):
        """'first name' emitted as two columns and reloaded as
        {'first': 'v', 'name': None}; 'a:b' had ':b' eaten as a type
        annotation. Both now fail where the mistake is visible."""
        graph = ISONGraph()
        with pytest.raises(InvalidPropertyNameError, match="first name"):
            graph.add_node("p", 1, **{"first name": "v"})
        with pytest.raises(InvalidPropertyNameError, match="a:b"):
            graph.add_node("p", 2, **{"a:b": "v"})

    def test_leading_hash_is_rejected(self):
        """A field line starting with '#' is read as a comment: the header
        vanishes, the first data row is taken as the header, and the whole
        block is lost silently. Reproduced on MultiGraph, where the
        canonical sort put '#flag' first and reloading gave 0 edges."""
        graph = ISONGraph()
        graph.add_node("p", 1)
        graph.add_node("p", 2)
        with pytest.raises(InvalidPropertyNameError, match="comment"):
            graph.add_edge("K", ("p", 1), ("p", 2), **{"#flag": "v"})

    def test_hash_is_only_rejected_in_first_position(self):
        """Over-rejecting would remove a legal name; 'a#b' round-trips."""
        graph = ISONGraph()
        graph.add_node("p", 1, **{"a#b": "v"})
        assert ISONGraph.from_ison(graph.to_ison()).get_node(
            "p", 1).properties["a#b"] == "v"

    def test_dot_paths_are_opted_out_of(self):
        """'.' is a working ISON feature, not a gap: 'a.b' reloads as
        {'a': {'b': 'v'}}. ISONGraph properties are flat, so it declines."""
        graph = ISONGraph()
        with pytest.raises(InvalidPropertyNameError, match="dot path"):
            graph.add_node("p", 1, **{"a.b": "v"})


class TestNodes:
    """Test node operations"""

    def test_add_node(self):
        graph = ISONGraph()
        node = graph.add_node('person', 1, name='Alice', age=30)

        assert node.type == 'person'
        assert node.id == 1
        assert node.properties['name'] == 'Alice'
        assert node.properties['age'] == 30

    def test_get_node(self):
        graph = ISONGraph()
        graph.add_node('person', 1, name='Alice')

        node = graph.get_node('person', 1)
        assert node.properties['name'] == 'Alice'

    def test_get_node_not_found(self):
        graph = ISONGraph()

        with pytest.raises(NodeNotFoundError):
            graph.get_node('person', 999)

    def test_has_node(self):
        graph = ISONGraph()
        graph.add_node('person', 1)

        assert graph.has_node('person', 1)
        assert not graph.has_node('person', 2)
        assert not graph.has_node('company', 1)

    def test_duplicate_node_error(self):
        graph = ISONGraph()
        graph.add_node('person', 1)

        with pytest.raises(DuplicateNodeError):
            graph.add_node('person', 1)

    def test_remove_node(self):
        graph = ISONGraph()
        graph.add_node('person', 1)
        graph.add_node('person', 2)
        graph.add_edge('KNOWS', ('person', 1), ('person', 2))

        graph.remove_node('person', 1)

        assert not graph.has_node('person', 1)
        assert graph.edge_count() == 0  # Edges should be removed

    def test_update_node(self):
        graph = ISONGraph()
        graph.add_node('person', 1, name='Alice', age=30)

        graph.update_node('person', 1, age=31, email='alice@example.com')

        node = graph.get_node('person', 1)
        assert node.properties['age'] == 31
        assert node.properties['email'] == 'alice@example.com'
        assert node.properties['name'] == 'Alice'

    def test_node_count(self):
        graph = ISONGraph()
        graph.add_node('person', 1)
        graph.add_node('person', 2)
        graph.add_node('company', 1)

        assert graph.node_count() == 3
        assert graph.node_count('person') == 2
        assert graph.node_count('company') == 1

    def test_node_types(self):
        graph = ISONGraph()
        graph.add_node('person', 1)
        graph.add_node('company', 1)
        graph.add_node('post', 1)

        types = graph.node_types()
        assert set(types) == {'person', 'company', 'post'}


# =============================================================================
# Edge Tests
# =============================================================================

class TestEdges:
    """Test edge operations"""

    def test_add_edge(self):
        graph = ISONGraph()
        graph.add_node('person', 1)
        graph.add_node('person', 2)

        edge = graph.add_edge('KNOWS', ('person', 1), ('person', 2), since=2020)

        assert edge.rel_type == 'KNOWS'
        assert edge.source == ('person', 1)
        assert edge.target == ('person', 2)
        assert edge.properties['since'] == 2020

    def test_edge_requires_nodes(self):
        graph = ISONGraph()
        graph.add_node('person', 1)

        with pytest.raises(NodeNotFoundError):
            graph.add_edge('KNOWS', ('person', 1), ('person', 999))

    def test_duplicate_edge_error(self):
        graph = ISONGraph()
        graph.add_node('person', 1)
        graph.add_node('person', 2)
        graph.add_edge('KNOWS', ('person', 1), ('person', 2))

        with pytest.raises(DuplicateEdgeError):
            graph.add_edge('KNOWS', ('person', 1), ('person', 2))

    def test_has_edge(self):
        graph = ISONGraph()
        graph.add_node('person', 1)
        graph.add_node('person', 2)
        graph.add_edge('KNOWS', ('person', 1), ('person', 2))

        assert graph.has_edge('KNOWS', ('person', 1), ('person', 2))
        assert not graph.has_edge('KNOWS', ('person', 2), ('person', 1))

    def test_remove_edge(self):
        graph = ISONGraph()
        graph.add_node('person', 1)
        graph.add_node('person', 2)
        graph.add_edge('KNOWS', ('person', 1), ('person', 2))

        graph.remove_edge('KNOWS', ('person', 1), ('person', 2))

        assert not graph.has_edge('KNOWS', ('person', 1), ('person', 2))

    def test_remove_edge_undirected(self):
        """Removing an undirected edge removes the auto-created reverse too"""
        graph = ISONGraph(directed=False)
        graph.add_node('person', 1)
        graph.add_node('person', 2)
        graph.add_edge('KNOWS', ('person', 1), ('person', 2))

        graph.remove_edge('KNOWS', ('person', 1), ('person', 2))

        assert not graph.has_edge('KNOWS', ('person', 1), ('person', 2))
        assert not graph.has_edge('KNOWS', ('person', 2), ('person', 1))
        assert graph.edge_count() == 0

    def test_edge_count(self):
        graph = ISONGraph()
        graph.add_node('person', 1)
        graph.add_node('person', 2)
        graph.add_node('company', 1)
        graph.add_edge('KNOWS', ('person', 1), ('person', 2))
        graph.add_edge('WORKS_AT', ('person', 1), ('company', 1))

        assert graph.edge_count() == 2
        assert graph.edge_count('KNOWS') == 1
        assert graph.edge_count('WORKS_AT') == 1

    def test_edge_types(self):
        graph = ISONGraph()
        graph.add_node('person', 1)
        graph.add_node('person', 2)
        graph.add_node('company', 1)
        graph.add_edge('KNOWS', ('person', 1), ('person', 2))
        graph.add_edge('WORKS_AT', ('person', 1), ('company', 1))

        types = graph.edge_types()
        assert set(types) == {'KNOWS', 'WORKS_AT'}


# =============================================================================
# Traversal Tests
# =============================================================================

class TestTraversal:
    """Test graph traversal"""

    def setup_method(self):
        """Create a test graph: 1 -> 2 -> 3 -> 4 -> 5"""
        self.graph = ISONGraph()
        for i in range(1, 6):
            self.graph.add_node('person', i, name=f'Person{i}')

        self.graph.add_edge('KNOWS', ('person', 1), ('person', 2))
        self.graph.add_edge('KNOWS', ('person', 2), ('person', 3))
        self.graph.add_edge('KNOWS', ('person', 3), ('person', 4))
        self.graph.add_edge('KNOWS', ('person', 4), ('person', 5))

    def test_neighbors(self):
        neighbors = self.graph.neighbors(('person', 2), 'KNOWS')
        assert neighbors == [('person', 3)]

    def test_neighbors_incoming(self):
        neighbors = self.graph.neighbors(('person', 2), 'KNOWS', Direction.IN)
        assert neighbors == [('person', 1)]

    def test_neighbors_both(self):
        neighbors = self.graph.neighbors(('person', 2), 'KNOWS', Direction.BOTH)
        assert set(neighbors) == {('person', 1), ('person', 3)}

    def test_multi_hop_1(self):
        result = self.graph.multi_hop(('person', 1), 'KNOWS', hops=1)
        assert result == [('person', 2)]

    def test_multi_hop_2(self):
        result = self.graph.multi_hop(('person', 1), 'KNOWS', hops=2)
        assert result == [('person', 3)]

    def test_multi_hop_3(self):
        result = self.graph.multi_hop(('person', 1), 'KNOWS', hops=3)
        assert result == [('person', 4)]

    def test_multi_hop_range(self):
        result = self.graph.multi_hop_range(('person', 1), 'KNOWS', min_hops=1, max_hops=3)
        assert set(result) == {('person', 2), ('person', 3), ('person', 4)}

    def test_traverse_pattern(self):
        # Add company and works_at edge
        self.graph.add_node('company', 100, name='Acme')
        self.graph.add_edge('WORKS_AT', ('person', 2), ('company', 100))

        # person:1 -> KNOWS -> person:2 -> WORKS_AT -> company:100
        result = self.graph.traverse(
            ('person', 1),
            [('KNOWS', Direction.OUT), ('WORKS_AT', Direction.OUT)]
        )
        assert result == [('company', 100)]


# =============================================================================
# Path Finding Tests
# =============================================================================

class TestPathFinding:
    """Test path finding algorithms"""

    def setup_method(self):
        """Create test graph"""
        self.graph = ISONGraph()
        for i in range(1, 6):
            self.graph.add_node('person', i)

        # 1 -> 2 -> 3
        #      |    |
        #      v    v
        #      4 -> 5
        self.graph.add_edge('KNOWS', ('person', 1), ('person', 2))
        self.graph.add_edge('KNOWS', ('person', 2), ('person', 3))
        self.graph.add_edge('KNOWS', ('person', 2), ('person', 4))
        self.graph.add_edge('KNOWS', ('person', 3), ('person', 5))
        self.graph.add_edge('KNOWS', ('person', 4), ('person', 5))

    def test_shortest_path(self):
        path = self.graph.shortest_path(('person', 1), ('person', 5))

        assert path is not None
        assert path.length == 3
        assert path.start == ('person', 1)
        assert path.end == ('person', 5)

    def test_shortest_path_same_node(self):
        path = self.graph.shortest_path(('person', 1), ('person', 1))

        assert path is not None
        assert path.length == 0

    def test_no_path(self):
        self.graph.add_node('person', 99)  # Isolated node

        path = self.graph.shortest_path(('person', 1), ('person', 99))
        assert path is None

    def test_path_exists(self):
        assert self.graph.path_exists(('person', 1), ('person', 5))
        assert not self.graph.path_exists(('person', 5), ('person', 1))  # Directed

    def test_all_paths(self):
        paths = self.graph.all_paths(('person', 1), ('person', 5))

        assert len(paths) == 2  # Two paths: 1->2->3->5 and 1->2->4->5

    def test_shortest_path_max_hops_boundary(self):
        """max_hops must be a strict upper bound on path length"""
        # 1 -> 2 -> 3 needs 2 hops
        assert self.graph.shortest_path(('person', 1), ('person', 3), max_hops=1) is None

        path = self.graph.shortest_path(('person', 1), ('person', 3), max_hops=2)
        assert path is not None
        assert path.length == 2

        # Direct edge still found with max_hops=1
        path = self.graph.shortest_path(('person', 1), ('person', 2), max_hops=1)
        assert path is not None
        assert path.length == 1


# =============================================================================
# Graph Analysis Tests
# =============================================================================

class TestGraphAnalysis:
    """Test graph analysis functions"""

    def test_degree(self):
        graph = ISONGraph()
        graph.add_node('person', 1)
        graph.add_node('person', 2)
        graph.add_node('person', 3)
        graph.add_edge('KNOWS', ('person', 1), ('person', 2))
        graph.add_edge('KNOWS', ('person', 1), ('person', 3))

        assert graph.out_degree(('person', 1)) == 2
        assert graph.in_degree(('person', 1)) == 0
        assert graph.in_degree(('person', 2)) == 1

    def test_is_connected(self):
        graph = ISONGraph()
        graph.add_node('person', 1)
        graph.add_node('person', 2)
        graph.add_edge('KNOWS', ('person', 1), ('person', 2))

        assert graph.is_connected()

        graph.add_node('person', 99)  # Isolated
        assert not graph.is_connected()

    def test_has_cycle(self):
        graph = ISONGraph()
        graph.add_node('person', 1)
        graph.add_node('person', 2)
        graph.add_node('person', 3)
        graph.add_edge('KNOWS', ('person', 1), ('person', 2))
        graph.add_edge('KNOWS', ('person', 2), ('person', 3))

        assert not graph.has_cycle()

        graph.add_edge('KNOWS', ('person', 3), ('person', 1))
        assert graph.has_cycle()

    def test_has_cycle_undirected_single_edge(self):
        """A single undirected edge is not a cycle"""
        graph = ISONGraph(directed=False)
        graph.add_node('person', 1)
        graph.add_node('person', 2)
        graph.add_edge('KNOWS', ('person', 1), ('person', 2))

        assert not graph.has_cycle()

        # An acyclic undirected chain is not a cycle either
        graph.add_node('person', 3)
        graph.add_edge('KNOWS', ('person', 2), ('person', 3))
        assert not graph.has_cycle()

    def test_has_cycle_undirected_triangle(self):
        """A real undirected triangle is a cycle"""
        graph = ISONGraph(directed=False)
        graph.add_node('person', 1)
        graph.add_node('person', 2)
        graph.add_node('person', 3)
        graph.add_edge('KNOWS', ('person', 1), ('person', 2))
        graph.add_edge('KNOWS', ('person', 2), ('person', 3))
        graph.add_edge('KNOWS', ('person', 3), ('person', 1))

        assert graph.has_cycle()

    def test_connected_components(self):
        graph = ISONGraph()
        graph.add_node('person', 1)
        graph.add_node('person', 2)
        graph.add_node('person', 3)
        graph.add_node('person', 4)
        graph.add_edge('KNOWS', ('person', 1), ('person', 2))
        graph.add_edge('KNOWS', ('person', 3), ('person', 4))

        components = graph.connected_components()
        assert len(components) == 2


# =============================================================================
# Serialization Tests
# =============================================================================

class TestSerialization:
    """Test ISON serialization"""

    def test_to_ison(self):
        graph = ISONGraph()
        graph.add_node('person', 1, name='Alice')
        graph.add_node('person', 2, name='Bob')
        graph.add_edge('KNOWS', ('person', 1), ('person', 2), since=2020)

        ison = graph.to_ison()

        assert 'nodes.person' in ison
        assert 'edges.KNOWS' in ison
        assert ':person:1' in ison
        assert ':person:2' in ison

    def test_from_ison(self):
        ison = """
nodes.person
id name
1 Alice
2 Bob

edges.KNOWS
source target since
:person:1 :person:2 2020
"""
        graph = ISONGraph.from_ison(ison)

        assert graph.node_count() == 2
        assert graph.edge_count() == 1
        assert graph.get_node('person', 1).properties['name'] == 'Alice'

    def test_roundtrip(self):
        graph1 = ISONGraph()
        graph1.add_node('person', 1, name='Alice', age=30)
        graph1.add_node('person', 2, name='Bob', age=25)
        graph1.add_edge('KNOWS', ('person', 1), ('person', 2), since=2020)

        ison = graph1.to_ison()
        graph2 = ISONGraph.from_ison(ison)

        assert graph2.node_count() == graph1.node_count()
        assert graph2.edge_count() == graph1.edge_count()

    def test_to_isonl(self):
        graph = ISONGraph()
        graph.add_node('person', 1, name='Alice')
        graph.add_edge('KNOWS', ('person', 1), ('person', 1))  # Self loop for test

        isonl = graph.to_isonl()

        assert 'nodes.person|' in isonl
        assert 'edges.KNOWS|' in isonl

    SPECIAL_VALUES = {
        'title': 'Hello World',      # contains a space
        'tag': 'a|b',                # contains a pipe
        'body': 'line1\nline2',      # contains a newline
        'note': '',                  # empty string
        'quote': 'say "hi"',         # contains a double quote
    }

    def test_roundtrip_special_values_ison(self):
        """Values with spaces, pipes, newlines, quotes, and empty strings
        survive an ISON round-trip losslessly"""
        graph1 = ISONGraph()
        graph1.add_node('doc', 1, **self.SPECIAL_VALUES)

        graph2 = ISONGraph.from_ison(graph1.to_ison())

        props = graph2.get_node('doc', 1).properties
        for key, expected in self.SPECIAL_VALUES.items():
            assert props[key] == expected

    def test_roundtrip_special_values_isonl(self):
        """Values with spaces, pipes, newlines, quotes, and empty strings
        survive an ISONL round-trip losslessly"""
        graph1 = ISONGraph()
        graph1.add_node('doc', 1, **self.SPECIAL_VALUES)

        graph2 = ISONGraph.from_isonl(graph1.to_isonl())

        props = graph2.get_node('doc', 1).properties
        for key, expected in self.SPECIAL_VALUES.items():
            assert props[key] == expected


# =============================================================================
# Identity Contract Tests
#
# A graph's meaning must survive dump -> load unchanged: a node id keeps its
# type and sign, an undirected graph stays undirected, and a value that the
# wire format cannot spell is refused before it enters the graph rather than
# changing type on reload. Each of these was reproduced live on 1.4.0:
# :p:-1 raised NodeNotFoundError on reload (isdigit() drops the sign), an
# undirected graph reloaded as directed with its mirror rows as two edges,
# float/bool ids wrote fine and then no edge to them resolved, and NaN came
# back as the string "nan".
# =============================================================================

class TestNodeIdDomain:
    """Node ids are strings or signed integers, nothing else."""

    @pytest.mark.parametrize("bad", [1.5, 1.0, -4.25, float('nan'), float('inf'), True, False, None])
    def test_non_str_non_int_ids_are_rejected(self, bad):
        graph = ISONGraph()
        with pytest.raises(InvalidIdentifierError):
            graph.add_node("p", bad)

    @pytest.mark.parametrize("node_id", [-1, 0, 1, 2**63 - 1, -(2**63), "-1", "007", "x"])
    def test_str_and_signed_int_ids_are_accepted(self, node_id):
        graph = ISONGraph()
        graph.add_node("p", node_id)
        assert graph.has_node("p", node_id)

    @pytest.mark.parametrize("first,second", [(1, "1"), ("1", 1), (-1, "-1"), ("-1", -1)])
    def test_int_string_twins_are_rejected_with_sign(self, first, second):
        graph = ISONGraph()
        graph.add_node("p", first)
        with pytest.raises(DuplicateNodeError):
            graph.add_node("p", second)


class TestNegativeIdRoundTrip:
    """A negative integer id resolves from a reference after reload."""

    @staticmethod
    def _graph():
        g = ISONGraph()
        g.add_node("p", -1, name="neg")
        g.add_node("p", 2)
        g.add_edge("R", ("p", -1), ("p", 2))
        g.add_edge("R", ("p", 2), ("p", -1))
        return g

    def test_ison(self):
        restored = ISONGraph.from_ison(self._graph().to_ison())
        assert restored.has_node("p", -1)
        assert not restored.has_node("p", "-1")
        assert restored.has_edge("R", ("p", -1), ("p", 2))
        assert restored.has_edge("R", ("p", 2), ("p", -1))

    def test_isonl(self):
        restored = ISONGraph.from_isonl(self._graph().to_isonl())
        assert restored.has_edge("R", ("p", -1), ("p", 2))

    def test_bytes_are_stable_across_reload(self):
        text = self._graph().to_ison()
        assert ISONGraph.from_ison(text).to_ison() == text

    def test_negative_string_id_stays_a_string(self):
        """'-1' as a *string* id is quoted in the id column and resolves to
        the string node, not to int -1, because the node table wins."""
        g = ISONGraph()
        g.add_node("p", "-1")
        g.add_node("p", 2)
        g.add_edge("R", ("p", "-1"), ("p", 2))
        restored = ISONGraph.from_ison(g.to_ison())
        assert restored.has_node("p", "-1")
        assert restored.has_edge("R", ("p", "-1"), ("p", 2))

    def test_query_pattern_accepts_negative_id(self):
        g = self._graph()
        assert g.query(":p:-1 -[:R]-> *") == [("p", 2)]


class TestDirectednessRoundTrip:
    """Undirected graphs persist their directedness; directed ones keep
    their 1.4.0 bytes."""

    def test_directed_output_is_unchanged(self):
        g = ISONGraph()
        g.add_node("p", 1)
        g.add_node("p", 2)
        g.add_edge("R", ("p", 1), ("p", 2))
        assert "meta.graph" not in g.to_ison()
        assert "meta.graph" not in g.to_isonl()

    def test_undirected_reloads_undirected(self):
        g = ISONGraph(directed=False)
        g.add_node("p", 1)
        g.add_node("p", 2)
        g.add_edge("R", ("p", 1), ("p", 2), w=1)

        text = g.to_ison()
        assert "meta.graph" in text
        restored = ISONGraph.from_ison(text)
        assert restored.directed is False
        # One logical edge, stored as its two mirrors - same as before dump.
        assert restored.edge_count() == g.edge_count() == 2
        assert restored.has_edge("R", ("p", 1), ("p", 2))
        assert restored.has_edge("R", ("p", 2), ("p", 1))
        assert restored.get_edge("R", ("p", 2), ("p", 1)).properties == {"w": 1}

    def test_undirected_isonl_roundtrip(self):
        g = ISONGraph(directed=False)
        g.add_node("p", 1)
        g.add_node("p", 2)
        g.add_edge("R", ("p", 1), ("p", 2))
        restored = ISONGraph.from_isonl(g.to_isonl())
        assert restored.directed is False
        assert restored.edge_count() == 2

    def test_undirected_bytes_are_stable_across_reload(self):
        g = ISONGraph(directed=False)
        g.add_node("p", 1)
        g.add_node("p", 2)
        g.add_edge("R", ("p", 1), ("p", 2))
        text = g.to_ison()
        assert ISONGraph.from_ison(text).to_ison() == text

    def test_directed_and_undirected_no_longer_collide(self):
        """{A->B, B->A} directed and {A-B} undirected used to serialize to
        the same bytes, so no identity built on them could tell them apart."""
        d = ISONGraph(directed=True)
        u = ISONGraph(directed=False)
        for g in (d, u):
            g.add_node("p", 1)
            g.add_node("p", 2)
        d.add_edge("R", ("p", 1), ("p", 2))
        d.add_edge("R", ("p", 2), ("p", 1))
        u.add_edge("R", ("p", 1), ("p", 2))
        assert d.to_ison() != u.to_ison()

    def test_directed_duplicate_rows_still_raise(self):
        text = "edges.R\nsource target\n:p:1 :p:2\n:p:1 :p:2\n\nnodes.p\nid\n1\n2"
        with pytest.raises(DuplicateEdgeError):
            ISONGraph.from_ison(text)

    def test_explicit_directed_true_is_honoured(self):
        text = "meta.graph\ndirected\ntrue\n\nnodes.p\nid\n1"
        assert ISONGraph.from_ison(text).directed is True


class TestPropertyValueDomain:
    """Non-finite floats have no ISON spelling and are refused."""

    @pytest.mark.parametrize("bad", [float('nan'), float('inf'), float('-inf')])
    def test_add_node_rejects(self, bad):
        graph = ISONGraph()
        with pytest.raises(InvalidPropertyValueError):
            graph.add_node("p", 1, x=bad)

    @pytest.mark.parametrize("bad", [float('nan'), float('inf')])
    def test_add_edge_rejects(self, bad):
        graph = ISONGraph()
        graph.add_node("p", 1)
        graph.add_node("p", 2)
        with pytest.raises(InvalidPropertyValueError):
            graph.add_edge("R", ("p", 1), ("p", 2), w=bad)

    def test_update_node_rejects(self):
        graph = ISONGraph()
        graph.add_node("p", 1)
        with pytest.raises(InvalidPropertyValueError):
            graph.update_node("p", 1, x=float('nan'))
        assert graph.get_node("p", 1).properties == {}

    def test_finite_floats_and_big_ints_still_roundtrip(self):
        graph = ISONGraph()
        graph.add_node("p", 1, a=1.5, b=-0.0, c=2**63 - 1, d=10**20, e=1.0)
        restored = ISONGraph.from_ison(graph.to_ison())
        props = restored.get_node("p", 1).properties
        assert props == {"a": 1.5, "b": -0.0, "c": 2**63 - 1, "d": 10**20, "e": 1.0}
        assert isinstance(props["e"], float)

    def test_error_is_a_graph_error(self):
        from ison_graph import GraphError
        assert issubclass(InvalidPropertyValueError, GraphError)


# =============================================================================
# Canonical Serialization Tests
#
# to_ison()/to_isonl() must be byte-identical for the same logical graph
# regardless of insertion order (node type blocks, node rows, edge type
# blocks, and edge rows are all sorted, ordinal string comparison). This is
# what makes serialized output safe to content-address or prompt-cache: the
# same graph always produces the same bytes.
#
# The golden fixture below is shared verbatim (as a literal string) across
# every ISONGraph language port's test suite - Python, JS, TS, Rust, C++,
# and C# - as the cross-language byte-identity contract. If this string
# changes here, it must change in all six places together.
# =============================================================================

CANONICAL_GOLDEN_ISON = (
    'edges.KNOWS\n'
    'since source target weight\n'
    '"2020" :person:1 :person:2 1.75\n'
    '"2021" :person:10 :person:1 0.5\n'
    '\n'
    'edges.WORKS_AT\n'
    'role source target\n'
    '"Lead Engineer" :person:1 :company:acme\n'
    '\n'
    'edges.WORKS_ON\n'
    'hours source target\n'
    '3 :person:10 :project:p1\n'
    '5 :person:2 :project:p1\n'
    '\n'
    'nodes.company\n'
    'id listed name staff\n'
    'acme false "Acme Corp" 42\n'
    '\n'
    'nodes.person\n'
    'id active age name score\n'
    '"1" true "30" Alice 9.5\n'
    '"10" false "22" Jax -2.25\n'
    '"2" null "25" Bob null\n'
    '\n'
    'nodes.project\n'
    'id budget name tag\n'
    'p1 1250 Alpha a|b'
)

CANONICAL_GOLDEN_ISONL = (
    'edges.KNOWS|since source target weight|"2020" :person:1 :person:2 1.75\n'
    'edges.KNOWS|since source target weight|"2021" :person:10 :person:1 0.5\n'
    'edges.WORKS_AT|role source target|"Lead Engineer" :person:1 :company:acme\n'
    'edges.WORKS_ON|hours source target|3 :person:10 :project:p1\n'
    'edges.WORKS_ON|hours source target|5 :person:2 :project:p1\n'
    'nodes.company|id listed name staff|acme false "Acme Corp" 42\n'
    'nodes.person|id active age name score|"1" true "30" Alice 9.5\n'
    'nodes.person|id active age name score|"10" false "22" Jax -2.25\n'
    'nodes.person|id active age name score|"2" null "25" Bob null\n'
    'nodes.project|id budget name tag|p1 1250 Alpha "a\\|b"'
)


def _build_canonical_fixture(order):
    """Same logical graph built in forward (0) or reversed (1) insertion order."""
    graph = ISONGraph('fixture')
    # Deliberately mixed types. The string ids '1'/'10'/'2' and the string
    # ages '30'/'22'/'25' pin that a value which would reparse as a number
    # stays quoted; the int, float and bool pin that a real number does not.
    #
    # No integral float appears here on purpose. JavaScript has one number
    # type, so 1.0 === 1 and a JS program cannot originate a float 1.0 -
    # putting one in a shared fixture would demand agreement no JS port can
    # give. Non-integral floats carry the same signal and are portable.
    nodes = [
        ('company', 'acme', {'name': 'Acme Corp', 'staff': 42, 'listed': False}),
        ('person', '1', {'name': 'Alice', 'age': '30', 'score': 9.5, 'active': True}),
        ('person', '10', {'name': 'Jax', 'age': '22', 'score': -2.25, 'active': False}),
        ('person', '2', {'name': 'Bob', 'age': '25'}),
        ('project', 'p1', {'name': 'Alpha', 'tag': 'a|b', 'budget': 1250}),
    ]
    edges = [
        ('KNOWS', ('person', '10'), ('person', '1'), {'since': '2021', 'weight': 0.5}),
        ('KNOWS', ('person', '1'), ('person', '2'), {'since': '2020', 'weight': 1.75}),
        ('WORKS_AT', ('person', '1'), ('company', 'acme'), {'role': 'Lead Engineer'}),
        ('WORKS_ON', ('person', '2'), ('project', 'p1'), {'hours': 5}),
        ('WORKS_ON', ('person', '10'), ('project', 'p1'), {'hours': 3}),
    ]
    seq_n = nodes if order == 0 else list(reversed(nodes))
    seq_e = edges if order == 0 else list(reversed(edges))
    for node_type, node_id, props in seq_n:
        graph.add_node(node_type, node_id, **props)
    for rel, source, target, props in seq_e:
        graph.add_edge(rel, source, target, **props)
    return graph


class TestCanonicalSerialization:
    """Serialization is insertion-order-independent and matches the shared
    cross-language golden fixture exactly."""

    def test_to_ison_independent_of_insertion_order(self):
        a = _build_canonical_fixture(0)
        b = _build_canonical_fixture(1)
        assert a.to_ison() == b.to_ison()

    def test_to_isonl_independent_of_insertion_order(self):
        a = _build_canonical_fixture(0)
        b = _build_canonical_fixture(1)
        assert a.to_isonl() == b.to_isonl()

    def test_to_ison_matches_golden_fixture(self):
        assert _build_canonical_fixture(0).to_ison() == CANONICAL_GOLDEN_ISON
        assert _build_canonical_fixture(1).to_ison() == CANONICAL_GOLDEN_ISON

    def test_to_isonl_matches_golden_fixture(self):
        assert _build_canonical_fixture(0).to_isonl() == CANONICAL_GOLDEN_ISONL
        assert _build_canonical_fixture(1).to_isonl() == CANONICAL_GOLDEN_ISONL

    def test_ordinal_not_numeric_sort(self):
        # "1" < "10" < "2" ordinally - the golden fixture already locks this
        # in, but assert it explicitly so the invariant reads as intentional.
        ison = _build_canonical_fixture(0).to_ison()
        person_block = ison.split('nodes.person\n')[1].split('\n\n')[0]
        # Ids are quoted because the fixture uses string ids - the canonical
        # writer quotes a string that would otherwise reparse as an int, so
        # the round trip stays lossless. Strip that to read the order.
        ids = [line.split(' ')[0].strip('"') for line in person_block.splitlines()[1:]]
        assert ids == ['1', '10', '2']

    def test_roundtrip_preserves_canonical_form(self):
        graph = _build_canonical_fixture(0)
        reloaded = ISONGraph.from_ison(graph.to_ison())
        assert reloaded.to_ison() == graph.to_ison()


# =============================================================================
# Fluent API Tests
# =============================================================================

class TestFluentAPI:
    """Test fluent traversal API"""

    def setup_method(self):
        self.graph = ISONGraph()
        self.graph.add_node('person', 1, name='Alice', age=30)
        self.graph.add_node('person', 2, name='Bob', age=25)
        self.graph.add_node('person', 3, name='Charlie', age=35)
        self.graph.add_edge('KNOWS', ('person', 1), ('person', 2))
        self.graph.add_edge('KNOWS', ('person', 2), ('person', 3))

    def test_hop(self):
        result = self.graph.start(('person', 1)).hop('KNOWS').collect()
        assert result == [('person', 2)]

    def test_hops(self):
        result = self.graph.start(('person', 1)).hops(2, 'KNOWS').collect()
        assert result == [('person', 3)]

    def test_filter(self):
        result = self.graph.start(('person', 1)) \
            .hop('KNOWS') \
            .hop('KNOWS') \
            .filter(lambda n: n.properties.get('age', 0) > 30) \
            .collect()

        assert result == [('person', 3)]

    def test_collect_nodes(self):
        nodes = self.graph.start(('person', 1)).hop('KNOWS').collect_nodes()
        assert len(nodes) == 1
        assert nodes[0].properties['name'] == 'Bob'


# =============================================================================
# Query Pattern Tests
# =============================================================================

class TestQueryPatterns:
    """Test query pattern syntax"""

    def setup_method(self):
        self.graph = ISONGraph()
        for i in range(1, 5):
            self.graph.add_node('person', i)
        self.graph.add_edge('KNOWS', ('person', 1), ('person', 2))
        self.graph.add_edge('KNOWS', ('person', 2), ('person', 3))
        self.graph.add_edge('KNOWS', ('person', 3), ('person', 4))

    def test_simple_query(self):
        result = self.graph.query(":person:1 -[:KNOWS]-> *")
        assert result == [('person', 2)]

    def test_multi_hop_query(self):
        result = self.graph.query(":person:1 -[:KNOWS*2]-> *")
        assert result == [('person', 3)]

    def test_range_query(self):
        result = self.graph.query(":person:1 -[:KNOWS*1..2]-> *")
        assert set(result) == {('person', 2), ('person', 3)}


# =============================================================================
# Deep Graph Tests (iterative DFS must not overflow the call stack)
# =============================================================================

class TestDeepGraphs:
    """DFS-based operations must handle graphs deeper than the recursion limit"""

    DEPTH = 2000  # deeper than CPython's default recursion limit (~1000)

    def _build_chain(self):
        graph = ISONGraph()
        for i in range(1, self.DEPTH + 1):
            graph.add_node('node', i)
        for i in range(1, self.DEPTH):
            graph.add_edge('NEXT', ('node', i), ('node', i + 1))
        return graph

    def test_has_cycle_deep_chain(self):
        graph = self._build_chain()
        assert not graph.has_cycle()

        graph.add_edge('NEXT', ('node', self.DEPTH), ('node', 1))
        assert graph.has_cycle()

    def test_all_paths_deep_chain(self):
        graph = self._build_chain()
        paths = graph.all_paths(
            ('node', 1), ('node', self.DEPTH), max_hops=self.DEPTH
        )
        assert len(paths) == 1
        assert paths[0].length == self.DEPTH - 1


# =============================================================================
# Schema Default Tests
# =============================================================================

class TestSchemaDefaults:
    """Field defaults are applied to missing fields during validation"""

    def test_default_applied_to_missing_field(self):
        from ison_graph.schema import GraphSchema, NodeType, String

        graph = ISONGraph()
        graph.add_node('person', 1, name='Alice')

        Person = (NodeType('person')
                  .field('name', String().required())
                  .field('status', String().default('active')))
        result = GraphSchema('s').node_types(Person).validate(graph)

        assert result.valid
        assert graph.get_node('person', 1).properties['status'] == 'active'

    def test_default_satisfies_required(self):
        from ison_graph.schema import GraphSchema, NodeType, String

        graph = ISONGraph()
        graph.add_node('person', 1)

        Person = NodeType('person').field(
            'status', String().required().default('active')
        )
        result = GraphSchema('s').node_types(Person).validate(graph)

        assert result.valid
        assert graph.get_node('person', 1).properties['status'] == 'active'

    def test_missing_required_without_default_still_errors(self):
        from ison_graph.schema import GraphSchema, NodeType, String

        graph = ISONGraph()
        graph.add_node('person', 1)

        Person = NodeType('person').field('name', String().required())
        result = GraphSchema('s').node_types(Person).validate(graph)

        assert not result.valid

    def test_present_value_not_overwritten_by_default(self):
        from ison_graph.schema import GraphSchema, NodeType, String

        graph = ISONGraph()
        graph.add_node('person', 1, status='inactive')

        Person = NodeType('person').field('status', String().default('active'))
        result = GraphSchema('s').node_types(Person).validate(graph)

        assert result.valid
        assert graph.get_node('person', 1).properties['status'] == 'inactive'

    def test_edge_default_applied(self):
        from ison_graph.schema import GraphSchema, NodeType, EdgeType, Int

        graph = ISONGraph()
        graph.add_node('person', 1)
        graph.add_node('person', 2)
        graph.add_edge('KNOWS', ('person', 1), ('person', 2))

        Person = NodeType('person')
        Knows = EdgeType('KNOWS').field('weight', Int().default(1))
        result = (GraphSchema('s')
                  .node_types(Person)
                  .edge_types(Knows)
                  .validate(graph))

        assert result.valid
        edge = graph.get_edge('KNOWS', ('person', 1), ('person', 2))
        assert edge.properties['weight'] == 1


# =============================================================================
# from_dict Duplicate Edge Tests
#
# ISONGraph is a simple graph: at most one edge per (rel_type, source,
# target) triple. A source dict/JSON payload with a repeated edge entry
# is not an error; the repeat is skipped and a single UserWarning
# summarizes how many were dropped instead of crashing the whole import.
# =============================================================================

class TestFromDictDuplicateEdges:
    def test_duplicate_edge_is_skipped_with_warning(self):
        data = {
            "nodes": [
                {"type": "person", "id": "alice"},
                {"type": "person", "id": "bob"},
            ],
            "edges": [
                {"rel_type": "KNOWS", "source": {"type": "person", "id": "alice"},
                 "target": {"type": "person", "id": "bob"}},
                {"rel_type": "KNOWS", "source": {"type": "person", "id": "alice"},
                 "target": {"type": "person", "id": "bob"}},
            ],
        }

        with pytest.warns(UserWarning, match="duplicate edge"):
            graph = ISONGraph.from_dict(data, name="dedup-test")

        assert graph.edge_count() == 1
        assert graph.has_edge("KNOWS", ("person", "alice"), ("person", "bob"))

    def test_no_warning_without_duplicates(self):
        import warnings

        data = {
            "nodes": [
                {"type": "person", "id": "alice"},
                {"type": "person", "id": "bob"},
            ],
            "edges": [
                {"rel_type": "KNOWS", "source": {"type": "person", "id": "alice"},
                 "target": {"type": "person", "id": "bob"}},
            ],
        }

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            graph = ISONGraph.from_dict(data, name="no-dupes")

        assert graph.edge_count() == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


class TestSubmoduleImports:
    """`from ison_graph import <submodule>` has to work.

    The lazy __getattr__ used `from . import <name>`, which probes the package
    with hasattr, re-entering __getattr__ for the same name until the stack ran
    out. Every doc example happened to use `from ison_graph.schema import ...`,
    which goes through the import machinery instead and never touched it, so
    the whole lazy path was broken from 1.0.0 with nothing to notice.
    """

    @pytest.mark.parametrize(
        "name", ["query", "schema", "multigraph", "structural"]
    )
    def test_submodule_is_importable_from_the_package(self, name):
        import importlib

        pkg = importlib.import_module("ison_graph")
        # drop any cached attribute so __getattr__ actually runs
        if hasattr(pkg, name):
            delattr(pkg, name)

        module = getattr(pkg, name)
        assert module.__name__ == f"ison_graph.{name}"

    def test_unknown_attribute_raises_attribute_error(self):
        import ison_graph

        with pytest.raises(AttributeError, match="no attribute"):
            ison_graph.definitely_not_a_submodule
