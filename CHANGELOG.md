# Changelog

All six ISONGraph ports — Python, JavaScript, TypeScript, Rust, C#, C++ —
share this file and, from 1.3.0, a single version number.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] — unreleased

Rust, C# and C++ change their property API. Those three stored every value
as a string, so they serialized differently from Python, JS and TS - one
graph produced two different documents depending on which language wrote
it. They now use their parser's own value type.

### Changed — breaking (Rust, C#, C++ only)

- **Properties carry types.** `HashMap<String, String>` becomes
  `HashMap<String, ison_rs::Value>`, `Dictionary<string, string>` becomes
  `Dictionary<string, object?>`, and `map<string, string>` becomes
  `map<string, ison::Value>`. Not a new union - the parser already models
  exactly the types the format has, and keeping a second one beside it is
  what caused the split.

  ```
  # 1.3.0 (Rust, C#, C++)      # 1.4.0 - matching Python/JS/TS
  nodes.company                nodes.company
  id listed name staff         id listed name staff
  acme "false" "Acme" "42"     acme false "Acme Corp" 42
  ```

- **Rust callers use `props!`.** A `Vec` is homogeneous, so a literal mixing
  an int and a string cannot be written directly, and the orphan rule stops
  this crate adding `From` impls to `ison_rs::Value`. `props![("name",
  "Acme"), ("staff", 42i64)]` converts each value before collecting.
  `vec![("k", "v")]` no longer compiles for properties.

- **A number now compares as a number** in queries, rather than as a parse
  of its rendering. A string holding a number still compares numerically,
  so filters written against the old storage keep working. Schema
  validation is unchanged - it still validates the rendered text; making it
  type-aware is a separate change.

### Fixed

- The three string-only ports round-trip values without flattening them.
  Loading `42` gave back the string `"42"`, which then re-emitted quoted.

### Known limitation

- **An integral float originated in JavaScript or TypeScript cannot be
  distinguished from an integer.** `1.0 === 1` in JS, so a JS-authored
  `{weight: 1.0}` emits `1` where Python emits `1.0`. This is a property of
  the language, not of ISONGraph. Values arriving *from* ISON keep their
  form in every port; only origination is affected. The shared test fixture
  deliberately contains no integral float for this reason.

## [1.3.0] — 2026-08-31

Serialized output changes in this release. A graph written by 1.3.0 is not
byte-identical to one written by 1.2.0, and identifiers that 1.2.0 accepted
are now refused at construction. Both changes remove ways the old code lost
data silently; see **Migrating** below.

### Changed — breaking

- **Every port now emits through its ISON parser's canonical writer.** Each
  port used to hand-roll its own ISON emitter beside the parser's, so ISON
  syntax had two implementations per language that had to agree forever.
  They did not: the id column was written unquoted, so a node id containing
  a space produced output that would not reparse, and a string id like `"1"`
  came back as the integer `1`.

  Blocks now sort by `kind.name` and columns sort within a block, so `edges`
  precedes `nodes` and column order is the writer's rather than the caller's.
  Strings that would otherwise reparse as numbers are quoted, which is what
  makes the round trip lossless.

  ```
  # 1.2.0                    # 1.3.0
  nodes.person               edges.KNOWS
  id name age                since source target
  1 Alice 30                 2020 :person:1 :person:2

  edges.KNOWS                nodes.person
  source target since        id age name
  :person:1 :person:2 2020   1 30 Alice
  ```

- **Unrepresentable identifiers are refused at construction.** Node types,
  node ids and relation types may no longer be empty or contain whitespace,
  `:` or `|`; types additionally may not contain `"` or `\` because they
  become block names, which ISONL cannot quote. Property names are checked
  against a wider set — they become ISON *field* names, where a leading `#`
  turns the header into a comment and loses the whole block.

  An audit of hostile values across all three identifier positions found 18
  of 24 combinations corrupting or crashing on round trip before this change.

- **Node ids that differ only by type are refused.** A reference carries no
  type, so `1` and `"1"` both write as `:p:1`. A graph holding both was
  addressable in memory and ambiguous on the wire; the second is now
  rejected when the first exists.

- **All six ports are on one version.** Python, JS and TS were at 1.2.0;
  Rust and C# at 1.0.0; C++ untagged. `ISONGraph 1.3.0` now means the same
  code in every language.

- **C++ requires ison-cpp >= 1.1.2.** `ison_graph.hpp` includes
  `ison_parser.hpp` rather than vendoring a copy, so an ISON fix arrives on
  the next build instead of when someone re-cuts the copy. CMake takes
  `ISON_CPP_INCLUDE_DIR` and fails configuration when the header is absent;
  a header older than 1.1.2 is a compile error rather than a behavioural
  difference.

### Added

- **`ison_graph.multigraph.MultiGraph`** (Python, experimental) — parallel
  edges keyed by a stable integer, so the same relationship can be recorded
  more than once between the same pair without inventing synthetic relation
  types. Serialized output carries an `ison-graph-multigraph-v1` marker, and
  plain `ISONGraph` refuses to load it rather than silently dropping the
  parallel edges.

- **`ison_graph.structural.ProtectedGraph`** (Python, experimental) —
  refuses properties that shadow structural fields, hands properties out as
  read-only views, and seals `type`/`id`/`rel_type`/`source`/`target` so an
  object cannot report an identity the graph's indexes never used.

- **`converters`** and **`schema-generator`** packages, with the crash bugs
  found while testing them fixed.

### Fixed

- Canonical serialization is genuinely insertion-order independent. Row
  order previously depended on the order rows were added whenever the first
  column tied.
- `from_ison` resolves references against the loaded nodes instead of
  guessing that a numeric-looking id is an integer, which silently broke
  graphs with string ids like `"1"`.
- Loaders take nodes before edges regardless of block order, which the
  canonical writer changed.
- Duplicate-edge imports no longer crash the CSV and GraphML converters.
- C++ tests assert with a macro that survives `NDEBUG`. All 134 assertions
  were compiled out under CMake's Release config, so the suite reported
  every case as passing while checking nothing.

### Migrating

- **Regenerate stored `.isong`/`.isonl` files** from source data, or accept
  that 1.3.0 output differs from 1.2.0. Content-addressed caches keyed on
  the old bytes will miss once.
- **Check identifiers.** If node ids or relation types contain whitespace,
  `:` or `|`, they were already corrupting on round trip — map them to
  graph-safe values at your boundary and translate back on the way out.
- **C++ users:** put `ison_parser.hpp` on your include path.

## [1.2.0] and earlier

Released before this file existed; see the git history.
