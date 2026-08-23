"""LLM query expansion + inferred metadata filters for retrieval."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.utils.config import get_app_config
from src.utils.models import get_chat_model

# Must stay aligned with data/knowledge_base frontmatter `category` values
KB_CATEGORIES = (
    "refunds",
    "shipping",
    "orders",
    "payments",
    "warranty",
    "account",
    "promotions",
    "faq",
    "escalation",
    "safety",
)

Category = Literal[
    "refunds",
    "shipping",
    "orders",
    "payments",
    "warranty",
    "account",
    "promotions",
    "faq",
    "escalation",
    "safety",
]

SYSTEM_PROMPT = """You expand a support ticket into search queries for a policy KB.

Brand: {brand}. Domain: ecommerce home goods.

Your job is retrieval prep only — never answer the customer, never invent policy.

Produce:
1. One primary search_query rewritten for semantic (vector) search
2. Up to two alternate_queries that paraphrase the same intent
3. Short keywords useful for lexical / metadata match (policy terms, product words)
4. Zero or more categories from this exact list: {categories}
5. Known policy_ids only if the ticket clearly names them (e.g. REFUND-14DAY); otherwise []
6. scopes only if clearly tenant-specific; otherwise prefer ["global"] or []

Prefer precision on categories. Empty categories is fine when unsure."""

HUMAN_PROMPT = """Ticket subject: {subject}

Context summary from intake:
{context_summary}

Conversation transcript:
{transcript}

Expand this into retrieval queries and metadata filters."""


class QueryExpansion(BaseModel):
    """Structured expansion used by vector + keyword retrieval."""

    search_query: str = Field(
        description="Primary natural-language query for vector search"
    )
    alternate_queries: list[str] = Field(
        default_factory=list,
        description="Up to two paraphrases of the same intent",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Short lexical keywords for keyword / metadata search",
    )
    categories: list[Category] = Field(
        default_factory=list,
        description="KB categories to soft-filter on, from the allowed list",
    )
    policy_ids: list[str] = Field(
        default_factory=list,
        description="Explicit policy IDs mentioned by the customer, if any",
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="Soft tenancy scopes; usually ['global'] or empty",
    )
    rationale: str = Field(
        default="",
        description="One sentence explaining the expansion choices",
    )


def _render_transcript(messages: list[Any]) -> str:
    lines: list[str] = []
    for message in messages:
        role = getattr(message, "type", None) or getattr(message, "role", "unknown")
        content = getattr(message, "content", str(message))
        if role in {"human", "user"}:
            label = "Customer"
        elif role in {"ai", "assistant"}:
            label = "Agent"
        else:
            label = str(role).capitalize()
        lines.append(f"{label}: {content}")
    return "\n".join(lines) if lines else "(no messages)"


def expand_query(
    *,
    subject: str,
    context_summary: str,
    messages: list[Any] | None = None,
) -> QueryExpansion:
    """Use DeepSeek to rewrite the ticket into search queries + filters."""
    prompt = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)]
    )
    chain = prompt | get_chat_model().with_structured_output(QueryExpansion)
    return chain.invoke(
        {
            "brand": get_app_config()["app"]["brand"],
            "categories": ", ".join(KB_CATEGORIES),
            "subject": subject or "(no subject)",
            "context_summary": context_summary or "(none)",
            "transcript": _render_transcript(messages or []),
        }
    )


def expansion_to_dict(expansion: QueryExpansion) -> dict[str, Any]:
    return expansion.model_dump()
