# ISONGraph Core Conformance Corpus

Executable vectors proving **"same document → same meaning in every port"**.
Owned by Core. ISONGraphExt, ISONGraph Visualize and products consume it at a
pinned commit through the Core Conformance Receipt; they never copy or fork
it. A missing vector is added here.

## What it tests

Documents. Each vector is an ISON or ISONL text; each port loads it, checks
directedness and counts, writes it back and compares bytes. Construction-time
API refusals (NaN at `add_node`, float ids, property-name rules) cannot be
carried on the wire and are each port's unit tests, not this corpus.

Expected Semantic/2 digests are not yet included; the `digest` column is
reserved and `null`.

## Layout

    manifest.ison       the only index; every port parses it with its own ISON parser
    ids/ values/ structure/ serialization/
    ../scripts/corpus_digest.py    sha256 over sorted (path, bytes) of vectors/**
    ../scripts/corpus_receipt.py   per-port Core Conformance Receipt

Every file is UTF-8 without BOM, LF-only, ending in exactly one newline; the
`.gitattributes` rule `vectors/** text eol=lf` keeps it so on every platform.
Comparison is always `to_ison() + "\n"` against the file. A file ending in
`.isonl` is loaded with `from_isonl`.

## Manifest columns

| column | meaning |
|---|---|
| `id` | `<group>/<name>`, unique |
| `file` | path relative to this directory |
| `semantic` | `identifiable` or `out_of_domain` under ISONGraph-Semantic/2 |
| `reason` | why out of domain; `null` when identifiable |
| `directed` | expected `graph.directed` after load |
| `nodes`, `edges` | expected counts after load; `edges` counts stored records (an undirected edge counts 2) |
| `canonical` | sibling file holding the canonical output when the input is deliberately non-canonical; set iff some port is `pass:canonicalized` |
| `digest` | reserved; `null` |
| `python` `ts` `js` `rust` `cs` `cpp` | per-port expectation, below |

## Per-port expectation grammar

| value | the runner checks |
|---|---|
| `pass` | loads; directed and counts match; output is byte-identical to the file |
| `pass:canonicalized` | loads; counts match; output equals the `canonical` file and is idempotent |
| `pass:lossy` | loads; counts match; output differs for a documented port limitation; idempotent |
| `defect` | loads without raising but contradicts the spec; directed and counts are pinned to what the port does and output must be idempotent; a Findings row below must name the vector |
| `reject:<ErrorName>` | loading raises that port's error class of that name |
| `todo` | no runner for this port yet |

Rules. Expectations are set from **observed** behaviour of the released port;
an observation that contradicts Semantic/2 becomes a Findings row, never a
weakened vector. **Port runner admission is atomic**: a column contains
`todo` iff the port's runner file is absent, so a port is either fully in or
not in. **Three postures never collapse**: `python = pass` on
`values/int-beyond-int64` says the port loads it; `semantic = out_of_domain`
says Semantic/2 assigns it no identity. `pass:lossy` is not conformance — a
consumer needing cross-port identity treats that port as `CORE_LOSSY` for the
input.

## Receipt

`python scripts/corpus_receipt.py --port <name>` prints one `meta.core_conformance_receipt`
row: core commit and version, semantic spec, corpus version/commit/digest,
port and version, the counts per expectation kind, and the derived posture
(`FULL`, `LOSSY_KNOWN`, `KNOWN_DEFECT`, `PARTIAL`, `INCONCLUSIVE`). Commits are
full SHAs. `NONCONFORMANT` is CI's verdict, not the script's: a receipt is
only meaningful for a green commit.

## Findings

| vector | ports | observed | spec says | status |
|---|---|---|---|---|
| structure/multigraph-document | ts, js | loads the document, treats `key` as an edge property, and drops the whole `meta.graph` block on output - so a TS/JS round trip turns a multigraph document into a simple-graph document that Python then accepts | Python, Rust, C# and C++ refuse an `ison-graph-multigraph-v1` document | open - CORE_BLOCKING_DIVERGENCE |
| values/nonfinite-as-text | ts, js | writer emits the strings `nan` / `inf` bare | ison-py quotes them (`"nan"`), so the same graph has two canonical byte forms | open - ISONCS writer divergence, needs an ison-ts/ison-js decision |
| ids/int64-extremes | ts, js | ids beyond 2^53 are read as binary64 and re-emitted rounded | 13-SEMANTIC-2 §1.2 JS binding rule: such input must arrive as BigInt or an exact integer token | known limitation - pass:lossy |
| values/int64-extreme-values | ts, js | as above for property values | as above | known limitation - pass:lossy |
| values/int-beyond-int64-inexact | ts, js | `100000000000000000001` is read as binary64 and re-emitted as `100000000000000000000`; the sibling `values/int-beyond-int64` (10^20) is `pass` only because that literal is exactly representable | as above - integers beyond 2^53 are not preserved unless exactly representable | known limitation - pass:lossy |
| values/int-vs-integral-float | ts, js | `1.0` is re-emitted as `1` | CHANGELOG 1.4.0 known limitation; Semantic/2 treats both as INT64(1) | known limitation - pass:lossy |
