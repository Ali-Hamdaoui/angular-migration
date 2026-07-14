"""Authoritative legal transitions for the draft G01 gate."""




class PreflightTransitionService:
    """Keep draft-gate state movement explicit until S1-F06 creates a run."""

    allowed = {"approved", "approved_with_comment", "modification_requested", "rejected"}

    def validate(self, *, gate, decision: str, expected_state_version: int) -> None:
        if decision not in self.allowed:
            raise ValueError("INVALID_G01_DECISION: The decision is not legal for G01.")
        if gate.status != "pending":
            raise ValueError("G01_ALREADY_DECIDED: The pending G01 gate has already received a decision.")
        if gate.state_version != expected_state_version:
            raise ValueError("STALE_STATE_VERSION: The G01 gate state version is stale.")

    def apply(self, *, gate, preflight, decision: str) -> None:
        gate.status = decision
        gate.state_version += 1
        preflight.status = decision
        preflight.state_version = gate.state_version
