# Agents

Owns AI-assisted agent interfaces, registries, and mock agent implementations.

Agents may analyze context and propose structured actions, explanations,
patches, or reports. They must not execute commands, mutate files directly,
access secret-bearing configuration, bypass policy checks, or become
deterministic platform services.