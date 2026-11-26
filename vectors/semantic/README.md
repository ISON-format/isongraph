# ISONGraph Semantic Golden Corpus

The pre-freeze golden corpus for the graph-identity contract
(ISONGraph-Semantic/2, still a draft; section numbers below are those of
13-SEMANTIC-2): executable vectors that say, per document, **what identity the
document has** and **what each port does with it**. It is a sub-corpus of the
[Core Conformance Corpus](../README.md), owned by Core in the same way,
consumed by pinned commit and digest, never copied or forked downstream.

It exists because the two statuses are different questions. The Core corpus
asks whether a port loads a document and writes it back. This corpus adds the
question the identity contract asks first: does the document have a semantic
identity at all (`identifiable` / `out_of_domain` with a reason), what is its
normal form, and which documents must have the same or a different identity.

## Status: no digests yet

The digest encoding of Semantic/2 (tag bytes, `u32` lengths) is **not
frozen**, so this corpus contains **no expected digest**. Every identifiable
vector carries `digest = pending-G-ID-freeze`; every out-of-domain vector
carries `digest = none`, because an out-of-domain input has no identity and so
can never have a digest. When the encoding is frozen the column is filled in
without any change to the structure.

What is executable today instead of a digest is the **normal-form listing**
(below): a plain-text rendering of the information the digest will hash,
without the byte encoding. Two documents have the same listing if and only if
they will have the same semantic digest, for any encoding that is injective on
the listing.

## Layout

    manifest.ison     three tables: vectors, relations, api
    ids/ values/ structure/ receipts/    vector documents (.ison)
    *.normal          normal-form listing of an identifiable vector
    *.canonical.ison  canonical output where a port normalizes the input

Same file rules as the Core corpus: UTF-8 without BOM, LF only, one final
newline (`vectors/** text eol=lf` in `.gitattributes` covers this directory).
Several documents are byte-identical to a Core corpus vector on purpose: this
directory is self-contained, so one digest pins it and an edit to the Core
corpus cannot silently change it.

Runners, one per port, in each port's existing suite (no new CI job):

| port | runner | command |
|---|---|---|
| python | `ison-graph/tests/test_semantic_vectors.py` | `cd ison-graph && pytest tests/test_semantic_vectors.py` |
| ts | `ison-graph-ts/src/semantic-vectors.test.ts` | `cd ison-graph-ts && npx vitest run src/semantic-vectors.test.ts` |
| js | `ison-graph-js/src/semantic-vectors.test.js` | `cd ison-graph-js && npx vitest run src/semantic-vectors.test.js` |
| rust, cs, cpp | none yet | their columns are `todo` |

Pin the corpus with `python scripts/corpus_digest.py vectors/semantic`. The
Core corpus digest (`python scripts/corpus_digest.py`) does **not** cover this
directory, so adding it did not move the digest that the six Core Conformance
Receipts carry, and `scripts/corpus_receipt.py` computes `corpus_commit` from
the Core corpus alone for the same reason. There is no semantic receipt yet: a
receipt for this corpus only becomes meaningful once there are digests to pin.

## Manifest

`meta.corpus` carries `version`, `semantic_spec` and `kind = semantic`.

### `table.vectors`

| column | meaning |
|---|---|
| `id`, `file` | `<group>/<name>`; path relative to this directory |
| `semantic`, `reason` | the Semantic/2 verdict on the document as such: `identifiable`, or `out_of_domain` with a section 1 / section 5 reason (`reason` is `null` iff identifiable). Document-level reasons are the Core corpus's: `AMBIGUOUS_NODE_REFERENCE` for a twin-carrying document, `INVALID_NODE_ID_TYPE`, `UNDIRECTED_EDGE_CONFLICT`, `INTEGER_OUT_OF_INT64`, `INTEGRAL_FLOAT_OUT_OF_INT64` |
| `directed`, `nodes`, `edges` | counts after a successful load, as in the Core corpus (an undirected edge counts 2); unused where every port rejects |
| `loader` | `graph` (`ISONGraph`) or `multigraph` (`MultiGraph`, Python only). A port without a multigraph reader records in its cell what `ISONGraph` does with the document |
| `canonical` | sibling holding canonical output; set iff some cell is `pass:canonicalized` |
| `normal` | the normal-form listing; set iff `identifiable` |
| `digest` | `pending-G-ID-freeze` or `none` (see above) |
| `python ts js rust cs cpp` | per-port expectation |

Cell grammar: the Core corpus grammar (`pass`, `pass:canonicalized`,
`pass:lossy`, `defect`, `reject:<ErrorName>`, `todo`) plus one value:

| value | the runner checks |
|---|---|
| `defect:unstable` | loads, counts match, and the output is **not** idempotent: the port writes a form it reads back as a different value. Needs a Findings row |

Additional rules over the Core corpus:

- A `defect*` cell, and any `reject:` cell on an **identifiable** vector (the
  port refuses a document that has an identity), needs a Findings row below.
- `todo` iff the port's *semantic* runner file is absent (atomic admission).
- For every cell except `pass:lossy` the runner also checks the document
  against the manifest's `semantic`/`reason` and, for identifiable vectors, the
  `normal` listing, **as that port's own ISON parser delivers the document**.
  This is independent of whether the port's graph loader accepts it, so a port
  that rejects a document is still checked on what it parses. `pass:lossy` is
  exactly where the port's parser or writer cannot carry the document, so the
  verdict is not asserted there.

### `table.relations`

`id a b semantic artifact`. A relation between two vectors: `semantic` is
`equal` or `differ` (do the two documents have the same normal-form listing,
that is, the same graph?) and `artifact` is `same` or `differ` (are the two
files byte-identical, that is, the same artifact digest?). This is how
"directed vs undirected must differ", "mirror collapse" and "same graph, two
writers" are executed before any digest exists.

### `table.api`

Conditions that a document cannot carry and that Core's construction API
decides: `id op semantic reason python ts js rust cs cpp`. `op` names a fixed
operation in each runner (`add_node` with one property whose value is the
named thing). Cells: `reject:<ErrorName>`; `accept` (accepted, written,
reloaded to the same type and value); `accept:retyped` (accepted and written,
but the reloaded value has another type or value); `accept:unwritable:<Name>`
(accepted, then writing raises); `accept:unencodable` (accepted, but the output
has no UTF-8 form). Any `accept:` cell needs a Findings row. This is a closed
list of seven operations, not a vector DSL; the Core corpus's rule that
construction-time behaviour belongs to each port's unit tests stands for
everything else.

## Normal-form listing

Non-normative and not a digest. One line per item, in the order Semantic/2
sections 2.3 and 3 sort them:

    header directed=<bool> multigraph=<bool>
    node <type>:<id> {<name>=<value>, ...}
    edge <type>:<id> <relation> <type>:<id> ordinal=STRING("<ordinal>") {<name>=<value>, ...}

- values and ids are `INT64(n)`, `FLOAT64(0x<16 hex digits of the IEEE-754
  bits>)`, `BOOL(true|false)` or `STRING("...")`; in strings printable ASCII is
  literal, `"` and `\` are backslash-escaped and every other code point is
  `\u{HEX}`, so NFD and NFC are visibly different;
- `1`, `1.0`, `-0.0` and `0.0` collapse to `INT64`; `1.5` is `FLOAT64`; a null
  member is absent (section 1.3);
- nodes are sorted by type bytes, then `INT64` before `STRING`, integers
  numerically, strings by UTF-8 bytes; properties by name bytes;
- edges are sorted by `(source, relation, target, ordinal)` with the ordinal
  compared as UTF-8 bytes, so `"0" < "1" < "10" < "2"`; a simple-graph edge has
  ordinal `"0"`, a multigraph edge the decimal spelling of its key;
- for an undirected graph the two stored records of an edge collapse to one
  logical edge listed with canonical endpoints (the smaller `NodeRef` first); no
  listing exists if the records disagree.

The runners' `normalize` function is a **test oracle** for sections 1 and 2 of
the draft, written so that the expectations are executed instead of being
prose. It is not the Semantic/2 implementation; it has one copy per language and
no shared code. The manifest is the authority for what each vector means; if the
oracle and the manifest disagree, the test fails and a human decides.

JavaScript cannot tell the integer `10^20` from the float `1e20`. Its oracle
reports `JS_UNSAFE_INTEGER` for any integral number beyond 2^53 (the binding
rule of section 1.2) and accepts it where the manifest expects either
`INTEGER_OUT_OF_INT64` or `INTEGRAL_FLOAT_OUT_OF_INT64`.

The `semantic` column for a multigraph document is its **multigraph** verdict
(identifiable, `multigraph=true` in the listing). The Core corpus's
`structure/multigraph-document` records the simple-graph reading
(`MULTIGRAPH_DOCUMENT`); each is right for the question its corpus asks.

## Coverage of the section 8 minimum corpus

| section 8 item | where |
|---|---|
| id `+1`, `-1`, `"1"`, `"-1"` | `ids/int-positive`, `ids/int-negative`, `ids/string-numeric`, `ids/string-negative` |
| id `"007"` | `ids/string-leading-zero`, `ids/leading-zero-not-twin` |
| id int64 min, max | `ids/int64-extremes` |
| twin rejection `1`/`"1"`, `-1`/`"-1"` | `ids/twin-int-string`, `ids/twin-negative` |
| `1` vs `1.0` collapse | `values/int-float-collapse` |
| `-0.0` | `values/zero-forms` |
| `1.5` | `values/float-fractional` |
| int64 min/max values | `values/int64-extreme-values` |
| out-of-range int | `values/int-beyond-int64`, `values/int-just-beyond-int64` |
| integral float outside int64 | `values/integral-float-outside-int64` |
| NaN, Inf | `api/nan-property`, `api/inf-property`; the wire spellings are text: `values/nonfinite-as-text` |
| null elision | `values/null-elision` |
| NFD != NFC | `values/nfd-vs-nfc` |
| lone surrogate rejection | `api/lone-surrogate-property`; no document can carry one (`values/unicode-escape-not-decoded`) |
| list property rejection | `api/list-property`, `api/dict-property`; on the wire a list is text: `values/json-text-is-string` |
| directed vs undirected differ | `rel/directed-vs-undirected` |
| undirected mirror collapse | `structure/undirected-basic`, `rel/undirected-single-row-vs-mirrors` |
| undirected mirror conflict | `structure/undirected-mirror-conflict`, `structure/undirected-three-records` |
| simple edge ordinal `"0"` | `structure/simple-edge-ordinal` (and every edge in the listings) |
| multiedge ordinals `"0"`/`"1"`/`"10"`/`"2"` | `structure/multiedge-ordinals` |
| self-loop | `structure/self-loop`, `structure/undirected-self-loop` |
| same graph, two writers: same semantic digest, different artifact digest | `rel/two-writers-int-float`, `rel/two-writers-nan-text` over `receipts/*`, which are the real outputs of ison-py and of ison-js/ison-ts for one graph. Today the equality is of listings and the difference is of file bytes; the digest values and the receipt object itself (`semantic_digest`, `artifact_digest`, `core_writer`) wait for the encoding freeze and for a receipt implementation |

Beyond section 8: `ids/plus-sign-text`, `ids/float-id`, `ids/bool-id`,
`values/bool-vs-int-vs-string`, `values/exponent-text`,
`structure/header-explicit-true` / `header-absent`,
`api/float-exponent-property`.

## Findings

Observations that contradict Semantic/2, plus divergences between ports. As in
the Core corpus, an expectation is set from observed behaviour and a
contradiction becomes a row here, never a weakened vector. Ports: `py`, `ts`,
`js` (Rust, C# and C++ have no semantic runner).

| vector | ports | observed | spec says | status |
|---|---|---|---|---|
| ids/leading-zero-not-twin | py, ts, js | `7` and `"007"` in one node type are refused with `DuplicateNodeError`: the twin test compares `int(text)`, not the canonical spelling | section 1.5: twins are ids whose canonical decimal spelling is identical (`1`/`"1"`); `"007"` is not the canonical spelling of 7, so the two are different identities and the document is identifiable | open - Core over-rejects; a document with a real identity is unloadable |
| values/integral-float-outside-int64 | py | `100000000000000000000.0` loads as a float and is written as `1e+20`, which is read back as the **string** `"1e+20"`: the output is not idempotent | section 6: persistence conformance requires round-trip invariance; here the type changes | open - TYPE_ROUNDTRIP_FAILURE |
| values/integral-float-outside-int64 | ts, js | the number is written as the integer text `100000000000000000000`, so the float/int distinction is lost | section 1.2 JavaScript binding rule | known limitation - pass:lossy |
| api/float-exponent-property | py, ts, js | a float whose spelling uses an exponent is written as an exponent token and reads back as a STRING: Python below 1e-4 and from 1e16 (`1e-07`, `1e+16`), JavaScript below 1e-6 and from 1e21 (`1e-7`, `1e+21`). These are ordinary FLOAT64 values with an identity | section 6 lists fractional FLOAT64 as persistence PASS; that holds only for values spelled without an exponent | open - TYPE_ROUNDTRIP_FAILURE in all three |
| structure/undirected-mirror-conflict | py, ts, js | the loader keeps the first row and silently skips the other mirror row, so the loaded graph shows `w` 1 on both sides and **no conflict is visible**; the output is identifiable | section 2.3: differing mirror properties are `UNDIRECTED_EDGE_CONFLICT` | open - the conflict can only be detected from the document's rows, not from a loaded graph; a Semantic/2 implementation must classify the parsed document |
| structure/undirected-three-records | py, ts, js | same: the third record is skipped silently | section 2.3: more than two records is `UNDIRECTED_EDGE_CONFLICT` | open, as above |
| structure/multiedge-ordinals | ts, js | `DuplicateEdgeError`: no multigraph reader (a single-edge multigraph document is the `defect` already recorded in the Core corpus) | section 2.2: a multigraph document has an identity with ordinals `"0"`, `"1"`, `"10"`, `"2"` | open - same cause as Core `structure/multigraph-document`; Python is the only port that executes this vector |
| api/lone-surrogate-property | py, ts, js | accepted at construction and written to the output string; the output has no UTF-8 form (Python raises on encode, JavaScript silently writes U+FFFD) | section 1.4: `INVALID_UNICODE_SCALAR` | open - Core-legal, identity-unavailable |
| api/list-property | py, js | accepted and written as JSON text; reloads as a STRING (`retyped`). The JSON spacing differs: Python `["a", "b"]`, JavaScript `["a","b"]`, so two ports write different strings for one list | section 1.1: `CONTAINER_PROPERTY` | open - lossy, and the two ports' strings differ |
| api/list-property | ts | accepted by `addNode`, then `toIson()` throws `TypeError` (ison-ts cannot write an array) | as above | open - TS fails late where Python and JS write |
| api/dict-property | py, js | as for lists: written as JSON text, reloads as a STRING | section 1.1: `CONTAINER_PROPERTY` | open - lossy |
| api/dict-property | ts | accepted, then `toIson()` throws `TypeError` | as above | open |
| api/int-beyond-int64-property | js | a `BigInt` beyond int64 is written as a **quoted string** (`"100000000000000000000"`) and reloads as a STRING | section 1.2: `INTEGER_OUT_OF_INT64` | open - silent retyping |
| api/int-beyond-int64-property | ts | a `BigInt` is accepted by `addNode`, then `toIson()` throws `TypeError` | as above | open |
| api/int-beyond-int64-property | py | `10**20` is accepted, written and read back as an int | as above | by design - Core-legal, identity-unavailable (`accept`) |
| values/exponent-text | ts | the strings `1e-7`, `1E5` are written bare; py and js quote them. Both readings are the same STRING | Core corpus finding on `nan` (writer divergence), extended to exponent-looking text | open - writer divergence (ison-ts) |
| ids/plus-sign-text | ts | the string id `+1` is written bare; py and js quote it | as above | open - writer divergence (ison-ts) |
| values/unicode-escape-not-decoded | py, ts, js | `"\ud800"` and `"é"` are read as the text `ud800` and `u00e9`: `\u` is not an ISON escape and the backslash is dropped without an error | section 1.4: no document can carry a lone surrogate, so `INVALID_UNICODE_SCALAR` is reachable only through the API (`api/lone-surrogate-property`) | informational - all ports agree; not a Semantic/2 contradiction, but a silent text change |

Spec gaps found while building the corpus (not vectors, because the draft does
not decide them):

- An integer **id** beyond int64 (Python accepts `2**63`, JavaScript rounds it)
  has no named reason: `INTEGER_OUT_OF_INT64` is written for values and
  `INVALID_NODE_ID_TYPE` for ids that are neither int nor string.
- A repeated directed edge row is `INVALID_EDGE_ADDRESS` in the Core corpus;
  section 5 lists the code but does not describe this case.
