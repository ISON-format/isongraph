#!/usr/bin/env python3
"""Print the digest ISONGraphExt pins as core_vector_corpus_digest.

    sha256( concat over sorted relative paths of: path + "\\0" + bytes + "\\0" )

Sorted by POSIX relative path so the result is the same on every platform
and independent of checkout order. Usage:

    python scripts/corpus_digest.py                   # defaults to <repo>/vectors
    python scripts/corpus_digest.py some/dir
    python scripts/corpus_digest.py vectors/semantic  # the semantic golden corpus

The Core corpus digest does not cover `semantic/`: that sub-corpus has its own
manifest and is pinned by its own digest, so adding it left the digest that
the Core Conformance Receipts carry unchanged.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


#: Top-level directories of a corpus root that belong to a different corpus.
EXCLUDED_TOP_LEVEL = ("semantic",)


def corpus_digest(root: Path) -> str:
    h = hashlib.sha256()
    # Sort by the exact key that is hashed - the POSIX relative path - so the
    # order never depends on platform path semantics or Path ordering rules.
    files = sorted(
        (
            p
            for p in root.rglob("*")
            if p.is_file() and p.relative_to(root).parts[0] not in EXCLUDED_TOP_LEVEL
        ),
        key=lambda p: p.relative_to(root).as_posix(),
    )
    for path in files:
        rel = path.relative_to(root).as_posix().encode("utf-8")
        h.update(rel + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1] / "vectors"
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    print(corpus_digest(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
