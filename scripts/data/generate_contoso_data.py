"""
Generate the Contoso Water Solutions synthetic dataset.

Everything under data/ is produced by this script so the dataset is
repeatable and easy to extend. Run it again after changing anything here:

    python scripts/data/generate_contoso_data.py

Outputs
  data/catalog/parts.json               Cosmos DB "parts" container (current catalog)
  data/catalog/cross_reference.json     Cosmos DB "crossReference" container
  data/docs/current/*.md                Official, current documents
  data/docs/archive/*.md                Superseded documents (intentional stale-content traps)
  data/docs/community/*.md              User generated content (intentional wrong answers)
  data/eval/eval_set.jsonl              Questions with expected part numbers and documents

The dataset is small on purpose (a few dozen documents) so every module
can be demonstrated in minutes. The traps are deliberate:
  * look-alike part numbers (CF-1100-XL, CF-1100-XLS, CF-1101-XL)
  * a discontinued part and a superseded repair kit
  * an archived spec sheet with a different price and flow rate
  * a community post that recommends the old repair kit
  * part numbers written with different separators in the wild
"""

import json
import os
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "data")


def w(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content.strip() + "\n")


# ---------------------------------------------------------------------------
# 1. Product catalog (Cosmos DB "parts")
# ---------------------------------------------------------------------------

PARTS = [
    # Contoso Flow: commercial flush valves and faucets
    dict(id="CF-1100-XL", brand="Contoso Flow", productLine="AquaSense Flush Valves", category="Flush valve",
         name="AquaSense Manual Flush Valve 1.28 gpf", status="current", listPrice=412.00,
         flowRate="1.28 gpf", inletSize="1 in", roughIn="11.5 in", finish="Polished chrome",
         repairKit="K-CF-1100-RK2", warrantyYears=3, replaces="CF-1101-XL", effectiveDate="2024-07-01"),
    dict(id="CF-1100-XLS", brand="Contoso Flow", productLine="AquaSense Flush Valves", category="Flush valve",
         name="AquaSense Sensor Flush Valve 1.28 gpf", status="current", listPrice=689.00,
         flowRate="1.28 gpf", inletSize="1 in", roughIn="11.5 in", finish="Polished chrome",
         repairKit="K-CF-1100-RK2", sensorModule="S-CF-IR3", batteryPack="B-CF-4AA", warrantyYears=3,
         effectiveDate="2024-07-01"),
    dict(id="CF-1101-XL", brand="Contoso Flow", productLine="AquaSense Flush Valves", category="Flush valve",
         name="AquaSense Manual Flush Valve 1.6 gpf", status="discontinued", listPrice=385.00,
         flowRate="1.6 gpf", inletSize="1 in", roughIn="11.5 in", finish="Polished chrome",
         repairKit="K-CF-1100-RK2", warrantyYears=3, replacedBy="CF-1100-XL",
         discontinuedDate="2024-06-30", effectiveDate="2019-03-01"),
    dict(id="CF-1250-M", brand="Contoso Flow", productLine="ClearTouch Faucets", category="Faucet",
         name="ClearTouch Manual Lavatory Faucet 0.5 gpm", status="current", listPrice=246.00,
         flowRate="0.5 gpm", inletSize="3/8 in", spoutHeight="4.5 in", finish="Polished chrome",
         repairKit="K-CF-1250-CART", warrantyYears=3, effectiveDate="2023-01-15"),
    dict(id="CF-1250-S", brand="Contoso Flow", productLine="ClearTouch Faucets", category="Faucet",
         name="ClearTouch Sensor Lavatory Faucet 0.5 gpm (hardwired)", status="current", listPrice=498.00,
         flowRate="0.5 gpm", inletSize="3/8 in", spoutHeight="4.5 in", finish="Polished chrome",
         repairKit="K-CF-1250-CART", sensorModule="S-CF-IR3", powerSupply="P-CF-24V", warrantyYears=3,
         effectiveDate="2023-01-15"),
    dict(id="CF-1250-SB", brand="Contoso Flow", productLine="ClearTouch Faucets", category="Faucet",
         name="ClearTouch Sensor Lavatory Faucet 0.5 gpm (battery)", status="current", listPrice=512.00,
         flowRate="0.5 gpm", inletSize="3/8 in", spoutHeight="4.5 in", finish="Polished chrome",
         repairKit="K-CF-1250-CART", sensorModule="S-CF-IR3", batteryPack="B-CF-4AA", warrantyYears=3,
         effectiveDate="2023-01-15"),
    # Fabrikam Fixtures: bottle filling stations and sinks
    dict(id="FX-2200-B", brand="Fabrikam Fixtures", productLine="HydroFill Stations", category="Bottle filling station",
         name="HydroFill Bottle Filling Station, non-refrigerated", status="current", listPrice=1_245.00,
         fillRate="1.1 gpm", filter="K-FX-2200-FLT", filterCapacity="3,000 gallons or 12 months",
         mounting="Wall, in-wall", warrantyYears=5, effectiveDate="2025-02-01"),
    dict(id="FX-2200-BR", brand="Fabrikam Fixtures", productLine="HydroFill Stations", category="Bottle filling station",
         name="HydroFill Bottle Filling Station, refrigerated 8 gph", status="current", listPrice=2_190.00,
         fillRate="1.1 gpm", filter="K-FX-2200-FLT", filterCapacity="3,000 gallons or 12 months",
         chillerCapacity="8 gph", mounting="Wall, in-wall", warrantyYears=5, effectiveDate="2025-02-01"),
    dict(id="FX-2210-B", brand="Fabrikam Fixtures", productLine="HydroFill Stations", category="Bottle filling station",
         name="HydroFill Classic Bottle Filling Station", status="discontinued", listPrice=1_090.00,
         fillRate="0.9 gpm", filter="K-FX-2210-FLT", filterCapacity="1,500 gallons or 6 months",
         mounting="Wall", warrantyYears=3, replacedBy="FX-2200-B", discontinuedDate="2022-12-31",
         effectiveDate="2018-05-01"),
    dict(id="FX-3100", brand="Fabrikam Fixtures", productLine="SteelCare Sinks", category="Sink",
         name="SteelCare Single Bowl Stainless Sink 25 x 22 in", status="current", listPrice=389.00,
         bowlDepth="8 in", gauge="18 gauge", material="Type 304 stainless steel", drainSize="3.5 in",
         warrantyYears=5, effectiveDate="2022-09-01"),
    dict(id="FX-3100-D", brand="Fabrikam Fixtures", productLine="SteelCare Sinks", category="Sink",
         name="SteelCare Single Bowl Stainless Sink 25 x 22 in with faucet deck", status="current", listPrice=421.00,
         bowlDepth="8 in", gauge="18 gauge", material="Type 304 stainless steel", drainSize="3.5 in",
         warrantyYears=5, effectiveDate="2022-09-01"),
    # Northwind Drains: floor drains and cleanouts
    dict(id="ND-415-A", brand="Northwind Drains", productLine="FloorGuard Drains", category="Floor drain",
         name="FloorGuard 4 in Round Floor Drain, nickel bronze strainer", status="current", listPrice=168.00,
         outletSize="2, 3 or 4 in (no-hub)", strainer="ND-415-AR", strainerMaterial="Nickel bronze",
         loadRating="Medium duty", warrantyYears=5, effectiveDate="2023-06-01"),
    dict(id="ND-415-AS", brand="Northwind Drains", productLine="FloorGuard Drains", category="Floor drain",
         name="FloorGuard 4 in Round Floor Drain with sediment bucket", status="current", listPrice=214.00,
         outletSize="2, 3 or 4 in (no-hub)", strainer="ND-415-AR", strainerMaterial="Nickel bronze",
         sedimentBucket="ND-415-SB", loadRating="Medium duty", warrantyYears=5, effectiveDate="2023-06-01"),
    dict(id="ND-515-A", brand="Northwind Drains", productLine="FloorGuard Drains", category="Floor drain",
         name="FloorGuard 5 in Round Floor Drain, nickel bronze strainer", status="current", listPrice=196.00,
         outletSize="2, 3 or 4 in (no-hub)", strainer="ND-515-AR", strainerMaterial="Nickel bronze",
         loadRating="Medium duty", warrantyYears=5, effectiveDate="2023-06-01"),
    dict(id="ND-600-CO", brand="Northwind Drains", productLine="FloorGuard Cleanouts", category="Cleanout",
         name="FloorGuard 6 in Round Floor Cleanout, nickel bronze cover", status="current", listPrice=142.00,
         outletSize="3 or 4 in (no-hub)", coverMaterial="Nickel bronze", loadRating="Heavy duty",
         warrantyYears=5, effectiveDate="2023-06-01"),
    # Service parts and kits
    dict(id="K-CF-1100-RK2", brand="Contoso Flow", productLine="AquaSense Flush Valves", category="Repair kit",
         name="AquaSense Diaphragm Repair Kit, generation 2 (fits CF-1100-XL, CF-1100-XLS, CF-1101-XL)",
         status="current", listPrice=38.50, fits=["CF-1100-XL", "CF-1100-XLS", "CF-1101-XL"],
         replaces="K-CF-1100-RK", warrantyYears=1, effectiveDate="2023-09-01"),
    dict(id="K-CF-1100-RK", brand="Contoso Flow", productLine="AquaSense Flush Valves", category="Repair kit",
         name="AquaSense Diaphragm Repair Kit, generation 1", status="discontinued", listPrice=34.00,
         fits=["CF-1101-XL"], replacedBy="K-CF-1100-RK2", discontinuedDate="2023-08-31", warrantyYears=1,
         effectiveDate="2019-03-01"),
    dict(id="K-CF-1250-CART", brand="Contoso Flow", productLine="ClearTouch Faucets", category="Repair kit",
         name="ClearTouch Ceramic Cartridge Kit", status="current", listPrice=29.00,
         fits=["CF-1250-M", "CF-1250-S", "CF-1250-SB"], warrantyYears=1, effectiveDate="2023-01-15"),
    dict(id="S-CF-IR3", brand="Contoso Flow", productLine="Sensors and Power", category="Sensor module",
         name="Infrared Sensor Module, generation 3", status="current", listPrice=118.00,
         fits=["CF-1100-XLS", "CF-1250-S", "CF-1250-SB"], warrantyYears=1, effectiveDate="2023-01-15"),
    dict(id="B-CF-4AA", brand="Contoso Flow", productLine="Sensors and Power", category="Battery pack",
         name="Battery Pack, 4 x AA holder", status="current", listPrice=22.00,
         fits=["CF-1100-XLS", "CF-1250-SB"], warrantyYears=1, effectiveDate="2023-01-15"),
    dict(id="P-CF-24V", brand="Contoso Flow", productLine="Sensors and Power", category="Power supply",
         name="Plug-in Power Supply 24 VDC", status="current", listPrice=46.00,
         fits=["CF-1250-S"], warrantyYears=1, effectiveDate="2023-01-15"),
    dict(id="K-FX-2200-FLT", brand="Fabrikam Fixtures", productLine="HydroFill Stations", category="Filter",
         name="HydroFill Replacement Filter, 3,000 gallons", status="current", listPrice=74.00,
         fits=["FX-2200-B", "FX-2200-BR"], warrantyYears=1, effectiveDate="2025-02-01"),
    dict(id="K-FX-2210-FLT", brand="Fabrikam Fixtures", productLine="HydroFill Stations", category="Filter",
         name="HydroFill Classic Replacement Filter, 1,500 gallons", status="current", listPrice=58.00,
         fits=["FX-2210-B"], warrantyYears=1, effectiveDate="2018-05-01"),
    dict(id="ND-415-AR", brand="Northwind Drains", productLine="FloorGuard Drains", category="Strainer",
         name="FloorGuard 4 in Replacement Strainer, nickel bronze", status="current", listPrice=41.00,
         fits=["ND-415-A", "ND-415-AS"], warrantyYears=1, effectiveDate="2023-06-01"),
    dict(id="ND-515-AR", brand="Northwind Drains", productLine="FloorGuard Drains", category="Strainer",
         name="FloorGuard 5 in Replacement Strainer, nickel bronze", status="current", listPrice=48.00,
         fits=["ND-515-A"], warrantyYears=1, effectiveDate="2023-06-01"),
    dict(id="ND-415-SB", brand="Northwind Drains", productLine="FloorGuard Drains", category="Sediment bucket",
         name="FloorGuard 4 in Sediment Bucket", status="current", listPrice=33.00,
         fits=["ND-415-AS"], warrantyYears=1, effectiveDate="2023-06-01"),
]

# Fictional competitor equivalents. competitorPartNumber is the lookup key.
CROSS_REFERENCE = [
    dict(id="LITWARE-L-9450", competitorBrand="Litware", competitorPartNumber="L-9450",
         competitorDescription="Manual flush valve 1.28 gpf, 1 in inlet", contosoPartNumber="CF-1100-XL",
         matchType="Functional equivalent", notes="Same rough-in. Contoso kit K-CF-1100-RK2 does not fit Litware valves."),
    dict(id="LITWARE-L-9450-S", competitorBrand="Litware", competitorPartNumber="L-9450-S",
         competitorDescription="Sensor flush valve 1.28 gpf", contosoPartNumber="CF-1100-XLS",
         matchType="Functional equivalent", notes="Litware uses a 6 VDC sensor; Contoso uses S-CF-IR3 with B-CF-4AA."),
    dict(id="LITWARE-L-9460", competitorBrand="Litware", competitorPartNumber="L-9460",
         competitorDescription="Manual flush valve 1.6 gpf", contosoPartNumber="CF-1100-XL",
         matchType="Nearest current equivalent",
         notes="Contoso 1.6 gpf model CF-1101-XL was discontinued 2024-06-30. Recommend CF-1100-XL (1.28 gpf)."),
    dict(id="TAILSPIN-TS-BF200", competitorBrand="Tailspin", competitorPartNumber="TS-BF200",
         competitorDescription="Bottle filling station, non-refrigerated", contosoPartNumber="FX-2200-B",
         matchType="Functional equivalent", notes="Tailspin filter is not interchangeable with K-FX-2200-FLT."),
    dict(id="TAILSPIN-TS-BF200R", competitorBrand="Tailspin", competitorPartNumber="TS-BF200R",
         competitorDescription="Bottle filling station, refrigerated", contosoPartNumber="FX-2200-BR",
         matchType="Functional equivalent", notes=""),
    dict(id="WOODGROVE-WG-FD4", competitorBrand="Woodgrove", competitorPartNumber="WG-FD4",
         competitorDescription="4 in round floor drain, nickel bronze top", contosoPartNumber="ND-415-A",
         matchType="Functional equivalent", notes="Woodgrove strainer bolt pattern differs; use ND-415-AR only on Contoso bodies."),
    dict(id="WOODGROVE-WG-FD4-SB", competitorBrand="Woodgrove", competitorPartNumber="WG-FD4-SB",
         competitorDescription="4 in round floor drain with sediment bucket", contosoPartNumber="ND-415-AS",
         matchType="Functional equivalent", notes=""),
    dict(id="WOODGROVE-WG-CO6", competitorBrand="Woodgrove", competitorPartNumber="WG-CO6",
         competitorDescription="6 in round floor cleanout", contosoPartNumber="ND-600-CO",
         matchType="Functional equivalent", notes=""),
    dict(id="LITWARE-LF-500", competitorBrand="Litware", competitorPartNumber="LF-500",
         competitorDescription="Sensor lavatory faucet, hardwired", contosoPartNumber="CF-1250-S",
         matchType="Functional equivalent", notes="Battery version equivalent is CF-1250-SB."),
]


# ---------------------------------------------------------------------------
# 2. Documents
# ---------------------------------------------------------------------------

# Where content comes from, and how much it should be trusted when two sources disagree.
# Tier 1 is official and current, 2 is curated support content, 3 is an internal copy that may
# lag the official version, 4 is an archive, 5 is user generated. The folder a document lives in
# decides its default source; a document can override it (the SharePoint copy trap below).
SOURCES = {
    "website":    {"tier": 1, "label": "Contoso brand websites"},
    "helpcenter": {"tier": 2, "label": "Customer Care help center"},
    "sharepoint": {"tier": 3, "label": "SharePoint, Engineering library"},
    "archive":    {"tier": 4, "label": "Archived website"},
    "community":  {"tier": 5, "label": "Community forum"},
}
FOLDER_SOURCE = {"current": "website", "archive": "archive", "community": "community"}


def front_matter(doc_id, title, brand, doc_type, status, effective_date, part_numbers, source_url,
                 source="website", is_canonical=True):
    return (
        "---\n"
        f"doc_id: {doc_id}\n"
        f"title: {title}\n"
        f"brand: {brand}\n"
        f"doc_type: {doc_type}\n"
        f"status: {status}\n"
        f"effective_date: {effective_date}\n"
        f"part_numbers: {json.dumps(part_numbers)}\n"
        f"source: {source}\n"
        f"source_tier: {SOURCES[source]['tier']}\n"
        f"is_canonical: {'true' if is_canonical else 'false'}\n"
        f"source_url: {source_url}\n"
        "---\n\n"
    )


def spec_sheet(p, status="current", effective=None, price=None, kit=None, extra_rows=None, intro_extra=""):
    """Long-form spec sheet. Intro text first, then the table, so that naive
    fixed-size chunking separates the table from the part number."""
    effective = effective or p["effectiveDate"]
    price = price if price is not None else p["listPrice"]
    kit = kit or p.get("repairKit") or p.get("filter") or p.get("strainer") or "n/a"
    rows = [
        ("Model", p["id"]),
        ("Description", p["name"]),
        ("Brand", p["brand"]),
        ("Product line", p["productLine"]),
    ]
    for key, label in [
        ("flowRate", "Flow rate"), ("fillRate", "Fill rate"), ("inletSize", "Inlet size"),
        ("roughIn", "Rough-in (centerline of supply to finished wall)"), ("spoutHeight", "Spout height"),
        ("finish", "Finish"), ("filterCapacity", "Filter capacity"), ("chillerCapacity", "Chiller capacity"),
        ("mounting", "Mounting"), ("bowlDepth", "Bowl depth"), ("gauge", "Gauge"), ("material", "Material"),
        ("drainSize", "Drain opening"), ("outletSize", "Outlet size"), ("strainerMaterial", "Strainer material"),
        ("coverMaterial", "Cover material"), ("loadRating", "Load rating"),
    ]:
        if key in p:
            rows.append((label, p[key]))
    rows.append(("Repair kit / consumable", kit))
    for key, label in [("sensorModule", "Sensor module"), ("batteryPack", "Battery pack"),
                       ("powerSupply", "Power supply"), ("sedimentBucket", "Sediment bucket")]:
        if key in p:
            rows.append((label, p[key]))
    rows.append(("Warranty", f"{p['warrantyYears']} years, see current Contoso Water Solutions warranty policy"))
    rows.append(("List price (USD)", f"${price:,.2f}"))
    if extra_rows:
        rows.extend(extra_rows)
    table = "| Attribute | Value |\n|---|---|\n" + "\n".join(f"| {a} | {b} |" for a, b in rows)

    intro = (
        f"# {p['name']}\n\n"
        f"Specification sheet for the {p['brand']} {p['productLine']} model {p['id']}.\n\n"
        "## Overview\n\n"
        f"The {p['name']} is designed for commercial and institutional installations where "
        "durability, water efficiency and ease of maintenance matter. It ships with all mounting "
        "hardware and is compatible with standard North American supply and waste connections. "
        "The product is tested to the applicable ASME A112 and CSA B125 requirements and carries the "
        "Contoso Water Solutions commercial warranty. Consult the installation guide for the product "
        "line before rough-in, and always confirm the model suffix on the carton label, because "
        "models within a line share the same body and differ only in the suffix. "
        f"{intro_extra}\n\n"
        "## Ordering information\n\n"
        f"Order using the full model number, {p['id']}, including the suffix. Replacement parts are "
        "listed in the table below and in the service parts catalog. For competitor equivalents "
        "use the Contoso cross reference guide.\n\n"
        "## Specifications\n\n"
    )
    return intro + table + "\n"


def write_docs():
    docs = []
    P = {p["id"]: p for p in PARTS}

    def add(folder, doc_id, title, brand, doc_type, status, effective, parts, body, source=None, is_canonical=None):
        source = source or FOLDER_SOURCE[folder]
        if is_canonical is None:
            is_canonical = status == "current" and SOURCES[source]["tier"] <= 2
        host = {"website": "www.contoso-water.example", "helpcenter": "help.contoso-water.example",
                "sharepoint": "contoso.sharepoint.example/sites/engineering",
                "archive": "archive.contoso-water.example", "community": "community.contoso-water.example"}[source]
        url = f"https://{host}/{doc_id}"
        path = os.path.join(DATA, "docs", folder, f"{doc_id}.md")
        w(path, front_matter(doc_id, title, brand, doc_type, status, effective, parts, url, source, is_canonical) + body)
        docs.append(dict(doc_id=doc_id, folder=folder, status=status, doc_type=doc_type, source=source))

    # --- Current spec sheets ---
    for pid in ["CF-1100-XL", "CF-1100-XLS", "CF-1250-M", "CF-1250-S", "CF-1250-SB",
                "FX-2200-B", "FX-2200-BR", "FX-3100", "FX-3100-D",
                "ND-415-A", "ND-415-AS", "ND-515-A", "ND-600-CO"]:
        p = P[pid]
        extra = ""
        if pid == "CF-1100-XL":
            extra = "This model replaces the 1.6 gpf CF-1101-XL, which was discontinued on June 30, 2024."
        if pid == "CF-1100-XLS":
            extra = ("The sensor version uses the generation 3 infrared module S-CF-IR3 and a 4 x AA battery pack. "
                     "It shares the diaphragm repair kit with the manual CF-1100-XL.")
        if pid == "FX-2200-B":
            extra = "This model replaces the HydroFill Classic FX-2210-B and uses a larger 3,000 gallon filter."
        add("current", f"spec-{pid}", f"Specification sheet {pid}", p["brand"], "spec_sheet", "current",
            p["effectiveDate"], [pid] + [v for k, v in p.items() if k in ("repairKit", "filter", "strainer", "sensorModule", "batteryPack", "powerSupply", "sedimentBucket")],
            spec_sheet(p, intro_extra=extra))

    # --- Archived spec sheets (stale traps) ---
    p = dict(P["CF-1101-XL"])
    add("archive", "spec-CF-1101-XL-2019", "Specification sheet CF-1101-XL (2019)", p["brand"], "spec_sheet",
        "archived", "2019-03-01", ["CF-1101-XL", "K-CF-1100-RK"],
        spec_sheet(p, status="archived", effective="2019-03-01", price=385.00, kit="K-CF-1100-RK",
                   intro_extra="This is the standard 1.6 gpf AquaSense valve for new construction and retrofit."))
    p = dict(P["FX-2210-B"])
    add("archive", "spec-FX-2210-B-2018", "Specification sheet FX-2210-B (2018)", p["brand"], "spec_sheet",
        "archived", "2018-05-01", ["FX-2210-B", "K-FX-2210-FLT"],
        spec_sheet(p, status="archived", effective="2018-05-01", price=1_090.00, kit="K-FX-2210-FLT"))
    # An archived copy of the CF-1100-XL sheet with the OLD price and OLD kit: same part number, stale values.
    p = dict(P["CF-1100-XL"])
    add("archive", "spec-CF-1100-XL-2022", "Specification sheet CF-1100-XL (2022)", p["brand"], "spec_sheet",
        "archived", "2022-01-10", ["CF-1100-XL", "K-CF-1100-RK"],
        spec_sheet(p, status="archived", effective="2022-01-10", price=368.00, kit="K-CF-1100-RK",
                   intro_extra="Early production units of the 1.28 gpf valve used the generation 1 repair kit."))

    # --- Install guides ---
    add("current", "install-CF-1100-series", "Installation guide, AquaSense CF-1100 series", "Contoso Flow",
        "install_guide", "current", "2024-07-01", ["CF-1100-XL", "CF-1100-XLS", "K-CF-1100-RK2", "S-CF-IR3", "B-CF-4AA"], """
# Installation guide, AquaSense CF-1100 series flush valves

Applies to CF-1100-XL (manual) and CF-1100-XLS (sensor). Revision 2024-07.

## Before you start

1. Confirm the model suffix on the carton. XL is manual, XLS is sensor operated.
2. Supply pressure must be between 25 and 80 psi flowing. Install a pressure reducing valve above 80 psi.
3. Rough-in is 11.5 in from the centerline of the supply stop to the finished wall for both models.
4. Flush the supply line before connecting the valve. Debris is the leading cause of a valve that runs continuously.

## Installing the valve body

1. Apply thread sealant to the 1 in supply stop and thread the control stop into the wall supply.
2. Slide the tailpiece and vacuum breaker into the fixture spud and hand tighten the coupling.
3. Align the valve body, then tighten the couplings with a smooth jaw wrench. Do not over tighten.
4. Open the control stop slowly and check for leaks.

## Sensor models (CF-1100-XLS)

1. Insert four AA batteries in the B-CF-4AA holder. Expected battery life is three years at 4,000 cycles per month.
2. The S-CF-IR3 sensor range is factory set to 24 in. To adjust, hold the range button for five seconds and follow the LED pattern.
3. A blinking red LED every four seconds means the batteries are below 20 percent.

## Servicing

Use repair kit K-CF-1100-RK2 for both models. The generation 1 kit K-CF-1100-RK is no longer supplied and should not be used on valves manufactured after September 2023 because the diaphragm relief hole diameter changed.

| Symptom | Likely cause | Action |
|---|---|---|
| Valve runs continuously | Debris under diaphragm | Close stop, clean or replace with K-CF-1100-RK2 |
| Short flush | Low supply pressure | Verify 25 psi flowing minimum |
| No flush on sensor model | Batteries depleted | Replace B-CF-4AA batteries |
| Sensor does not detect user | Range set too short | Adjust S-CF-IR3 range |
""")

    add("archive", "install-CF-1100-series-2020", "Installation guide, AquaSense CF-1100 series (2020)", "Contoso Flow",
        "install_guide", "archived", "2020-02-01", ["CF-1100-XL", "CF-1101-XL", "K-CF-1100-RK"], """
# Installation guide, AquaSense CF-1100 series flush valves

Applies to CF-1101-XL (1.6 gpf) and CF-1100-XL (1.28 gpf). Revision 2020-02.

## Before you start

1. Supply pressure must be between 20 and 80 psi flowing.
2. Rough-in is 11.5 in from the centerline of the supply stop to the finished wall.

## Servicing

Use repair kit K-CF-1100-RK for all AquaSense valves. The kit contains the diaphragm, relief valve and guide assembly.

| Symptom | Likely cause | Action |
|---|---|---|
| Valve runs continuously | Debris under diaphragm | Close stop, clean or replace with K-CF-1100-RK |
| Short flush | Low supply pressure | Verify 20 psi flowing minimum |
""")

    add("current", "install-FX-2200-series", "Installation guide, HydroFill FX-2200 series", "Fabrikam Fixtures",
        "install_guide", "current", "2025-02-01", ["FX-2200-B", "FX-2200-BR", "K-FX-2200-FLT"], """
# Installation guide, HydroFill FX-2200 series bottle filling stations

Applies to FX-2200-B (non-refrigerated) and FX-2200-BR (refrigerated). Revision 2025-02.

## Rough-in

1. Mount the in-wall carrier so the bottle filler nozzle is 42 in above the finished floor for accessibility.
2. Provide a 3/8 in cold water supply with a shutoff and a 1.25 in drain.
3. FX-2200-BR requires a dedicated 115 VAC, 15 A circuit with a GFCI receptacle inside the cabinet.

## Filter

Install the K-FX-2200-FLT filter before first use and flush two gallons through the unit. Replace the filter every 3,000 gallons or 12 months, whichever comes first. The filter status LED turns yellow at 90 percent of capacity and red at 100 percent. Reset the counter by holding the filter button for ten seconds after replacement.

## Refrigerated model (FX-2200-BR)

The chiller delivers 8 gallons per hour of 50 F water at 90 F ambient. Allow 4 in of clearance behind the cabinet for airflow. Do not install the refrigerated model in an unconditioned space below 40 F.

## Green ticker

The bottle counter estimates plastic bottles saved at 20 fl oz per fill. It can be reset from the service menu.
""")

    # --- Warranty policies ---
    # Policies are about product families, not individual parts, so their part_numbers list
    # is empty on purpose. Listing every product here would put every part number into the
    # contextual header of every warranty chunk, and any part number query would then match
    # the (fresh, current, heavily boosted) warranty document first. That is exactly the
    # "general catalog page that mentions everything" problem seen in real indexes.
    add("current", "warranty-policy-2026", "Contoso Water Solutions commercial warranty policy (2026)", "Contoso Water Solutions",
        "warranty", "current", "2026-01-01", [], """
# Contoso Water Solutions commercial warranty policy

Effective January 1, 2026. Supersedes the 2021 policy for products shipped on or after the effective date.

## Coverage periods

| Product family | Brand | Warranty period |
|---|---|---|
| AquaSense flush valves (CF-1100 series) | Contoso Flow | 3 years |
| ClearTouch faucets (CF-1250 series) | Contoso Flow | 3 years |
| Sensor modules, battery packs and power supplies | Contoso Flow | 1 year |
| HydroFill bottle filling stations (FX-2200 series) | Fabrikam Fixtures | 5 years (chiller compressor 5 years) |
| SteelCare sinks (FX-3100 series) | Fabrikam Fixtures | 5 years |
| FloorGuard drains and cleanouts (ND series) | Northwind Drains | 5 years |
| Repair kits, filters, strainers and consumables | All brands | 1 year |

## What is covered

Contoso Water Solutions warrants products to be free from defects in material and workmanship under normal commercial use. The remedy is repair or replacement of the product or component at Contoso's option. Labor is not covered unless the product is registered within 90 days of installation, in which case reasonable labor is covered for the first year.

## What is not covered

Damage from debris, water hammer, freezing, chemical cleaners, installation not in accordance with the installation guide, or use of non-Contoso repair parts.

## How to file a claim

Contact Customer Care with the model number, date code from the product label, installation date and a description of the failure. Photographs speed up the review. Claims are normally answered within two business days.
""")

    add("archive", "warranty-policy-2021", "Contoso Water Solutions commercial warranty policy (2021)", "Contoso Water Solutions",
        "warranty", "archived", "2021-01-01", [], """
# Contoso Water Solutions commercial warranty policy

Effective January 1, 2021.

## Coverage periods

| Product family | Brand | Warranty period |
|---|---|---|
| AquaSense flush valves | Contoso Flow | 3 years |
| ClearTouch faucets | Contoso Flow | 2 years |
| HydroFill bottle filling stations | Fabrikam Fixtures | 3 years (chiller compressor 1 year) |
| SteelCare sinks | Fabrikam Fixtures | 5 years |
| FloorGuard drains and cleanouts | Northwind Drains | 3 years |
| Repair kits and consumables | All brands | 90 days |

## What is covered

Products are warranted against defects in material and workmanship. Labor is never covered under this policy.
""")

    # --- Bulletins and FAQ ---
    add("current", "bulletin-2024-07-CF-1101-XL", "Product bulletin: CF-1101-XL discontinued, replaced by CF-1100-XL", "Contoso Flow",
        "bulletin", "current", "2024-07-01", ["CF-1101-XL", "CF-1100-XL", "K-CF-1100-RK", "K-CF-1100-RK2"], """
# Product bulletin PB-2024-07: AquaSense CF-1101-XL discontinued

Effective June 30, 2024 the 1.6 gpf AquaSense manual flush valve CF-1101-XL is discontinued. The direct replacement is CF-1100-XL (1.28 gpf). Rough-in, inlet size and finish are unchanged, so no wall modification is needed for retrofit.

Existing CF-1101-XL valves remain serviceable. Use repair kit K-CF-1100-RK2. The generation 1 kit K-CF-1100-RK was discontinued August 31, 2023 and remaining stock should not be used on valves manufactured after September 2023.

Orders received for CF-1101-XL after the effective date will be converted to CF-1100-XL unless the customer objects.
""")

    add("current", "faq-contoso-flow", "Frequently asked questions, Contoso Flow", "Contoso Flow",
        "faq", "current", "2025-06-01", ["CF-1100-XL", "CF-1100-XLS", "CF-1250-S", "CF-1250-SB", "K-CF-1100-RK2", "K-CF-1250-CART"], source="helpcenter", body="""
# Frequently asked questions, Contoso Flow

## Which repair kit fits my AquaSense valve?

All current AquaSense valves (CF-1100-XL and CF-1100-XLS) and the discontinued CF-1101-XL use kit K-CF-1100-RK2. If you have old stock of K-CF-1100-RK, do not use it on valves manufactured after September 2023.

## How do I tell the manual and sensor valves apart?

The suffix XL is manual and XLS is sensor operated. The body is the same. The sensor model adds the S-CF-IR3 module and a B-CF-4AA battery pack.

## What is the difference between CF-1250-S and CF-1250-SB?

Both are ClearTouch sensor faucets. S is hardwired with the P-CF-24V power supply. SB runs on the B-CF-4AA battery pack. Both use the K-CF-1250-CART cartridge.

## Can I convert a manual CF-1100-XL to a sensor valve?

No. Order CF-1100-XLS. The body castings are the same but the sensor cover and solenoid are not sold as a retrofit.

## My flush valve runs continuously. What should I check?

Close the control stop, remove the cover and inspect the diaphragm for debris. Replace with K-CF-1100-RK2 if the relief hole is blocked or the diaphragm is deformed.
""")

    add("current", "cross-reference-guide", "Competitor cross reference guide", "Contoso Water Solutions",
        "cross_reference", "current", "2025-09-01", sorted({x["contosoPartNumber"] for x in CROSS_REFERENCE}), """
# Competitor cross reference guide

Use this guide to find the Contoso Water Solutions equivalent of a competitor part. Equivalents are functional matches, not drop-in replacements for service parts: repair kits, filters and strainers are never interchangeable across manufacturers.

| Competitor | Competitor part | Description | Contoso equivalent | Match type |
|---|---|---|---|---|
""" + "\n".join(
        f"| {x['competitorBrand']} | {x['competitorPartNumber']} | {x['competitorDescription']} | {x['contosoPartNumber']} | {x['matchType']} |"
        for x in CROSS_REFERENCE) + """

## Notes

* Litware L-9460 (1.6 gpf) has no current 1.6 gpf Contoso equivalent. CF-1101-XL was discontinued in 2024; recommend CF-1100-XL.
* Woodgrove floor drain strainers use a different bolt pattern. ND-415-AR fits only Contoso bodies.
* Tailspin filters do not fit HydroFill stations.
""")

    add("current", "service-parts-ND-series", "Service parts, FloorGuard ND series", "Northwind Drains",
        "service_parts", "current", "2023-06-01", ["ND-415-A", "ND-415-AS", "ND-515-A", "ND-600-CO", "ND-415-AR", "ND-515-AR", "ND-415-SB"], """
# Service parts, FloorGuard ND series drains and cleanouts

| Drain model | Replacement strainer or cover | Sediment bucket | Outlet options |
|---|---|---|---|
| ND-415-A | ND-415-AR | not applicable | 2, 3 or 4 in no-hub |
| ND-415-AS | ND-415-AR | ND-415-SB | 2, 3 or 4 in no-hub |
| ND-515-A | ND-515-AR | not applicable | 2, 3 or 4 in no-hub |
| ND-600-CO | ND-600-COV | not applicable | 3 or 4 in no-hub |

Strainers are nickel bronze and secured with two vandal resistant screws. The 4 in strainer ND-415-AR does not fit the 5 in body ND-515-A even though the bolt pattern looks similar; the outer diameter differs by one inch.
""")

    # --- Duplicate at an older revision (the SharePoint trap) ---
    # A genuine internal copy of the FX-2200-B spec sheet, saved in the engineering library
    # before the 2025 filter change. It is not archived (nobody marked it), it is not wrong on
    # purpose, it is simply not the canonical copy. Only a canonical-source rule separates it
    # from the website version. Its status is 'current', so a status filter does not catch it.
    # Same title, same prose, same part number as the website copy. Only the table values
    # (filter, capacity, price) and the effective date differ, which is what a real duplicate
    # at an older revision looks like. Nothing in the text tells a ranker which copy to prefer.
    p = dict(P["FX-2200-B"], filterCapacity="1,500 gallons or 6 months", filter="K-FX-2210-FLT")
    add("current", "spec-FX-2200-B-sharepoint", "Specification sheet FX-2200-B", p["brand"],
        "spec_sheet", "current", "2023-04-10", ["FX-2200-B", "K-FX-2210-FLT"],
        spec_sheet(p, effective="2023-04-10", price=1_180.00, kit="K-FX-2210-FLT",
                   intro_extra="This model replaces the HydroFill Classic FX-2210-B."),
        source="sharepoint", is_canonical=False)

    # --- Community posts (user generated, not authoritative) ---
    add("community", "forum-2022-cf1100-repair-kit", "Forum: Which repair kit for CF-1100-XL?", "Contoso Flow",
        "community_post", "community", "2022-04-18", ["CF-1100-XL", "K-CF-1100-RK"], """
# Forum thread: Which repair kit for CF-1100-XL?

**plumber_mike_wi** (April 2022): Have a CF1100XL running constantly in a school restroom. Which kit do I order?

**jdoe_facilities** (April 2022): K-CF-1100-RK worked for me on a dozen of these. Same kit as the old 1.6 gallon valves. Takes ten minutes.

**plumber_mike_wi** (April 2022): Thanks, ordered the RK kit.

**tstark_supply** (May 2022): Confirming RK is the right one, we stock it for all AquaSense.
""")

    add("community", "forum-2023-fx2200-filter-interval", "Forum: FX-2200-B filter change interval?", "Fabrikam Fixtures",
        "community_post", "community", "2023-03-02", ["FX-2200-B", "K-FX-2200-FLT"], """
# Forum thread: FX-2200-B filter change interval?

**campus_maint** (March 2023): How often do you change the filter on the FX 2200 B? The yellow light came on after about 5 months.

**bottlefiller_fan** (March 2023): We do every 6 months on all our HydroFills, same as the old Classic units. Never had a problem.

**campus_maint** (March 2023): OK, will put it on a 6 month schedule.
""")

    add("community", "forum-2024-nd415-install-tip", "Forum: ND-415-A install tip", "Northwind Drains",
        "community_post", "community", "2024-09-11", ["ND-415-A", "ND-415-AR"], """
# Forum thread: ND-415-A install tip

**drainguy** (September 2024): Tip for the ND-415-A. Set the strainer 1/8 in below the finished floor so the slope actually drains. Also the strainer ND-415-AR screws strip if you use an impact driver, hand tighten only.

**facilities_sam** (September 2024): Agreed on hand tightening. We also keep a couple of ND-415-AR on the shelf, they get damaged by floor machines.
""")

    return docs


# ---------------------------------------------------------------------------
# 3. Evaluation set
# ---------------------------------------------------------------------------

EVAL = [
    # part number lookup, look-alike traps
    dict(id="q01", category="part_lookup", question="What repair kit fits the CF-1100-XLS?",
         expected_part_numbers=["K-CF-1100-RK2"], expected_doc_ids=["spec-CF-1100-XLS", "faq-contoso-flow", "install-CF-1100-series"],
         must_contain=["K-CF-1100-RK2"], must_not_contain=["K-CF-1100-RK"],
         expected_answer="K-CF-1100-RK2"),
    dict(id="q02", category="part_lookup", question="Which sensor module does the CF-1100-XLS use?",
         expected_part_numbers=["S-CF-IR3"], expected_doc_ids=["spec-CF-1100-XLS", "install-CF-1100-series", "faq-contoso-flow"],
         must_contain=["S-CF-IR3"], must_not_contain=[],
         expected_answer="S-CF-IR3 infrared sensor module, generation 3"),
    dict(id="q03", category="part_lookup", question="What is the list price of the CF-1100-XL?",
         expected_part_numbers=["CF-1100-XL"], expected_doc_ids=["spec-CF-1100-XL"],
         must_contain=["412"], must_not_contain=["368", "385"],
         expected_answer="$412.00"),
    dict(id="q04", category="part_lookup", question="What is the flow rate of the CF-1100-XL?",
         expected_part_numbers=["CF-1100-XL"], expected_doc_ids=["spec-CF-1100-XL", "bulletin-2024-07-CF-1101-XL"],
         must_contain=["1.28"], must_not_contain=["1.6 gpf"],
         expected_answer="1.28 gpf"),
    dict(id="q05", category="part_lookup", question="Is the CF-1101-XL still available?",
         expected_part_numbers=["CF-1101-XL", "CF-1100-XL"], expected_doc_ids=["bulletin-2024-07-CF-1101-XL", "spec-CF-1100-XL"],
         must_contain=["discontinued", "CF-1100-XL"], must_not_contain=[],
         expected_answer="No, discontinued June 30, 2024, replaced by CF-1100-XL"),
    dict(id="q06", category="part_lookup", question="Which cartridge kit do I order for a CF-1250-SB faucet?",
         expected_part_numbers=["K-CF-1250-CART"], expected_doc_ids=["spec-CF-1250-SB", "faq-contoso-flow"],
         must_contain=["K-CF-1250-CART"], must_not_contain=[],
         expected_answer="K-CF-1250-CART"),
    dict(id="q07", category="part_lookup", question="What power supply does the CF-1250-S need?",
         expected_part_numbers=["P-CF-24V"], expected_doc_ids=["spec-CF-1250-S", "faq-contoso-flow"],
         must_contain=["P-CF-24V"], must_not_contain=[],
         expected_answer="P-CF-24V plug-in 24 VDC power supply"),
    dict(id="q08", category="part_lookup", question="Replacement strainer for ND-515-A?",
         expected_part_numbers=["ND-515-AR"], expected_doc_ids=["spec-ND-515-A", "service-parts-ND-series"],
         must_contain=["ND-515-AR"], must_not_contain=[],
         expected_answer="ND-515-AR"),
    dict(id="q09", category="part_lookup", question="Does the ND-415-AR strainer fit the ND-515-A?",
         expected_part_numbers=["ND-415-AR", "ND-515-A", "ND-515-AR"], expected_doc_ids=["service-parts-ND-series"],
         must_contain=["ND-515-AR"], must_not_contain=[],
         expected_answer="No, the outer diameter differs by one inch; use ND-515-AR"),
    dict(id="q10", category="part_lookup", question="What sediment bucket goes with the ND-415-AS?",
         expected_part_numbers=["ND-415-SB"], expected_doc_ids=["spec-ND-415-AS", "service-parts-ND-series"],
         must_contain=["ND-415-SB"], must_not_contain=[],
         expected_answer="ND-415-SB"),
    # part number formatting variations
    dict(id="q11", category="part_format", question="repair kit for cf1100xls",
         expected_part_numbers=["K-CF-1100-RK2"], expected_doc_ids=["spec-CF-1100-XLS", "faq-contoso-flow", "install-CF-1100-series"],
         must_contain=["K-CF-1100-RK2"], must_not_contain=[],
         expected_answer="K-CF-1100-RK2"),
    dict(id="q12", category="part_format", question="What filter does the FX 2200 BR take?",
         expected_part_numbers=["K-FX-2200-FLT"], expected_doc_ids=["spec-FX-2200-BR", "install-FX-2200-series"],
         must_contain=["K-FX-2200-FLT"], must_not_contain=["K-FX-2210-FLT"],
         expected_answer="K-FX-2200-FLT"),
    dict(id="q13", category="part_format", question="price of ND415A",
         expected_part_numbers=["ND-415-A"], expected_doc_ids=["spec-ND-415-A"],
         must_contain=["168"], must_not_contain=[],
         expected_answer="$168.00"),
    # spec values inside tables
    dict(id="q14", category="spec_value", question="What is the rough-in for the CF-1100-XLS?",
         expected_part_numbers=["CF-1100-XLS"], expected_doc_ids=["spec-CF-1100-XLS", "install-CF-1100-series"],
         must_contain=["11.5"], must_not_contain=[],
         expected_answer="11.5 in from centerline of supply to finished wall"),
    dict(id="q15", category="spec_value", question="What supply pressure range does the CF-1100 series require?",
         expected_part_numbers=["CF-1100-XL", "CF-1100-XLS"], expected_doc_ids=["install-CF-1100-series"],
         must_contain=["25", "80"], must_not_contain=["20 psi", "20 to 80"],
         expected_answer="25 to 80 psi flowing"),
    dict(id="q16", category="spec_value", question="How many gallons per hour does the FX-2200-BR chiller deliver?",
         expected_part_numbers=["FX-2200-BR"], expected_doc_ids=["spec-FX-2200-BR", "install-FX-2200-series"],
         must_contain=["8"], must_not_contain=[],
         expected_answer="8 gph of 50 F water at 90 F ambient"),
    dict(id="q17", category="spec_value", question="What is the bowl depth of the FX-3100-D sink?",
         expected_part_numbers=["FX-3100-D"], expected_doc_ids=["spec-FX-3100-D"],
         must_contain=["8 in"], must_not_contain=[],
         expected_answer="8 in"),
    dict(id="q18", category="spec_value", question="What outlet sizes are available on the ND-600-CO cleanout?",
         expected_part_numbers=["ND-600-CO"], expected_doc_ids=["spec-ND-600-CO", "service-parts-ND-series"],
         must_contain=["3", "4"], must_not_contain=[],
         expected_answer="3 or 4 in no-hub"),
    dict(id="q19", category="spec_value", question="How high should the FX-2200-B nozzle be above the finished floor?",
         expected_part_numbers=["FX-2200-B"], expected_doc_ids=["install-FX-2200-series"],
         must_contain=["42"], must_not_contain=[],
         expected_answer="42 in"),
    # cross reference
    dict(id="q20", category="cross_reference", question="What is the Contoso equivalent of Litware L-9450?",
         expected_part_numbers=["CF-1100-XL"], expected_doc_ids=["cross-reference-guide"],
         must_contain=["CF-1100-XL"], must_not_contain=[],
         expected_answer="CF-1100-XL"),
    dict(id="q21", category="cross_reference", question="Customer has a Tailspin TS-BF200R. What do we offer?",
         expected_part_numbers=["FX-2200-BR"], expected_doc_ids=["cross-reference-guide"],
         must_contain=["FX-2200-BR"], must_not_contain=[],
         expected_answer="FX-2200-BR"),
    dict(id="q22", category="cross_reference", question="Cross reference for Woodgrove WG-FD4-SB",
         expected_part_numbers=["ND-415-AS"], expected_doc_ids=["cross-reference-guide"],
         must_contain=["ND-415-AS"], must_not_contain=[],
         expected_answer="ND-415-AS"),
    dict(id="q23", category="cross_reference", question="Is there a Contoso replacement for the Litware L-9460 1.6 gpf valve?",
         expected_part_numbers=["CF-1100-XL"], expected_doc_ids=["cross-reference-guide", "bulletin-2024-07-CF-1101-XL"],
         must_contain=["CF-1100-XL"], must_not_contain=[],
         expected_answer="No current 1.6 gpf model; recommend CF-1100-XL (1.28 gpf)"),
    dict(id="q24", category="cross_reference", question="Will the K-CF-1100-RK2 kit fit a Litware L-9450 valve?",
         expected_part_numbers=["K-CF-1100-RK2"], expected_doc_ids=["cross-reference-guide"],
         must_contain=["not"], must_not_contain=[],
         expected_answer="No, service parts are never interchangeable across manufacturers"),
    # stale content traps: the correct answer exists only in current docs
    dict(id="q25", category="stale_trap", question="Which repair kit should I use on a CF-1100-XL manufactured in 2025?",
         expected_part_numbers=["K-CF-1100-RK2"], expected_doc_ids=["install-CF-1100-series", "faq-contoso-flow", "bulletin-2024-07-CF-1101-XL", "spec-CF-1100-XL"],
         must_contain=["K-CF-1100-RK2"], must_not_contain=[],
         expected_answer="K-CF-1100-RK2, not the generation 1 K-CF-1100-RK"),
    dict(id="q26", category="stale_trap", question="How often should the FX-2200-B filter be replaced?",
         expected_part_numbers=["K-FX-2200-FLT"], expected_doc_ids=["install-FX-2200-series", "spec-FX-2200-B"],
         must_contain=["3,000", "12 months"], must_not_contain=["6 month"],
         expected_answer="Every 3,000 gallons or 12 months, whichever comes first"),
    dict(id="q27", category="stale_trap", question="What is the warranty on HydroFill bottle filling stations?",
         expected_part_numbers=["FX-2200-B", "FX-2200-BR"], expected_doc_ids=["warranty-policy-2026", "spec-FX-2200-B"],
         must_contain=["5 year"], must_not_contain=["3 year"],
         expected_answer="5 years under the 2026 policy"),
    dict(id="q28", category="stale_trap", question="What is the warranty period for FloorGuard drains?",
         expected_part_numbers=["ND-415-A"], expected_doc_ids=["warranty-policy-2026", "spec-ND-415-A", "spec-ND-415-AS", "spec-ND-515-A", "spec-ND-600-CO"],
         must_contain=["5 year"], must_not_contain=["3 year"],
         expected_answer="5 years under the 2026 policy"),
    dict(id="q29", category="stale_trap", question="Is labor covered under the Contoso warranty?",
         expected_part_numbers=[], expected_doc_ids=["warranty-policy-2026"],
         must_contain=["90 days"], must_not_contain=["never covered"],
         expected_answer="Yes for the first year if the product is registered within 90 days of installation"),
    dict(id="q30", category="stale_trap", question="What is the minimum flowing supply pressure for a CF-1100-XL?",
         expected_part_numbers=["CF-1100-XL"], expected_doc_ids=["install-CF-1100-series"],
         must_contain=["25 psi"], must_not_contain=["20 psi"],
         expected_answer="25 psi flowing (the 2020 guide said 20 psi)"),
    # descriptive questions where vector search does fine
    dict(id="q31", category="descriptive", question="My flush valve keeps running and will not shut off. What should I check?",
         expected_part_numbers=["K-CF-1100-RK2"], expected_doc_ids=["faq-contoso-flow", "install-CF-1100-series"],
         must_contain=["diaphragm"], must_not_contain=[],
         expected_answer="Close the stop, inspect the diaphragm for debris, replace with K-CF-1100-RK2"),
    dict(id="q32", category="descriptive", question="What does a blinking red light on a sensor flush valve mean?",
         expected_part_numbers=["B-CF-4AA"], expected_doc_ids=["install-CF-1100-series"],
         must_contain=["batter"], must_not_contain=[],
         expected_answer="Batteries below 20 percent; replace the B-CF-4AA batteries"),
    dict(id="q33", category="descriptive", question="Can a refrigerated bottle filler be installed in an unheated loading dock?",
         expected_part_numbers=["FX-2200-BR"], expected_doc_ids=["install-FX-2200-series"],
         must_contain=["40"], must_not_contain=[],
         expected_answer="No, not below 40 F"),
    dict(id="q34", category="descriptive", question="How do I file a warranty claim?",
         expected_part_numbers=[], expected_doc_ids=["warranty-policy-2026"],
         must_contain=["model number"], must_not_contain=[],
         expected_answer="Contact Customer Care with model number, date code, installation date, description and photos"),
    dict(id="q35", category="descriptive", question="What is the difference between the CF-1250-S and CF-1250-SB?",
         expected_part_numbers=["CF-1250-S", "CF-1250-SB"], expected_doc_ids=["faq-contoso-flow", "spec-CF-1250-S", "spec-CF-1250-SB"],
         must_contain=["P-CF-24V", "B-CF-4AA"], must_not_contain=[],
         expected_answer="S is hardwired with P-CF-24V, SB is battery powered with B-CF-4AA"),
    dict(id="q36", category="stale_trap", question="What is the filter capacity of the FX-2200-B?",
         expected_part_numbers=["FX-2200-B", "K-FX-2200-FLT"], expected_doc_ids=["spec-FX-2200-B", "install-FX-2200-series"],
         must_contain=["3,000"], must_not_contain=["1,500"],
         expected_answer="3,000 gallons or 12 months (the SharePoint copy still says 1,500)"),
    dict(id="q37", category="stale_trap", question="What is the list price of the FX-2200-B?",
         expected_part_numbers=["FX-2200-B"], expected_doc_ids=["spec-FX-2200-B"],
         must_contain=["1,245"], must_not_contain=["1,180"],
         expected_answer="$1,245.00 (the SharePoint copy still says $1,180.00)"),
]


def main():
    w(os.path.join(DATA, "catalog", "parts.json"), json.dumps(PARTS, indent=2))
    w(os.path.join(DATA, "catalog", "cross_reference.json"), json.dumps(CROSS_REFERENCE, indent=2))
    docs = write_docs()
    w(os.path.join(DATA, "eval", "eval_set.jsonl"), "\n".join(json.dumps(q) for q in EVAL))

    # sanity checks: every expected doc exists, every expected part exists
    doc_ids = {d["doc_id"] for d in docs}
    part_ids = {p["id"] for p in PARTS}
    for q in EVAL:
        for d in q["expected_doc_ids"]:
            assert d in doc_ids, f"{q['id']} references unknown doc {d}"
        for p in q["expected_part_numbers"]:
            assert p in part_ids, f"{q['id']} references unknown part {p}"

    by_folder = {}
    for d in docs:
        by_folder[d["folder"]] = by_folder.get(d["folder"], 0) + 1
    print(f"parts: {len(PARTS)}  cross references: {len(CROSS_REFERENCE)}  eval questions: {len(EVAL)}")
    print("documents:", by_folder)
    print(f"generated on {date.today().isoformat()} into {DATA}")


if __name__ == "__main__":
    main()
