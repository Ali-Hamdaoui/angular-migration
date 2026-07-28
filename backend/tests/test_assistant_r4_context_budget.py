from app.llm_gateway import LlmContextSegment
from app.services.assistant_context_budget import (
    ANSWER_TARGETS,
    ConservativeUtf8Tokenizer,
    ContextBudgetExceeded,
    prepare_assistant_request,
)


class CountingTokenizer:
    strategy_key = "test_exact"
    strategy_version = "1"
    deployment_or_model = "test-model"

    def count_text(self, text: str) -> int:
        return len(text)

    def count_final_request(self, serialized_request: str) -> int:
        return len(serialized_request)


def _build(question="status", segments=None, mode="concise"):
    return prepare_assistant_request(
        policy="policy",
        schema={"type": "object", "properties": {"answer": {"type": "string"}}},
        question=question,
        segments=segments or [LlmContextSegment(segment_id="projection", label="projection", content="authoritative")],
        answer_mode=mode,
        tokenizer=CountingTokenizer(),
    )


def test_final_count_changes_for_question_and_schema_without_context_change():
    base = _build()
    longer_question = _build(question="status " + "question " * 100)
    larger_schema = prepare_assistant_request(
        policy="policy",
        schema={"type": "object", "description": "schema " * 100},
        question="status",
        segments=[LlmContextSegment(segment_id="projection", label="projection", content="authoritative")],
        tokenizer=CountingTokenizer(),
    )
    assert longer_question.final_input_tokens > base.final_input_tokens
    assert larger_schema.final_input_tokens > base.final_input_tokens


def test_final_request_is_repeatedly_identical_and_manifest_is_sanitized():
    segments = [
        LlmContextSegment(segment_id="projection", label="projection", content="state"),
        LlmContextSegment(segment_id="excerpt-a", label="approved evidence", content="evidence"),
        LlmContextSegment(segment_id="history", label="history", content="prior answer"),
    ]
    first, second = _build(segments=segments), _build(segments=segments)
    assert first.serialized_input == second.serialized_input
    assert first.manifest == second.manifest
    assert "state" not in str(first.manifest)
    assert first.manifest["context_budget"]["tokenizer_strategy"] == "test_exact"


def test_duplicate_and_optional_items_are_trimmed_deterministically():
    segments = [
        LlmContextSegment(segment_id="projection", label="projection", content="state"),
        LlmContextSegment(segment_id="excerpt-a", label="approved evidence", content="same"),
        LlmContextSegment(segment_id="excerpt-duplicate", label="approved evidence", content="same"),
        LlmContextSegment(segment_id="history", label="history", content="old " * 20_000),
    ]
    prepared = _build(segments=segments)
    assert "excerpt-duplicate" in prepared.manifest["omitted_item_ids"]
    assert prepared.manifest["omission_reasons"]["excerpt-duplicate"] == "exact_duplicate"
    assert prepared.final_input_tokens + prepared.safety_reserve_tokens <= prepared.hard_input_limit


def test_mandatory_content_failure_is_fail_closed():
    try:
        _build(question="q" * 50_000, segments=[LlmContextSegment(segment_id="projection", label="projection", content="state")])
    except ContextBudgetExceeded as error:
        assert error.code == "assistant_context_budget_exceeded"
    else:
        raise AssertionError("mandatory oversized package must fail closed")


def test_adaptive_targets_are_distinct_and_hard_cap_is_separate():
    prepared = [_build(mode=mode) for mode in ("concise", "detailed", "deep")]
    assert [item.adaptive_answer_target for item in prepared] == [ANSWER_TARGETS["concise"], ANSWER_TARGETS["detailed"], ANSWER_TARGETS["deep"]]
    assert {item.adaptive_answer_target for item in prepared} == {2000, 6000, 20000}
    assert all(item.hard_output_cap == 20_000 for item in prepared)
    assert all(item.manifest["context_budget"]["hard_output_cap"] == 20_000 for item in prepared)


def test_conservative_fallback_is_named_and_never_smaller_than_utf8():
    strategy = ConservativeUtf8Tokenizer()
    corpus = ["ascii", "é", "中文", "emoji 😀", "line\n" * 100]
    assert strategy.strategy_key == "conservative_utf8_upper_bound"
    assert all(strategy.count_text(value) >= len(value) for value in corpus)
