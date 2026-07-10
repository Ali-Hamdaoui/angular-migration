# Domain

Owns canonical Pydantic contracts, DTOs, enums, and state vocabulary shared by
backend services and API responses.

Domain models must not perform persistence, filesystem I/O, command execution,
HTTP routing, or frontend-specific rendering behavior.