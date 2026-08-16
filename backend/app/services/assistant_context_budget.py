"""Final Assistant request preparation and fail-closed token budgeting.

This module owns the only Assistant pre-invocation budget gate.  The canonical
JSON below is also the text sent as the provider input, so a successful budget
check cannot be invalidated by a later Assistant-only append.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

MAX_INPUT_TOKENS = 40_000
SAFETY_RESERVE_TOKENS = 2_000
HARD_OUTPUT_CAP = 20_000
ANSWER_TARGETS = {"concise": 2_000, "detailed": 6_000, "deep": 20_000}
# Ceiling actually sent to the provider as max_output_tokens. The adaptive
# target guides length; this ceiling bounds worst-case latency/cost without
# constraining the deep mode. Headroom absorbs the structured JSON envelope.
EFFECTIVE_OUTPUT_CAPS = {mode: min(HARD_OUTPUT_CAP, target * 2) for mode, target in ANSWER_TARGETS.items()}


class TokenizerStrategy(Protocol):
    strategy_key: str
    strategy_version: str
    deployment_or_model: str

    def count_text(self, text: str) -> int: ...

    def count_final_request(self, serialized_request: str) -> int: ...


class ConservativeUtf8Tokenizer:
    """Upper bound: every UTF-8 byte is treated as one token.

    This is intentionally conservative and never claims model-exact counts.
    """

    strategy_key = "conservative_utf8_upper_bound"
    strategy_version = "1"
    deployment_or_model = "configured-deployment"

    def count_text(self, text: str) -> int:
        return len(text.encode("utf-8"))

    def count_final_request(self, serialized_request: str) -> int:
        return self.count_text(serialized_request)


class ContextBudgetExceeded(ValueError):
    code = "assistant_context_budget_exceeded"


@dataclass(frozen=True)
class PreparedAssistantProviderRequest:
    context: tuple[object, ...]
    question: str
    policy: str
    schema: dict[str, object]
    serialized_input: str
    final_input_tokens: int
    safety_reserve_tokens: int
    hard_input_limit: int
    hard_output_cap: int
    effective_output_cap: int
    adaptive_answer_target: int
    answer_mode: str
    manifest: dict[str, object]
    tokenizer: TokenizerStrategy

    @property
    def tokenizer_strategy(self) -> str:
        return self.tokenizer.strategy_key


@dataclass(frozen=True)
class BoundedContext:
    segments: list[object]
    manifest: dict[str, object]


def count_tokens(text: str) -> int:
    """Legacy estimate retained only for old callers/tests.

    The production Assistant path never uses this approximation; it uses the
    named conservative strategy through ``prepare_assistant_request``.
    """
    return max(0, (len(text) + 3) // 4)


def _segment_id(segment: object) -> str:
    return str(getattr(segment, "segment_id", "unknown"))


def _segment_content(segment: object) -> str:
    return str(getattr(segment, "content", ""))


def _section(segment_id: str) -> str:
    if segment_id == "projection":
        return "projection"
    if segment_id == "history":
        return "conversation"
    if segment_id.startswith(("event", "command", "failure")):
        return "events_commands_failures"
    if segment_id.startswith(("excerpt-", "evidence")):
        return "approved_excerpts"
    return "events_commands_failures"


def _canonical(policy: str, schema: dict[str, object], question: str, segments: list[object], *, answer_mode: str, adaptive_answer_target: int) -> str:
    # Keep this representation stable: Azure receives this exact string as its
    # user input when the prepared contract is present.
    payload = {
        "framing": "assistant-provider-input-v1",
        "instructions": policy,
        "schema": schema,
        "answer_mode": answer_mode,
        "adaptive_answer_target": adaptive_answer_target,
        "question": question,
        "context": [
            {"id": _segment_id(item), "label": str(getattr(item, "label", "")), "content": _segment_content(item)}
            for item in segments
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def prepare_assistant_request(
    *,
    policy: str,
    schema: dict[str, object],
    question: str,
    segments: list[object],
    answer_mode: str = "concise",
    tokenizer: TokenizerStrategy | None = None,
    deployment_or_model: str = "configured-deployment",
) -> PreparedAssistantProviderRequest:
    if answer_mode not in ANSWER_TARGETS:
        raise ValueError("unsupported answer mode")
    strategy = tokenizer or ConservativeUtf8Tokenizer()
    if tokenizer is None:
        # Make the fallback's configured deployment explicit in persisted data.
        strategy.deployment_or_model = deployment_or_model  # type: ignore[misc]
    max_final = MAX_INPUT_TOKENS - SAFETY_RESERVE_TOKENS
    working = list(segments)
    omitted: list[str] = []
    reasons: dict[str, str] = {}

    # Deduplicate by exact stable content before any relevance-based omission.
    seen: set[str] = set()
    deduped: list[object] = []
    for item in working:
        fingerprint = hashlib.sha256(_segment_content(item).encode("utf-8")).hexdigest()
        item_id = _segment_id(item)
        if fingerprint in seen:
            omitted.append(item_id)
            reasons[item_id] = "exact_duplicate"
        else:
            seen.add(fingerprint)
            deduped.append(item)
    working = deduped

    def count(items: list[object]) -> tuple[str, int]:
        serialized = _canonical(policy, schema, question, items, answer_mode=answer_mode, adaptive_answer_target=ANSWER_TARGETS[answer_mode])
        return serialized, strategy.count_final_request(serialized)

    serialized, total = count(working)
    while total > max_final:
        optional = [item for item in working if _segment_id(item) != "projection"]
        if not optional:
            raise ContextBudgetExceeded("mandatory Assistant policy, schema, question and projection exceed the input budget")
        # Stable omission order follows the contract: old history, then
        # diagnostics, then lower-ranked evidence. Retrieval order is already
        # persisted, so later items are the lower-ranked tie-break.
        indexed = list(enumerate(optional))
        victim = min(indexed, key=lambda pair: ({"history": 0, "events_commands_failures": 1, "approved_excerpts": 2}.get(_section(_segment_id(pair[1])), 3), -pair[0], _segment_id(pair[1])))[1]
        working.remove(victim)
        item_id = _segment_id(victim)
        omitted.append(item_id)
        reasons[item_id] = "input_budget"
        serialized, total = count(working)

    section_counts: dict[str, int] = {name: 0 for name in ("policy_schema", "projection", "conversation", "events_commands_failures", "approved_excerpts")}
    section_counts["policy_schema"] = strategy.count_text(json.dumps({"instructions": policy, "schema": schema}, sort_keys=True, separators=(",", ":")))
    for item in working:
        section_counts[_section(_segment_id(item))] += strategy.count_text(_segment_content(item))
    section_counts["conversation"] += strategy.count_text(question)
    manifest = {
        "schema": "assistant-input-manifest-v2",
        "context_budget": {
            "hard_input_limit": MAX_INPUT_TOKENS,
            "final_serialized_input_tokens": total,
            "safety_reserve_tokens": SAFETY_RESERVE_TOKENS,
            "tokenizer_strategy": strategy.strategy_key,
            "tokenizer_version": strategy.strategy_version,
            "deployment_or_model": getattr(strategy, "deployment_or_model", deployment_or_model),
            "sections": {
                name: {"token_count": value, "selected_item_ids": [_segment_id(item) for item in working if _section(_segment_id(item)) == name], "omitted_item_ids": [item for item in omitted if _section(item) == name], "truncated_item_ids": [], "truncation_reason": next((reasons[item] for item in omitted if _section(item) == name), None)}
                for name, value in section_counts.items()
            },
            "provider_framing_tokens": strategy.count_text('{"framing":"assistant-provider-input-v1"}'),
            "question_tokens": strategy.count_text(question),
            "policy_schema_tokens": section_counts["policy_schema"],
            "hard_output_cap": HARD_OUTPUT_CAP,
            "effective_output_cap": EFFECTIVE_OUTPUT_CAPS[answer_mode],
            "adaptive_answer_target": ANSWER_TARGETS[answer_mode],
            "answer_mode": answer_mode,
        },
        "selected_item_ids": [_segment_id(item) for item in working],
        "omitted_item_ids": omitted,
        "truncated_item_ids": [],
        "omission_reasons": reasons,
    }
    return PreparedAssistantProviderRequest(tuple(working), question, policy, schema, serialized, total, SAFETY_RESERVE_TOKENS, MAX_INPUT_TOKENS, HARD_OUTPUT_CAP, EFFECTIVE_OUTPUT_CAPS[answer_mode], ANSWER_TARGETS[answer_mode], answer_mode, manifest, strategy)


def build_bounded_context(segments: list[object], limit: int = MAX_INPUT_TOKENS) -> BoundedContext:
    """Legacy helper retained for non-R4 callers; Assistant uses preparation above."""
    selected: list[object] = []
    omitted: list[str] = []
    total = 0
    counts: dict[str, int] = {}
    strategy = ConservativeUtf8Tokenizer()
    for segment in segments:
        segment_id = _segment_id(segment)
        tokens = strategy.count_text(_segment_content(segment))
        if total + tokens <= limit:
            selected.append(segment)
            total += tokens
            counts[segment_id] = tokens
        else:
            omitted.append(segment_id)
    return BoundedContext(selected, {"configured_input_limit": limit, "total_tokens": total, "token_count_per_section": counts, "selected_item_identifiers": [_segment_id(x) for x in selected], "omitted_item_identifiers": omitted, "truncated_sections": [], "truncation_reason": "input_budget" if omitted else None})
