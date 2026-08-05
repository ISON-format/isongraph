<p align="center">
  <img src="../../logo/ison_graph_logo_stretch.png" alt="ISONGraph Logo">
</p>

# ISONGraph Data Traversal Benchmark

A comprehensive benchmark suite testing **ISONGraph's graph traversal and analysis capabilities** against other serialization formats.

## Overview

This benchmark evaluates how well Large Language Models (LLMs) can perform graph operations (traversal, path finding, analysis) when graph data is presented in different serialization formats. Unlike the Knowledge Graph Benchmark which tests comprehension across 10 formats, this benchmark focuses on **core graph operations** with 5 formats.

### Key Results

| Metric | ISONGraph | Best Alternative | Improvement |
|--------|-----------|------------------|-------------|
| **Token Efficiency** | 639 tokens | ISON (685) | 7% fewer |
| **Accuracy** | 92.0% | ISON (88.0%) | +4% |
| **Efficiency Score** | 143.97 Acc/1K | ISON (128.47) | **12% better** |

## Benchmark Focus

This benchmark specifically tests:

1. **Multi-hop Traversal** - Friends of friends, N-hop reachability
2. **Path Finding** - Shortest path, path existence, hop counting
3. **Graph Analysis** - Connectivity, cycles, node/edge counts
4. **Relationship Patterns** - follows, knows, works_at, reports_to

## Formats Tested

| Format | Description | Token Count | Accuracy |
|--------|-------------|-------------|----------|
| **ISONGraph** | Graph-native ISON format | 639 | 92.0% |
| **ISON** | Base ISON tabular format | 685 | 88.0% |
| **TOON** | Token-Optimized Object Notation | 856 | 80.0% |
| **JSON Compact** | Minified JSON | 1,072 | 82.0% |
| **JSON** | Standard indented JSON | 2,039 | 84.0% |

## Quick Start

### Prerequisites

```bash
pip install tiktoken requests toon
pip install -e ../ison-py
pip install -e ../ison-graph
```

### Running the Benchmark

```bash
# Token counting + unit tests (no API calls)
python benchmark_graph.py

# Unit tests only
python benchmark_graph.py --unit-tests

# Full benchmark with LLM accuracy testing
python benchmark_graph.py --full
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `--skip-llm` | Skip LLM API calls, only count tokens |
| `--full` | Run complete benchmark with LLM accuracy testing |
| `--unit-tests` | Run ISONGraph unit tests only |

## Benchmark Structure

### Datasets (4 domains, 50 questions)

| Dataset | Questions | Description |
|---------|-----------|-------------|
| Social Network | 15 | Users with follows relationships, cycles |
| Knowledge Graph | 15 | Companies, people, products with various relations |
| Organization Chart | 10 | Hierarchical structure (DAG - no cycles) |
| Flight Routes | 10 | Cities connected by flights with distances |

### Question Categories

| Category | Count | Description |
|----------|-------|-------------|
| Single-hop | 15 | Direct neighbor queries |
| Multi-hop | 10 | Friends of friends, reachability |
| Analysis | 20 | Connectivity, cycles, degrees, counts |
| Path Finding | 5 | Shortest path, path existence |

## Unit Tests

The benchmark includes comprehensive unit tests for ISONGraph functionality:

1. **Basic Operations** - Node/edge CRUD
2. **Multi-hop Traversal** - 1-hop, 2-hop, N-hop queries
3. **Shortest Path** - BFS-based path finding
4. **Cycle Detection** - Graph cycle detection
5. **Connectivity** - Connected component checking
6. **Serialization** - ISON roundtrip
7. **Query Patterns** - Mini-query language
8. **Fluent API** - Chained traversal calls

## Results

See [BENCHMARK.md](BENCHMARK.md) for detailed results and analysis.

### Summary Table

| Rank | Format | Tokens | Accuracy | Acc/1K |
|------|--------|--------|----------|--------|
| 1 | **ISONGraph** | 639 | **92.0%** | **143.97** |
| 2 | ISON | 685 | 88.0% | 128.47 |
| 3 | TOON | 856 | 80.0% | 93.46 |
| 4 | JSON Compact | 1,072 | 82.0% | 76.49 |
| 5 | JSON | 2,039 | 84.0% | 41.20 |

## Configuration

### API Configuration

The benchmark uses the DeepSeek API. Set the `DEEPSEEK_API_KEY` environment variable before running:

```bash
export DEEPSEEK_API_KEY="your-api-key"   # Windows PowerShell: $env:DEEPSEEK_API_KEY = "your-api-key"
```

### Tokenizer

Uses `tiktoken` with the `o200k_base` encoding (GPT-4o/GPT-5 tokenizer).

## Output Files

After running, the benchmark generates:

- `benchmark_graph_YYYYMMDD_HHMMSS.log` - Timestamped detailed log
- `benchmark_graph_latest.log` - Latest run log (overwritten each run)

## Why ISONGraph Excels at Traversal

1. **Explicit Edge Sections**: `edges.FOLLOWS`, `edges.REPORTS_TO` make relationship types clear
2. **Reference Syntax**: `:person:1` notation enables precise node identification
3. **Graph-Native Structure**: Unlike flat JSON, ISONGraph preserves graph topology
4. **LLM-Friendly**: Tabular format is easier for LLMs to parse and reason about

### Traversal Example

**ISONGraph (119 tokens):**
```
nodes.person
id name age verified
1 Alice 28 true
2 Bob 34 false
3 Carol 29 true

edges.FOLLOWS
source target since
:person:1 :person:2 2020
:person:1 :person:3 2021
:person:2 :person:3 2019
```

**JSON (411 tokens):**
```json
{
  "nodes": [
    {"id": 1, "type": "person", "name": "Alice", "age": 28, "verified": true},
    ...
  ],
  "edges": [
    {"source": 1, "target": 2, "relation": "follows", "since": 2020},
    ...
  ]
}
```

**Token Savings: 71%**

## Comparison with Knowledge Graph Benchmark

| Aspect | DataTraversal Benchmark | KnowledgeGraph Benchmark |
|--------|------------------------|--------------------------|
| **Focus** | Graph operations | Format comprehension |
| **Questions** | 50 | 100 |
| **Formats** | 5 (core) | 10 (comprehensive) |
| **Best Accuracy** | 92.0% (ISONGraph) | 90.0% (ISONGraph) |
| **Best Efficiency** | 143.97 Acc/1K | 53.00 Acc/1K |

## Related Benchmarks

- [Knowledge Graph Benchmark](../KnowledgeGraph_Benchmark/) - 100 questions, 10 formats

## License

MIT License - See LICENSE file for details.

## Author

Mahesh Vaikri

## Links

- [ISONGraph Repository](https://github.com/ISON-format/isongraph)
- [ISON Format Specification](https://www.ison.dev)
- [Benchmark Results](BENCHMARK.md)
