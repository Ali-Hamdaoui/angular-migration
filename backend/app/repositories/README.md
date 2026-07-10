# Repositories

Owns persistence adapters, SQLAlchemy models, sessions, and repository methods.

Repositories store and retrieve data for services. They must not authorize
commands, call LLMs, emit SSE directly, decide workflow transitions, or expose
database models through API routers.