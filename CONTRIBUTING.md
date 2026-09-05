# Contributing to ISONGraph

Thanks for your interest in contributing! This monorepo hosts the six ISONGraph implementations — Python, JavaScript, TypeScript, Rust, C#, and C++ — plus benchmarks, the converters and schema-generator packages, and the `vscode-isongraph` and `vscode-isongraphviz` extensions.

## Getting Started

```bash
git clone https://github.com/ISON-format/isongraph.git
cd isongraph
```

## Building and Testing

| Directory | Build / Test |
|-----------|--------------|
| `ison-graph/` (Python) | `pip install -e ".[dev]"` then `pytest` |
| `ison-graph-js/` (JavaScript) | `npm install` then `npm test` |
| `ison-graph-ts/` (TypeScript) | `npm install` then `npm run build && npm test` |
| `ison-graph-rs/` (Rust, crate `ison-graph`) | `cargo build` then `cargo test` |
| `ison-graph-cpp/` (C++, header-only) | `cmake -B build && cmake --build build` then `ctest --test-dir build` |
| `converters/` (Python) | `pip install -e .` then `pytest` |
| `schema-generator/` (Python) | `pip install -e .` then `pytest` |
| `ison-graph-cs/` (C#, .NET 8) | `dotnet build` then `dotnet test` |
| `vscode-isongraph/` (VS Code extension) | `npm install` then `npm run compile` |
| `vscode-isongraphviz/` (VS Code extension) | `npm install` then `npm run compile` |

`ison-graph-cpp` includes `ison_parser.hpp` from ison-cpp rather than vendoring a copy, so it needs an [ison](https://github.com/ISON-format/ison) checkout beside this one. CMake looks for a sibling `ison/` by default; point it elsewhere with `-DISON_CPP_INCLUDE_DIR=<path to ison-cpp/include>`.

Benchmarks live in `benchmark/`; they call the DeepSeek API — set the `DEEPSEEK_API_KEY` environment variable before running.

## Pull Requests

1. Fork the repository and create a branch from `main`.
2. Keep changes focused: one fix or feature per PR.
3. Add or update tests for the language implementation you touch.
4. Make sure the tests for the affected directory pass locally.
5. If behavior changes, update the relevant README section.
6. Open the PR with a short description of what changed and why.

Feature parity matters: if you add a feature to one language implementation, please open an issue so it can be tracked for the others.

## Releases

From 1.3.0 the six ports share one version number, so a release is **one
unprefixed tag covering all of them**: `vX.Y.Z`. There are no per-package
tags. `npm-v1.1.0` predates the shared version and is kept only as history.

A breaking change ships as a minor bump — 1.3.0 and 1.4.0 both broke API or
output, and neither took a major.

Before tagging, every version must already agree: `ison-graph/pyproject.toml`
and `src/ison_graph/__init__.py`, both `package.json` files,
`ison-graph-rs/Cargo.toml`, `IsonGraph.csproj`, and
`ison-graph-cpp/CMakeLists.txt`. Date the `CHANGELOG.md` entry in the same
commit.

Then tag, release, and publish — in that order:

1. `git tag -a vX.Y.Z <commit> -m "ISONGraph X.Y.Z"` and push the tag.
2. Publish the GitHub release for it. This fires `publish-pypi` on its
   `release` trigger.
3. Dispatch the rest **against the tag**, not `main`:
   `gh workflow run publish-crates.yml --ref vX.Y.Z` (likewise
   `publish-npm.yml -f package=both` and `publish-nuget.yml`).

The workflows do a bare `actions/checkout@v4` with no ref, so they publish
whatever ref they are dispatched on. Dispatching on `main` publishes
whatever `main` happens to be at that moment, which is only the tested tree
if nothing has merged since.

Tag before publishing, because the order is reversibility: a tag nobody has
fetched can be moved, while a version on crates.io, npm, NuGet or PyPI is
permanent. `cargo publish` has no `--skip-existing` and hard-fails on a
version that exists, so a bad release costs a patch bump, not a retry.

Note that `twine upload --skip-existing` and `dotnet nuget push
--skip-duplicate` both succeed *without uploading* when the version is
already there. A green job is not evidence that anything was published —
check the registry.

## Reporting Issues

Use [GitHub Issues](https://github.com/ISON-format/isongraph/issues). Include the language implementation, version, a minimal reproduction, and expected vs actual behavior.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE) that covers this project.
