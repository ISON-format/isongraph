"""
Tests for ison_graph.multigraph
===============================

MultiGraph lifts ISONGraph's simple-graph constraint from
(rel_type, source, target) to (rel_type, source, target, key), so parallel
edges survive instead of raising DuplicateEdgeError. These tests cover key
assignment, the widened lookup/removal API, insertion-order preservation,
canonical serialization, and the format marker that stops ISONGraph from
silently dropping parallel edges.
"""

import json

import pytest
from ison_parser import dumps_canonical, dumps_canonical_isonl, loads

from ison_graph import (
    DuplicateEdgeError,
    EdgeNotFoundError,
    ISONGraph,
    InvalidIdentifierError,
    NodeNotFoundError,
)
from ison_graph.multigraph import (
    MULTIGRAPH_FORMAT,
    InvalidEdgeKeyError,
    MultiGraph,
)


@pytest.fixture
def mg():
    """Two people with two parallel KNOWS edges between them."""
    g = MultiGraph()
    g.add_node("person", 1, name="Alice")
    g.add_node("person", 2, name="Bob")
    g.add_edge("KNOWS", ("person", 1), ("person", 2), since=2015)
    g.add_edge("KNOWS", ("person", 1), ("person", 2), since=2020)
    return g


# =============================================================================
# Keys
# =============================================================================

class TestEdgeKeys:
    def test_first_edge_gets_key_zero(self):
        g = MultiGraph()
        g.add_node("p", 1)
        g.add_node("p", 2)
        assert g.add_edge("K", ("p", 1), ("p", 2)).key == 0

    def test_keys_auto_increment(self, mg):
        keys = [k for k, _ in mg.edges_between(("person", 1), ("person", 2))]
        assert keys == [0, 1]

    def test_explicit_key_is_honored(self):
        g = MultiGraph()
        g.add_node("p", 1)
        g.add_node("p", 2)
        assert g.add_edge("K", ("p", 1), ("p", 2), key=7).key == 7

    def test_auto_key_follows_highest_explicit_key(self):
        g = MultiGraph()
        g.add_node("p", 1)
        g.add_node("p", 2)
        g.add_edge("K", ("p", 1), ("p", 2), key=7)
        assert g.add_edge("K", ("p", 1), ("p", 2)).key == 8

    def test_keys_are_scoped_per_triple(self):
        g = MultiGraph()
        for i in (1, 2, 3):
            g.add_node("p", i)
        g.add_edge("K", ("p", 1), ("p", 2))
        g.add_edge("K", ("p", 1), ("p", 2))
        # A different target restarts at 0
        assert g.add_edge("K", ("p", 1), ("p", 3)).key == 0

    def test_keys_are_scoped_per_rel_type(self, mg):
        assert mg.add_edge("LIKES", ("person", 1), ("person", 2)).key == 0

    def test_duplicate_explicit_key_raises(self, mg):
        with pytest.raises(DuplicateEdgeError):
            mg.add_edge("KNOWS", ("person", 1), ("person", 2), key=0)

    def test_relation_type_is_preserved_verbatim(self, mg):
        """No r_<encoded>_0 rewriting - the caller's rel_type is what is stored."""
        assert mg.edge_types() == ["KNOWS"]
        assert all(e.rel_type == "KNOWS" for e in mg.edges())


# =============================================================================
# Lookup
# =============================================================================

class TestLookup:
    def test_has_edge_without_key_matches_any(self, mg):
        assert mg.has_edge("KNOWS", ("person", 1), ("person", 2)) is True

    def test_has_edge_with_key(self, mg):
        assert mg.has_edge("KNOWS", ("person", 1), ("person", 2), key=1) is True
        assert mg.has_edge("KNOWS", ("person", 1), ("person", 2), key=5) is False

    def test_get_edge_defaults_to_key_zero(self, mg):
        assert mg.get_edge("KNOWS", ("person", 1), ("person", 2)).properties["since"] == 2015

    def test_get_edge_by_key(self, mg):
        assert mg.get_edge(
            "KNOWS", ("person", 1), ("person", 2), key=1
        ).properties["since"] == 2020

    def test_get_edge_unknown_key_raises(self, mg):
        with pytest.raises(EdgeNotFoundError):
            mg.get_edge("KNOWS", ("person", 1), ("person", 2), key=99)

    def test_edges_between_returns_keys_and_edges(self, mg):
        assert [
            (k, e.properties["since"])
            for k, e in mg.edges_between(("person", 1), ("person", 2))
        ] == [(0, 2015), (1, 2020)]

    def test_edges_between_filters_by_rel_type(self, mg):
        mg.add_edge("LIKES", ("person", 1), ("person", 2))
        assert len(mg.edges_between(("person", 1), ("person", 2), "KNOWS")) == 2
        assert len(mg.edges_between(("person", 1), ("person", 2))) == 3

    def test_edge_count_counts_parallel_edges(self, mg):
        assert mg.edge_count() == 2

    def test_add_edge_validates_nodes_exist(self):
        g = MultiGraph()
        g.add_node("p", 1)
        with pytest.raises(NodeNotFoundError):
            g.add_edge("K", ("p", 1), ("p", 99))

    def test_add_edge_validates_rel_type(self, mg):
        with pytest.raises(InvalidIdentifierError):
            mg.add_edge("BAD:TYPE", ("person", 1), ("person", 2))


# =============================================================================
# Traversal - queried by the real relation type, key stays out of the way
# =============================================================================

class TestTraversal:
    def test_neighbors_returns_one_entry_per_parallel_edge(self, mg):
        assert mg.neighbors(("person", 1), "KNOWS") == [("person", 2)] * 2

    def test_out_degree_counts_parallel_edges(self, mg):
        assert mg.out_degree(("person", 1)) == 2

    def test_shortest_path_traverses_parallel_edges(self, mg):
        path = mg.shortest_path(("person", 1), ("person", 2))
        assert path is not None
        assert path.length == 1


# =============================================================================
# Removal
# =============================================================================

class TestRemoval:
    def test_remove_edge_by_key_leaves_siblings(self, mg):
        mg.remove_edge("KNOWS", ("person", 1), ("person", 2), key=0)
        assert [k for k, _ in mg.edges_between(("person", 1), ("person", 2))] == [1]
        assert mg.edge_count() == 1

    def test_remove_edge_without_key_removes_all_parallel_edges(self, mg):
        mg.remove_edge("KNOWS", ("person", 1), ("person", 2))
        assert mg.edge_count() == 0

    def test_remove_edge_unknown_key_raises(self, mg):
        with pytest.raises(EdgeNotFoundError):
            mg.remove_edge("KNOWS", ("person", 1), ("person", 2), key=99)

    def test_keys_restart_after_full_removal(self, mg):
        mg.remove_edge("KNOWS", ("person", 1), ("person", 2))
        assert mg.add_edge("KNOWS", ("person", 1), ("person", 2)).key == 0

    def test_remove_node_clears_all_parallel_edges(self, mg):
        """Regression: the base _remove_edge_internal keys off edge.key,
        which on a MultiEdge is an int, not the identity tuple."""
        mg.remove_node("person", 2)
        assert mg.edge_count() == 0
        assert list(mg.edges()) == []


# =============================================================================
# Undirected
# =============================================================================

class TestKeyValidation:
    """A rejected edge must not leave a trace in any index."""

    @pytest.mark.parametrize("bad", [-1, 1.5, True, False, "7", None.__class__, 2 + 3j])
    def test_invalid_keys_are_rejected(self, bad):
        g = MultiGraph()
        g.add_node("p", 1)
        g.add_node("p", 2)
        with pytest.raises(InvalidEdgeKeyError):
            g.add_edge("K", ("p", 1), ("p", 2), key=bad)

    @pytest.mark.parametrize("bad", [-1, 1.5, True, "7"])
    def test_rejected_key_leaves_no_partial_state(self, bad):
        g = MultiGraph()
        g.add_node("p", 1)
        g.add_node("p", 2)
        with pytest.raises(InvalidEdgeKeyError):
            g.add_edge("K", ("p", 1), ("p", 2), key=bad)

        assert g.edge_count() == 0
        assert list(g.edges()) == []
        assert g.edges_between(("p", 1), ("p", 2)) == []
        assert g._edge_set == set()
        assert g._triple_edges == {}
        assert g._next_keys == {}

    def test_rejected_key_does_not_disturb_existing_edges(self):
        g = MultiGraph()
        g.add_node("p", 1)
        g.add_node("p", 2)
        g.add_edge("K", ("p", 1), ("p", 2), w="keep")

        with pytest.raises(InvalidEdgeKeyError):
            g.add_edge("K", ("p", 1), ("p", 2), key=-5)

        assert g.edge_count() == 1
        assert g.add_edge("K", ("p", 1), ("p", 2)).key == 1

    def test_zero_is_valid(self):
        g = MultiGraph()
        g.add_node("p", 1)
        g.add_node("p", 2)
        assert g.add_edge("K", ("p", 1), ("p", 2), key=0).key == 0


class TestDirectednessRoundTrip:
    """Directedness is part of the document, not a loader default."""

    @pytest.mark.parametrize("directed", [True, False])
    @pytest.mark.parametrize("dump,load", [
        ("to_ison", "from_ison"),
        ("to_isonl", "from_isonl"),
        ("to_dict", "from_dict"),
    ])
    def test_directedness_survives(self, directed, dump, load):
        g = MultiGraph(directed=directed)
        for i in (1, 2, 3):
            g.add_node("p", i)
        g.add_edge("K", ("p", 1), ("p", 2), since=2015)
        g.add_edge("K", ("p", 1), ("p", 2), since=2020)
        g.add_edge("K", ("p", 2), ("p", 3))

        restored = getattr(MultiGraph, load)(getattr(g, dump)())

        assert restored.directed is directed
        assert restored.edge_count() == g.edge_count()
        assert getattr(restored, dump)() == getattr(g, dump)()

    def test_undirected_mirrors_survive(self):
        g = MultiGraph(directed=False)
        g.add_node("p", 1)
        g.add_node("p", 2)
        g.add_edge("K", ("p", 1), ("p", 2))
        g.add_edge("K", ("p", 1), ("p", 2))

        restored = MultiGraph.from_ison(g.to_ison())

        assert [k for k, _ in restored.edges_between(("p", 2), ("p", 1))] == [0, 1]
        assert restored.neighbors(("p", 2)) == g.neighbors(("p", 2))

    def test_reloaded_undirected_graph_still_mirrors_new_edges(self):
        """The restored graph must behave undirected, not merely look it."""
        g = MultiGraph(directed=False)
        g.add_node("p", 1)
        g.add_node("p", 2)
        g.add_node("p", 3)
        g.add_edge("K", ("p", 1), ("p", 2))

        restored = MultiGraph.from_ison(g.to_ison())
        restored.add_edge("K", ("p", 2), ("p", 3))

        assert restored.has_edge("K", ("p", 3), ("p", 2)) is True


class TestUndirected:
    def test_reverse_edges_mirror_keys(self):
        g = MultiGraph(directed=False)
        g.add_node("p", 1)
        g.add_node("p", 2)
        g.add_edge("K", ("p", 1), ("p", 2), w=1)
        g.add_edge("K", ("p", 1), ("p", 2), w=2)

        assert [k for k, _ in g.edges_between(("p", 2), ("p", 1))] == [0, 1]

    def test_removing_an_edge_removes_its_mirror(self):
        g = MultiGraph(directed=False)
        g.add_node("p", 1)
        g.add_node("p", 2)
        g.add_edge("K", ("p", 1), ("p", 2), w=1)
        g.add_edge("K", ("p", 1), ("p", 2), w=2)

        g.remove_edge("K", ("p", 1), ("p", 2), key=0)
        assert g.edge_count() == 2
        assert g.has_edge("K", ("p", 2), ("p", 1), key=0) is False


# =============================================================================
# Serialization
# =============================================================================

class TestSerialization:
    def test_ison_roundtrip_is_byte_identical(self, mg):
        assert MultiGraph.from_ison(mg.to_ison()).to_ison() == mg.to_ison()

    def test_isonl_roundtrip_is_byte_identical(self, mg):
        assert MultiGraph.from_isonl(mg.to_isonl()).to_isonl() == mg.to_isonl()

    def test_dict_roundtrip_preserves_parallel_edges(self, mg):
        restored = MultiGraph.from_dict(mg.to_dict())
        assert restored.edge_count() == 2
        assert restored.to_ison() == mg.to_ison()

    def test_roundtrip_preserves_keys_and_properties(self, mg):
        restored = MultiGraph.from_ison(mg.to_ison())
        assert [
            (k, e.properties["since"])
            for k, e in restored.edges_between(("person", 1), ("person", 2))
        ] == [(0, 2015), (1, 2020)]

    def test_explicit_keys_survive_roundtrip(self):
        g = MultiGraph()
        g.add_node("p", 1)
        g.add_node("p", 2)
        g.add_edge("K", ("p", 1), ("p", 2), key=41)
        assert [k for k, _ in MultiGraph.from_ison(g.to_ison()).edges_between(
            ("p", 1), ("p", 2))] == [41]

    def test_ison_emits_key_column(self, mg):
        """Column order is the canonical writer's business (alphabetical);
        what matters here is that the key is a column, not a property."""
        block = next(b for b in loads(mg.to_ison()).blocks if b.kind == "edges")
        assert "key" in block.fields
        assert [row["key"] for row in block.rows] == [0, 1]

    def test_to_dict_is_json_serializable(self, mg):
        assert json.loads(json.dumps(mg.to_dict()))["format"] == MULTIGRAPH_FORMAT

    def test_save_load_roundtrip(self, mg, tmp_path):
        path = tmp_path / "g.isong"
        mg.save(path)
        assert MultiGraph.from_ison(path.read_text(encoding="utf-8")).edge_count() == 2

    def test_emission_is_delegated_to_isoncs(self, mg):
        """MultiGraph owns ordering; ison_parser owns the bytes. Building
        the same Document by hand must reproduce the output exactly."""
        assert mg.to_ison() == dumps_canonical(mg._document())
        assert mg.to_isonl() == dumps_canonical_isonl(mg._document())

    def test_values_are_quoted_by_the_canonical_writer(self):
        g = MultiGraph()
        g.add_node("p", 1, note='has space and "quote"')
        g.add_node("p", 2)
        g.add_edge("K", ("p", 1), ("p", 2), label="two words")

        restored = MultiGraph.from_ison(g.to_ison())
        assert restored.get_node("p", 1).properties["note"] == 'has space and "quote"'
        assert restored.get_edge("K", ("p", 1), ("p", 2)).properties["label"] == "two words"

    def test_serialization_is_canonical(self):
        """Same logical graph, different construction order, same bytes."""
        a = MultiGraph()
        a.add_node("z", 1)
        a.add_node("a", 1)
        a.add_edge("ZZZ", ("z", 1), ("a", 1), key=1)
        a.add_edge("ZZZ", ("z", 1), ("a", 1), key=0)
        a.add_edge("AAA", ("a", 1), ("z", 1))

        b = MultiGraph()
        b.add_node("a", 1)
        b.add_node("z", 1)
        b.add_edge("AAA", ("a", 1), ("z", 1))
        b.add_edge("ZZZ", ("z", 1), ("a", 1), key=0)
        b.add_edge("ZZZ", ("z", 1), ("a", 1), key=1)

        assert a.to_ison() == b.to_ison()
        assert a.to_isonl() == b.to_isonl()


class TestInsertionOrder:
    """ISON-Cache depends on relation order staying as inserted."""

    def test_edges_iterate_in_insertion_order(self):
        g = MultiGraph()
        for i in (1, 2):
            g.add_node("p", i)
        for w in ("c", "a", "b"):
            g.add_edge("K", ("p", 1), ("p", 2), w=w)

        assert [e.properties["w"] for e in g.edges()] == ["c", "a", "b"]

    def test_edges_between_preserves_insertion_order(self):
        g = MultiGraph()
        for i in (1, 2):
            g.add_node("p", i)
        g.add_edge("K", ("p", 1), ("p", 2), key=5, w="first")
        g.add_edge("K", ("p", 1), ("p", 2), key=2, w="second")

        assert [e.properties["w"] for _, e in g.edges_between(("p", 1), ("p", 2))] == [
            "first", "second"
        ]

    def test_rel_type_order_follows_first_insertion(self):
        g = MultiGraph()
        for i in (1, 2):
            g.add_node("p", i)
        g.add_edge("ZZZ", ("p", 1), ("p", 2))
        g.add_edge("AAA", ("p", 1), ("p", 2))

        assert g.edge_types() == ["ZZZ", "AAA"]


# =============================================================================
# Format marker - ISONGraph must refuse rather than drop parallel edges
# =============================================================================

class TestFormatMarker:
    def test_ison_carries_the_marker(self, mg):
        assert MULTIGRAPH_FORMAT in mg.to_ison()

    def test_isonl_carries_the_marker(self, mg):
        assert MULTIGRAPH_FORMAT in mg.to_isonl()

    def test_dict_carries_the_marker(self, mg):
        assert mg.to_dict()["format"] == MULTIGRAPH_FORMAT

    @pytest.mark.parametrize("loader,payload", [
        (ISONGraph.from_ison, "to_ison"),
        (ISONGraph.from_isonl, "to_isonl"),
        (ISONGraph.from_dict, "to_dict"),
    ])
    def test_isongraph_refuses_multigraph_input(self, mg, loader, payload):
        with pytest.raises(ValueError, match=MULTIGRAPH_FORMAT):
            loader(getattr(mg, payload)())

    def test_multigraph_accepts_unmarked_simple_graph_dict(self):
        """A simple graph is a valid multigraph where every key is 0."""
        plain = ISONGraph()
        plain.add_node("p", 1)
        plain.add_node("p", 2)
        plain.add_edge("K", ("p", 1), ("p", 2), w=1)

        restored = MultiGraph.from_dict(plain.to_dict())
        assert restored.edge_count() == 1
        assert restored.get_edge("K", ("p", 1), ("p", 2)).key == 0

    def test_multigraph_rejects_unknown_format(self):
        with pytest.raises(ValueError, match="ison-graph-somethingelse"):
            MultiGraph.from_dict({"format": "ison-graph-somethingelse", "nodes": [], "edges": []})


class TestSimpleGraphUnaffected:
    """The marker guard must not change ISONGraph's behavior on real input."""

    @pytest.mark.parametrize("dump,load", [
        ("to_ison", "from_ison"),
        ("to_isonl", "from_isonl"),
        ("to_dict", "from_dict"),
    ])
    def test_simple_graph_still_roundtrips(self, dump, load):
        g = ISONGraph()
        g.add_node("p", 1, name="Alice")
        g.add_node("p", 2, name="Bob")
        g.add_edge("K", ("p", 1), ("p", 2), w=1)

        restored = getattr(ISONGraph, load)(getattr(g, dump)())
        assert restored.node_count() == 2
        assert restored.edge_count() == 1

    def test_isongraph_still_rejects_parallel_edges(self):
        g = ISONGraph()
        g.add_node("p", 1)
        g.add_node("p", 2)
        g.add_edge("K", ("p", 1), ("p", 2))
        with pytest.raises(DuplicateEdgeError):
            g.add_edge("K", ("p", 1), ("p", 2))


class TestMultiEdge:
    def test_edge_key_is_the_four_tuple(self, mg):
        edge = mg.get_edge("KNOWS", ("person", 1), ("person", 2), key=1)
        assert edge.edge_key == ("KNOWS", ("person", 1), ("person", 2), 1)

    def test_parallel_edges_are_not_equal(self, mg):
        a = mg.get_edge("KNOWS", ("person", 1), ("person", 2), key=0)
        b = mg.get_edge("KNOWS", ("person", 1), ("person", 2), key=1)
        assert a != b
        assert len({a, b}) == 2

    def test_repr_shows_key(self, mg):
        assert "KNOWS#1" in repr(
            mg.get_edge("KNOWS", ("person", 1), ("person", 2), key=1)
        )

    def test_key_deliberately_diverges_from_the_base_contract(self, mg):
        """On Edge, .key is the identity tuple; on MultiEdge it is the int.
        Documented as an incompatible subtype - pinned so the divergence
        cannot widen unnoticed."""
        plain = ISONGraph()
        plain.add_node("p", 1)
        plain.add_node("p", 2)
        plain_edge = plain.add_edge("K", ("p", 1), ("p", 2))
        assert plain_edge.key == ("K", ("p", 1), ("p", 2))

        multi = mg.get_edge("KNOWS", ("person", 1), ("person", 2), key=1)
        assert multi.key == 1
        assert multi.edge_key == ("KNOWS", ("person", 1), ("person", 2), 1)

    def test_edge_id_is_a_stable_alias_for_the_integer_key(self, mg):
        edge = mg.get_edge("KNOWS", ("person", 1), ("person", 2), key=1)
        assert edge.edge_id == edge.key == 1
