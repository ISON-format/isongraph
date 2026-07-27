# Reproducing the Knowledge Graph Benchmark

Everything needed is in this folder: datasets, prompts, format converters, and evaluation logic all live in `benchmark_kg_100.py` (self-contained).

## Setup

```bash
pip install ison-py ison-graph tiktoken requests
# optional, for the TOON format row:
pip install toon-format
```

## Token counts only (no API key, deterministic, ~1 minute)

```bash
python benchmark_kg_100.py --skip-llm
```

This regenerates the token table exactly. Counts use the o200k_base tokenizer.

## Full run with accuracy (needs an LLM endpoint)

The recorded results used DeepSeek Chat at temperature 0:

```bash
export DEEPSEEK_API_KEY=sk-...
python benchmark_kg_100.py --full
```

The harness speaks the OpenAI chat-completions format. To run it against any other OpenAI-compatible endpoint (llama.cpp server, Ollama, vLLM, OpenRouter), edit two constants at the top of `benchmark_kg_100.py`: set `DEEPSEEK_API_URL` to your endpoint's `/chat/completions` URL and the `model` field in `call_llm` to your model name. Local-model replications are welcome; please open an issue with your results either way.

## What gets logged

Each run writes a timestamped log plus `benchmark_kg100_latest.log` in this folder with per-question, per-format responses and pass/fail judgments.

## Known caveats

See "Methodology Notes & Limitations" in [BENCHMARK.md](BENCHMARK.md) before citing numbers: baseline choice (pretty vs minified JSON), single-run accuracy confidence intervals, prompt-cache behavior on mutating graphs, and tokenizer specificity are all documented there.
