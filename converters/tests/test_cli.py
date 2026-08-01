"""
Tests for the ison-convert CLI
===============================

Covers format auto-detection from file extension, and the load/save
round trip through the actual CLI entry point functions that
`ison-convert input output` calls.
"""

import json
import sys

import pytest

from ison_graph import ISONGraph
from converters.cli import get_format_from_extension, load_graph, save_graph, main


@pytest.fixture
def sample_graph():
    graph = ISONGraph(name="test-graph")
    graph.add_node("person", "alice", name="Alice Smith")
    graph.add_node("person", "bob", name="Bob Jones")
    graph.add_edge("KNOWS", ("person", "alice"), ("person", "bob"), since=2020)
    return graph


class TestFormatDetection:
    @pytest.mark.parametrize("path,expected", [
        ("graph.ison", "ison"),
        ("graph.isonl", "isonl"),
        ("graph.json", "json"),
        ("graph.graphml", "graphml"),
        ("graph.xml", "graphml"),
        ("graph.ttl", "turtle"),
        ("graph.nt", "ntriples"),
        ("graph.rdf", "rdf"),
        ("graph.csv", "csv"),
        ("graph.cypher", "cypher"),
        ("graph.cql", "cypher"),
        ("graph.dot", "dot"),
        ("graph.gv", "dot"),
    ])
    def test_known_extensions(self, path, expected):
        assert get_format_from_extension(path) == expected

    def test_unknown_extension_defaults_to_ison(self):
        assert get_format_from_extension("graph.unknown") == "ison"


class TestLoadSaveRoundtrip:
    def test_json_to_ison(self, sample_graph, tmp_path):
        json_path = tmp_path / "graph.json"
        ison_path = tmp_path / "graph.ison"

        json_path.write_text(json.dumps(sample_graph.to_dict()), encoding="utf-8")

        graph = load_graph(str(json_path))
        save_graph(graph, str(ison_path))

        assert ison_path.exists()
        restored = load_graph(str(ison_path))
        assert restored.node_count() == sample_graph.node_count()
        assert restored.edge_count() == sample_graph.edge_count()

    def test_ison_to_graphml(self, sample_graph, tmp_path):
        ison_path = tmp_path / "graph.ison"
        graphml_path = tmp_path / "graph.graphml"

        ison_path.write_text(sample_graph.to_ison(), encoding="utf-8")

        graph = load_graph(str(ison_path))
        save_graph(graph, str(graphml_path))

        assert graphml_path.exists()
        restored = load_graph(str(graphml_path))
        assert restored.node_count() == sample_graph.node_count()
        assert restored.edge_count() == sample_graph.edge_count()

    def test_ison_to_dot(self, sample_graph, tmp_path):
        ison_path = tmp_path / "graph.ison"
        dot_path = tmp_path / "graph.dot"

        ison_path.write_text(sample_graph.to_ison(), encoding="utf-8")

        graph = load_graph(str(ison_path))
        save_graph(graph, str(dot_path))

        assert dot_path.exists()
        assert "digraph" in dot_path.read_text(encoding="utf-8")

    def test_ison_to_csv_writes_two_files(self, sample_graph, tmp_path):
        ison_path = tmp_path / "graph.ison"
        nodes_path = tmp_path / "graph.csv"
        edges_path = tmp_path / "graph_edges.csv"

        ison_path.write_text(sample_graph.to_ison(), encoding="utf-8")

        graph = load_graph(str(ison_path))
        save_graph(graph, str(nodes_path))

        assert nodes_path.exists()
        assert edges_path.exists()

    def test_load_unsupported_format_raises(self, tmp_path):
        path = tmp_path / "graph.unsupported"
        path.write_text("data", encoding="utf-8")

        with pytest.raises(ValueError):
            load_graph(str(path), format="bogus")

    def test_save_unsupported_format_raises(self, sample_graph, tmp_path):
        path = tmp_path / "graph.out"

        with pytest.raises(ValueError):
            save_graph(sample_graph, str(path), format="bogus")


class TestMainEntrypoint:
    def test_main_converts_json_to_ison(self, sample_graph, tmp_path, monkeypatch, capsys):
        json_path = tmp_path / "graph.json"
        ison_path = tmp_path / "graph.ison"
        json_path.write_text(json.dumps(sample_graph.to_dict()), encoding="utf-8")

        monkeypatch.setattr(sys, "argv", ["ison-convert", str(json_path), str(ison_path)])
        main()

        assert ison_path.exists()
        out = capsys.readouterr().out
        assert "Nodes: 2" in out
        assert "Edges: 1" in out

    def test_main_missing_input_file_exits_nonzero(self, tmp_path, monkeypatch, capsys):
        missing = tmp_path / "does_not_exist.ison"
        out_path = tmp_path / "out.json"

        monkeypatch.setattr(sys, "argv", ["ison-convert", str(missing), str(out_path)])

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code != 0
