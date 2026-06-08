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

## Required Before Public Claims

- Publish the dataset version and preprocessing steps.
- Publish raw result JSON.
- Publish provider/model versions.
- Run ablations for vector-only, keyword-only, and hybrid retrieval.
- Run comparable benchmarks against other memory providers in the same environment when making competitive claims.
- Record latency and provider cost per run.
