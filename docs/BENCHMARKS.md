# Benchmarks

Clark benchmark claims must be generated from real datasets and real provider credentials. Do not publish comparison numbers from old local scripts or marketing pages.

## LongMemEval-Style Retrieval

The current runner indexes each question's haystack sessions into the real Clark Postgres/pgvector backend, queries Clark, and reports recall at K against the gold answer session IDs.

Requirements:

- `CLARK_DATABASE_URL`
- `GEMINI_API_KEY`
- A real LongMemEval-S-compatible JSON dataset
- Postgres with `pgvector`

Run:

```bash
CLARK_DATABASE_URL=postgresql://clark:strong-password@127.0.0.1:5432/clark \
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
CLARK_DATABASE_URL=postgresql://clark:strong-password@127.0.0.1:5432/clark \
uv run python benchmark/run_longmemeval.py \
  --dataset /path/to/longmemeval_s_cleaned.json \
  --tenant-id remote-longmemeval-full \
  --checkpoint-jsonl benchmark/results/remote-longmemeval-full.checkpoint.jsonl \
  --resume \
  --sleep-seconds 1 \
  --output benchmark/results/remote-longmemeval-full.json
```

If the provider returns quota errors, the runner writes a partial artifact from the checkpoint and exits non-zero.

## Verified Clark Result

Remote full run on `82.38.4.10`:

- Dataset: `/opt/clark-bench-data/longmemeval_s_cleaned.json`
- Artifact: `/opt/clark-production-ready-test/benchmark/results/remote-longmemeval-full-resume-slow-timeout.json`
- Scored questions: 500/500
- Recall@1: 446/500 = 0.892
- Recall@3: 486/500 = 0.972
- Recall@5: 493/500 = 0.986
- Recall@10: 497/500 = 0.994
- Recall@20: 498/500 = 0.996
- Elapsed: 4963.962 seconds

## External Published Baselines

These are published/self-reported external numbers. They were not reproduced in this repository and should not be mixed with the verified Clark run without the caveats below.

| System | Published result | Metric/source note | Reproduced here |
| --- | ---: | --- | --- |
| Clark / CLARK | 98.6% | Recall@5, 500/500 LongMemEval-S retrieval run on our server | Yes |
| MemPalace | 96.6% | Published raw LongMemEval Recall@5 | No |
| agentmemory | 95.2% | Published LongMemEval-S retrieval R@5 | No |
| Mem0 | 93.4 | Official Mem0 research LongMemEval score; methodology/metric is not guaranteed identical to retrieval Recall@5 | No |

Caveats:

- Clark's number above is a real run on the test server with Gemini embeddings and Postgres/pgvector.
- Mem0, MemPalace, and agentmemory numbers are external published claims.
- The only direct Clark-vs-Mem0 run in this repo so far is a 1-question smoke: both hit Recall@1, but Clark completed in 2.341 seconds and Mem0 in 260.276 seconds.
- Do not publish "beats everyone" phrasing until either external methodology is matched exactly or the competitors are run locally under the same harness.

Sources:

- Mem0 research: https://mem0.ai/research
- MemPalace benchmark page: https://www.mempalace.tech/benchmarks
- agentmemory benchmark page: https://www.agentmemory.tech/

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

Run Clark and Mem0 on the same LongMemEval-S slice:

```bash
GEMINI_API_KEY=... \
DEEPSEEK_API_KEY=... \
CLARK_DATABASE_URL=postgresql://clark:strong-password@127.0.0.1:5432/clark \
uv run python benchmark/run_provider_comparison.py \
  --dataset /path/to/longmemeval_s_cleaned.json \
  --providers clark,mem0 \
  --max-questions 5 \
  --run-id provider-compare-clark-mem0-5 \
  --checkpoint-dir benchmark/results/provider-checkpoints \
  --resume \
  --output benchmark/results/provider-comparison.json
```

Current real adapters:

- `clark`: Clark Postgres/pgvector with Gemini embeddings.
- `mem0`: Mem0 OSS with DeepSeek LLM, Gemini embeddings, and local Qdrant.

Managed providers such as Supermemory and hosted Zep require their own API keys. Do not include them in public comparison tables until they have been run in the same environment.
