# Demo runbook: accurate and timely in 25 minutes

A condensed walkthrough of modules 01 to 06 for a live audience. Every command is copy-paste; expected observations are in italics. Rehearse once; the whole thing runs in 20 to 25 minutes with talking.

## Before the session (15 minutes, the day before)

```bash
cd rag-search-tuning-playbook && source .venv/bin/activate
python scripts/data/generate_contoso_data.py          # dataset in its original state
python scripts/setup/01_storage.py                     # fresh upload
python scripts/setup/02_cosmos.py                      # catalog loaded
python scripts/setup/03_index.py --recreate            # clean index
python scripts/setup/04_ingest.py --chunking structured
python scripts/reset/reset.py --results                # no old result files
python scripts/pre_demo_check.py                       # all green, all private
```

Then pre-compute the baseline result files so the comparison step is instant during the session:

```bash
python scripts/eval/run_eval.py --mode vector
python scripts/eval/run_eval.py --mode hybrid --current
python scripts/eval/run_eval.py --mode semantic --current
python scripts/eval/run_eval.py --mode semantic --current --profile prefer-current
```

Keep two terminals open: one for commands, one with `data/docs/current/spec-CF-1100-XLS.md` visible for the chunking part. Increase the terminal font.

Record a screen capture of sections 1 to 3 once everything works. A recorded demo costs less credibility than a failed live one.

## Five minutes before

```bash
python scripts/pre_demo_check.py
```

*Every line `[ok]`; hostnames resolve to private addresses (10.x or 192.168.x). If a service resolves to a public IP you are not on the VPN.*

Drive the demo from the scripts, not from the portal. With public network access disabled, portal blades such as Search Explorer make data plane calls from your browser and fail unless the browser resolves the private endpoint. If you intend to show a portal screen, test that exact blade end to end beforehand.

## 1. The problem (3 minutes)

Tell the story: Contoso Water Solutions, three brands, reps ask about part numbers all day, the assistant is wrong on look-alikes and quotes old documents.

```bash
python scripts/demo/query.py "What repair kit fits the CF-1100-XLS?" --mode vector --answer
```

*Top passages include CF-1100-XL and the archived CF-1101-XL sheet. The answer may say K-CF-1100-RK, or hedge between the two kits. Point at the `<-- ARCHIVED` markers.*

```bash
python scripts/demo/query.py "What repair kit fits the CF-1100-XLS?" --mode vector --show-request
```

*"This is the whole request. No text, just a vector. The service never saw the letters XLS."*

## 2. Inspect the query: vector to hybrid to semantic (5 minutes)

```bash
python scripts/demo/compare.py "What repair kit fits the CF-1100-XLS?"
```

*Vector: wrong or unstable order. Keyword: right document first. Hybrid and semantic: right document first, with better neighbours.*

```bash
python scripts/demo/compare.py "price of ND415A"
python scripts/demo/compare.py "My flush valve keeps running and will not shut off. What should I check?"
```

*The typed-without-hyphens case works because of normalization plus the analyzer. The descriptive question works in every mode: hybrid is a superset, not a trade-off.*

Optional if the audience is technical:

```bash
python scripts/demo/query.py "What filter does the FX 2200 BR take?" --mode hybrid --no-normalize
python scripts/demo/query.py "What filter does the FX 2200 BR take?" --mode hybrid
```

*"Hybrid only helps if the keyword leg can match what the user typed. This is the analyzer conversation."*

## 3. Clean index: filters and scoring profile (5 minutes)

```bash
python scripts/demo/query.py "How often should the FX-2200-B filter be replaced?" --mode semantic --answer
```

*A community thread ("every 6 months") competes with the install guide ("3,000 gallons or 12 months").*

```bash
python scripts/demo/query.py "How often should the FX-2200-B filter be replaced?" --mode semantic --current --answer
```

*Only current documents; answer is correct and cites the install guide. Show the `filter` line in the header.*

```bash
python scripts/demo/query.py "rough-in for the CF-1101-XL" --mode semantic --current
python scripts/demo/query.py "rough-in for the CF-1101-XL" --mode semantic --profile prefer-current
```

*With the filter, a discontinued product is unanswerable. With the scoring profile, the archived sheet is still found but ranked under the current bulletin. "Filter for what must never be used, profile for what should usually lose."*

```bash
python scripts/demo/query.py "What is the filter capacity of the FX-2200-B?" --mode semantic --current
python scripts/demo/query.py "What is the filter capacity of the FX-2200-B?" --mode semantic --current --canonical
```

*The SharePoint copy is current, official and wrong for this question. Only a canonical-source rule separates it from the website version. "Deduplication is not enough; you need a rule for which copy wins."*

Listen for: whether anyone knows which sources are in the index today, whether archive and community were a deliberate choice, and whether the same spec exists in more than one system.

## 4. Chunking (4 minutes)

Show the spec sheet file in the second terminal: prose first, table last.

```bash
python scripts/setup/04_ingest.py --chunking naive --dry-run | tail -3
python scripts/setup/04_ingest.py --chunking structured --dry-run | tail -3
```

*Naive produces more chunks; the interesting part is what is in them.* Then, if the index was pre-built with naive chunking in a second index (`SEARCH_INDEX=contoso-kb-naive`), query it; otherwise describe module 03 and show one structured chunk:

```bash
python - <<'EOF'
import sys; sys.path.insert(0, "scripts"); import common
r = common.search_query({"search": "*", "filter": "doc_id eq 'spec-CF-1100-XLS' and section eq 'Specifications'", "select": "content", "top": 1})
print(r["value"][0]["content"][:600])
EOF
```

*"Every chunk carries the document title, the part numbers and the section. A table row never travels without its product."*

## 5. Structured lookup (3 minutes)

```bash
python scripts/demo/lookup.py "Is the CF-1101-XL still available?" --answer
python scripts/demo/lookup.py "What is the Contoso equivalent of a Tailspin TS-BF200R?"
```

*Facts from Cosmos DB first (discontinued, replaced by CF-1100-XL, kit K-CF-1100-RK2), then search filtered to those part numbers, then an answer that is the same every time.*

## 6. Measure (3 minutes)

```bash
python scripts/eval/run_eval.py --compare results/<vector>.json results/<semantic-current>.json
python scripts/eval/run_eval.py --compare results/<semantic-current>.json results/<semantic-current-prefer-current>.json
```

*First comparison: `hit@1` up sharply, `stale@1` to zero, and a per-question list of what changed. Second comparison: the scoring profile, if it lowers `hit@1`, is the proof that tuning without measurement goes backwards. "This is the artifact to keep: every change to the index or the query gets this comparison before it ships."*

Close with module 05 in one sentence (change detection, deletion, cache invalidation are three separate mechanisms; a weekly crawl is one of them) and module 07 if the audience is planning an external phase.

## What not to do

* Do not say an implementation is wrong. Show the mechanism on Contoso data and let the audience map it to their own system.
* Do not walk through the audience's architecture back to them. Ask how each layer decides.
* Do not quote the synthetic catalog as real product data, and do not put a customer's real part numbers into the public repository.
* Do not type commands live; paste them from this file.

## Backup plan

* If Azure OpenAI throttles during `compare.py`, run `query.py --mode keyword` (no embedding call) to keep the flow going, and note that the keyword leg alone already fixes part lookups.
* If the semantic ranker is not enabled on the service, every `--mode semantic` command fails with a 400; use `--mode hybrid` throughout. The story holds.
* If DNS is wrong, nothing works; `pre_demo_check.py` tells you before the audience does. Keep the pre-computed `results/*.json` files and the `--compare` output as screenshots.

## Reset for the next session

See [reset.md](reset.md). The short version: `python scripts/reset/reset.py --all` followed by the "before the session" block.
