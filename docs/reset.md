# Reset

The playbook never creates or deletes Azure resources; it only creates objects inside them (a blob container, a database with two containers, one index). Resetting means emptying or recreating those objects, which takes a couple of minutes.

## Full reset (before a repeat demo)

```bash
python scripts/reset/reset.py --all              # empties the index, both Cosmos containers, the blob container, results/
python scripts/data/generate_contoso_data.py     # restores data/ to its original state (undoes module 05 edits)
python scripts/setup/01_storage.py
python scripts/setup/02_cosmos.py
python scripts/setup/03_index.py --recreate      # only needed if index.json changed; harmless otherwise
python scripts/setup/04_ingest.py
python scripts/pre_demo_check.py
```

## Partial resets

| Goal | Command |
|---|---|
| Re-chunk everything with the other strategy | `python scripts/setup/04_ingest.py --chunking naive --force` (or `structured`) |
| Remove archived and community chunks, keep current | `python scripts/reset/reset.py --index` then `python scripts/setup/04_ingest.py --source current` |
| Undo the module 05 edits (price change, deleted blob) | `python scripts/data/generate_contoso_data.py` then `python scripts/setup/01_storage.py` then `python scripts/setup/04_ingest.py --sync` |
| Change embedding dimensions | edit `.env`, then `python scripts/setup/03_index.py --recreate` and `python scripts/setup/04_ingest.py --force` |
| Drop the index entirely | `python scripts/reset/reset.py --index --drop` |
| Clear old evaluation results | `python scripts/reset/reset.py --results` |

## Two indexes side by side

For a demo that compares chunking strategies without re-ingesting in front of the audience, build a second index once:

```bash
SEARCH_INDEX=contoso-kb-naive python scripts/setup/03_index.py
SEARCH_INDEX=contoso-kb-naive python scripts/setup/04_ingest.py --chunking naive
```

Then switch with the environment variable: `SEARCH_INDEX=contoso-kb-naive python scripts/demo/query.py "..."`. On Windows PowerShell use `$env:SEARCH_INDEX="contoso-kb-naive"` before the command.

The same trick gives a faithful "vector only" baseline for audiences that want to see the two configurations as two indexes with identical chunks and vectors: copy `index.json`, make `content` and `part_numbers` non-searchable and the metadata non-filterable, create it under another name and ingest into both. The playbook does not ship that variant because the request body already isolates the difference on one index, but it removes the "you changed the data too" objection for a sceptical room.

## Removing everything

Delete the index, the `ContosoCatalog` database and the `contoso-docs` container in the portal or with the CLI, or simply delete the resource group if the services were created for the playbook. Pause or delete the AI Search service and the Cosmos DB account when not in use; they are the cost drivers.
