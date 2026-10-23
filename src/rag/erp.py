"""Mock ERP: accounts, customer-specific pricing, stock, credit, carts and the sales queue.

Everything here is deterministic business logic. The LLM never calculates a price or
places an order: it calls tools that call these functions, and write actions only run
after the buyer confirms them in the UI.
"""
import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from rag.context import simulation

DATA_DIR = Path(__file__).resolve().parents[2] / "resources" / "commerce"

FREE_SHIPPING_FROM = 500.0           # KS-OPS-001 v3.0
SHIPPING_FEE_DOMESTIC = 25.0         # NL, BE, DE
SHIPPING_FEE_EU = 45.0
DOMESTIC_COUNTRIES = {"NL", "BE", "DE"}
QUOTE_REQUIRED_ABOVE = 10_000.0      # KS-SAL-004 v1.0
VOLUME_TIERS = ((50, 0.10), (10, 0.05))  # (min quantity, discount), highest first


class ErpUnavailable(Exception):
    """The ERP didn't answer in time. Tools turn this into an explicit signal for the agent."""


def eur(amount: float) -> str:
    """Single money format used everywhere, so guards can match prices exactly."""
    return f"€{amount:,.2f}"


@lru_cache
def _products() -> dict[str, dict]:
    rows = json.loads((DATA_DIR / "products.json").read_text(encoding="utf-8"))
    return {p["sku"]: p for p in rows}


@lru_cache
def _accounts() -> dict[str, dict]:
    rows = json.loads((DATA_DIR / "accounts.json").read_text(encoding="utf-8"))
    return {a["account_id"]: a for a in rows}


def _ensure_available() -> None:
    if simulation().erp_down:
        raise ErpUnavailable("ERP request timed out after 5 s")


def all_products() -> list[dict]:
    return list(_products().values())


def product(sku: str) -> dict | None:
    return _products().get(sku.strip().upper())


def account(account_id: str) -> dict:
    acc = _accounts().get(account_id)
    if acc is None:
        raise KeyError(f"Unknown account {account_id}")
    return acc


def list_accounts() -> list[dict]:
    return [
        {
            "account_id": a["account_id"], "company": a["company"], "buyer": a["buyer"],
            "location": a["location"], "price_group": a["price_group"], "payment_terms": a["payment_terms"],
            "available_credit": available_credit(a), "sales_rep": a["sales_rep"],
        }
        for a in _accounts().values()
    ]


def available_credit(acc: dict) -> float:
    return max(acc["credit_limit"] - acc["credit_used"], 0.0)


def tier_discount(quantity: int) -> float:
    return next((discount for min_qty, discount in VOLUME_TIERS if quantity >= min_qty), 0.0)


@dataclass(frozen=True)
class PriceLine:
    sku: str
    name: str
    pack: str
    quantity: int
    list_price: float
    unit_price: float
    line_total: float
    basis: str               # how the price was derived, shown to the buyer
    warehouse: str
    stock_at_warehouse: int
    stock_total: int
    lead_time_days: int
    alternatives: tuple[str, ...]

    @property
    def in_stock(self) -> bool:
        return self.stock_at_warehouse >= self.quantity


def price_line(account_id: str, sku: str, quantity: int) -> PriceLine:
    """Customer net price: contract price if agreed, else list - group discount - volume tier."""
    _ensure_available()
    acc = account(account_id)
    item = product(sku)
    if item is None:
        raise KeyError(f"Unknown SKU {sku}")
    if quantity < 1:
        raise ValueError("Quantity must be at least 1")

    contract = acc["contract_prices"].get(item["sku"])
    if contract is not None:
        unit, basis = contract, "contract price (fixed, no volume tiers)"
    else:
        tier = tier_discount(quantity)
        unit = round(item["list_price"] * (1 - acc["group_discount"]) * (1 - tier), 2)
        parts = [f"list {eur(item['list_price'])}"]
        if acc["group_discount"]:
            parts.append(f"price group {acc['price_group']} -{acc['group_discount']:.0%}")
        if tier:
            parts.append(f"volume tier -{tier:.0%}")
        basis = ", ".join(parts)

    warehouse = acc["warehouse"]
    return PriceLine(
        sku=item["sku"], name=item["name"], pack=item["pack"], quantity=quantity,
        list_price=item["list_price"], unit_price=unit, line_total=round(unit * quantity, 2), basis=basis,
        warehouse=warehouse, stock_at_warehouse=item["stock"].get(warehouse, 0),
        stock_total=sum(item["stock"].values()), lead_time_days=item["lead_time_days"],
        alternatives=tuple(item.get("alternatives", [])),
    )


def order_history(account_id: str, limit: int = 3) -> list[dict]:
    _ensure_available()
    return account(account_id)["orders"][:limit]


@dataclass(frozen=True)
class OrderCheck:
    lines: list[PriceLine]
    net_total: float
    shipping: float
    quote_reasons: list[str]    # empty -> can go straight to the cart

    @property
    def requires_quote(self) -> bool:
        return bool(self.quote_reasons)


def check_order(account_id: str, items: list[tuple[str, int]]) -> OrderCheck:
    """Apply the business rules a web store order must pass (credit, quote threshold, shipping)."""
    acc = account(account_id)
    lines = [price_line(account_id, sku, qty) for sku, qty in items]
    net = round(sum(line.line_total for line in lines), 2)
    domestic = acc["country"] in DOMESTIC_COUNTRIES
    shipping = 0.0 if net >= FREE_SHIPPING_FROM else (SHIPPING_FEE_DOMESTIC if domestic else SHIPPING_FEE_EU)

    reasons = []
    if acc["payment_terms"] == "Prepayment":
        reasons.append("account pays by prepayment")
    elif net > available_credit(acc):
        reasons.append(f"order total {eur(net)} exceeds available credit {eur(available_credit(acc))}")
    if net > QUOTE_REQUIRED_ABOVE:
        reasons.append(f"order total above {eur(QUOTE_REQUIRED_ABOVE)}")
    return OrderCheck(lines, net, shipping, reasons)


# ---------------------------------------------------------------------------
# Write side: proposed actions, carts and the sales queue (in-memory for the demo)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_pending: dict[str, dict] = {}
_carts: dict[str, list[dict]] = {}
_queue: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def propose(action_type: str, account_id: str, summary: str, payload: dict) -> dict:
    action = {
        "action_id": f"ACT-{uuid.uuid4().hex[:8].upper()}",
        "type": action_type, "account_id": account_id, "summary": summary,
        "payload": payload, "status": "pending", "created_at": _now(),
    }
    with _lock:
        _pending[action["action_id"]] = action
    return action


def confirm(action_id: str, account_id: str) -> dict:
    """Run a proposed action. Called by the API after the buyer clicks confirm, never by the LLM."""
    with _lock:
        action = _pending.get(action_id)
        if action is None or action["account_id"] != account_id:
            raise KeyError("Action not found for this account")
        if action["status"] != "pending":
            raise ValueError(f"Action already {action['status']}")
        action["status"] = "confirmed"

    if action["type"] == "cart_add":
        with _lock:
            cart = _carts.setdefault(account_id, [])
            for line in action["payload"]["lines"]:
                existing = next((c for c in cart if c["sku"] == line["sku"]), None)
                if existing:
                    existing["quantity"] += line["quantity"]
                else:
                    cart.append({"sku": line["sku"], "quantity": line["quantity"]})
        return {"result": "added_to_cart", "cart": cart_summary(account_id)}

    ticket = {
        "ticket_id": f"Q-{uuid.uuid4().hex[:6].upper()}",
        "type": action["type"], "account_id": account_id, "company": account(account_id)["company"],
        "sales_rep": account(account_id)["sales_rep"], "summary": action["summary"],
        "payload": action["payload"], "status": "open", "created_at": _now(), "decision_note": None,
    }
    with _lock:
        _queue[ticket["ticket_id"]] = ticket
    return {"result": "sent_to_sales", "ticket": ticket}


def dismiss(action_id: str, account_id: str) -> None:
    with _lock:
        action = _pending.get(action_id)
        if action and action["account_id"] == account_id and action["status"] == "pending":
            action["status"] = "dismissed"


def cart_summary(account_id: str) -> dict:
    items = [(c["sku"], c["quantity"]) for c in _carts.get(account_id, [])]
    if not items:
        return {"lines": [], "net_total": 0.0, "shipping": 0.0, "quote_reasons": []}
    check = check_order(account_id, items)
    return {
        "lines": [asdict(line) for line in check.lines], "net_total": check.net_total,
        "shipping": check.shipping, "quote_reasons": check.quote_reasons,
    }


def sales_queue() -> list[dict]:
    with _lock:
        return sorted(_queue.values(), key=lambda t: t["created_at"], reverse=True)


def decide(ticket_id: str, decision: str, note: str | None) -> dict:
    with _lock:
        ticket = _queue.get(ticket_id)
        if ticket is None:
            raise KeyError("Ticket not found")
        if ticket["status"] != "open":
            raise ValueError(f"Ticket already {ticket['status']}")
        ticket["status"] = "approved" if decision == "approve" else "rejected"
        ticket["decision_note"] = note
        ticket["decided_at"] = _now()
        return ticket
