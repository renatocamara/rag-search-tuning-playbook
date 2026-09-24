# Module 06: Evaluation (measure every change)

**Symptom at Contoso:** every tuning discussion ends in "it seems better". The team switched embedding models once and could not say whether it helped. Reps report failures by email, someone reproduces one, fixes it, and a different question breaks.

**Root cause:** no fixed set of questions with known answers, so no way to compare before and after.

**Fix:** an evaluation set built from real questions, a script that runs it in seconds, and the habit of running it before and after every change. Modules 01 to 05 each ended with this step; this module explains what is being measured and how to build the set for your own content.

Time: 10 minutes.

## The evaluation set

`data/eval/eval_set.jsonl` has 35 questions, one per line:

```json
{"id": "q01", "category": "part_lookup",
 "question": "What repair kit fits the CF-1100-XLS?",
 "expected_part_numbers": ["K-CF-1100-RK2"],
 "expected_doc_ids": ["spec-CF-1100-XLS", "faq-contoso-flow", "install-CF-1100-series"],
 "expected_answer": "K-CF-1100-RK2"}
```

| Category | Count | What it tests |
|---|---|---|
| `part_lookup` | 10 | exact part numbers, look-alikes, kits, accessories |
| `part_format` | 3 | the same, typed as `cf1100xls`, `FX 2200 BR`, `ND415A` |
| `spec_value` | 6 | a value inside a table: rough-in, pressure range, bowl depth |
| `cross_reference` | 5 | competitor part to Contoso part, including a two-hop question |
| `stale_trap` | 6 | the correct answer exists only in current documents; archive or community has a wrong one |
| `descriptive` | 5 | symptom and how-to questions where vector search already does well |

Three fields carry the ground truth. `expected_doc_ids` is the set of documents that contain the answer (any one is a hit). `expected_part_numbers` are the part numbers a correct answer must mention. `expected_answer` is a short reference for the judge.

## Metrics

```bash
python scripts/eval/run_eval.py --mode semantic --current --profile prefer-current
```

```
  ok  q01 [part_lookup    ] rank=1 top1=spec-CF-1100-XLS
  ...
semantic-current-prefer-current  (35 questions)
  category             hit@1     hit@3     hit@5       mrr    part@3   stale@1
  ALL                   0.94      1.00      1.00      0.97      0.97      0.00
  cross_reference       1.00      1.00      1.00      1.00      1.00      0.00
  ...
```

| Metric | Meaning | What to watch |
|---|---|---|
| `hit@1`, `hit@3`, `hit@5` | an expected document is in the top 1 / 3 / 5 passages | `hit@5` below 1.0 means the answer is not even available to the model; fix retrieval before touching prompts |
| `mrr` | mean of 1 / rank of the first expected document | sensitive to ordering; the metric to compare modes with |
| `part@3` | an expected part number appears in the `part_numbers` of the top 3 passages | the look-alike test |
| `stale@1` | the top passage is archived or community | should be 0 in production; anything else is a filter or metadata gap |
| `answer_ok` | with `--answer`: a judge model compared the generated answer with `expected_answer` | the end-to-end number, slower and noisier; run it before releases, not on every tweak |

Results are saved to `results/<timestamp>-<label>.json`. Compare two runs:

```bash
python scripts/eval/run_eval.py --compare results/20260101-100000-vector.json results/20260101-100500-semantic-current-prefer-current.json
```

The comparison prints the deltas per metric and then only the questions whose top result changed, which is where the conversation about a change should happen: "q25 used to return the 2022 archived sheet, now returns the install guide".

## Expected progression on this dataset

Numbers vary with the embedding model and the semantic ranker version, but the shape is consistent:

Measured with `text-embedding-3-large` (3072 dimensions), `gpt-4.1-mini` and structured chunking:

| Run | hit@1 | hit@5 | stale@1 | Notes |
|---|---|---|---|---|
| `--mode vector` (no filter) | 0.66 | 0.91 | 0.20 | prices, flow rates and pressures answered from 2019 to 2022 documents; filter interval from the forum |
| `--mode hybrid --current` | 0.89 | 0.97 | 0.00 | the big step: exact part numbers count, archive and community excluded |
| `--mode semantic --current` | 0.91 | 1.00 | 0.00 | reranker orders the candidates better; every question has the right document in the top 5 |
| `--mode semantic --current --profile prefer-current` (first version of the profile) | 0.83 | 1.00 | 0.00 | worse: a freshness boost of 2.0 pushed the newest documents above the relevant ones |

The last row is the reason this module exists. The remaining miss in the best run is a two-hop question (a kit and a competitor part in the same question), which module 04 answers with the catalog lookup.

If a run does not move in the expected direction, that is the point: something in your environment differs (an analyzer, a field not in the semantic configuration, a filter excluding a needed document), and the per-question diff shows which question to look at.

## Building an evaluation set for your own assistant

1. **Collect real questions.** Chat logs, support tickets, the "it got this wrong" emails. 50 is enough to start; 200 is comfortable. Include the ones that currently fail and the ones that currently work, in roughly the proportion reps ask them.
2. **Write the expected answer with a subject matter expert**, not from the assistant's output. Where the answer is a part number or a value, record exactly that.
3. **Record which documents contain the answer** (`expected_doc_ids`). This is what makes retrieval measurable without a model in the loop.
4. **Categorize.** Categories should map to failure modes you care about (exact lookup, spec value, policy, stale trap, descriptive), because averages hide regressions: a change can raise the overall score while breaking one category.
5. **Add trap questions on purpose.** For every document you know is stale or duplicated, write a question whose correct answer differs between the old and new version. `stale@1` only means something if the set contains traps.
6. **Version the set with the index.** When documents change, some expected answers change; review the set at each content release.
7. **Run it in CI**, or at least before every deployment of the ingestion or query code, and keep the results files.

## Beyond retrieval metrics

Once retrieval is solid, the remaining quality questions are about the answer: groundedness (does it say only what the passages say), completeness, citation accuracy, tone. Azure AI Foundry's evaluation SDK has built-in evaluators for these (groundedness, relevance, coherence, and retrieval evaluators that work with the same question and context format). The `results/*.json` files from this script contain the question, the passages returned and, with `--answer`, the answer, which is exactly the input those evaluators need.

## References

* [Evaluate generative AI applications with the Azure AI Evaluation SDK](https://learn.microsoft.com/azure/ai-foundry/how-to/develop/evaluate-sdk)
* [Retrieval and RAG evaluators](https://learn.microsoft.com/azure/ai-foundry/concepts/evaluation-evaluators/rag-evaluators)
