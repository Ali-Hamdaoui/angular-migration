"""Common agent contract boundary.

Every agent - mock or real - must inherit ``BaseMockAgent`` and implement
``execute``. Agents receive an ``AgentInputEnvelope`` and return an
``AgentOutputEnvelope``. They must never call shell commands, mutate files,
approve gates, or bypass backend authority directly.
"""

from abc import ABC, abstractmethod

from app.domain.contracts import AgentInputEnvelope, AgentOutputEnvelope
from app.llm_gateway import LlmRequest, LlmResponse, MockLlmGateway


class BaseMockAgent(ABC):
    """Abstract base for all agents using the shared input/output envelope."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique display name matching the agent catalog vocabulary."""

    @abstractmethod
    def execute(self, envelope: AgentInputEnvelope) -> AgentOutputEnvelope:
        """Process the input envelope and return a structured output.

        Mock agents return deterministic outputs without LLM reasoning,
        file mutation, or command execution.
        """

    def request_llm_assistance(self, gateway: MockLlmGateway, request: LlmRequest) -> LlmResponse:
        """Route optional LLM help through the backend gateway boundary only."""
        return gateway.complete(request)