# AGENT.md

## 1. Purpose

This file defines the mandatory working rules for any AI coding agent operating in the `angular-migration` repository.

The agent must protect the repository, respect the project documentation, implement only the selected Sprint 0 issue, and leave all remote operations and merges to the user.

These instructions are mandatory.

---

## 2. Repository and Branch Model

Repository:

```text
angular-migration
```

Permanent branches:

```text
main
dev
```

Branch responsibilities:

- `main` contains the current final validated version.
- `main` is protected and must not be modified, rebased, merged into, pushed to, or used as the base branch for issue work.
- `dev` contains stable code that has already been reviewed and validated.
- All issue branches must be created from the latest version of `dev`.
- Each Sprint 0 issue must be implemented in its own dedicated branch.
- Never implement two unrelated issues in the same branch.

Recommended issue branch format:

```text
issue/<issue-id>-<short-description>
```

Example:

```text
issue/s0-03-bootstrap-fastapi-backend
```

Use the exact issue identifier defined in the project documentation whenever one exists.

---

## 3. Mandatory Startup Workflow

Before reading, editing, generating, or committing implementation code, the agent must:

1. Confirm that the current repository is `angular-migration`.
2. Inspect the current Git status.
3. Ensure there are no unexpected uncommitted changes.
4. Fetch the latest remote state.
5. Switch to `dev`.
6. Pull the latest version of `dev`.
7. Read the relevant project documentation.
8. Identify the exact Sprint 0 issue to implement.
9. Create a new issue branch from the updated local `dev`.

Expected workflow:

```bash
git status
git fetch origin
git switch dev
git pull --ff-only origin dev
git switch -c issue/<issue-id>-<short-description>
```

The agent must not use `git pull` without first confirming the active branch.

The agent must not use force operations such as:

```bash
git push --force
git push --force-with-lease
git reset --hard
git clean -fd
```

unless the user explicitly requests the exact operation and understands its impact.

---

## 4. Documentation Is the Source of Truth

Before implementing an issue, the agent must inspect the `docs/` directory and read:

- the Sprint 0 backlog or Sprint 0 issue definition;
- the architecture documentation;
- the workflow documentation;
- the technical stack documentation;
- the product vision and MVP scope;
- any coding, API, database, agent, orchestration, security, testing, or UI conventions relevant to the issue.

The agent must use the documentation as the primary source of truth.

The agent must:

- implement the issue according to its documented acceptance criteria;
- preserve the complete project vision;
- verify dependencies on earlier or related issues;
- respect established naming, folder structure, architecture, and technology decisions;
- update documentation when the implementation changes documented behavior, setup, configuration, APIs, or architecture.

The agent must not:

- invent requirements;
- silently expand the issue scope;
- replace documented technologies with preferred alternatives;
- introduce architecture that conflicts with the project vision;
- assume missing acceptance criteria;
- implement future-sprint functionality unless it is strictly required by the current issue.

If the requested issue cannot be identified in `docs/`, the agent must stop and ask the user which documented issue should be implemented.

---

## 5. Clarification Rule

The agent must ask the user a focused question before implementation when a missing decision could materially affect:

- architecture;
- public APIs;
- database schema;
- workflow or state transitions;
- security;
- artifact layout;
- sandbox behavior;
- agent responsibilities;
- user-facing behavior;
- acceptance criteria;
- compatibility with another Sprint 0 issue.

The agent must not guess or invent a project decision.

The agent may make small, reversible implementation choices only when they:

- follow existing repository conventions;
- do not alter product behavior;
- do not conflict with the documentation;
- are documented in the final summary.

Questions must be specific and limited to information that cannot be determined from the repository or documentation.

---

## 6. Issue Scope

For every issue, the agent must first establish:

```text
Issue identifier
Issue title
Objective
Relevant documentation
Acceptance criteria
Dependencies
Files expected to change
Validation required
Out-of-scope items
```

The implementation must remain limited to the selected issue.

Do not perform unrelated:

- refactoring;
- dependency upgrades;
- formatting changes across the repository;
- file renaming;
- architecture redesign;
- feature additions;
- cleanup outside the affected area.

A necessary supporting change is allowed only when it is directly required by the issue and is included in the implementation summary.

---

## 7. Implementation Standards

All code must be:

- clear;
- maintainable;
- modular;
- typed where supported;
- consistent with the repository structure;
- easy to test;
- explicit rather than overly clever;
- documented when behavior is not self-explanatory.

The agent must:

- reuse existing abstractions before creating new ones;
- keep functions and modules focused;
- use meaningful names;
- avoid duplicated logic;
- handle expected failures explicitly;
- avoid swallowing exceptions;
- provide useful error messages;
- keep configuration externalized where appropriate;
- avoid hard-coded environment-specific paths, secrets, credentials, tokens, or URLs;
- preserve backward compatibility unless the issue explicitly changes it;
- add or update tests for implemented behavior;
- avoid adding dependencies unless they are necessary and aligned with the documented stack.

Temporary placeholders, fake implementations, silent fallbacks, and unfinished TODO-based behavior are not acceptable unless the issue explicitly requires a scaffold. Any intentional scaffold must be clearly marked and documented.

---

## 8. Project Stack Constraints

The current approved stack must be respected.

### Backend

- Python
- FastAPI
- Uvicorn
- Pydantic v2
- SQLAlchemy
- Alembic
- SQLite
- LangGraph
- Azure OpenAI LLM Gateway
- Local filesystem artifact store
- Python sandbox execution worker
- Server-Sent Events

### Migration Worker Runtime

- Python
- Node.js
- npm
- Angular CLI through `npx`
- Git

### Frontend

- Node.js
- Next.js
- React
- TypeScript
- Custom React components
- CSS Modules
- Server-Sent Events client
- Custom log viewer
- Custom unified diff viewer
- Markdown report viewer

Do not replace an approved technology without explicit user approval and a documented project decision.

---

## 9. Safety and Repository Protection

The agent must preserve existing stable behavior.

Before changing code, inspect the surrounding implementation and related tests.

The agent must never:

- modify `main`;
- push any branch;
- merge any branch;
- open or merge a pull request;
- delete local or remote branches;
- rewrite published history;
- alter user Git configuration;
- commit secrets or local environment files;
- bypass failing tests by disabling them;
- remove validation to make an issue appear complete;
- modify unrelated user work;
- discard uncommitted changes that were not created by the agent.

When unexpected local changes exist, stop and explain what was found before continuing.

---

## 10. Validation Requirements

Before committing, the agent must run the relevant validation available in the repository.

Depending on the affected area, this may include:

```text
formatting
linting
type checking
unit tests
integration tests
API tests
database migration checks
frontend build
backend startup validation
production build
sandbox worker validation
SSE workflow validation
```

The agent must not claim that validation passed unless the corresponding command was actually executed successfully.

If a validation command cannot run because of an environment limitation, missing dependency, unavailable service, or existing repository failure, the agent must:

1. report the exact limitation;
2. distinguish it from failures caused by the new changes;
3. complete all other available validation;
4. avoid presenting the issue as fully verified.

---

## 11. Commit Rules

After the implementation and validation are complete, the agent must commit the work locally.

Do not put the entire issue into one large commit when the work contains multiple logical changes.

Each commit must:

- represent one clear purpose;
- keep the repository in a coherent state where practical;
- use a concise and descriptive message;
- avoid mixing implementation, tests, documentation, and unrelated cleanup without reason.

Preferred commit message format:

```text
<type>(<scope>): <clear description>
```

Common types:

```text
chore
feat
fix
refactor
test
docs
build
ci
```

Example commit sequence:

```text
chore(backend): add FastAPI application skeleton
feat(config): add typed application settings
test(backend): add application health endpoint tests
docs(setup): document local backend startup
```

Before every commit, inspect:

```bash
git status
git diff
git diff --staged
```

Stage only the files that belong to that logical commit.

Do not use:

```bash
git add .
```

without first reviewing all changed files.

Do not amend, squash, rebase, or rewrite commits unless the user explicitly asks for it.

---

## 12. Mandatory Stop Point

After creating the local logical commits, the agent must stop.

The agent must not:

```text
push the branch
merge into dev
merge into main
create a pull request
approve a pull request
delete the issue branch
```

The user will manually review, push, and merge the work into `dev`.

At the end, the agent must provide:

```text
Branch name
Implemented issue
Summary of changes
Files changed
Validation commands executed
Validation results
Local commits created
Known limitations or follow-up items
Suggested manual review steps
```

The final statement must clearly say:

```text
The work is committed locally. No push or merge was performed.
```

---

## 13. Required Execution Sequence

For every Sprint 0 issue, follow this sequence:

```text
1. Inspect repository and Git status.
2. Fetch origin.
3. Switch to dev.
4. Pull dev using fast-forward only.
5. Read the relevant files under docs/.
6. Identify the exact Sprint 0 issue and its acceptance criteria.
7. Ask a focused question only when a material requirement is missing.
8. Create a dedicated issue branch from the updated dev branch.
9. Inspect the existing implementation and related tests.
10. Implement only the selected issue.
11. Add or update tests.
12. Update relevant documentation.
13. Run all applicable validation.
14. Review the complete diff.
15. Create multiple logical local commits.
16. Report the result.
17. Stop before push, pull request, or merge.
```

---

## 14. Priority of Instructions

When instructions conflict, use this priority:

```text
1. Explicit user instruction in the current task
2. This AGENT.md file
3. Approved project documentation in docs/
4. Existing repository conventions
5. General engineering best practices
```

No instruction may override repository safety rules unless the user explicitly requests the exact exceptional action.
