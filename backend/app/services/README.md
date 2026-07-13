# Services

Owns application service facades used by API routers and orchestration nodes to
coordinate domain contracts, repositories, state, events, artifacts, policies,
and execution boundaries.

Services may compose lower-level modules but must not hide direct source
mutation, bypass transition invariants, leak secrets, or implement frontend
rendering logic.