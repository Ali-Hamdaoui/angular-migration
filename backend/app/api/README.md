# API

Owns FastAPI routers, request validation, response shaping, dependency wiring,
and error-envelope adaptation.

Routers must delegate workflow, persistence, execution, artifact, approval, and
assistant behavior to application services. They must not implement state-machine
logic, call repositories directly, execute commands, or infer workflow progress.