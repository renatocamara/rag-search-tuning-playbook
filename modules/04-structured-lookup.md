# Module 04: Structured lookup first, search second

**Symptom at Contoso:** "Is the CF-1101-XL still available?" gets a confident description of the valve from its 2019 spec sheet. "What is the Contoso equivalent of a Tailspin TS-BF200R?" gets "I could not find that" one day and the right answer the next, depending on which chunk of the cross reference table ranked in the top five. Prices are quoted from whichever spec sheet was retrieved, current or not.

**Root cause:** facts that have a key (part number, competitor part number) are being retrieved by similarity. Similarity is the right tool for "how do I fix a running valve" and the wrong tool for "what is the price of ND-415-A". The catalog already knows the answer with certainty and is the one source that is updated the moment a price changes or a part is discontinued.

**Fix:** when the question contains a part number, resolve it in Cosmos DB first. Use the result to answer the factual part directly and to filter the search for the explanatory part.

Time: 10 minutes. Requires: setup step 2 (Cosmos DB loaded).

## Step 1: Search alone

```bash
python scripts/demo/query.py "Is the CF-1101-XL still available?" --mode semantic
python scripts/demo/query.py "What is the Contoso equivalent of a Tailspin TS-BF200R?" --mode semantic
python scripts/demo/query.py "Will the K-CF-1100-RK2 kit fit a Litware L-9450 valve?" --mode semantic
```

The first one finds the archived sheet (and, with `--current`, the bulletin, which is fine, but only because Contoso happened to publish a bulletin). The second depends on the cross reference chunk ranking. The third is a two-hop question: the search has to find both the kit and the competitor valve.

## Step 2: Catalog first

```bash
python scripts/demo/lookup.py "Is the CF-1101-XL still available?"
python scripts/demo/lookup.py "What is the Contoso equivalent of a Tailspin TS-BF200R?"
python scripts/demo/lookup.py "price of nd415a"
python scripts/demo/lookup.py "What repair kit fits the CF-1100-XLS?" --answer
```

`scripts/demo/lookup.py` does what the `/query` handler should do:

1. **Detect** part numbers in the question with the same regular expression the ingestion uses. `nd415a`, `ND 415 A` and `ND-415-A` all resolve.
2. **Look up** each one in `parts` (by normalized id) and, if not found, in `crossReference` (by normalized competitor part number). The Cosmos query normalizes on the server side (`LOWER(REPLACE(c.id, '-', ''))`), so the container needs no extra field.
3. **Print the facts**: status, price, kit, replacement, equivalents, notes.
4. **Search** the index with a filter on the resolved part numbers and `status eq 'current'`, so the passages are about the right product.
5. With `--answer`, give the model the catalog facts as the first "passage" (labelled `cosmos:catalog`) plus the search passages. The prompt tells it to quote part numbers exactly and cite sources.

Output for the first question:

```
part numbers detected: CF-1101-XL

--- 1. Structured lookup (Cosmos DB) ---
  CF-1101-XL: AquaSense Manual Flush Valve 1.6 gpf | status=discontinued | list price $385.00 | repairKit=K-CF-1100-RK2 | replacedBy=CF-1100-XL | discontinuedDate=2024-06-30

--- 2. Search, filtered to the resolved part numbers ---
  1. bulletin-2024-07-CF-1101-XL   ...
```

The status, replacement and kit are now facts from the system of record, and the search brings the bulletin text for the model to explain the transition.

## Step 3: The router pattern

In an application this becomes a small decision at the top of `/query`:

```
if part numbers detected:
    facts = catalog lookup (parts, then cross reference)
    filter = part_numbers/any(p: p eq '<resolved>') and status eq 'current'
    if any resolved part is discontinued: drop the status filter (the rep needs the archived sheet)
else:
    facts = none
    filter = status eq 'current'
passages = hybrid + semantic search(question, filter, scoring profile)
answer = model(question, facts, passages)
```

Three details that make it robust:

* **Normalize on both sides.** The regex, the index field and the Cosmos query all reduce to lowercase alphanumerics.
* **Restrict detection to the catalog.** Without a known list, `ASME A112` and `in 2025 the` look like part numbers. The lookup itself is the check: a match in Cosmos DB is a part number, anything else is not.
* **Let the catalog steer the filter.** A discontinued part relaxes the `status` filter; a competitor part swaps the search to the Contoso equivalent.

## Step 4: Measure

```bash
python scripts/eval/run_eval.py --mode semantic --current --profile prefer-current
```

The retrieval metrics do not change much from module 02, because the evaluation set measures whether the right document is retrieved, and the catalog is not a document. What changes is answer correctness on `part_lookup`, `cross_reference` and `stale_trap` when you run with `--answer`, and, more importantly, the variance: the same question gives the same answer every time.

For a proper comparison, run `run_eval.py --answer` before and after switching `retrieval.answer()` to include catalog facts (a one-line change in `run_eval.py` if you want to automate it; `lookup.py` shows the pieces).

## Keeping the catalog in the loop

The catalog is only as good as its feed. At Contoso, `parts` is refreshed nightly from the product master (PIM or ERP), and `crossReference` is maintained by the product management team in a spreadsheet that is loaded weekly. Both are cheap to keep current, which is the point: a price change reaches the assistant the next morning without a re-crawl, a re-chunk or a re-embed.

The same design works with Azure SQL, Dataverse or a REST API in front of the ERP. Cosmos DB is used here because it is already in the landing zone and needs no schema.

## What to change in your application

| Setting | Before | After |
|---|---|---|
| `/query` | search, then answer | detect part numbers, catalog lookup, filtered search, answer with facts + passages |
| Grounding | passages | catalog facts first, passages second, model told which is authoritative |
| Filter | static | derived from the lookup (part number, status) |
| Data sources | documents only | documents plus a structured catalog with a refresh job |

## References

* [Cosmos DB role-based access control (data plane)](https://learn.microsoft.com/azure/cosmos-db/how-to-setup-rbac)
* [Azure AI Search OData collection filters](https://learn.microsoft.com/azure/search/search-query-odata-collection-operators)
