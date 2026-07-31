#!/usr/bin/env python3
"""
Duplicate-Edge Import Benchmark
================================

ISONGraph is a simple graph: at most one edge per (rel_type, source,
target) triple. Before this fix, importing a CSV/GraphML/JSON payload
with a repeated edge crashed the entire import with an uncaught
DuplicateEdgeError - a single bad row lost the whole file.

This benchmark:
  1. Proves correctness: a duplicate-heavy import now succeeds and
     dedupes to the expected edge count, at a range of duplicate rates
     including the ~0.04% rate observed in KG-LLM-Bench-style exports
     and much heavier rates (1%, 5%, 20%) for stress-testing.
  2. Measures throughput: import speed (edges/sec) for CSVConverter,
     GraphMLConverter, and ISONGraph.from_dict, to quantify the cost
     of the has_edge() dedup guard added to each import path.

Run: python benchmarks/bench_dedup_import.py
"""

import random
import time
import warnings
from dataclasses import dataclass
from typing import List, Tuple

from ison_graph import ISONGraph
from converters.csv_converter import CSVConverter
from converters.graphml import GraphMLConverter

random.seed(42)

NODE_COUNT = 2000
EDGE_COUNTS = [5_000, 20_000]
DUPLICATE_RATES = [0.0, 0.0004, 0.01, 0.05, 0.20]


@dataclass
class Dataset:
    edge_count: int
    duplicate_rate: int
    unique_edges: List[Tuple[str, str, str]]
    all_edges: List[Tuple[str, str, str]]
    expected_unique: int


def build_dataset(edge_count: int, duplicate_rate: float) -> Dataset:
    """Build a synthetic (rel_type, source_id, target_id) edge list with
    a controlled fraction of exact-triple duplicates mixed in."""
    unique_target = max(1, round(edge_count * (1 - duplicate_rate)))

    unique_edges = []
    seen = set()
    while len(unique_edges) < unique_target:
        s = random.randint(0, NODE_COUNT - 1)
        t = random.randint(0, NODE_COUNT - 1)
        if s == t:
            continue
        triple = ("LINKS_TO", f"n{s}", f"n{t}")
        if triple in seen:
            continue
        seen.add(triple)
        unique_edges.append(triple)

    all_edges = list(unique_edges)
    while len(all_edges) < edge_count:
        all_edges.append(random.choice(unique_edges))
    random.shuffle(all_edges)

    return Dataset(
        edge_count=edge_count,
        duplicate_rate=duplicate_rate,
        unique_edges=unique_edges,
        all_edges=all_edges,
        expected_unique=len(unique_edges),
    )


def to_csv_strings(ds: Dataset) -> Tuple[str, str]:
    node_ids = {n for _, s, t in ds.all_edges for n in (s, t)}
    nodes_csv = "type,id\n" + "".join(f"node,{n}\n" for n in sorted(node_ids))
    edges_csv = "rel_type,source_type,source_id,target_type,target_id\n" + "".join(
        f"{rel},node,{s},node,{t}\n" for rel, s, t in ds.all_edges
    )
    return nodes_csv, edges_csv


def to_graphml_string(ds: Dataset) -> str:
    node_ids = {n for _, s, t in ds.all_edges for n in (s, t)}
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '<key id="edge_type" for="edge" attr.name="rel_type" attr.type="string"/>',
        '<graph id="g" edgedefault="directed">',
    ]
    lines += [f'<node id="node:{n}"/>' for n in sorted(node_ids)]
    for rel, s, t in ds.all_edges:
        lines.append(f'<edge source="node:{s}" target="node:{t}"><data key="edge_type">{rel}</data></edge>')
    lines += ["</graph>", "</graphml>"]
    return "\n".join(lines)


def to_dict_payload(ds: Dataset) -> dict:
    node_ids = {n for _, s, t in ds.all_edges for n in (s, t)}
    return {
        "nodes": [{"type": "node", "id": n} for n in sorted(node_ids)],
        "edges": [
            {"rel_type": rel, "source": {"type": "node", "id": s}, "target": {"type": "node", "id": t}}
            for rel, s, t in ds.all_edges
        ],
    }


def time_it(fn):
    start = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = fn()
    elapsed = time.perf_counter() - start
    return result, elapsed


def run():
    print("=" * 88)
    print("ISONGraph Converter Duplicate-Edge Import Benchmark")
    print("=" * 88)
    print(f"{'Format':<10} {'Edges':>8} {'DupRate':>8} {'Unique':>8} "
          f"{'Got':>8} {'Match':>6} {'Time(s)':>9} {'Edges/s':>10}")
    print("-" * 88)

    for edge_count in EDGE_COUNTS:
        for dup_rate in DUPLICATE_RATES:
            ds = build_dataset(edge_count, dup_rate)

            # CSV
            nodes_csv, edges_csv = to_csv_strings(ds)
            csv_conv = CSVConverter()
            graph, elapsed = time_it(lambda: csv_conv.from_csv(nodes_csv, edges_csv, "bench"))
            ok = graph.edge_count() == ds.expected_unique
            print(f"{'CSV':<10} {ds.edge_count:>8} {dup_rate*100:>7.2f}% {ds.expected_unique:>8} "
                  f"{graph.edge_count():>8} {'OK' if ok else 'FAIL':>6} {elapsed:>9.4f} "
                  f"{ds.edge_count/elapsed:>10.0f}")

            # GraphML
            graphml_str = to_graphml_string(ds)
            gml_conv = GraphMLConverter()
            graph, elapsed = time_it(lambda: gml_conv.from_graphml(graphml_str, "bench"))
            ok = graph.edge_count() == ds.expected_unique
            print(f"{'GraphML':<10} {ds.edge_count:>8} {dup_rate*100:>7.2f}% {ds.expected_unique:>8} "
                  f"{graph.edge_count():>8} {'OK' if ok else 'FAIL':>6} {elapsed:>9.4f} "
                  f"{ds.edge_count/elapsed:>10.0f}")

            # JSON (from_dict)
            payload = to_dict_payload(ds)
            graph, elapsed = time_it(lambda: ISONGraph.from_dict(payload, name="bench"))
            ok = graph.edge_count() == ds.expected_unique
            print(f"{'JSON':<10} {ds.edge_count:>8} {dup_rate*100:>7.2f}% {ds.expected_unique:>8} "
                  f"{graph.edge_count():>8} {'OK' if ok else 'FAIL':>6} {elapsed:>9.4f} "
                  f"{ds.edge_count/elapsed:>10.0f}")

        print("-" * 88)

    print("\nAll rows 'OK' confirms: duplicate-heavy imports that previously")
    print("crashed with an uncaught DuplicateEdgeError now succeed and dedupe")
    print("to the correct unique-edge count, across CSV, GraphML, and JSON.")


if __name__ == "__main__":
    run()
