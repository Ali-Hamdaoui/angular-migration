"""Bounded, deterministic Assistant input context packaging."""

from dataclasses import dataclass

MAX_INPUT_TOKENS = 40_000


def count_tokens(text: str) -> int:
    return max(0, (len(text) + 3) // 4)


@dataclass(frozen=True)
class BoundedContext:
    segments: list[object]
    manifest: dict[str, object]


def build_bounded_context(segments: list[object], limit: int = MAX_INPUT_TOKENS) -> BoundedContext:
    selected: list[object] = []
    omitted: list[str] = []
    total = 0
    counts: dict[str, int] = {}
    for segment in segments:
        segment_id = str(getattr(segment, "segment_id", "unknown"))
        tokens = count_tokens(str(getattr(segment, "content", "")))
        if total + tokens <= limit:
            selected.append(segment); total += tokens; counts[segment_id] = tokens
        else:
            omitted.append(segment_id)
    return BoundedContext(selected, {"configured_input_limit": limit, "total_tokens": total, "token_count_per_section": counts, "selected_item_identifiers": [getattr(x, "segment_id", "unknown") for x in selected], "omitted_item_identifiers": omitted, "truncated_sections": [], "truncation_reason": "input_budget" if omitted else None})
