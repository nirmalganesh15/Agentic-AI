import json
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASET = PROJECT_ROOT / "evals" / "commerce_cases.json"

DECLINE_CATEGORIES = frozenset({"off_topic", "prompt_injection"})


@dataclass(frozen=True)
class EvalCase:
    id: str
    category: str
    account_id: str
    question: str
    expected_answer: str
    expected_intents: tuple[str, ...]
    expected_skus: tuple[str, ...] = ()       # catalog retrieval targets (any one counts as a hit)
    expected_sources: tuple[str, ...] = ()    # policy ids for policy retrieval
    expected_action: str | None = None        # cart_add | quote_request | handoff
    expected_fallback: str | None = None      # erp_unavailable | model_fallback
    allowed_actions: tuple[str, ...] = ()     # write proposals that are acceptable but not required
    history: tuple[str, ...] = ()             # earlier buyer turns in the same thread (not graded)
    must_include: tuple[str, ...] = ()
    must_not_include: tuple[str, ...] = ()
    simulate: dict = field(default_factory=dict)
    retrieval_eval: bool = True


def load_cases() -> list[EvalCase]:
    rows = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = [
        EvalCase(
            id=r["id"], category=r["category"], account_id=r["account_id"], question=r["question"],
            expected_answer=r["expected_answer"], expected_intents=tuple(r.get("expected_intents", [])),
            expected_skus=tuple(r.get("expected_skus", [])), expected_sources=tuple(r.get("expected_sources", [])),
            expected_action=r.get("expected_action"), expected_fallback=r.get("expected_fallback"),
            must_include=tuple(r.get("must_include", [])), must_not_include=tuple(r.get("must_not_include", [])),
            allowed_actions=tuple(r.get("allowed_actions", [])), history=tuple(r.get("history", [])),
            simulate=r.get("simulate", {}), retrieval_eval=r.get("retrieval_eval", True),
        )
        for r in rows
    ]
    if len({c.id for c in cases}) != len(cases):
        raise ValueError("Duplicate eval case ids")
    return cases
