"""Deterministic output guards, run on every final answer before it reaches the buyer.

- Price grounding: every money amount in the answer must appear in a tool result.
  The LLM may repeat prices; it may not compute or invent them.
- Citation validity: every cited policy source must have been retrieved in this request.
"""
import re
from dataclasses import dataclass, field

AMOUNT = re.compile(r"(?:€|EUR)\s?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)")
CITATION_GROUP = re.compile(r"\[([^\]]*p\.\d+[^\]]*)\]")
CITED_ID = re.compile(r"[A-Z]{2,}-[A-Z]{2,}-\d{3} p\.\d+")
RETRIEVED_ID = re.compile(r'<source id="([^"]+)"')


def _amounts(text: str) -> set[float]:
    return {round(float(m.replace(",", "")), 2) for m in AMOUNT.findall(text)}


@dataclass
class GuardResult:
    amounts_checked: int = 0
    unverified_amounts: list[str] = field(default_factory=list)
    citations_checked: int = 0
    invalid_citations: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.unverified_amounts and not self.invalid_citations


def check_answer(answer: str, tool_outputs: list[str]) -> GuardResult:
    evidence = "\n".join(tool_outputs)
    known_amounts = _amounts(evidence)
    answer_amounts = _amounts(answer)

    cited = {cid for group in CITATION_GROUP.findall(answer) for cid in CITED_ID.findall(group)}
    retrieved = set(RETRIEVED_ID.findall(evidence))

    return GuardResult(
        amounts_checked=len(answer_amounts),
        unverified_amounts=sorted(f"€{a:,.2f}" for a in answer_amounts - known_amounts),
        citations_checked=len(cited),
        invalid_citations=sorted(cited - retrieved),
    )
