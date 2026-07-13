# Core

Owns application construction, metadata, lifecycle wiring, and typed
configuration access.

This module must not contain workflow decisions, route handlers, repository
models, command execution logic, or secret-bearing values serialized to clients.