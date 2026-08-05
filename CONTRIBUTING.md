# Contributing to ISONGraph

Thanks for your interest in contributing! This monorepo hosts the ISONGraph implementations for Python, JavaScript, TypeScript, Rust, and C++, plus benchmarks. Developer tooling (VS Code extensions and related utilities) lives in separate repositories.

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
| `ison-graph-cs/` (C#, .NET 8) | `dotnet build` then `dotnet test` |
| `vscode-isongraph/` (VS Code extension) | `npm install` then `npm run compile` |
| `vscode-isongraphviz/` (VS Code extension) | `npm install` then `npm run compile` |

Benchmarks live in `benchmark/`; they call the DeepSeek API — set the `DEEPSEEK_API_KEY` environment variable before running.

## Pull Requests

1. Fork the repository and create a branch from `main`.
2. Keep changes focused: one fix or feature per PR.
3. Add or update tests for the language implementation you touch.
4. Make sure the tests for the affected directory pass locally.
5. If behavior changes, update the relevant README section.
6. Open the PR with a short description of what changed and why.

Feature parity matters: if you add a feature to one language implementation, please open an issue so it can be tracked for the others.

## Reporting Issues

Use [GitHub Issues](https://github.com/ISON-format/isongraph/issues). Include the language implementation, version, a minimal reproduction, and expected vs actual behavior.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE) that covers this project.
