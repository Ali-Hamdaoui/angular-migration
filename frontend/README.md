# Frontend

This workspace contains the Next.js Control Tower UI. It will provide migration
setup and migration-progress views using backend API contracts and server-sent
events.

Boundary: the frontend renders backend-owned workflow state. It must not infer
workflow transitions, execute migration commands, mutate sandboxes, or approve
gates without a backend request.
diff --git a/shared/README.md b/shared/README.md
