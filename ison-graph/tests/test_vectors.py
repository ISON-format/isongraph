"""Core Conformance Corpus runner - Python is the reference port.

Reads vectors/manifest.ison with ison-py, loads every vector document and
checks this port's expectation column. The grammar of that column and the
meaning of every other column are in vectors/README.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ison_parser import loads

from ison_graph import ISONGraph

ROOT = Path(__file__).resolve().parents[2]
VECTORS = ROOT / "vectors"
PORT = "python"

#: Runner file per port, relative to the repo root. A port column may say
#: 'todo' only while its runner does not exist - admission is atomic.
RUNNERS = {
    "python": "ison-graph/tests/test_vectors.py",
    "ts": "ison-graph-ts/src/vectors.test.ts",
    "js": "ison-graph-js/src/vectors.test.js",
    "rust": "ison-graph-rs/tests/vectors.rs",
    "cs": "ison-graph-cs/tests/IsonGraph.Tests/VectorsTests.cs",
    "cpp": "ison-graph-cpp/tests/test_vectors.cpp",
}
PORTS = tuple(RUNNERS)
EXPECTATIONS = ("pass", "pass:canonicalized", "pass:lossy", "defect", "todo")


def _read(rel: str) -> str:
    # newline='' keeps '\n' exactly; read_text would translate on Windows.
    with open(VECTORS / rel, encoding="utf-8", newline="") as f:
        return f.read()


def _manifest() -> list[dict]:
    doc = loads(_read("manifest.ison"))
    rows = [r for b in doc.blocks if b.kind == "table" and b.name == "vectors" for r in b.rows]
    assert rows, "manifest.ison has no table.vectors rows"
    return rows


ROWS = _manifest()


def _load(rel: str, text: str) -> ISONGraph:
    return ISONGraph.from_isonl(text) if rel.endswith(".isonl") else ISONGraph.from_ison(text)


def _emit(graph: ISONGraph) -> str:
    return graph.to_ison() + "\n"


def _findings_ids() -> set[str]:
    text = _read("README.md")
    return set(re.findall(r"^\| (\S+) \|", text, flags=re.M)) - {"vector", "---"}


# =============================================================================
# Meta-test: the manifest and files are what the runners assume they are.
# =============================================================================

def test_manifest_integrity():
    ids = [r["id"] for r in ROWS]
    assert len(ids) == len(set(ids)), "duplicate vector ids"

    findings = _findings_ids()
    for row in ROWS:
        assert row["semantic"] in ("identifiable", "out_of_domain"), row["id"]
        assert (row["semantic"] == "identifiable") == (row["reason"] is None), row["id"]
        assert row["digest"] is None, row["id"]
        assert isinstance(row["directed"], bool), row["id"]
        assert isinstance(row["nodes"], int) and isinstance(row["edges"], int), row["id"]

        for key in ("file", "canonical"):
            rel = row[key]
            if rel is None:
                continue
            path = VECTORS / rel
            assert path.is_file(), f"{row['id']}: {key} {rel} missing"
            data = path.read_bytes()
            assert b"\r" not in data, f"{rel}: CRLF"
            assert not data.startswith(b"\xef\xbb\xbf"), f"{rel}: BOM"
            assert data.endswith(b"\n") and not data.endswith(b"\n\n"), f"{rel}: must end in exactly one LF"
            data.decode("utf-8")  # raises on invalid UTF-8

        cells = {p: row[p] for p in PORTS}
        for port, cell in cells.items():
            assert isinstance(cell, str) and cell, f"{row['id']}: {port} empty"
            assert cell in EXPECTATIONS or cell.startswith("reject:"), f"{row['id']}: {port}={cell!r}"
            runner_exists = (ROOT / RUNNERS[port]).is_file()
            assert (cell == "todo") == (not runner_exists), (
                f"{row['id']}: {port} is {cell!r} but runner "
                f"{'exists' if runner_exists else 'is missing'}"
            )
            if cell == "defect":
                assert row["id"] in findings, f"{row['id']}: {port}=defect needs a README Findings row"

        wants_canonical = any(c == "pass:canonicalized" for c in cells.values())
        assert (row["canonical"] is not None) == wants_canonical, (
            f"{row['id']}: canonical must be set iff some port is pass:canonicalized"
        )


# =============================================================================
# Runner
# =============================================================================

@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_vector(row):
    expectation = row[PORT]
    text = _read(row["file"])

    if expectation.startswith("reject:"):
        with pytest.raises(Exception) as info:
            _load(row["file"], text)
        assert type(info.value).__name__ == expectation[len("reject:"):]
        return

    graph = _load(row["file"], text)
    assert graph.directed == row["directed"]
    assert graph.node_count() == row["nodes"]
    assert graph.edge_count() == row["edges"]

    out = _emit(graph)
    if expectation == "defect":
        # Contradicts the spec (see README Findings) - but pin what the port
        # does so a wrong reading cannot drift into a different wrong one.
        assert _emit(ISONGraph.from_ison(out)) == out
    elif expectation == "pass":
        assert out == text
    elif expectation == "pass:canonicalized":
        assert out == _read(row["canonical"])
        assert _emit(ISONGraph.from_ison(out)) == out
    elif expectation == "pass:lossy":
        assert _emit(ISONGraph.from_ison(out)) == out
    else:
        pytest.fail(f"unknown expectation {expectation!r} for {PORT}")
