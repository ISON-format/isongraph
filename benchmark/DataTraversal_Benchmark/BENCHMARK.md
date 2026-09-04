<p align="center">
  <img src="../../logo/ison_graph_logo_stretch.png" alt="ISONGraph Logo">
</p>

# ISONGraph Data Traversal Benchmark Results

**Date:** December 27, 2025
**Tokenizer:** o200k_base (GPT-4o/GPT-5)
**LLM:** DeepSeek Chat
**Questions:** 50
**Formats Tested:** 5

---

## Executive Summary

ISONGraph demonstrates **exceptional performance** in graph traversal tasks:

- **Highest Accuracy:** 92% (vs. 88% for second-best ISON)
- **Best Token Efficiency:** 68.7% savings vs JSON
- **Best Overall Efficiency:** 143.97 Acc/1K tokens (12% better than next)

---

## Token Efficiency Results

Lower token count means more efficient use of LLM context windows.

### Overall Token Counts

| Rank | Format | Total Tokens | Savings vs JSON | Relative Size |
|:----:|--------|-------------:|----------------:|--------------:|
| 1 | **ISONGraph** | **639** | **68.7%** | 0.31x |
| 2 | ISON | 685 | 66.4% | 0.34x |
| 3 | TOON | 856 | 58.0% | 0.42x |
| 4 | JSON Compact | 1,072 | 47.4% | 0.53x |
| 5 | JSON | 2,039 | 0.0% | 1.00x |

### Token Counts by Dataset

| Dataset | ISONGraph | ISON | TOON | JSON Compact | JSON |
|---------|----------:|-----:|-----:|-------------:|-----:|
| Social Network | 119 | 129 | 145 | 218 | 411 |
| Knowledge Graph | 216 | 217 | 331 | 300 | 576 |
| Org Chart | 161 | 182 | 198 | 278 | 528 |
| Flight Routes | 143 | 157 | 182 | 276 | 524 |
| **Total** | **639** | **685** | **856** | **1,072** | **2,039** |

---

## Accuracy Results

Percentage of questions answered correctly by the LLM.

### Overall Accuracy

| Rank | Format | Correct | Total | Accuracy |
|:----:|--------|--------:|------:|---------:|
| 1 | **ISONGraph** | **46** | 50 | **92.0%** |
| 2 | ISON | 44 | 50 | 88.0% |
| 3 | JSON | 42 | 50 | 84.0% |
| 4 | JSON Compact | 41 | 50 | 82.0% |
| 5 | TOON | 40 | 50 | 80.0% |

### Accuracy by Question Category

| Category | ISONGraph | ISON | JSON Compact | JSON | TOON |
|----------|----------:|-----:|-------------:|-----:|-----:|
| Single-hop (15) | 15 | 15 | 15 | 15 | 15 |
| Multi-hop (10) | 8 | 7 | 4 | 5 | 4 |
| Analysis (20) | 18 | 17 | 17 | 17 | 17 |
| Path Finding (5) | 5 | 5 | 5 | 5 | 4 |

---

## Efficiency Score (Accuracy per 1K Tokens)

The efficiency score combines accuracy and token efficiency: **Accuracy / (Tokens / 1000)**

Higher is better - it measures how much accuracy you get per token spent.

### Efficiency Ranking

| Rank | Format | Acc/1K Tokens | Accuracy | Tokens | Analysis |
|:----:|--------|:-------------:|---------:|-------:|----------|
| 1 | **ISONGraph** | **143.97** | 92.0% | 639 | Best overall efficiency |
| 2 | ISON | 128.47 | 88.0% | 685 | Strong baseline |
| 3 | TOON | 93.46 | 80.0% | 856 | Token-optimized but lower accuracy |
| 4 | JSON Compact | 76.49 | 82.0% | 1,072 | Moderate efficiency |
| 5 | JSON | 41.20 | 84.0% | 2,039 | Verbose baseline |

---

## Detailed Analysis

### Why ISONGraph Excels at Traversal

1. **Explicit Edge Sections**
   - `edges.FOLLOWS` and `edges.REPORTS_TO` make relationship types immediately clear
   - LLMs can identify which edges to traverse for specific queries

2. **Reference Syntax**
   - `:person:1` notation enables precise source/target identification
   - No ambiguity about node types in multi-type graphs

3. **Tabular Edge Layout**
   - Each row is one edge, easy to scan
   - Column headers define edge properties once

4. **Graph Topology Preservation**
   - Unlike nested JSON, ISONGraph maintains explicit graph structure
   - Multi-hop queries become straightforward table lookups

### Multi-hop Query Performance

Multi-hop queries showed the biggest accuracy differences:

| Format | Multi-hop Accuracy | Why |
|--------|-------------------:|-----|
| ISONGraph | 80% | Clear edge references, explicit types |
| ISON | 70% | Good structure but lacks edge types |
| JSON | 50% | Verbose, harder to trace relationships |
| JSON Compact | 40% | Compact but loses readability |
| TOON | 40% | Token-optimized but confusing for graphs |

### Path Finding Performance

All formats performed well on path finding except TOON:

| Format | Path Finding Accuracy |
|--------|----------------------:|
| ISONGraph | 100% (5/5) |
| ISON | 100% (5/5) |
| JSON | 100% (5/5) |
| JSON Compact | 100% (5/5) |
| TOON | 80% (4/5) |

---

## Dataset-Specific Insights

### Social Network (15 questions)

- **Challenge**: Cyclic follows relationships
- **Best**: ISONGraph (13/15)
- **Failure pattern**: "Is graph connected?" failed for all formats

### Knowledge Graph (15 questions)

- **Challenge**: Multiple entity types (company, person, product)
- **Best**: ISONGraph (14/15)
- **ISONGraph advantage**: Type-specific node sections help identify entities

### Organization Chart (10 questions)

- **Challenge**: Hierarchical DAG structure
- **Best**: ISONGraph, ISON (9/10)
- **Failure pattern**: "How many levels?" - LLMs count differently

### Flight Routes (10 questions)

- **Challenge**: Path finding with distances
- **Best**: All formats tied (10/10 except JSON 9/10)
- **Note**: Numeric properties (distance, duration) parsed well

---

## Unit Test Results

All ISONGraph unit tests passed:

| Test | Result |
|------|--------|
| Basic Operations | PASS |
| Multi-hop Traversal | PASS |
| Shortest Path | PASS |
| Cycle Detection | PASS |
| Connectivity Check | PASS |
| Serialization Roundtrip | PASS |
| Query Patterns | PASS |
| Fluent API | PASS |

**Total: 8/8 tests passed**

---

## Notable Question Results

### Questions Where ISONGraph Outperformed

**Q6 [multi_hop]: Who can Alice reach in 2 hops?**
- Expected: Carol, David
- ISONGraph: PASS (Carol, David)
- JSON Compact: FAIL (returned IDs [3, 5])
- TOON: FAIL (returned IDs [3, 4])

**Q7 [multi_hop]: Can Alice reach Eve in 3 hops?**
- Expected: True
- ISONGraph: PASS
- ISON: PASS
- JSON Compact, JSON, TOON: FAIL (all answered "false")

### Questions All Formats Failed

**Q15 [analysis]: Is the graph connected?**
- Expected: True
- All formats: FAIL (answered "false")
- Analysis: LLMs interpret "connected" differently for directed graphs

**Q8 [multi_hop]: Who are Carol's followers' followers?**
- Expected: Carol (self-loop via cycle)
- All formats: FAIL
- Analysis: Question phrasing was ambiguous

---

## Format Examples

### ISONGraph (119 tokens - Social Network)
```
edges.FOLLOWS
since source target
2019 :person:2 :person:3
2020 :person:1 :person:2
2020 :person:3 :person:4
2021 :person:1 :person:3
2021 :person:5 :person:1
2022 :person:4 :person:5

nodes.person
id age name verified
1 28 Alice true
2 34 Bob false
3 29 Carol true
4 42 David false
5 31 Eve true
```

### JSON (411 tokens - same data)
```json
{
  "nodes": [
    {"id": 1, "type": "person", "name": "Alice", "age": 28, "verified": true},
    {"id": 2, "type": "person", "name": "Bob", "age": 34, "verified": false},
    {"id": 3, "type": "person", "name": "Carol", "age": 29, "verified": true},
    {"id": 4, "type": "person", "name": "David", "age": 42, "verified": false},
    {"id": 5, "type": "person", "name": "Eve", "age": 31, "verified": true}
  ],
  "edges": [
    {"source": 1, "target": 2, "relation": "follows", "since": 2020},
    {"source": 1, "target": 3, "relation": "follows", "since": 2021},
    {"source": 2, "target": 3, "relation": "follows", "since": 2019},
    {"source": 3, "target": 4, "relation": "follows", "since": 2020},
    {"source": 4, "target": 5, "relation": "follows", "since": 2022},
    {"source": 5, "target": 1, "relation": "follows", "since": 2021}
  ]
}
```

---

## Reproducibility

### Running the Benchmark

```bash
# From the repo root
cd benchmark/DataTraversal_Benchmark
python benchmark_graph.py --full
```

### Configuration

Set the `DEEPSEEK_API_KEY` environment variable before running:

```bash
export DEEPSEEK_API_KEY="your-key"   # Windows PowerShell: $env:DEEPSEEK_API_KEY = "your-key"
```

```python
# API Settings (read from environment)
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# Model Settings
model = "deepseek-chat"
temperature = 0  # Deterministic responses
```

### Estimated Runtime

- **Token counting only**: ~2 seconds
- **Full benchmark (50 questions x 5 formats)**: ~15 minutes
- **Rate limiting**: 0.5s delay between API calls

---

## Conclusions

### Key Findings

1. **ISONGraph is the best format for graph traversal tasks**
   - 92% accuracy (highest)
   - 143.97 Acc/1K tokens (best efficiency)
   - 68.7% token savings vs JSON

2. **Multi-hop queries benefit most from ISONGraph**
   - 80% accuracy vs 40-70% for other formats
   - Explicit edge types enable better chain reasoning

3. **TOON underperforms despite being token-optimized**
   - 80% accuracy (lowest)
   - Token compression hurts LLM comprehension for graphs

4. **Path finding works well across formats**
   - All formats achieve 80-100% accuracy
   - Shorter paths are easier for LLMs to trace

### Recommendations

| Use Case | Recommended Format |
|----------|-------------------|
| Graph traversal (LLM) | **ISONGraph** |
| Multi-hop queries | **ISONGraph** |
| General graph data | ISON or ISONGraph |
| API compatibility | JSON Compact |
| Human debugging | JSON (pretty) |

---

## Comparison with Knowledge Graph Benchmark

| Metric | DataTraversal | KnowledgeGraph |
|--------|--------------|----------------|
| Questions | 50 | 100 |
| Formats | 5 | 10 |
| ISONGraph Accuracy | 92.0% | 90.0% |
| ISONGraph Tokens | 639 | 1,698 |
| ISONGraph Acc/1K | 143.97 | 53.00 |
| Focus | Traversal ops | Format comparison |

---

## Appendix: Question Categories Explained

| Category | Description | Example |
|----------|-------------|---------|
| **Single-hop** | Direct neighbor lookup | "Who does Alice follow?" |
| **Multi-hop** | N-hop traversal | "Who can Alice reach in 2 hops?" |
| **Path Finding** | Route between nodes | "What is the shortest path from NYC to Tokyo?" |
| **Analysis** | Graph properties | "Does this graph have a cycle?" |

---

*Generated by ISONGraph Data Traversal Benchmark v1.0.0*
