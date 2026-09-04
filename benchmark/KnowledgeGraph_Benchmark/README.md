<p align="center">
  <img src="../../logo/ison_graph_logo_stretch.png" alt="ISONGraph Logo">
</p>

# ISONGraph Knowledge Graph Benchmark

A comprehensive benchmark suite comparing **ISONGraph** against all major graph serialization formats for LLM comprehension and token efficiency.

## Overview

This benchmark evaluates how well Large Language Models (LLMs) can understand and answer questions about graph data when presented in different serialization formats. The key insight: **format matters significantly** for both token efficiency and LLM accuracy.

### Key Results

| Metric | ISONGraph | Best Alternative | Improvement |
|--------|-----------|------------------|-------------|
| **Token Efficiency** | 1,698 tokens | ISON (1,976) | 14% fewer |
| **Accuracy** | 90.0% | Cypher (89.0%) | +1% |
| **Efficiency Score** | 53.00 Acc/1K | ISON (44.53) | **19% better** |

## Formats Tested

| Format | Description | Token Efficiency | LLM Optimized |
|--------|-------------|------------------|---------------|
| **ISONGraph** | Token-efficient property graph format | Highest | Yes |
| **ISON** | Base ISON tabular format | Very High | Yes |
| **JSON Compact** | Minified JSON | Medium | No |
| **TOON** | Token-Optimized Object Notation | Medium | Yes |
| **Cypher** | Neo4j's query language format | Medium | No |
| **GML** | Graph Modelling Language | Low | No |
| **RDF/Turtle** | W3C linked data standard | Low | No |
| **JSON** | Standard JSON with indentation | Low | No |
| **JSON-LD** | JSON for Linked Data | Very Low | No |
| **GraphML** | XML-based graph format | Lowest | No |

## Quick Start

### Prerequisites

```bash
pip install tiktoken requests toon
pip install -e ../ison-py
pip install -e ../ison-graph
```

### Running the Benchmark

```bash
# Token counting only (fast, no API calls)
python benchmark_kg_100.py --skip-llm

# Quick test with core formats
python benchmark_kg_100.py --skip-llm --quick

# Full benchmark with all 10 formats
python benchmark_kg_100.py --full --formats all

# Test specific formats
python benchmark_kg_100.py --full --formats ISONGraph JSON Cypher TOON
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `--skip-llm` | Skip LLM API calls, only count tokens |
| `--full` | Run complete benchmark with LLM accuracy testing |
| `--quick` | Test only core formats (ISONGraph, ISON, JSON Compact, JSON) |
| `--formats` | Specify which formats to test |

## Benchmark Structure

### Datasets (7 domains, 100 questions)

| Dataset | Questions | Description |
|---------|-----------|-------------|
| Social Network | 15 | Users, follows relationships, cycles |
| Knowledge Graph | 15 | Companies, people, products |
| Organization Chart | 15 | Hierarchical reporting structure (DAG) |
| Flight Routes | 15 | Cities, flights, distances |
| Movie Database | 15 | Movies, actors, directors, genres |
| E-Commerce | 15 | Customers, orders, products |
| Academic Citations | 10 | Papers, authors, citations |

### Question Categories

| Category | Count | Description |
|----------|-------|-------------|
| Single-hop | 33 | Direct neighbor queries |
| Multi-hop | 21 | Friends of friends, reachability |
| Analysis | 23 | Connectivity, cycles, degrees |
| Aggregation | 13 | Counts, sums, averages |
| Path Finding | 9 | Shortest path, path existence |
| Pattern | 1 | Complex relationship patterns |

## Results

See [BENCHMARK.md](BENCHMARK.md) for detailed results and analysis.

### Summary Table

| Rank | Format | Tokens | Savings | Accuracy | Acc/1K |
|------|--------|--------|---------|----------|--------|
| 1 | **ISONGraph** | 1,698 | 68.6% | **90.0%** | **53.00** |
| 2 | ISON | 1,976 | 63.4% | 88.0% | 44.53 |
| 3 | JSON Compact | 2,893 | 46.5% | 88.0% | 30.42 |
| 4 | TOON | 2,934 | 45.7% | 85.0% | 28.97 |
| 5 | Cypher | 3,522 | 34.9% | 89.0% | 25.27 |
| 6 | GML | 4,202 | 22.3% | 86.0% | 20.47 |
| 7 | JSON | 5,406 | 0.0% | 87.0% | 16.09 |
| 8 | RDF/Turtle | 4,166 | 22.9% | 58.0% | 13.92 |
| 9 | JSON-LD | 8,191 | -51.5% | 86.0% | 10.50 |
| 10 | GraphML | 9,093 | -68.2% | 87.0% | 9.57 |

## Configuration

### API Configuration

The benchmark uses the DeepSeek API by default. Set the `DEEPSEEK_API_KEY` environment variable before running:

```bash
export DEEPSEEK_API_KEY="your-api-key"   # Windows PowerShell: $env:DEEPSEEK_API_KEY = "your-api-key"
```

### Tokenizer

Uses `tiktoken` with the `o200k_base` encoding (GPT-4o/GPT-5 tokenizer) for accurate token counting.

## Output Files

After running, the benchmark generates:

- `benchmark_kg100_YYYYMMDD_HHMMSS.log` - Timestamped detailed log
- `benchmark_kg100_latest.log` - Latest run log (overwritten each run)

## Understanding the Metrics

### Token Efficiency
Lower token count = less context window usage = more room for conversation/results.

**ISONGraph uses 68.6% fewer tokens than JSON** - meaning you can fit 3x more graph data in the same context window.

### Accuracy
Percentage of questions answered correctly by the LLM given the graph data.

**ISONGraph achieves 90% accuracy** - the highest among all formats tested.

### Efficiency Score (Acc/1K)
Accuracy per 1000 tokens - combines both metrics into a single efficiency measure.

**ISONGraph: 53.00 Acc/1K** - nearly 2x better than the next best alternative.

## Why ISONGraph Wins

1. **Tabular Format**: Column headers appear once, not repeated per row
2. **Reference Syntax**: Uses `:type:id` instead of verbose JSON object nesting
3. **No Redundant Keys**: Eliminates `"nodes":`, `"edges":`, `"properties":` wrappers
4. **Whitespace Delimited**: Spaces instead of `{`, `}`, `:`, `,` characters
5. **Human Readable**: LLMs can parse and understand the structure easily

### Format Comparison Example

**JSON (596 tokens):**
```json
{
  "nodes": [
    {"id": 1, "type": "person", "name": "Alice", "age": 28},
    {"id": 2, "type": "person", "name": "Bob", "age": 34}
  ],
  "edges": [
    {"source": 1, "target": 2, "relation": "follows", "since": 2020}
  ]
}
```

**ISONGraph (177 tokens):**
```
edges.FOLLOWS
since source target
2020 :person:1 :person:2

nodes.person
id age name
1 28 Alice
2 34 Bob
```

**Token Savings: 70.3%**

## Related Benchmarks

This benchmark is part of the ISONGraph benchmark suite:

| Benchmark | Focus | Questions | Formats | Best Acc/1K |
|-----------|-------|-----------|---------|-------------|
| **Knowledge Graph** (this) | Format comparison | 100 | 10 | 53.00 |
| [Data Traversal](../DataTraversal_Benchmark/) | Graph operations | 50 | 5 | 143.97 |

### Benchmark Comparison

| Aspect | Knowledge Graph | Data Traversal |
|--------|----------------|----------------|
| **Purpose** | Compare all graph formats | Test traversal capabilities |
| **Formats** | 10 (comprehensive) | 5 (core) |
| **Questions** | 100 | 50 |
| **ISONGraph Accuracy** | 90.0% | 92.0% |
| **Key Insight** | ISONGraph beats all competitors | ISONGraph excels at multi-hop |

## License

MIT License - See LICENSE file for details.

## Author

Mahesh Vaikri

## Links

- [ISONGraph Repository](https://github.com/ISON-format/isongraph)
- [ISON Format Specification](https://www.ison.dev)
- [Benchmark Results](BENCHMARK.md)
- [Data Traversal Benchmark](../DataTraversal_Benchmark/)
