"""Generate the fictional Kestrel Supply Co. B2B policy PDFs and their manifest.

Run: uv run python scripts/generate_policies.py
Output: resources/policies/*.pdf + manifest.json (committed, so builds are reproducible)
"""
import json
from pathlib import Path

import pymupdf

OUT_DIR = Path(__file__).resolve().parents[1] / "resources" / "policies"
COMPANY = "Kestrel Supply Co. B.V."

POLICIES = [
    {
        "file": "KS-OPS-001_Shipping_and_Delivery_v3.0.pdf",
        "policy_id": "KS-OPS-001", "version": "3.0", "status": "valid", "effective_date": "2026-03-01",
        "title": "Shipping and Delivery Policy",
        "sections": [
            ("1. Order cut-off and dispatch",
             "Orders placed on the web store before 15:00 CET on a business day are dispatched the same day "
             "when all lines are in stock at the shipping warehouse. Orders placed after 15:00 CET are dispatched "
             "the next business day. Customers are served from their default warehouse: Rotterdam (NL) or Duisburg (DE)."),
            ("2. Shipping charges",
             "Shipping is free for orders with a net value of EUR 500 or more (excluding VAT). Orders below EUR 500 "
             "are charged a flat fee of EUR 25 for delivery to the Netherlands, Belgium and Germany, and EUR 45 for "
             "delivery to other EU countries. Pallet deliveries above 500 kg are quoted separately."),
            ("3. Delivery times",
             "Standard delivery takes 1-2 business days to the Netherlands, Belgium and Germany and 3-5 business days "
             "to other EU countries. Delivery times start from dispatch, not from order placement."),
            ("4. Backorders and partial shipments",
             "Lines that are out of stock are placed on backorder and shipped as soon as stock arrives. The expected "
             "date is based on the supplier lead time shown in the web store. Partial shipments of in-stock lines are "
             "sent at no extra charge; customers can request a single complete shipment instead."),
        ],
    },
    {
        # Superseded by v3.0. Kept on disk to prove retired documents never reach the index.
        "file": "KS-OPS-001_Shipping_and_Delivery_v2.0_RETIRED.pdf",
        "policy_id": "KS-OPS-001", "version": "2.0", "status": "invalid", "effective_date": "2025-01-01",
        "title": "Shipping and Delivery Policy (superseded)",
        "sections": [
            ("1. Order cut-off and dispatch",
             "Orders placed before 14:00 CET are dispatched the same day when all lines are in stock."),
            ("2. Shipping charges",
             "Shipping is free for orders with a net value of EUR 750 or more. Orders below EUR 750 are charged "
             "a flat fee of EUR 35 within the Benelux and Germany."),
        ],
    },
    {
        "file": "KS-FIN-002_Payment_Terms_and_Credit_v2.1.pdf",
        "policy_id": "KS-FIN-002", "version": "2.1", "status": "valid", "effective_date": "2026-01-01",
        "title": "Payment Terms and Credit Policy",
        "sections": [
            ("1. Payment terms",
             "Payment terms are agreed per customer account, typically Net 30 or Net 45 days from the invoice date. "
             "New customers and accounts without an approved credit line pay by prepayment: orders ship once payment "
             "is received."),
            ("2. Credit limits",
             "Each credit account has a credit limit. Available credit is the credit limit minus open invoices. "
             "Web store orders that exceed the available credit cannot be placed directly; they are converted into a "
             "quote request and reviewed by the account's sales representative and the credit team."),
            ("3. Late payment",
             "Overdue invoices accrue interest of 1% per month. Accounts with invoices more than 30 days overdue are "
             "placed on hold until the balance is settled."),
            ("4. Invoicing",
             "Invoices are issued per shipment and sent by e-mail. All prices in the web store are net prices "
             "excluding VAT."),
        ],
    },
    {
        "file": "KS-OPS-003_Returns_and_RMA_v1.2.pdf",
        "policy_id": "KS-OPS-003", "version": "1.2", "status": "valid", "effective_date": "2026-02-01",
        "title": "Returns and RMA Policy",
        "sections": [
            ("1. Return window",
             "Unused products in their original, unopened packaging can be returned within 30 days of delivery. "
             "A return authorisation (RMA number) must be requested in the web store before sending goods back."),
            ("2. Restocking fee",
             "Returns of non-defective products are subject to a 15% restocking fee. Return shipping for "
             "non-defective products is paid by the customer."),
            ("3. Non-returnable items",
             "Cut-to-length products such as cable from a drum, custom orders, and opened hygiene-sensitive PPE "
             "such as disposable gloves and ear plugs cannot be returned."),
            ("4. Defective products and warranty",
             "Defective products are covered by a 12-month warranty from delivery. Kestrel pays return shipping and "
             "replaces or credits defective items after inspection, without a restocking fee."),
        ],
    },
    {
        "file": "KS-SAL-004_Quotes_and_Volume_Pricing_v1.0.pdf",
        "policy_id": "KS-SAL-004", "version": "1.0", "status": "valid", "effective_date": "2026-04-01",
        "title": "Quotes and Volume Pricing Policy",
        "sections": [
            ("1. Price structure",
             "Customer prices are calculated from the list price, minus the account's price-group discount, minus "
             "a volume tier discount: 5% from 10 units and 10% from 50 units of the same product. Contract prices "
             "agreed for specific products are fixed net prices and are not combined with volume tiers."),
            ("2. When a quote is required",
             "A quote request is required for orders with a net value above EUR 10,000, for discounts beyond the "
             "standard tiers, and for orders that exceed the account's available credit."),
            ("3. Quote handling",
             "Quote requests are handled by the account's sales representative, who responds within one business day. "
             "Approved quotes are valid for 30 days and can be converted into an order in the web store."),
        ],
    },
]


def _write_pdf(policy: dict, path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4
    header = f"{COMPANY}  |  {policy['policy_id']} v{policy['version']}  |  Fictional sample for testing"
    body = [header, "", policy["title"],
            f"Document ID: {policy['policy_id']}  |  Version {policy['version']}  |  "
            f"Effective date: {policy['effective_date']}", ""]
    for heading, text in policy["sections"]:
        body += [heading, text, ""]
    page.insert_textbox(pymupdf.Rect(56, 56, 539, 800), "\n".join(body), fontsize=10.5, fontname="helv")
    doc.set_metadata({"title": policy["title"], "author": COMPANY})
    doc.save(path)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for policy in POLICIES:
        _write_pdf(policy, OUT_DIR / policy["file"])
        manifest[policy["file"]] = {k: policy[k] for k in ("policy_id", "version", "status", "effective_date")}
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(POLICIES)} PDFs and manifest.json to {OUT_DIR}")


if __name__ == "__main__":
    main()
