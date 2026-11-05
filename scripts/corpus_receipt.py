#!/usr/bin/env python3
"""Emit the Core Conformance Receipt for one port, as ISON.

The receipt is computed from vectors/manifest.ison - whose expectations are
observed behaviour by the corpus rules - plus the port's declared version
and the repo's git state. The port's runner is what makes the manifest
trustworthy, so a receipt is only meaningful for a commit whose CI is
green. Posture is derived, never hand-set:

    FULL          runner exists, no todo, no pass:lossy, no defect
    LOSSY_KNOWN   runner exists, no todo, no defect, some pass:lossy
    KNOWN_DEFECT  runner exists, no todo, some defect (contradicts the spec)
    PARTIAL       no runner (every cell todo)
    INCONCLUSIVE  manifest and runner disagree about admission

Commits are full SHAs: the receipt is a long-lived pin.

Usage:
    python scripts/corpus_receipt.py --port python
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from ison_parser import Block, Document, dumps_canonical, loads

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_digest import corpus_digest  # noqa: E402

RUNNERS = {
    "python": "ison-graph/tests/test_vectors.py",
    "ts": "ison-graph-ts/src/vectors.test.ts",
    "js": "ison-graph-js/src/vectors.test.js",
    "rust": "ison-graph-rs/tests/vectors.rs",
    "cs": "ison-graph-cs/tests/IsonGraph.Tests/VectorsTests.cs",
    "cpp": "ison-graph-cpp/tests/test_vectors.cpp",
}

VERSION_FILES = {
    "python": ("ison-graph/pyproject.toml", r'^version = "([^"]+)"'),
    "ts": ("ison-graph-ts/package.json", None),
    "js": ("ison-graph-js/package.json", None),
    "rust": ("ison-graph-rs/Cargo.toml", r'^version = "([^"]+)"'),
    "cs": ("ison-graph-cs/src/IsonGraph/IsonGraph.csproj", r"<Version>([^<]+)</Version>"),
    "cpp": ("ison-graph-cpp/CMakeLists.txt", r"VERSION ([0-9.]+) "),
}


def posture(cells: list[str], runner_exists: bool) -> str:
    todo = sum(c == "todo" for c in cells)
    if not runner_exists:
        return "PARTIAL" if todo == len(cells) else "INCONCLUSIVE"
    if todo:
        return "INCONCLUSIVE"
    if any(c == "defect" for c in cells):
        return "KNOWN_DEFECT"
    if any(c == "pass:lossy" for c in cells):
        return "LOSSY_KNOWN"
    return "FULL"


def port_version(root: Path, port: str) -> str:
    rel, pattern = VERSION_FILES[port]
    text = (root / rel).read_text(encoding="utf-8")
    if pattern is None:
        return json.loads(text)["version"]
    m = re.search(pattern, text, flags=re.M)
    if not m:
        raise SystemExit(f"no version in {rel}")
    return m.group(1)


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def build_receipt(root: Path, port: str) -> dict:
    manifest = loads((root / "vectors" / "manifest.ison").read_text(encoding="utf-8"))
    meta = next(b for b in manifest.blocks if b.kind == "meta" and b.name == "corpus").rows[0]
    rows = [r for b in manifest.blocks if b.kind == "table" and b.name == "vectors" for r in b.rows]
    cells = [r[port] for r in rows]
    runner_exists = (root / RUNNERS[port]).is_file()
    return {
        "core_format": "isongraph",
        "core_version": port_version(root, "python"),
        "core_commit": git(root, "rev-parse", "HEAD"),
        "semantic_spec": meta["semantic_spec"],
        "corpus_version": meta["version"],
        "corpus_commit": git(root, "log", "-1", "--format=%H", "--", "vectors") or git(root, "rev-parse", "HEAD"),
        "corpus_digest": corpus_digest(root / "vectors"),
        "port": port,
        "port_version": port_version(root, port),
        "total": len(cells),
        "pass": sum(c == "pass" for c in cells),
        "canonicalized": sum(c == "pass:canonicalized" for c in cells),
        "lossy": sum(c == "pass:lossy" for c in cells),
        "defect": sum(c == "defect" for c in cells),
        "rejected_as_expected": sum(c.startswith("reject:") for c in cells),
        "todo": sum(c == "todo" for c in cells),
        "posture": posture(cells, runner_exists),
    }


def to_ison(receipt: dict) -> str:
    block = Block(kind="meta", name="core_conformance_receipt", fields=list(receipt), rows=[receipt])
    return dumps_canonical(Document(blocks=[block]))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", required=True, choices=sorted(RUNNERS))
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv[1:])
    print(to_ison(build_receipt(Path(args.root), args.port)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
