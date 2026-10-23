"""Tools the commerce agent can call.

Rules every tool follows:
- Read tools return facts from the ERP, catalog or policy index. Prices only ever come from the ERP.
- Write tools never write. They create a *proposed action* that the buyer confirms in the UI,
  and deterministic code executes it (erp.confirm). The LLM can't place an order on its own.
- Failures become explicit signals (ERP_UNAVAILABLE, NO_RELEVANT_POLICY_FOUND, UNKNOWN_SKU)
  so the agent falls back instead of guessing.
- Every call is recorded in the request trace that the UI shows.
"""
import functools
import logging
import re
from typing import Literal, TypedDict

from rag import erp
from rag.catalog import search_products
from rag.context import Timer, current
from rag.erp import ErpUnavailable, eur
from rag.retrieval import retrieve

logger = logging.getLogger(__name__)

SKU_PATTERN = re.compile(r"\b[A-Z]{3}-\d{4}\b")
ERP_UNAVAILABLE = (
    "ERP_UNAVAILABLE: live prices, stock and order data can't be retrieved right now. "
    "Don't state any price or stock level. Offer to send the request to the sales team instead."
)
NO_RESULTS = "NO_RELEVANT_POLICY_FOUND"
WAREHOUSES = {"NL": "Rotterdam (NL)", "DE": "Duisburg (DE)"}

Category = Literal["Fasteners", "PPE", "Packaging", "Tools", "Electrical", "Maintenance"]


class CartItem(TypedDict):
    sku: str
    quantity: int


def traced(fn):
    """Record each tool call (name, status, latency) in the request trace, and keep its output for the guards."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        ctx = current()
        with Timer() as timer:
            try:
                result = fn(*args, **kwargs)
            except ErpUnavailable as exc:
                logger.warning("ERP unavailable in %s: %s", fn.__name__, exc)
                result = ERP_UNAVAILABLE
        if result.startswith("ERP_UNAVAILABLE"):
            ctx.record("tool", fn.__name__, "error", "ERP timed out, so the agent was told not to state prices", timer.ms)
            ctx.record("fallback", "erp_unavailable", "fallback", "Tool returned ERP_UNAVAILABLE instead of data")
        else:
            ctx.record("tool", fn.__name__, "ok", _summarise_args(kwargs or (args[0] if args else {})), timer.ms)
        ctx.tool_outputs.append(result)
        return result
    return wrapper


def _summarise_args(args) -> str:
    if isinstance(args, dict):
        return ", ".join(f"{k}={v!r}" for k, v in args.items())[:160]
    return repr(args)[:160]


def _add_card(sku: str, quantity: int = 1) -> None:
    """Structured product card for the UI, priced by the ERP (never by the LLM)."""
    ctx = current()
    item = erp.product(sku)
    if item is None or sku in ctx.products:
        return
    card = {"sku": item["sku"], "name": item["name"], "pack": item["pack"], "category": item["category"],
            "unit_price": None, "price_basis": None, "stock": None, "warehouse": None, "lead_time_days": None}
    try:
        line = erp.price_line(ctx.account_id, sku, quantity)
        card.update(unit_price=line.unit_price, price_basis=line.basis, stock=line.stock_at_warehouse,
                    warehouse=WAREHOUSES.get(line.warehouse, line.warehouse), lead_time_days=line.lead_time_days)
    except ErpUnavailable:
        pass  # the card shows "price unavailable"
    ctx.products[sku] = card


@traced
def search_catalog(query: str, category: Category | None = None) -> str:
    """Search Kestrel's product catalog by description, specification or SKU.

    Returns up to 5 matching active products (SKU, name, pack size). Prices are NOT included:
    call get_price_and_stock for the buyer's own price and availability.
    """
    lines = []
    for sku in dict.fromkeys(SKU_PATTERN.findall(query.upper())):
        item = erp.product(sku)
        if item is None:
            lines.append(f"UNKNOWN_SKU: {sku} doesn't exist in the catalog.")
        elif item["status"] == "discontinued":
            lines.append(f"{sku} ({item['name']}) is discontinued. Its replacement is {item['replaced_by']}.")
            _add_card(item["replaced_by"])

    hits = search_products(query, category)
    for hit in hits:
        lines.append(f"- {hit.sku}: {hit.name} ({hit.pack}), category {hit.category}")
        _add_card(hit.sku)
    if not hits and not lines:
        return "NO_MATCHING_PRODUCTS: nothing in the catalog matches this search."
    return "\n".join(lines)


@traced
def get_price_and_stock(sku: str, quantity: int = 1) -> str:
    """Get the buyer's net price (their contract or price-group price with volume tiers) and stock
    for one SKU at a given quantity. Use this for every price you mention."""
    ctx = current()
    item = erp.product(sku)
    if item is None:
        return f"UNKNOWN_SKU: {sku} doesn't exist in the catalog."
    if item["status"] == "discontinued":
        _add_card(item["replaced_by"], quantity)
        return f"{item['sku']} is discontinued and can't be ordered. Its replacement is {item['replaced_by']}; check that SKU."

    line = erp.price_line(ctx.account_id, item["sku"], quantity)
    _add_card(line.sku, quantity)
    warehouse = WAREHOUSES.get(line.warehouse, line.warehouse)
    text = (
        f"{line.sku} {line.name} ({line.pack}), quantity {line.quantity}: unit price {eur(line.unit_price)} "
        f"[{line.basis}], line total {eur(line.line_total)} excl. VAT.\n"
        f"Stock at {warehouse} (the buyer's warehouse): {line.stock_at_warehouse}. "
        f"Other warehouses: {line.stock_total - line.stock_at_warehouse}."
    )
    if not line.in_stock:
        backorder = line.quantity - line.stock_at_warehouse
        text += (f"\nNot enough stock at {warehouse}: {backorder} would be on backorder, "
                 f"supplier lead time {line.lead_time_days} days.")
        if line.alternatives:
            text += f" In-stock alternatives to suggest: {', '.join(line.alternatives)}."
    return text


@traced
def get_order_history(limit: int = 3) -> str:
    """Get the buyer's most recent orders with their lines, for reordering or "same as last time" requests."""
    orders = erp.order_history(current().account_id, limit)
    if not orders:
        return "No previous orders on this account."
    out = []
    for order in orders:
        lines = ", ".join(f"{l['sku']} x{l['quantity']}" for l in order["lines"])
        out.append(f"{order['order_id']} ({order['date']}): {lines}")
    return "\n".join(out)


@traced
def search_policies(query: str) -> str:
    """Search Kestrel's current trade policies: shipping and delivery, payment terms and credit,
    returns and RMA, quotes and volume pricing. Returns excerpts in <source> tags, or NO_RELEVANT_POLICY_FOUND."""
    chunks = retrieve(query)
    if not chunks:
        return NO_RESULTS
    return "\n\n".join(
        f'<source id="{c.source_id}" citation="{c.citation}">\n{c.text}\n</source>' for c in chunks
    )


def _items(items: list[CartItem]) -> list[tuple[str, int]]:
    return [(str(i["sku"]).strip().upper(), int(i["quantity"])) for i in items]


@traced
def propose_cart(items: list[CartItem]) -> str:
    """Propose adding products to the buyer's cart. This does NOT place an order: the buyer confirms it in the UI.

    Business rules decide the outcome: if the order needs a quote (exceeds available credit, prepayment
    account, or above €10,000), a quote request for the sales team is proposed instead.
    """
    ctx = current()
    parsed = _items(items)
    unknown = [sku for sku, _ in parsed if erp.product(sku) is None or erp.product(sku)["status"] != "active"]
    if unknown:
        return f"CANNOT_PROPOSE: these SKUs aren't orderable: {', '.join(unknown)}. Check them with search_catalog."

    check = erp.check_order(ctx.account_id, parsed)
    lines_text = "; ".join(f"{l.sku} x{l.quantity} = {eur(l.line_total)}" for l in check.lines)
    payload = {
        "lines": [{"sku": l.sku, "name": l.name, "quantity": l.quantity, "unit_price": l.unit_price,
                   "line_total": l.line_total, "in_stock": l.in_stock} for l in check.lines],
        "net_total": check.net_total, "shipping": check.shipping, "quote_reasons": check.quote_reasons,
    }
    for l in check.lines:
        _add_card(l.sku, l.quantity)

    if check.requires_quote:
        summary = f"Quote request: {lines_text}. Net {eur(check.net_total)}. Needs sales review: {'; '.join(check.quote_reasons)}."
        action = erp.propose("quote_request", ctx.account_id, summary, payload)
        ctx.actions.append(action)
        ctx.record("action", "quote_request", "ok", f"Rule-based: {'; '.join(check.quote_reasons)}")
        return (f"PROPOSED_QUOTE_REQUEST {action['action_id']}: this order can't go straight to the cart because "
                f"{'; '.join(check.quote_reasons)}. Lines: {lines_text}. Net total {eur(check.net_total)}. "
                "The buyer must confirm sending it to their sales rep. Nothing has been ordered.")

    summary = f"Add to cart: {lines_text}. Net {eur(check.net_total)}, shipping {eur(check.shipping)}."
    action = erp.propose("cart_add", ctx.account_id, summary, payload)
    ctx.actions.append(action)
    ctx.record("action", "cart_add", "ok", "Awaiting buyer confirmation")
    backorders = [l.sku for l in check.lines if not l.in_stock]
    note = f" Backorder lines: {', '.join(backorders)}." if backorders else ""
    return (f"PROPOSED_CART {action['action_id']}: {lines_text}. Net total {eur(check.net_total)}, "
            f"shipping {eur(check.shipping)} excl. VAT.{note} Awaiting buyer confirmation; nothing is ordered yet.")


@traced
def request_quote(items: list[CartItem], reason: str, requested_discount_pct: float | None = None) -> str:
    """Propose a quote request to the buyer's sales rep, e.g. for discounts beyond standard tiers or
    large orders. The agent can't grant discounts; only the sales rep can. The buyer confirms sending it."""
    ctx = current()
    check = erp.check_order(ctx.account_id, _items(items))
    lines_text = "; ".join(f"{l.sku} x{l.quantity} = {eur(l.line_total)}" for l in check.lines)
    payload = {
        "lines": [{"sku": l.sku, "name": l.name, "quantity": l.quantity, "unit_price": l.unit_price,
                   "line_total": l.line_total, "in_stock": l.in_stock} for l in check.lines],
        "net_total": check.net_total, "reason": reason, "requested_discount_pct": requested_discount_pct,
        "quote_reasons": check.quote_reasons,
    }
    discount = f", requested discount {requested_discount_pct:g}%" if requested_discount_pct else ""
    summary = f"Quote request: {lines_text}. Net {eur(check.net_total)}{discount}. Reason: {reason}"
    action = erp.propose("quote_request", ctx.account_id, summary, payload)
    ctx.actions.append(action)
    ctx.record("action", "quote_request", "ok", f"Agent-proposed: {reason}"[:160])
    return (f"PROPOSED_QUOTE_REQUEST {action['action_id']}: {lines_text}. Current net total {eur(check.net_total)}"
            f"{discount}. The buyer must confirm sending it; the sales rep replies within one business day.")


@traced
def handoff_to_sales(reason: str) -> str:
    """Propose handing the conversation to the buyer's sales rep when the request needs a human:
    disputes, special terms, anything the tools can't answer, or when the buyer asks for a person."""
    ctx = current()
    acc = erp.account(ctx.account_id)
    action = erp.propose("handoff", ctx.account_id, f"Handoff to {acc['sales_rep']}: {reason}", {"reason": reason})
    ctx.actions.append(action)
    ctx.record("action", "handoff", "ok", reason[:160])
    return f"PROPOSED_HANDOFF {action['action_id']} to sales rep {acc['sales_rep']}. The buyer must confirm sending it."


ALL_TOOLS = [search_catalog, get_price_and_stock, get_order_history, search_policies,
             propose_cart, request_quote, handoff_to_sales]
