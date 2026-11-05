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
