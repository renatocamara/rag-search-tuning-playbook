# Prerequisites

## Azure services

You need these five services. They can be new or existing; the playbook only creates objects inside them (a container, a database, an index) and never changes the services themselves.

| Service | Minimum | Notes |
|---|---|---|
| **Azure AI Search** | Basic tier or higher, **semantic ranker enabled** (Standard recommended for demos with several indexes) | Semantic ranker is a service-level setting: *Settings > Semantic ranker > Free or Standard*. Vector search is available on all tiers created after mid-2023. |
| **Azure OpenAI** (Foundry / AI Services account) | Deployments of `text-embedding-3-large` (or `-small`) and a chat model such as `gpt-4.1-mini` | Deployment names go in `.env`. Any chat model works for answers and judging. |
| **Storage account** | Standard general purpose v2, hierarchical namespace not required | One container (`contoso-docs`) is created by the scripts. |
| **Cosmos DB for NoSQL** | Serverless or 400 RU/s provisioned | Database `ContosoCatalog` with two containers (see [setup/02-cosmos-db.md](setup/02-cosmos-db.md)). |
| **Somewhere to run Python** that can reach the private endpoints | A laptop over VPN, a jump box in the landing zone, or a Container App job | Python 3.10 or later, Azure CLI. |

Optional, referenced in the modules but not required to run them: API Management, Managed Redis, Application Insights, an Azure AI Foundry project (for [setup/05-agent.md](setup/05-agent.md)).

## Deploying the services with the AI Landing Zone Terraform module

If you are starting from nothing, or want a private-by-default environment that matches how these services are deployed in production, use the Azure Verified Module pattern for AI landing zones. It deploys the spoke network, private endpoints and DNS, AI Foundry with Azure OpenAI, AI Search, Cosmos DB, Storage, Key Vault, optionally API Management, a firewall, Bastion and a jump box, in one `terraform apply`.

* Module: [Azure/terraform-azurerm-avm-ptn-aiml-landing-zone](https://github.com/Azure/terraform-azurerm-avm-ptn-aiml-landing-zone)
* Documentation and design guidance: [AI Landing Zones](https://azure.github.io/AI-Landing-Zones/)

Start from the `examples/standalone` folder (self-contained, no platform landing zone needed) or `examples/default-byo-vnet` if you already have hub and spoke networking. The module deploys two groups of resources: the **Foundry dependencies** (AI Search, Cosmos DB, Storage, Key Vault declared inside `ai_foundry_definition`, used by the agent service) and the **GenAI application resources** (`genai_*` and `ks_ai_search_definition`, meant for your own application). This playbook works with either group; using the GenAI group keeps the Foundry dependencies untouched. A trimmed configuration, adapted from the module's standalone example, looks like this. Variable names change between releases, so compare with the example in the release you pin:

```hcl
module "ailz" {
  source  = "Azure/avm-ptn-aiml-landing-zone/azurerm"
  version = "~> 0.1"   # pin to the latest release listed in the repository

  location            = "eastus2"
  resource_group_name = "rg-ailz-contoso"
  flag_platform_landing_zone = false      # standalone: the module creates its own hub-like services

  vnet_definition = {
    name          = "vnet-ailz-contoso"
    address_space = ["10.10.0.0/20"]
  }

  ai_foundry_definition = {
    ai_foundry = { create_ai_agent_service = true }
    ai_model_deployments = {
      "text-embedding-3-large" = {
        name  = "text-embedding-3-large"
        model = { format = "OpenAI", name = "text-embedding-3-large", version = "1" }
        scale = { type = "Standard", capacity = 120 }
      }
      "gpt-4.1-mini" = {
        name  = "gpt-4.1-mini"
        model = { format = "OpenAI", name = "gpt-4.1-mini", version = "2025-04-14" }
        scale = { type = "GlobalStandard", capacity = 50 }
      }
    }
    ai_search_definition       = { this = {} }
    cosmosdb_definition        = { this = { consistency_level = "Session" } }
    key_vault_definition       = { this = {} }
    storage_account_definition = { this = { endpoints = { blob = { type = "blob" } } } }
  }

  # Application-side resources used by this playbook
  ks_ai_search_definition          = {}     # knowledge store search service (enable semantic ranker after deploy)
  genai_cosmosdb_definition        = { consistency_level = "Session" }
  genai_storage_account_definition = {}
  genai_key_vault_definition       = {}

  jumpvm_definition  = { sku = "Standard_D2s_v5" }   # run the scripts from here
  bastion_definition = {}
  apim_definition    = { publisher_email = "admin@contoso.example", publisher_name = "Contoso" }  # for module 07
}
```

After `terraform apply`, connect to the jump box (or your VPN) and confirm from that machine that the service hostnames resolve to private IPs. `scripts/pre_demo_check.py` does exactly that. Enable the semantic ranker on the search service you will use (the module does not turn it on).

Things that commonly need attention in an existing landing zone:

* **DNS**: the private DNS zones (`privatelink.search.windows.net`, `privatelink.openai.azure.com`, `privatelink.cognitiveservices.azure.com`, `privatelink.services.ai.azure.com`, `privatelink.blob.core.windows.net`, `privatelink.documents.azure.com`) must be linked to the network you run from. In a hub and spoke, they live in the hub; do not create duplicates in the spoke.
* **Public network access**: policies usually force it off. That is fine; the scripts never use public endpoints.
* **Azure OpenAI reachability from AI Search**: only needed if you use a vectorizer or integrated vectorization (module 05 mentions it). The push model in this playbook does not need it.

## Roles

Assign these to the identity that runs the scripts (your user for a laptop, the managed identity for an app). All are Azure RBAC roles except the Cosmos DB one, which is a data plane role.

| Scope | Role | Used by |
|---|---|---|
| Search service | **Search Service Contributor** | `03_index.py`, `reset.py --drop` |
| Search service | **Search Index Data Contributor** | `04_ingest.py`, `reset.py` |
| Search service | **Search Index Data Reader** (included in Contributor) | `query.py`, `compare.py`, `run_eval.py` |
| Azure OpenAI account | **Cognitive Services OpenAI User** | embeddings and chat |
| Storage account | **Storage Blob Data Contributor** | `01_storage.py`, `04_ingest.py` |
| Cosmos DB account | **Cosmos DB Built-in Data Contributor** (data plane) | `02_cosmos.py`, `lookup.py`, `reset.py` |

The Search service must accept Entra ID tokens: *Settings > Keys > API access control > Both* (or *Role-based access control*).

Cosmos DB data plane role assignment (control plane roles such as Contributor do not grant data access):

```bash
az cosmosdb sql role assignment create \
  --account-name <cosmos-account> --resource-group <rg> \
  --role-definition-id 00000000-0000-0000-0000-000000000002 \
  --principal-id $(az ad signed-in-user show --query id -o tsv) \
  --scope "/"
```

## Tools

* Python 3.10 or later and `pip install -r requirements.txt`
* Azure CLI 2.60 or later, signed in to the subscription (`az login`, `az account set --subscription <id>`)
* Git
* Optional: Visual Studio Code with the Azure AI Search extension to look at the index

## Cost

Running the whole playbook (35 questions, four modes, a few ingestions) costs a few dollars in Azure OpenAI tokens. The services themselves dominate: AI Search Standard S1 and a Cosmos DB account are the two items to pause or delete after a demo. The dataset is about 30 documents and 100 chunks, so index storage is negligible.
