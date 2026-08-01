"""
Tests for the ison-schema-gen CLI
====================================

Covers the actual entry point (`schema_generator.cli:main`, exposed as
both the `ison-schema-gen` console script and `python -m schema_generator`)
end to end: reading JSON input, generating a schema, and writing it out
in each supported format.
"""

import json
import subprocess
import sys

import pytest

from schema_generator.cli import main


@pytest.fixture
def sample_json_path(tmp_path):
    data = {
        "nodes": [
            {"type": "person", "id": "1", "name": "Alice", "age": 30},
            {"type": "person", "id": "2", "name": "Bob", "age": 25},
        ],
        "edges": [
            {"rel_type": "KNOWS",
             "source": {"type": "person", "id": "1"},
             "target": {"type": "person", "id": "2"}},
        ],
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestCliMain:
    def test_default_python_output_to_stdout(self, sample_json_path, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["ison-schema-gen", str(sample_json_path)])
        main()

        out = capsys.readouterr().out
        assert "NodeType(\"person\")" in out
        assert "EdgeType(\"KNOWS\")" in out

    @pytest.mark.parametrize("fmt,expected", [
        ("python", "NodeType(\"person\")"),
        ("typescript", "new NodeType(\"person\")"),
        ("json", "\"person\""),
        ("ison", "schema.node person"),
    ])
    def test_each_output_format(self, sample_json_path, monkeypatch, capsys, fmt, expected):
        monkeypatch.setattr(sys, "argv", ["ison-schema-gen", str(sample_json_path), "--format", fmt])
        main()

        assert expected in capsys.readouterr().out

    def test_writes_to_output_file(self, sample_json_path, tmp_path, monkeypatch, capsys):
        out_path = tmp_path / "schema.py"
        monkeypatch.setattr(
            sys, "argv",
            ["ison-schema-gen", str(sample_json_path), "-o", str(out_path)]
        )
        main()

        assert out_path.exists()
        assert "NodeType(\"person\")" in out_path.read_text(encoding="utf-8")

    def test_custom_schema_name(self, sample_json_path, monkeypatch, capsys):
        monkeypatch.setattr(
            sys, "argv",
            ["ison-schema-gen", str(sample_json_path), "-n", "my_custom_schema"]
        )
        main()

        assert "my_custom_schema" in capsys.readouterr().out

    def test_analyze_mode_prints_summary(self, sample_json_path, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["ison-schema-gen", str(sample_json_path), "--analyze"])
        main()

        out = capsys.readouterr().out
        assert "Data Analysis Summary" in out
        assert "Node Types: 1" in out
        assert "Edge Types: 1" in out

    def test_missing_input_file_exits_nonzero(self, tmp_path, monkeypatch):
        missing = tmp_path / "does_not_exist.json"
        monkeypatch.setattr(sys, "argv", ["ison-schema-gen", str(missing)])

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code != 0

    def test_strict_mode_forces_required(self, tmp_path, monkeypatch, capsys):
        data = {"nodes": [
            {"type": "person", "id": "1", "name": "Alice"},
            {"type": "person", "id": "2"},
        ], "edges": []}
        path = tmp_path / "graph.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        monkeypatch.setattr(sys, "argv", ["ison-schema-gen", str(path), "--strict"])
        main()

        out = capsys.readouterr().out
        assert '.field("name", StringField().required()' in out


class TestModuleEntrypoint:
    def test_python_dash_m_schema_generator(self, sample_json_path):
        """python -m schema_generator works, matching the CLI's own docstring."""
        result = subprocess.run(
            [sys.executable, "-m", "schema_generator", str(sample_json_path)],
            capture_output=True, text=True,
        )

        assert result.returncode == 0
        assert "NodeType(\"person\")" in result.stdout
