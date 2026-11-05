# ISONGraph Core Conformance Corpus

Executable vectors proving "same document -> same meaning in every port". Owned by Core; consumed by ISONGraphExt and downstream at a pinned commit, never copied.

See `manifest.ison` for the index. Full design: ISONGraphExt blueprint `15-CORE-CONFORMANCE-CORPUS.md`.

## Findings

| vector | ports | observed | spec says | status |
|---|---|---|---|---|
| structure/multigraph-document | ts, js | loads the document and treats `key` as an edge property | Python, Rust, C# and C++ refuse an `ison-graph-multigraph-v1` document | open - CORE_BLOCKING_DIVERGENCE |
| values/nonfinite-as-text | ts, js | writer emits the strings `nan` / `inf` bare | ison-py quotes them (`"nan"`), so the same graph has two canonical byte forms | open - ISONCS writer divergence, needs an ison-ts/ison-js decision |
| ids/int64-extremes | ts, js | ids beyond 2^53 are read as binary64 and re-emitted rounded | 13-SEMANTIC-2 §1.2 JS binding rule: such input must arrive as BigInt or an exact integer token | known limitation - pass:lossy |
| values/int64-extreme-values | ts, js | as above for property values | as above | known limitation - pass:lossy |
| values/int-vs-integral-float | ts, js | `1.0` is re-emitted as `1` | CHANGELOG 1.4.0 known limitation; Semantic/2 treats both as INT64(1) | known limitation - pass:lossy |
