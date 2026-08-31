#!/usr/bin/env python3
"""Assert the six ISONGraph ports agree on the canonical golden bytes.

Each port's own suite checks its code against its own golden, which catches
that port drifting from its expectation. Nothing checks the ports against
each other: if js emits X and rust emits Y, goldenJs=X and goldenRs=Y both
pass their own suites and the disagreement is invisible.

Byte-identity across languages is the property ISONCS exists to provide, so
it gets its own check. Python is the reference.

A golden that cannot be located is a failure, not a skip - a silent skip
would let a renamed constant quietly retire the guarantee.

Exit: 0 all agree, 1 any disagree or missing.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _concat_string_literals(body: str) -> str:
    """Join a run of adjacent double-quoted literals (js/ts/cs/cpp style)."""
    parts = re.findall(r'"(?:[^"\\]|\\.)*"', body)
    if not parts:
        raise ValueError("no string literals found")
    return "".join(json.loads(p) for p in parts)


def python_golden(name: str) -> str:
    s = (ROOT / "ison-graph/tests/test_ison_graph.py").read_text(encoding="utf-8")
    m = re.search(rf"^{name} = \((.*?)\n\)", s, re.S | re.M)
    if not m:
        raise ValueError(f"{name} not found")
    return "".join(eval(line.strip()) for line in m.group(1).strip().split("\n"))


def js_like_golden(path: str, name: str) -> str:
    s = (ROOT / path).read_text(encoding="utf-8")
    m = re.search(rf"^const {name} =\n(.*?);$", s, re.S | re.M)
    if not m:
        raise ValueError(f"{name} not found")
    return _concat_string_literals(m.group(1))


def rust_golden(name: str) -> str:
    s = (ROOT / "ison-graph-rs/src/lib.rs").read_text(encoding="utf-8")
    m = re.search(rf'const {name}: &str = r#"(.*?)"#;', s, re.S)
    if not m:
        raise ValueError(f"{name} not found")
    return m.group(1)


def concat_golden(path: str, pattern: str) -> str:
    s = (ROOT / path).read_text(encoding="utf-8")
    m = re.search(pattern, s, re.S)
    if not m:
        raise ValueError("pattern not found")
    return _concat_string_literals(m.group(1))


PORTS = {
    "python": lambda: (python_golden("CANONICAL_GOLDEN_ISON"),
                       python_golden("CANONICAL_GOLDEN_ISONL")),
    "js": lambda: (js_like_golden("ison-graph-js/src/index.test.js", "CANONICAL_GOLDEN_ISON"),
                   js_like_golden("ison-graph-js/src/index.test.js", "CANONICAL_GOLDEN_ISONL")),
    "ts": lambda: (js_like_golden("ison-graph-ts/src/index.test.ts", "CANONICAL_GOLDEN_ISON"),
                   js_like_golden("ison-graph-ts/src/index.test.ts", "CANONICAL_GOLDEN_ISONL")),
    "rust": lambda: (rust_golden("CANONICAL_GOLDEN_ISON"),
                     rust_golden("CANONICAL_GOLDEN_ISONL")),
    "csharp": lambda: (
        concat_golden("ison-graph-cs/tests/IsonGraph.Tests/SerializationTests.cs",
                      r"private const string GoldenIson =\n(.*?);\n"),
        concat_golden("ison-graph-cs/tests/IsonGraph.Tests/SerializationTests.cs",
                      r"private const string GoldenIsonl =\n(.*?);\n")),
    "cpp": lambda: (
        concat_golden("ison-graph-cpp/tests/test_ison_graph.cpp",
                      r"static const std::string CANONICAL_GOLDEN_ISON =\n(.*?);\n"),
        concat_golden("ison-graph-cpp/tests/test_ison_graph.cpp",
                      r"static const std::string CANONICAL_GOLDEN_ISONL =\n(.*?);\n")),
}

REFERENCE = "python"


def main() -> int:
    goldens: dict[str, tuple[str, str]] = {}
    failures: list[str] = []

    for port, extract in PORTS.items():
        try:
            goldens[port] = extract()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{port}: could not read its golden - {exc}")

    if REFERENCE not in goldens:
        print(f"FAIL: no reference golden from {REFERENCE}")
        for f in failures:
            print(f"  {f}")
        return 1

    ref_ison, ref_isonl = goldens[REFERENCE]
    print(f"{'port':9} {'ISON':>10} {'ISONL':>10}")
    print("-" * 32)
    for port, (ison, isonl) in goldens.items():
        a = "match" if ison == ref_ison else "DIFFERS"
        b = "match" if isonl == ref_isonl else "DIFFERS"
        print(f"{port:9} {a:>10} {b:>10}")
        if ison != ref_ison:
            failures.append(f"{port} ISON differs from {REFERENCE}")
        if isonl != ref_isonl:
            failures.append(f"{port} ISONL differs from {REFERENCE}")

    print()
    print(f"reference ({REFERENCE}): {len(ref_ison)} bytes ISON, "
          f"{len(ref_isonl)} bytes ISONL")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  {f}")
        return 1

    print(f"\nAll {len(goldens)} ports agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
