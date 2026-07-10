# Backend

This workspace is the Migration Factory's execution authority. Subsequent work
adds FastAPI APIs, persistence, orchestration, artifact access, approval
processing, sandbox policy, command execution, and the Azure OpenAI LLM Gateway
here.

Boundary: frontend code, fixture applications, and direct agent command
execution do not belong here. Agents may propose actions through backend
contracts; backend services validate and execute approved work.
