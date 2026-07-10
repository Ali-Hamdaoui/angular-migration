"""Registry mapping agent names to mock agent instances.

The orchestrator looks up agents by name so nodes can call the correct
agent through the shared contract without importing individual classes.
"""

from app.agents.base import BaseMockAgent
from app.agents.mock_agents import MOCK_AGENTS

_AGENT_REGISTRY: dict[str, BaseMockAgent] = {
    agent.name: agent for agent in MOCK_AGENTS
}


def get_agent(name: str) -> BaseMockAgent | None:
    return _AGENT_REGISTRY.get(name)


def list_agent_names() -> list[str]:
    return list(_AGENT_REGISTRY.keys())
