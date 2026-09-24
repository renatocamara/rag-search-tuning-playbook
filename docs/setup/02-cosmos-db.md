# Setup 2: Cosmos DB, the system of record for the catalog

## Why a database next to the index

A product catalog is structured data. Part number, status, list price, the repair kit that fits, what replaced what, and competitor equivalents are facts with a key. Retrieving them by vector similarity is the wrong tool: the embedding of "CF-1100-XL" and "CF-1100-XLS" are almost the same, while the facts behind them differ. Module 04 shows the application looking the part number up here first and searching the index second. Cosmos DB is also what most companies already have (or an equivalent SQL database, a PIM or an ERP view); the pattern is the same.

## What gets created

| Object | Setting | Content |
|---|---|---|
| Database | `ContosoCatalog` | |
| Container `parts` | partition key `/brand` | 26 items from `data/catalog/parts.json`: 15 products and 11 service parts, with `status` (`current` or `discontinued`), `listPrice`, `repairKit`, `replaces` / `replacedBy`, `fits`, `effectiveDate` |
| Container `crossReference` | partition key `/competitorBrand` | 9 items from `data/catalog/cross_reference.json`: competitor part number to Contoso part number, match type, notes |

Example item in `parts`:

```json
{
  "id": "CF-1101-XL",
  "brand": "Contoso Flow",
  "name": "AquaSense Manual Flush Valve 1.6 gpf",
  "status": "discontinued",
  "listPrice": 385.0,
  "repairKit": "K-CF-1100-RK2",
  "replacedBy": "CF-1100-XL",
  "discontinuedDate": "2024-06-30"
}
```

## Steps

1. Create the database and containers. Data plane RBAC cannot create them, so do it once in the portal or with the CLI:

    ```bash
    az cosmosdb sql database create -a <cosmos-account> -g <rg> -n ContosoCatalog
    az cosmosdb sql container create -a <cosmos-account> -g <rg> -d ContosoCatalog -n parts --partition-key-path /brand
    az cosmosdb sql container create -a <cosmos-account> -g <rg> -d ContosoCatalog -n crossReference --partition-key-path /competitorBrand
    ```

    Serverless accounts need no throughput setting. For provisioned accounts add `--throughput 400` to each container or share 400 RU/s at the database level.

2. Grant your identity the **Cosmos DB Built-in Data Contributor** role (data plane). Control plane roles such as Owner or Contributor do not grant data access:

    ```bash
    az cosmosdb sql role assignment create -a <cosmos-account> -g <rg> \
      --role-definition-id 00000000-0000-0000-0000-000000000002 \
      --principal-id $(az ad signed-in-user show --query id -o tsv) --scope "/"
    ```

3. Set `COSMOS_ENDPOINT` (and the database and container names if you changed them) in `.env`.
4. Load:

    ```bash
    python scripts/setup/02_cosmos.py
    ```

    Output:

    ```
      ContosoCatalog/parts: 26 items
      ContosoCatalog/crossReference: 9 items
    ```

## Notes for private environments

* The Cosmos DB private endpoint (`privatelink.documents.azure.com`) must resolve from where the script runs. `scripts/pre_demo_check.py` checks it.
* The portal's Data Explorer often fails behind private endpoints and conditional access. Loading with a script from inside the network, as done here, avoids that entirely.
* If Azure AI Search will read from Cosmos DB with an indexer (an alternative discussed in module 05), the search service needs a **shared private link** to the Cosmos account and the indexer needs `executionEnvironment: private`. The push model used by the playbook does not need either.
