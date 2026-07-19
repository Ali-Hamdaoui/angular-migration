# Coding Standards

- Cohesive domain modules and explicit business names.
- Thin FastAPI routes and LangGraph nodes.
- Typed Pydantic v2 boundary models and explicit internal contracts.
- No duplicate DTO/event/state/path/command definitions.
- No silent mocks/fallbacks, broad exception swallowing, or test-aware production behavior.
- No transaction across subprocess/LLM/copy/approval/user wait.
- Production Python soft/hard 500/700 lines; TS/React 400/600; tests 700/1000. Generated/migration exceptions require review.
- Functions normally below 60 logical lines.
- No speculative modernization or unrelated refactor.
- Comments explain invariants and policy, not syntax.
