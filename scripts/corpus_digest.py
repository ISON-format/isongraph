#!/usr/bin/env python3
"""Print the digest ISONGraphExt pins as core_vector_corpus_digest.

    sha256( concat over sorted relative paths of: path + "\\0" + bytes + "\\0" )

Sorted by POSIX relative path so the result is the same on every platform
and independent of checkout order. Usage:

    python scripts/corpus_digest.py            # defaults to <repo>/vectors
    python scripts/corpus_digest.py some/dir
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def corpus_digest(root: Path) -> str:
    h = hashlib.sha256()
    # Sort by the exact key that is hashed - the POSIX relative path - so the
    # order never depends on platform path semantics or Path ordering rules.
    files = sorted(
        (p for p in root.rglob("*") if p.is_file()),
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
