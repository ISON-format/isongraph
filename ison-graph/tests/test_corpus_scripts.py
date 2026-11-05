"""Tests for the repo-level corpus scripts (scripts/corpus_digest.py and
scripts/corpus_receipt.py). They live outside the package, so they are
imported by path."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _import(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


digest_mod = _import("corpus_digest")


def _make(tmp_path: Path, files: dict[str, bytes]) -> Path:
    for rel, data in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return tmp_path


def test_digest_is_sha256_over_sorted_path_and_bytes(tmp_path):
    root = _make(tmp_path, {"b/two.ison": b"2\n", "a.ison": b"1\n"})
    expected = hashlib.sha256(b"a.ison\0" + b"1\n" + b"\0" + b"b/two.ison\0" + b"2\n" + b"\0").hexdigest()
    assert digest_mod.corpus_digest(root) == expected


def test_digest_ignores_creation_order(tmp_path):
    a = _make(tmp_path / "x", {"a.ison": b"1\n", "b.ison": b"2\n"})
    b = _make(tmp_path / "y", {"b.ison": b"2\n", "a.ison": b"1\n"})
    assert digest_mod.corpus_digest(a) == digest_mod.corpus_digest(b)


def test_digest_changes_when_a_byte_changes(tmp_path):
    root = _make(tmp_path, {"a.ison": b"1\n"})
    before = digest_mod.corpus_digest(root)
    (root / "a.ison").write_bytes(b"1 \n")
    assert digest_mod.corpus_digest(root) != before


def test_real_corpus_digest_is_stable_across_two_calls():
    d1 = digest_mod.corpus_digest(ROOT / "vectors")
    d2 = digest_mod.corpus_digest(ROOT / "vectors")
    assert d1 == d2 and len(d1) == 64


receipt_mod = _import("corpus_receipt")


@pytest.mark.parametrize("cells,runner,expected", [
    (["pass", "reject:X", "pass:canonicalized"], True, "FULL"),
    (["pass", "pass:lossy"], True, "LOSSY_KNOWN"),
    (["pass", "defect"], True, "KNOWN_DEFECT"),
    (["pass:lossy", "defect"], True, "KNOWN_DEFECT"),
    (["todo", "todo"], False, "PARTIAL"),
    (["pass", "todo"], True, "INCONCLUSIVE"),
    (["pass"], False, "INCONCLUSIVE"),
])
def test_posture(cells, runner, expected):
    assert receipt_mod.posture(cells, runner) == expected


def test_receipt_for_python_is_full_and_counts_add_up():
    r = receipt_mod.build_receipt(ROOT, "python")
    assert r["port"] == "python"
    assert r["core_format"] == "isongraph"
    assert r["semantic_spec"] == "ISONGraph-Semantic/2-draft"
    assert r["corpus_version"] == 1
    assert len(r["corpus_digest"]) == 64
    assert re.fullmatch(r"[0-9a-f]{40}", r["core_commit"])
    assert re.fullmatch(r"[0-9a-f]{40}", r["corpus_commit"])
    assert r["posture"] == "FULL"
    assert r["total"] == r["pass"] + r["canonicalized"] + r["lossy"] + r["defect"] + r["rejected_as_expected"] + r["todo"]
    assert r["todo"] == 0


def test_receipt_for_ts_is_known_defect():
    r = receipt_mod.build_receipt(ROOT, "ts")
    assert r["posture"] == "KNOWN_DEFECT"
    assert r["defect"] >= 1 and r["lossy"] >= 1


def test_receipt_for_rust_is_partial():
    r = receipt_mod.build_receipt(ROOT, "rust")
    assert r["posture"] == "PARTIAL" and r["todo"] == r["total"]


def test_receipt_cli_prints_ison(capsys):
    assert receipt_mod.main(["corpus_receipt.py", "--port", "python"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("meta.core_conformance_receipt\n")
    assert " FULL" in out
