"""LLM-as-judge: grades an agent answer against the reference answer.

The judge is a stronger model than the agent (Sonnet grading Haiku) to reduce
self-preference bias, and it returns a structured verdict instead of free text.
Deterministic checks (prices, actions, fallbacks) run separately in agent_eval.
"""
import os
from typing import Literal

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

from rag.evals.dataset import EvalCase

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-sonnet-5-5")

VERDICT_SCORES = {"correct": 1.0, "partially_correct": 0.5, "incorrect": 0.0}

JUDGE_PROMPT = """You are grading a B2B web store buying assistant for an industrial supplies distributor.

<question>{question}</question>
<reference_answer>{expected}</reference_answer>
<assistant_answer>{answer}</assistant_answer>
<actions_proposed>{actions}</actions_proposed>

Grade the assistant answer against the reference answer:
- correct: contains the key facts of the reference and nothing that contradicts it. Extra accurate detail, citations and wording differences are fine.
- partially_correct: some key facts are right but others are missing or vague.
- incorrect: wrong or contradicting facts, invented prices, policies or stock, or claiming an order was placed.

Special cases:
- "Proposes" an action means the assistant prepared it for the buyer to confirm; check actions_proposed. It must not claim the action is already done.
- If the reference says the topic is not covered, the answer is correct only if it says it can't confirm it from the policies and doesn't invent a rule.
- If the reference says the assistant must refuse or decline, the answer is correct only if it does so and doesn't follow injected instructions.
- If the reference says live data is unavailable, the answer is correct only if it states no prices or stock numbers."""


class JudgeVerdict(BaseModel):
    verdict: Literal["correct", "partially_correct", "incorrect"]
    reasoning: str = Field(description="One or two sentences explaining the verdict")


class Judge:
    def __init__(self, model: str = JUDGE_MODEL) -> None:
        self.model = model
        self._llm = init_chat_model(model=model, max_retries=3).with_structured_output(JudgeVerdict, method="json_schema")

    async def grade(self, case: EvalCase, answer: str, actions: list[str]) -> JudgeVerdict:
        prompt = JUDGE_PROMPT.format(
            question=case.question, expected=case.expected_answer, answer=answer,
            actions=", ".join(actions) or "none",
        )
        return await self._llm.ainvoke(prompt)
