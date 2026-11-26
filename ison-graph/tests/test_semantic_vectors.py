"""Semantic golden corpus runner - Python is the reference port.

Reads vectors/semantic/manifest.ison with ison-py and checks this port's
column of three tables (vectors, relations, api). The grammar of every
column, the normal-form listing format and the findings are in
vectors/semantic/README.md.

The *normalizer* below is a test oracle for ISONGraph-Semantic/2-draft
sections 1-2 (value and logical-graph normalization). It is not the Semantic/2
implementation and it computes no digest - the digest encoding (section 3) is
not frozen. It exists so that every expected normal form and every
SemanticStatus in the corpus is executed against what each port's ISON parser
actually delivers, instead of being prose.
"""

from __future__ import annotations

import hashlib
import math
import re
import struct
from pathlib import Path

import pytest
from ison_parser import Reference, loads

from ison_graph import ISONGraph
from ison_graph.multigraph import MultiGraph

ROOT = Path(__file__).resolve().parents[2]
SEMANTIC = ROOT / "vectors" / "semantic"
PORT = "python"

#: Semantic runner file per port. A port column may say 'todo' only while
#: its runner does not exist - admission is atomic, as in the Core corpus.
RUNNERS = {
    "python": "ison-graph/tests/test_semantic_vectors.py",
    "ts": "ison-graph-ts/src/semantic-vectors.test.ts",
    "js": "ison-graph-js/src/semantic-vectors.test.js",
    "rust": "ison-graph-rs/tests/semantic_vectors.rs",
    "cs": "ison-graph-cs/tests/IsonGraph.Tests/SemanticVectorsTests.cs",
    "cpp": "ison-graph-cpp/tests/test_semantic_vectors.cpp",
}
PORTS = tuple(RUNNERS)
VECTOR_CELLS = ("pass", "pass:canonicalized", "pass:lossy", "defect", "defect:unstable", "todo")
API_CELLS = ("accept", "accept:retyped", "accept:unencodable", "todo")
MULTIGRAPH_FORMAT = "ison-graph-multigraph-v1"
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1
_INT_TEXT = re.compile(r"-?[0-9]+")


def _read(rel: str) -> str:
    # newline='' keeps '\n' exactly; read_text would translate on Windows.
    with open(SEMANTIC / rel, encoding="utf-8", newline="") as f:
        return f.read()


def _tables() -> dict[str, list[dict]]:
    doc = loads(_read("manifest.ison"))
    out = {}
    for b in doc.blocks:
        if b.kind == "table":
            out[b.name] = b.rows
    return out


TABLES = _tables()
ROWS = TABLES["vectors"]
RELATIONS = TABLES["relations"]
API = TABLES["api"]
BY_ID = {r["id"]: r for r in ROWS}


def _findings_ids() -> set[str]:
    text = _read("README.md")
    return set(re.findall(r"^\| (\S+) \|", text, flags=re.M)) - {"vector", "---"}


# =============================================================================
# Test oracle: Semantic/2 sections 1-2 over a parsed ISON document
# =============================================================================

class OutOfDomain(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _bytes(s: str) -> bytes:
    return s.encode("utf-8", "surrogatepass")


def quote(s: str) -> str:
    """STRING rendering: printable ASCII as is, everything else as \\u{HEX}."""
    out = ['"']
    for ch in s:
        cp = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif 0x20 <= cp <= 0x7E:
            out.append(ch)
        else:
            out.append("\\u{%X}" % cp)
    out.append('"')
    return "".join(out)


def value_form(v) -> tuple[str, object]:
    """Section 1.1/1.2: one scalar to ('INT64'|'FLOAT64'|'STRING'|'BOOL', payload)."""
    if isinstance(v, bool):
        return ("BOOL", v)
    if isinstance(v, int):
        if not INT64_MIN <= v <= INT64_MAX:
            raise OutOfDomain("INTEGER_OUT_OF_INT64")
        return ("INT64", v)
    if isinstance(v, float):
        if not math.isfinite(v):
            raise OutOfDomain("NONFINITE_FLOAT")
        if v == 0:
            return ("INT64", 0)
        if v.is_integer():
            if not INT64_MIN <= int(v) <= INT64_MAX:
                raise OutOfDomain("INTEGRAL_FLOAT_OUT_OF_INT64")
            return ("INT64", int(v))
        return ("FLOAT64", struct.pack(">d", v).hex().upper())
    if isinstance(v, str):
        if any(0xD800 <= ord(ch) <= 0xDFFF for ch in v):
            raise OutOfDomain("INVALID_UNICODE_SCALAR")
        return ("STRING", v)
    if isinstance(v, (list, tuple, dict)):
        raise OutOfDomain("CONTAINER_PROPERTY")
    raise AssertionError(f"oracle has no rule for {type(v).__name__}")


def render(form: tuple[str, object]) -> str:
    kind, payload = form
    if kind == "INT64":
        return f"INT64({payload})"
    if kind == "FLOAT64":
        return f"FLOAT64(0x{payload})"
    if kind == "BOOL":
        return f"BOOL({'true' if payload else 'false'})"
    return f"STRING({quote(payload)})"


def _id_form(v) -> tuple[str, object]:
    if v is None or isinstance(v, (bool, float)):
        raise OutOfDomain("INVALID_NODE_ID_TYPE")
    if isinstance(v, int):
        if not INT64_MIN <= v <= INT64_MAX:
            raise AssertionError("Semantic/2 names no reason for an integer id beyond int64")
        return ("INT64", v)
    return value_form(v)


def _ref_key(ref: tuple[str, tuple[str, object]]):
    """Section 2.3 NodeRef order: type bytes, then INT64 < STRING, ints numerically, strings by UTF-8 bytes."""
    node_type, (kind, payload) = ref
    return (_bytes(node_type), 0 if kind == "INT64" else 1, payload if kind == "INT64" else _bytes(payload))


def _ref_text(ref) -> str:
    return f"{ref[0]}:{render(ref[1])}"


def _props_text(props: dict[str, tuple[str, object]]) -> str:
    items = sorted(props.items(), key=lambda kv: _bytes(kv[0]))
    return "{" + ", ".join(f"{k}={render(v)}" for k, v in items) + "}"


def _props(row: dict, skip: set[str]) -> dict[str, tuple[str, object]]:
    out = {}
    for name, v in row.items():
        if name in skip or v is None:  # null members are elided (1.3)
            continue
        out[name] = value_form(v)
    return out


def normalize(doc) -> tuple[str, str | None, str | None]:
    """Return (status, reason, listing). listing is None when out of domain."""
    directed, multigraph = True, False
    for b in doc.blocks:
        if b.kind == "meta" and b.name == "graph":
            for row in b.rows:
                if "directed" in row:
                    directed = bool(row["directed"])
                if row.get("format") == MULTIGRAPH_FORMAT:
                    multigraph = True
    try:
        nodes: dict[tuple, dict] = {}
        for b in doc.blocks:
            if b.kind != "nodes":
                continue
            for row in b.rows:
                nid = _id_form(row.get("id"))
                nodes[(b.name, nid)] = _props(row, {"id"})
        ints = {(t, i[1]) for (t, i) in nodes if i[0] == "INT64"}
        for (t, i) in nodes:
            if i[0] == "STRING" and _INT_TEXT.fullmatch(i[1]) and (t, int(i[1])) in ints and str(int(i[1])) == i[1]:
                raise OutOfDomain("AMBIGUOUS_NODE_REFERENCE")

        def resolve(ref: Reference):
            if (ref.type, ("STRING", ref.id)) in nodes:
                key = (ref.type, ("STRING", ref.id))
            elif _INT_TEXT.fullmatch(ref.id):
                key = (ref.type, ("INT64", int(ref.id)))
            else:
                key = (ref.type, ("STRING", ref.id))
            if key not in nodes:
                raise OutOfDomain("INVALID_EDGE_ADDRESS")
            return key

        records = []
        for b in doc.blocks:
            if b.kind != "edges":
                continue
            for row in b.rows:
                ordinal = "0"
                skip = {"source", "target"}
                if multigraph:
                    key = row.get("key")
                    if isinstance(key, bool) or not isinstance(key, int) or key < 0:
                        raise OutOfDomain("INVALID_EDGE_ADDRESS")
                    ordinal = str(key)
                    skip.add("key")
                records.append((resolve(row["source"]), b.name, resolve(row["target"]), ordinal, _props(row, skip)))

        logical: dict[tuple, list] = {}
        for src, rel, tgt, ordinal, props in records:
            if directed:
                addr = (_ref_key(src), _bytes(rel), _ref_key(tgt), _bytes(ordinal))
                ends = (src, tgt)
            else:
                lo, hi = sorted((src, tgt), key=_ref_key)
                addr = (_ref_key(lo), _bytes(rel), _ref_key(hi), _bytes(ordinal))
                ends = (lo, hi)
            logical.setdefault(addr, []).append((src, tgt, ends, rel, ordinal, props))

        edges = []
        for addr, recs in logical.items():
            src, tgt, ends, rel, ordinal, props = recs[0]
            if directed:
                if len(recs) > 1:
                    raise OutOfDomain("INVALID_EDGE_ADDRESS")
            else:
                if len(recs) > 2:
                    raise OutOfDomain("UNDIRECTED_EDGE_CONFLICT")
                if len(recs) == 2:
                    if ends[0] != ends[1] and recs[0][0] == recs[1][0]:
                        raise OutOfDomain("INVALID_EDGE_ADDRESS")
                    if _props_text(recs[0][5]) != _props_text(recs[1][5]):
                        raise OutOfDomain("UNDIRECTED_EDGE_CONFLICT")
            edges.append((addr, f"edge {_ref_text(ends[0])} {rel} {_ref_text(ends[1])} ordinal={render(('STRING', ordinal))} {_props_text(props)}"))
    except OutOfDomain as e:
        return ("out_of_domain", e.reason, None)

    lines = [f"header directed={'true' if directed else 'false'} multigraph={'true' if multigraph else 'false'}"]
    for key in sorted(nodes, key=lambda k: _ref_key(k)):
        lines.append(f"node {_ref_text(key)} {_props_text(nodes[key])}")
    lines.extend(text for _, text in sorted(edges, key=lambda e: e[0]))
    return ("identifiable", None, "\n".join(lines) + "\n")


def _classify(text: str):
    return normalize(loads(text))


# =============================================================================
# Meta-test: the manifest and files are what the runners assume they are.
# =============================================================================

def test_manifest_integrity():
    meta = next(b for b in loads(_read("manifest.ison")).blocks if b.kind == "meta" and b.name == "corpus").rows[0]
    assert meta["kind"] == "semantic"
    findings = _findings_ids()

    ids = [r["id"] for r in ROWS]
    assert len(ids) == len(set(ids)), "duplicate vector ids"

    for path in SEMANTIC.rglob("*"):
        if path.is_file() and path.name != "README.md":
            data = path.read_bytes()
            rel = path.relative_to(SEMANTIC).as_posix()
            assert b"\r" not in data, f"{rel}: CRLF"
            assert not data.startswith(b"\xef\xbb\xbf"), f"{rel}: BOM"
            assert data.endswith(b"\n") and not data.endswith(b"\n\n"), f"{rel}: must end in exactly one LF"
            data.decode("utf-8")

    referenced = {"manifest.ison", "README.md"}
    for row in ROWS:
        assert row["semantic"] in ("identifiable", "out_of_domain"), row["id"]
        assert (row["semantic"] == "identifiable") == (row["reason"] is None), row["id"]
        assert row["loader"] in ("graph", "multigraph"), row["id"]
        assert isinstance(row["directed"], bool), row["id"]
        assert isinstance(row["nodes"], int) and isinstance(row["edges"], int), row["id"]
        assert (row["digest"] == "pending-G-ID-freeze") == (row["semantic"] == "identifiable"), (
            f"{row['id']}: identifiable rows carry digest pending-G-ID-freeze, out_of_domain rows carry none"
        )
        assert (row["normal"] is not None) == (row["semantic"] == "identifiable"), (
            f"{row['id']}: a normal-form listing exists iff the vector is identifiable"
        )
        for key in ("file", "canonical", "normal"):
            if row[key] is not None:
                assert (SEMANTIC / row[key]).is_file(), f"{row['id']}: {key} {row[key]} missing"
                referenced.add(row[key])

        cells = {p: row[p] for p in PORTS}
        for port, cell in cells.items():
            assert isinstance(cell, str) and cell, f"{row['id']}: {port} empty"
            assert cell in VECTOR_CELLS or cell.startswith("reject:"), f"{row['id']}: {port}={cell!r}"
            runner_exists = (ROOT / RUNNERS[port]).is_file()
            assert (cell == "todo") == (not runner_exists), (
                f"{row['id']}: {port} is {cell!r} but runner {'exists' if runner_exists else 'is missing'}"
            )
            needs_finding = cell.startswith("defect") or (
                cell.startswith("reject:") and row["semantic"] == "identifiable"
            )
            if needs_finding:
                assert row["id"] in findings, f"{row['id']}: {port}={cell} needs a README Findings row"
        assert (row["canonical"] is not None) == any(c == "pass:canonicalized" for c in cells.values()), (
            f"{row['id']}: canonical must be set iff some port is pass:canonicalized"
        )

    for rel in RELATIONS:
        assert rel["semantic"] in ("equal", "differ") and rel["artifact"] in ("same", "differ"), rel["id"]
        for side in ("a", "b"):
            assert rel[side] in BY_ID, f"{rel['id']}: {side}={rel[side]} is not a vector id"

    for row in API:
        assert row["semantic"] in ("identifiable", "out_of_domain"), row["id"]
        assert (row["semantic"] == "identifiable") == (row["reason"] is None), row["id"]
        for port in PORTS:
            cell = row[port]
            assert cell in API_CELLS or cell.startswith("reject:") or cell.startswith("accept:unwritable:"), (
                f"{row['id']}: {port}={cell!r}"
            )
            assert (cell == "todo") == (not (ROOT / RUNNERS[port]).is_file()), f"{row['id']}: {port} admission"
            if cell.startswith("accept:"):
                assert row["id"] in findings, f"{row['id']}: {port}={cell} needs a README Findings row"

    on_disk = {p.relative_to(SEMANTIC).as_posix() for p in SEMANTIC.rglob("*") if p.is_file()}
    assert on_disk == referenced, f"unreferenced or missing files: {sorted(on_disk ^ referenced)}"


# =============================================================================
# Vector runner
# =============================================================================

def _load(row: dict, text: str):
    return (MultiGraph if row["loader"] == "multigraph" else ISONGraph).from_ison(text)


def _emit(graph) -> str:
    return graph.to_ison() + "\n"


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_vector(row):
    expectation = row[PORT]
    text = _read(row["file"])

    # Semantic/2 verdict on what this port's ISON parser delivers. A lossy
    # cell is exactly where the port's parser or writer cannot carry the
    # document, so the verdict is not asserted there.
    if expectation != "pass:lossy":
        status, reason, listing = _classify(text)
        assert (status, reason) == (row["semantic"], row["reason"])
        if row["semantic"] == "identifiable":
            assert listing == _read(row["normal"])

    if expectation.startswith("reject:"):
        with pytest.raises(Exception) as info:
            _load(row, text)
        assert type(info.value).__name__ == expectation[len("reject:"):]
        return

    graph = _load(row, text)
    assert graph.directed == row["directed"]
    assert graph.node_count() == row["nodes"]
    assert graph.edge_count() == row["edges"]

    out = _emit(graph)
    again = _emit(_load(row, out))
    if expectation == "pass":
        assert out == text
    elif expectation == "pass:canonicalized":
        assert out == _read(row["canonical"])
        assert again == out
    elif expectation == "pass:lossy":
        assert out != text, "pass:lossy but output equals the file - promote the cell to pass"
        assert again == out
    elif expectation == "defect":
        assert again == out
    elif expectation == "defect:unstable":
        # The port writes a form it reads back as a different value.
        assert again != out, "defect:unstable but output is idempotent - the cell is stale"
    else:
        pytest.fail(f"unknown expectation {expectation!r} for {PORT}")


# =============================================================================
# Relations: same graph / different graph, same bytes / different bytes
# =============================================================================

@pytest.mark.parametrize("rel", RELATIONS, ids=[r["id"] for r in RELATIONS])
def test_relation(rel):
    a, b = (_read(BY_ID[rel[s]]["file"]) for s in ("a", "b"))
    forms = [_classify(t) for t in (a, b)]
    assert (forms[0] == forms[1]) == (rel["semantic"] == "equal")
    same_bytes = hashlib.sha256(a.encode()).digest() == hashlib.sha256(b.encode()).digest()
    assert same_bytes == (rel["artifact"] == "same")


# =============================================================================
# API-level conditions: documents cannot carry them
# =============================================================================

OPS = {
    "nan-property": lambda: float("nan"),
    "inf-property": lambda: float("inf"),
    "lone-surrogate-property": lambda: chr(0xD800),
    "list-property": lambda: ["a", "b"],
    "dict-property": lambda: {"a": 1},
    "int-beyond-int64-property": lambda: 10**20,
    "float-exponent-property": lambda: 1e-7,
}


@pytest.mark.parametrize("row", API, ids=[r["id"] for r in API])
def test_api(row):
    value = OPS[row["op"]]()
    try:
        value_form(value)
        verdict = ("identifiable", None)
    except OutOfDomain as e:
        verdict = ("out_of_domain", e.reason)
    assert verdict == (row["semantic"], row["reason"])

    expectation = row[PORT]
    graph = ISONGraph("g")
    if expectation.startswith("reject:"):
        with pytest.raises(Exception) as info:
            graph.add_node("p", 1, x=value)
        assert type(info.value).__name__ == expectation[len("reject:"):]
        return

    graph.add_node("p", 1, x=value)
    out = graph.to_ison()
    if expectation == "accept:unencodable":
        with pytest.raises(UnicodeEncodeError):
            out.encode("utf-8")
        return
    after = ISONGraph.from_ison(out).get_node("p", 1).properties["x"]
    same = type(after) is type(value) and after == value
    assert same == (expectation == "accept"), f"reloaded {after!r} ({type(after).__name__}) from {value!r}"
