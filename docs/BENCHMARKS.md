# Benchmarks

JKG benchmark claims must be generated from real datasets and real provider credentials. Do not publish comparison numbers from old local scripts or marketing pages.

## LongMemEval-Style Retrieval

The current runner indexes each question's haystack sessions into the real JKG Postgres/pgvector backend, queries JKG, and reports recall at K against the gold answer session IDs.

Requirements:

- `JKG_DATABASE_URL`
- `GEMINI_API_KEY`
- A real LongMemEval-S-compatible JSON dataset
- Postgres with `pgvector`

Run:

```bash
JKG_DATABASE_URL=postgresql://jkg:strong-password@127.0.0.1:5432/jkg \
GEMINI_API_KEY=... \
uv run python benchmark/run_longmemeval.py \
  --dataset /path/to/longmemeval_s_cleaned.json \
  --max-questions 100
```

Outputs are written to `benchmark/results/` unless `--output` is provided.

Use a unique tenant per run. The runner creates one automatically. Add `--cleanup` only when you intentionally want to delete the benchmark tenant rows after saving the result.

For long runs, use checkpoint/resume:

```bash
GEMINI_API_KEY=... \
JKG_DATABASE_URL=postgresql://jkg:strong-password@127.0.0.1:5432/jkg \
uv run python benchmark/run_longmemeval.py \
  --dataset /path/to/longmemeval_s_cleaned.json \
  --tenant-id remote-longmemeval-full \
  --checkpoint-jsonl benchmark/results/remote-longmemeval-full.checkpoint.jsonl \
  --resume \
  --sleep-seconds 1 \
  --output benchmark/results/remote-longmemeval-full.json
```

If the provider returns quota errors, the runner writes a partial artifact from the checkpoint and exits non-zero.

## Required Before Public Claims

- Publish the dataset version and preprocessing steps.
- Publish raw result JSON.
- Publish provider/model versions.
- Run ablations for vector-only, keyword-only, and hybrid retrieval.
- Run comparable benchmarks against other memory providers in the same environment when making competitive claims.
- Record latency and provider cost per run.

## Provider Comparison Runner

Install benchmark dependencies:

```bash
uv sync --extra benchmark --extra postgres
```

Run JKG and Mem0 on the same LongMemEval-S slice:

```bash
GEMINI_API_KEY=... \
DEEPSEEK_API_KEY=... \
JKG_DATABASE_URL=postgresql://jkg:strong-password@127.0.0.1:5432/jkg \
uv run python benchmark/run_provider_comparison.py \
  --dataset /path/to/longmemeval_s_cleaned.json \
  --providers jkg,mem0 \
  --max-questions 1 \
  --output benchmark/results/provider-comparison.json
```

Current real adapters:

- `jkg`: JKG Postgres/pgvector with Gemini embeddings.
- `mem0`: Mem0 OSS with DeepSeek LLM, Gemini embeddings, and local Qdrant.

Managed providers such as Supermemory and hosted Zep require their own API keys. Do not include them in public comparison tables until they have been run in the same environment.
