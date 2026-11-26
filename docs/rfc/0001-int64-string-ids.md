# RFC 0001: INT64 | STRING node ids in the Rust, C# and C++ ports

Status: **DRAFT proposal** (not accepted, nothing implemented)
Date: 2026-11-26
Baseline examined: `main` at `ce9d3b7` (ISONGraph 1.4.1)
Affects: `ison-graph-rs`, `ison-graph-cs`, `ison-graph-cpp`; touches the conformance corpus and, if accepted, the next shared release (1.5.0).

## 1. Problem

Python, JavaScript and TypeScript model a node id as an **integer or a string**
(`int | str`, `number | string`) and keep the two apart: `1` and `"1"` are
different ids, a document writes them differently (`1` vs `"1"`), and 1.4.1
refuses the pair as twins. Rust, C# and C++ model an id as **a string only**
(`String`, `string`, `std::string`).

The draft graph-identity contract (ISONGraph-Semantic/2, section 7, "Open
before freeze") says that, left as it is, the *same ISON file* has a different
semantic identity depending on which port read it. This RFC checks that claim
against the source and the behaviour of the three ports, lays out the options,
and recommends one.

Non-goals: this RFC does not propose any code; it does not define the digest
encoding; it does not change what Python, TS and JS accept except where
section 7 says so.

## 2. What the three ports do today

Verified by running each port at `ce9d3b7` on the inputs below (Rust:
`ison-graph` 1.4.1 with `ison-rs` 1.2.0; C#: `IsonGraph` 1.4.1 with
`Ison.Parser` 1.2.0; Python, TS, JS: the 1.4.1 sources with ison-py, ison-ts,
ison-parser 1.2.0). **C++ was read, not run**: no C++ toolchain was available
and `ison-cpp` was not checked out, so every C++ statement below is from
`ison_graph.hpp` only.

Document -> what each port holds and writes back (the id column):

| input id column | Python / TS / JS | Rust, C# (run) | C++ (source) |
|---|---|---|---|
| `1`, `2` (integers) | INT64 ids; written back as `1`, `2` | STRING ids `"1"`, `"2"`; written back as `"1"`, `"2"` | STRING; `std::to_string`; written as a string |
| `"1"`, `"2"` | STRING; written `"1"` | STRING; written `"1"` | same |
| `1` and `"1"` together | rejected (`DuplicateNodeError`) | rejected (same string key) | rejected (same string key) |
| `-1` | INT64 | STRING `"-1"` | STRING |
| `7` and `"007"` together | **rejected** as twins (see 5.3) | accepted: two ids `"7"`, `"007"` | accepted |
| `1.5` | rejected (`InvalidIdentifierError`) | **accepted** as STRING `"1.5"` | accepted as `std::to_string(1.5)`, i.e. `"1.500000"` (source) |
| `true` | rejected | **accepted** as STRING `"true"` | accepted as `"true"` (source) |
| `9223372036854775807` | INT64 | STRING `"9223372036854775807"` | STRING |
| `9223372036854775808` | Python: int (out of int64); TS/JS: rounded number | Rust: parsed as a float, id becomes `"9223372036854776000"`; C#: `"9223372036854775808"` exact | STRING (source) |
| `+1` | the string `+1` | Rust: parsed as the integer 1, id `"1"`; C#: string `"+1"` | depends on `ison-cpp` (not checked) |

So, concretely:

1. A Python-written document with integer ids is **retyped** by Rust and C#:
   `INT64(1)` becomes `STRING("1")`, and the port writes `"1"`. A
   Python -> Rust -> Python round trip silently changes every integer id into a
   string id. The claim in section 7 of the draft is correct, and the effect is
   not limited to digests: it changes the bytes the port itself writes.
2. These three ports also do not carry the other 1.4.1 id checks (float and
   boolean ids are accepted; there is no twin test at all because `1` and `"1"`
   can never be distinct in a `string`). The id typing question is therefore
   bundled with an id *validation* gap.
3. The retyping is not only about ids. The three ISON parsers differ on
   numbers: `+1` and `1e-7` are strings in ison-py/ts/js (and `1e-7` in C#), but
   `+1` is an integer and `1e-7` a float in ison-rs. Making ids typed does not,
   by itself, make a document mean the same thing in every port.

Source facts behind the table (all at `ce9d3b7`):

- **Rust** (`ison-graph-rs/src/lib.rs`): `pub type NodeRef<'a> = (&'a str, &'a str)`;
  `pub struct NodeId { node_type: String, id: String }` deriving
  `Debug, Clone, PartialEq, Eq, Hash` (and `Serialize/Deserialize` with the
  `serde` feature); `pub struct Node { node_type, id: String, properties }`;
  `add_node(&mut self, &str, &str, Vec<(&str, Value)>)`; `get_node`, `has_node`,
  `remove_node`, `update_node` take `&str` ids; the writer emits
  `IsonValue::String(node.id)` for every id; the reader's `id_text` turns
  `Int`, `Float`, `Bool` and `Reference` into text. Roughly 71 mentions of
  `NodeRef`/`NodeId` in `lib.rs` and 17 in `query.rs`; `schema.rs` has none.
- **C#** (`ison-graph-cs/src/IsonGraph`): `readonly record struct NodeRef(string Type, string Id)`
  (value equality and hashing on the two strings); `Node.Id` is `string`;
  `AddNode(string, string, ...)`, `GetNode(string, string)` and the `NodeRef`
  overloads; the writer sets `["id"] = node.Id`; the reader's `IdText` calls
  `value.ToString()` (not checked for culture sensitivity). `NodeRef` appears 82
  times in `IsonGraph.cs`, 19 in `Query.cs`, 11 in `Viz.cs`, 4 in
  `Serialization.cs`, 3 in `Schema.cs`.
- **C++** (`ison-graph-cpp/include`): `struct NodeRef { std::string type, id; }`
  with `operator==` and a lexicographic `operator<` on the strings;
  `NodeRefHash` hashes `type + ":" + id`; `Node.id` is `std::string`;
  properties are `std::map<std::string, ison::Value>` (already typed); the
  writer sets `row["id"] = ison::Value(node.id)`. 87 mentions of `NodeRef` in
  `ison_graph.hpp`, 20 in `isonql.hpp`, 1 in `isongraphantic.hpp`.
- Property values are already typed in all three ports (changed in 1.4.0), so
  ids are the one remaining string-typed value.

## 3. Options

### Option A - give the three ports `INT64 | STRING` ids (the draft's preference)

An id becomes a sum type: Rust `enum NodeKey { Int(i64), Str(String) }` (or
equivalent), C# a small `readonly record struct`/union around `long` or
`string`, C++ `std::variant<std::int64_t, std::string>`. Everything that holds
or compares an id changes type. Matches Semantic/2 section 0 and 1.5 exactly;
it is the only option under which the three ports can be `FULL`.

**API impact.**
- *Rust*: `NodeRef<'a>` stops being `(&str, &str)`; `NodeId.id`, `Node.id`
  change type; `add_node`, `get_node`, `has_node`, `remove_node`, `update_node`,
  every `add_edge`/`neighbors`/`multi_hop`/`shortest_path` call and the ISONQL
  result types take the new type; `Eq`/`Hash`/`Ord` must include the variant;
  the `serde` shape of `NodeId` and `Node` changes (a stored JSON graph no
  longer deserializes without a shim). Breaking at compile time for essentially
  every caller.
- *C#*: `NodeRef.Id` and `Node.Id` change type; every `AddNode`/`GetNode`/
  `NodeRef` construction with a string literal breaks unless an implicit
  conversion is provided; record equality follows the new field.
- *C++*: `NodeRef::id`, `Node::id` change type; `operator==`, `operator<`
  (today string order; Semantic/2 section 2.3 wants INT64 before STRING and
  numeric order) and `NodeRefHash` change; `isonql.hpp` parses ids from query
  text and must follow.
- *Parser*: stop stringifying `Int` ids; refuse `Float`, `Bool`, `Null` ids
  (parity with 1.4.1); decide ids beyond int64 (today's behaviour differs per
  port, and the draft names no reason code for an integer *id* beyond int64).
- *Serializer*: write an integer id as an integer (unquoted), a string id quoted
  as needed; the canonical bytes of a directed all-string graph do not change.
- *Equality/hash*: include the discriminant; add the twin test (`1`/`"1"`,
  `-1`/`"-1"`) so that reference text `:p:1` resolves to exactly one id.

**Migration path.** Core 1.5.0, all six ports (the shared version already ships
breaking changes as minor bumps, per CONTRIBUTING). For Rust this is the weak
point: crates.io consumers on `^1.4` would pick up a compile-breaking 1.5.0.
Either accept that on the strength of the repo's policy, or hold the removals
for 2.0 and use deprecation in 1.5 (that is Option C).

**Corpus and receipts.** The Rust/C#/C++ columns of the Core corpus are `todo`
because no runner exists. A runner written today would observe `defect` on
`ids/positive-int`, `ids/negative-int` and `ids/int64-extremes` (the loaded
graph's identity differs from the document's, not merely its bytes), on
`ids/float-id` and `ids/bool-id` (accepted where Python/TS/JS reject), and
would diverge on the semantic corpus' `ids/leading-zero-not-twin`. Their
posture would be `KNOWN_DEFECT`. Under A those cells become `pass`, the posture
`FULL`, and no receipt schema change is needed.

**Downstream consumers.** Anything that reads ids from these ports as `String`
must adapt once. In return, a Python-produced graph keeps its identity when a
Rust, C# or C++ program loads and re-saves it, and cross-port identity
equivalence becomes admissible for integer-id graphs. (Whether a given
downstream consumer, such as ISONGraph Visualize, depends on string-typed ids
from these ports was **not checked**.)

**Risks.** A source-breaking change to three public APIs at once;
the ISON parsers underneath still disagree about numeric tokens (finding 3
above), so typed ids need a parser-side guard rather than trust; the C++ side
could not be run during this analysis.

### Option B - declare `id_typing: string-only` for the three ports

Two readings, which have very different safety properties.

**B1 - declare today's behaviour.** Semantic/2 treats every id read by these
ports as STRING. No port code changes.
- *Identity*: the same document has two identities: INT64(1) from Python/TS/JS,
  STRING("1") from Rust/C#/C++. A graph that crosses ports with integer ids
  changes identity silently, and the port writes `"1"` for what was `1`. Float
  and boolean ids (accepted today as `"1.5"`, `"true"`) become valid STRING ids
  in those ports while being out of domain in the other three.
- *Admission postures*: needs a new declared field (`id_typing`) in the Core
  Conformance Receipt and in whatever binds to it, and a rule that
  cross-port equivalence is inadmissible when either side is string-only *and*
  the artifact has an integer id. That rule needs an artifact-level domain
  classification ("does this document contain an integer id column?") which
  today exists only as the corpus' per-vector `semantic` verdict. This is a
  contract change for every consumer of the receipt.
- *Corpus*: cells for the integer-id vectors stay `defect` forever, or the
  corpus grows an `id_typing` concept to excuse them.

**B2 - declare string-only and refuse integer ids.** The three ports reject a
document with an integer id column (`reject:` an id-typing error), and keep
accepting only string ids (plus the 1.4.1 checks for float and boolean ids).
- *Identity*: every identity these ports can ever produce is STRING-only and no
  retyping can happen silently: a document either has an identity there or it
  is refused loudly.
- *API impact*: none for callers that already use string ids; a behaviour
  change (error) for callers that load integer-id files. Small code: a check in
  each reader.
- *Corpus*: integer-id cells become `reject:<Name>` with a Findings row each
  (the corpus rule for rejecting an identifiable vector), posture
  `KNOWN_DEFECT` as long as the port cannot load the graph Python's README
  example produces first.
- *Downstream*: these ports cannot process most graphs produced by the three
  reference ports, because integer ids are the natural choice there. This
  turns a silent hazard into a hard limit rather than removing it.

**Risks of B overall.** It is permanent: every future receipt, binding and
cross-port statement carries the exception; it leaves Semantic/2 section 0
("the same file must have one identity") false for half of the six ports.

### Option C - additive tagged ids (A's semantics, without A's API break)

Keep the string as the id's canonical spelling and add its kind beside it:
`id` stays `String`/`string`/`std::string` (the canonical spelling, `-?[0-9]+`
for an integer), and a new kind (`Int` | `Str`, default `Str`) is stored with
it. Identity is `(type, kind, spelling)`; the writer emits an `Int` id
unquoted; the reader keeps `Int` for an integer token, `Str` for a quoted or
non-integer one; float, boolean and non-int64 ids are refused as in 1.4.1.

The lookup rule that makes this additive is **ID-TWIN-INVARIANT**: a graph
cannot hold `1` and `"1"` together, so lookup by spelling is unambiguous.
`get_node("p", "1")`, `add_edge` with `("p", "1")` and ISONQL patterns keep
working with the existing `&str`/`string` arguments and resolve to whichever
kind holds that spelling, exactly as `:p:1` references already resolve against
the node table in Python (`_resolve_ref`) and TS/JS.

**API impact.** Rust: `NodeRef<'a>`, `add_node`, `get_node` and friends keep
their signatures; new constructors for typed ids (`NodeId::int`, `add_node_int`
or an `impl Into` argument); a `kind` field added to `NodeId` and `Node`, which
breaks only code that builds those structs by literal (`NodeId::new`/`Node::new`
are unchanged and default to `Str`); `serde` gets `#[serde(default)]` on the new
field so stored graphs still load. C#: `NodeRef(string, string)` keeps its
constructor; an optional kind; equality now includes it. C++: same, with a
defaulted `kind` member in `NodeRef` and `Node` and the comparison/hash updated.
Nothing else in the three public surfaces has to change.

**Behaviour changes** (all of them observable, none of them source-breaking):
integer id tokens now load as `Int` instead of `Str` (and so are written back
unquoted, which is the original document); float, boolean and out-of-range ids
now error; `7` and `"007"` stay distinct.

**Migration path.** Core 1.5.0 with a CHANGELOG note under a breaking/behaviour
heading (the repo's "no breaking change without a note" rule), because the
loaded type of an integer id changes even though signatures do not. An enum id
type (Option A proper) can follow in 2.0 if wanted, with 1.5 deprecating the
string-only constructors.

**Corpus and receipts.** Same end state as A: integer-id cells go from `defect`
to `pass`, postures from `KNOWN_DEFECT` to `FULL`, no schema change.

**Downstream.** The least disruptive route to an identity-preserving port: code
that treats ids as strings keeps compiling; code that needs to know the kind
can read it.

**Risks.** Two representations of "the id" live side by side until 2.0 (the
spelling and the kind), so a careless comparison on the spelling alone can
collapse `Int` and `Str` in code that bypasses the new equality; the twin
invariant must hold in every entry point (constructor, loader, `update_node`,
deserialization) because lookup correctness depends on it; ordering must follow
Semantic/2 section 2.3, not string order, wherever a canonical order is needed.

## 4. Comparison

| | A | B1 | B2 | C |
|---|---|---|---|---|
| same file -> same identity in all six ports | yes | **no** | yes, by refusing | yes |
| silent retyping removed | yes | **no** | yes (loud error) | yes |
| source break for Rust/C#/C++ callers | large | none | none | small (struct literals only) |
| three ports can reach `FULL` | yes | no (declared exception) | no (cannot load integer-id graphs) | yes |
| receipt/binding schema change | none | **new field + rule** | none (cells are `reject:`) | none |
| work | highest | none now, cost forever | low | medium |

## 5. Related findings that the decision should absorb

1. The three ports do not run the 1.4.1 id checks (float/bool ids accepted).
   Any option should include them.
2. The ISON parsers underneath disagree on numeric tokens (`+1`, `1e-7`, an
   integer beyond int64). Typed ids do not make a document portable until the
   parser behaviour is pinned by the corpus (the semantic corpus records the
   Python/TS/JS side).
3. Python, TS and JS currently decide twins by `int(text)`, so `7` and `"007"`
   are refused although the draft defines twins by canonical spelling and
   Rust/C#/C++ happen to accept the pair. If the three ports adopt typed ids,
   the twin test should be the spelling-based one in all six in the same
   release, or the ports will diverge in the other direction.
4. No reason code in the draft covers an integer *id* beyond int64.

## 6. Recommendation

Adopt **Option C as the route to Option A's identity guarantees**, in this
order:

1. Give Rust, C# and C++ corpus runners (Core corpus and semantic corpus) with
   the cells they have today, `defect` where the document's identity is
   changed. This makes the divergence visible in CI and gives a measurable
   target; it needs no library change.
2. Implement the kind-tagged id with spelling-based lookup in the three ports,
   with the 1.4.1 id checks, in one PR per port, and flip the cells to `pass`.
3. Ship it as Core 1.5.0 with a CHANGELOG note under a behaviour-change
   heading. Decide separately whether to introduce an enum id type in 2.0.
4. Align the twin rule across all six ports to the canonical-spelling
   definition in the same release.

Reasoning. Semantic/2 section 0 requires that a document have one identity
whatever port reads it; that rules out B1, and B2 meets the letter of the rule
while excluding Rust, C# and C++ from the main use case (integer ids are what
the reference ports' examples use). Between A and C the end state is the same;
C reaches it without making every caller of three public APIs change at once,
and without handing crates.io consumers a compile-breaking 1.5.0 under a `^1.4`
requirement. If the maintainers prefer the enum type for its type safety, A is
a defensible variant; the sequence above (corpus first) is the same.

B2 is the fallback if the three ports cannot be changed in time: refusing
integer ids is honest, B1 is not.

## 7. What was verified and what was not

Verified by running code: Python, TS and JS behaviour (the semantic corpus
branch records it as vectors); Rust and C# behaviour for every row marked "run"
in section 2 (a small throwaway program per port that loads each document,
writes it back and reloads it); the absence of any twin or id-type check in the
three ports (read the source and ran the probes).

Verified by reading source only: everything about C++; the API surface
inventory (type definitions, which functions take ids, mention counts).

Not verified: C++ behaviour at runtime; the Rust/C#/C++ test suites at this
commit (not run for this RFC); `ison-cpp`'s numeric tokenisation; the
culture-sensitivity of C#'s `IdText`; whether any downstream consumer relies on
string-typed ids from these ports; how the receipt consumers would implement the
`id_typing` field in B1; the effort in person-days of any option.
