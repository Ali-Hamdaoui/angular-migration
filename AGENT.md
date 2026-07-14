# AGENT.md

## 1. Purpose

This file defines the mandatory working rules for any AI coding agent operating in the `angular-migration` repository.

The agent must protect the repository, preserve the stability of `main` and `dev`, respect the approved project documentation, and implement work only inside an explicitly authorized feature branch.

A feature may contain multiple related issues. Therefore, branches are created per feature, not per issue.

The agent must never automatically create branches, commit changes, push changes, merge branches, or modify protected branches. Every repository-changing Git action requires explicit user authorization at the appropriate approval gate.

These instructions are mandatory.

---

## 2. Repository and Branch Model

Repository:

```text
angular-migration
```

Permanent protected branches:

```text
main
dev
```

### 2.1 `main`

- `main` contains the final validated and approved version.
- `main` must not be modified during normal development.
- The agent must not commit to, push to, merge into, rebase, reset, or rewrite `main`.
- The agent must not use `main` as the base branch for feature development.
- Integration into `main` remains a separate human-controlled release decision.

### 2.2 `dev`

- `dev` is the stable integration branch.
- `dev` must remain untouched during feature implementation.
- The agent must not implement code while checked out on `dev`.
- The agent must not commit directly to `dev`.
- The agent must not push directly to `dev`.
- The agent must not automatically merge a feature branch into `dev`.
- The agent must not rebase, reset, rewrite, or force-update `dev`.
- Integration into `dev` must be performed through a separately authorized and reviewed integration process, preferably a pull request.

Reading, fetching, and synchronizing the local `dev` branch with `origin/dev` are allowed as part of the mandatory new-feature startup workflow. This does not authorize implementation work, commits, pushes, merges, rebases, resets, or rewrites on `dev`.

### 2.3 Feature branches

- Development work must be performed in a dedicated branch for the selected feature.
- One feature branch may contain several related issues belonging to the same documented feature.
- Do not create a separate branch for every issue.
- Do not mix unrelated features in the same branch.
- Do not create a new feature branch while another feature branch is active unless the user explicitly authorizes parallel work.
- Do not create a replacement or duplicate feature branch when a suitable branch already exists.
- A feature branch must be based on the latest fetched `origin/dev`.
- The agent must obtain explicit user permission before creating any feature branch.

Recommended feature branch format:

```text
feature/<feature-id>-<short-description>
```

Examples:

```text
feature/s0-f03-backend-foundation
feature/s1-f02-migration-job-creation
feature/s2-f04-stage-execution-control
```

Use the exact documented feature identifier whenever one exists.

Issue identifiers must be tracked inside the feature branch through commit messages, documentation updates, pull-request descriptions, or a feature progress record. Issue identifiers must not be encoded by creating separate issue branches.

---

## 3. Git Action Permission Model

Git operations are divided into read-only actions and repository-changing actions.

### 3.1 Read-only actions allowed without additional permission

The agent may perform the following actions to inspect the repository and prepare a proposal:

```bash
git status
git branch --show-current
git branch --list
git remote -v
git fetch --prune origin
git log
git show
git diff
git diff --staged
git ls-files
git rev-parse
```

The agent may also inspect files, documentation, tests, configuration, and repository history.

`git fetch` is allowed because it updates remote-tracking references without committing to or merging into `dev`.

### 3.2 Actions requiring explicit permission

The agent must ask for and receive explicit user permission before performing any of the following:

```text
creating a branch
switching to a newly created branch
creating a commit
amending a commit
pushing a branch
creating a pull request
updating a pull request
merging a branch
deleting a local branch
deleting a remote branch
creating or deleting a tag
performing a rebase
performing a reset
restoring or discarding user changes
changing Git configuration
```

Permission for one action does not imply permission for later actions.

Examples:

- Permission to create a branch does not authorize commits.
- Permission to commit does not authorize pushing.
- Permission to push does not authorize creating a pull request.
- Permission to create a pull request does not authorize merging.
- Permission to work on one feature does not authorize creating the next feature branch.

### 3.3 Approval must be informed

Before requesting permission, the agent must explain the exact proposed action.

For branch creation, provide:

```text
Feature identifier
Feature title
Issues expected in the feature
Proposed branch name
Base reference
Base commit
Reason a new branch is needed
```

For a commit, provide:

```text
Issue identifier
Purpose of the commit
Files to be included
Files intentionally excluded
Proposed commit message
Validation already executed
Known limitations
```

For a push, provide:

```text
Branch to push
Remote destination
Commits that will be published
Working-tree status
Validation status
```

The agent must wait for an explicit approval such as:

```text
Create the branch.
Commit these changes.
Push the feature branch.
Create the pull request.
```

Silence, an unrelated reply, or earlier general permission must not be treated as authorization.

---

## 4. Mandatory Startup and Repository Inspection

Before editing implementation code, the agent must:

1. Confirm that the repository is `angular-migration`.
2. Identify the current branch.
3. Inspect the working tree.
4. Detect staged, unstaged, and untracked files.
5. Confirm that existing user work will not be overwritten.
6. Fetch the latest remote state using `git fetch --prune origin`.
7. Inspect the latest `origin/dev` commit.
8. Read the relevant project documentation.
9. Identify the selected feature and its related issues.
10. Determine whether an existing feature branch should be reused.
11. Present the feature execution proposal.
12. Ask for explicit permission before creating a branch.

When starting work on a new feature, the agent must first synchronize from `dev` using this sequence:

```bash
git switch dev
git fetch --prune origin
git pull --ff-only origin dev
```

After the pull completes successfully and the latest `dev` state has been inspected, the agent must create the approved feature branch from the updated local `dev`:

```bash
git switch -c feature/<feature-id>-<short-description> dev
```

The agent must never start a new feature from a stale local branch or from another feature branch. If the working tree contains changes that would prevent switching to `dev` or pulling safely, the agent must stop and report them before taking further action.

Safe inspection workflow:

```bash
git status
git branch --show-current
git remote -v
git fetch --prune origin
git log --oneline --decorate -n 10 origin/dev
```

When a new feature branch is approved, create it from the synchronized local `dev` branch as described above. Pulling updates local `dev` to the latest fast-forward from `origin/dev`; implementation changes must then be made only on the feature branch.

If the current branch is `dev`, the agent must not edit files. It must first inspect the repository, request branch-creation permission, and move to the approved feature branch.

If unexpected local changes exist, the agent must stop before editing and report:

```text
Current branch
Changed files
Whether changes are staged
Whether files are tracked
Potential conflict with the requested work
```

The agent must not stash, discard, reset, clean, overwrite, or commit unexpected user changes without explicit permission.

---

## 5. Documentation Is the Source of Truth

Before implementing a feature or issue, inspect the `docs/` directory and read all relevant material, including:

- the backlog and sprint documentation;
- the selected feature definition;
- the selected issue definition;
- architecture documentation;
- workflow documentation;
- technical stack documentation;
- product vision and MVP scope;
- state-machine and transition rules;
- API and database conventions;
- agent and orchestration responsibilities;
- sandbox and command-execution rules;
- security constraints;
- testing conventions;
- frontend and UI conventions;
- relevant architecture decision records.

The documentation is the primary source of truth.

The agent must:

- implement documented acceptance criteria;
- preserve the complete project vision;
- respect feature and issue dependencies;
- respect established naming and folder structure;
- respect approved architecture and technology decisions;
- update documentation when behavior, setup, configuration, APIs, schema, workflow, or architecture changes;
- identify conflicts between documents before implementation;
- prefer the newest explicitly approved document when document versions conflict, while reporting the conflict.

The agent must not:

- invent requirements;
- silently expand scope;
- replace approved technologies with preferred alternatives;
- introduce architecture that conflicts with the project vision;
- assume missing acceptance criteria;
- implement future feature behavior unless strictly required by the current issue;
- use generated code as authority when it conflicts with documentation.

If the selected feature or issue cannot be identified in `docs/`, the agent must stop and ask the user to identify the correct documented work item.

---

## 6. Feature and Issue Scope Management

### 6.1 Feature definition

Before requesting permission to create a feature branch, establish:

```text
Feature identifier
Feature title
Feature objective
Sprint
Related issue identifiers
Relevant documentation
Dependencies
Expected backend scope
Expected frontend scope
Expected database scope
Expected workflow scope
Expected files or modules
Validation strategy
Out-of-scope items
```

A feature branch must have one coherent objective.

### 6.2 Issue execution inside the feature branch

Issues must be implemented one at a time inside the approved feature branch.

Before starting an issue, establish:

```text
Issue identifier
Issue title
Objective
Acceptance criteria
Dependencies
Current feature branch
Expected files to change
Tests required
Manual validation required
Out-of-scope items
```

After completing an issue, the agent must stop at an issue review checkpoint before starting the next issue.

The review checkpoint must include:

```text
Issue implemented
Summary of changes
Files changed
Tests added or updated
Validation commands and results
Current diff status
Known limitations
Proposed commit plan
Recommended next issue
```

The agent must not automatically commit, push, or start the next issue.

The user may:

- inspect and commit the changes manually;
- ask the agent to adjust the implementation;
- explicitly authorize one or more commits;
- explicitly authorize a push;
- authorize work on the next issue in the same feature branch.

### 6.3 Scope restrictions

Do not perform unrelated:

- refactoring;
- dependency upgrades;
- repository-wide formatting;
- file renaming;
- architecture redesign;
- feature additions;
- cleanup outside the affected area;
- speculative abstractions;
- premature optimization.

A supporting change is allowed only when it is directly necessary for the selected issue and is clearly reported.

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
- avoid adding dependencies unless necessary and aligned with the approved stack;
- preserve strict Angular migration functional parity;
- keep LangGraph as an orchestration adapter rather than the state database or execution authority;
- keep SQLite as authoritative persistent state for the MVP;
- keep the Transition Service authoritative for legal state changes;
- keep the CommandExecutor authoritative for command execution;
- keep the Artifact Store authoritative for execution evidence;
- keep workspace mutation inside the approved sandbox execution boundary.

Temporary placeholders, fake implementations, silent fallbacks, and unfinished TODO-based behavior are not acceptable unless the issue explicitly requires a scaffold.

Any intentional scaffold must be clearly marked, tested where practical, and documented.

---

## 8. Project Stack Constraints

The approved stack must be respected.

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

Do not replace an approved technology without explicit user approval and a documented architecture decision.

Do not introduce excluded or company-restricted tools without explicit approval.

---

## 9. Safety and Repository Protection

The agent must preserve existing stable behavior and user work.

Before changing code, inspect the surrounding implementation, contracts, migrations, tests, and documentation.

The agent must never:

- modify `main`;
- commit to `main`;
- push to `main`;
- merge into `main`;
- modify `dev` during feature implementation;
- commit directly to `dev`;
- push directly to `dev`;
- automatically merge a feature branch into `dev`;
- force-push any branch;
- rewrite published history;
- delete branches without permission;
- alter user Git configuration;
- commit secrets or local environment files;
- bypass failing tests by disabling them;
- remove validation to make work appear complete;
- modify unrelated user work;
- discard changes not created by the agent;
- use destructive commands without exact, informed authorization;
- claim a Git action was performed when it was not.

Prohibited by default:

```bash
git push --force
git push --force-with-lease
git reset --hard
git clean -fd
git clean -fdx
git checkout -- .
git restore .
git restore --staged .
git rebase
git commit --amend
```

A destructive command requires a separate, exact user instruction that identifies the command or its intended effect and acknowledges the impact.

---

## 10. Validation Requirements

Validation must be performed before presenting an issue as complete.

Depending on the affected area, validation may include:

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
state-transition validation
artifact-generation validation
manual end-to-end validation
```

The agent must:

- run the smallest relevant checks during implementation;
- run the complete applicable validation before the issue review checkpoint;
- record the exact commands executed;
- report pass, fail, skipped, and blocked checks separately;
- distinguish pre-existing failures from failures introduced by the changes;
- avoid claiming validation passed when a command was not executed;
- avoid changing tests merely to hide a product defect.

If validation cannot run because of environment limitations, missing dependencies, unavailable services, corporate restrictions, or existing repository failures, report:

```text
Blocked command
Exact error or limitation
Whether the limitation is pre-existing
What validation was still completed
Residual risk
```

---

## 11. Commit Rules and Approval Gate

The default behavior is to leave completed issue changes uncommitted for human review.

The developer may inspect, modify, stage, commit, and push manually after being satisfied with the implementation.

The agent must not create a commit unless the user explicitly authorizes it.

### 11.1 Commit proposal

At the issue review checkpoint, the agent must propose logical commits when appropriate.

Each proposed commit must:

- represent one clear purpose;
- reference the relevant issue identifier when practical;
- keep the repository coherent;
- use a concise descriptive message;
- avoid unrelated changes.

Preferred commit message format:

```text
<type>(<scope>): <clear description> [<issue-id>]
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

Example proposal:

```text
feat(api): add migration job creation endpoint [S1-F02-I01]
test(api): cover migration job validation [S1-F02-I01]
docs(api): document migration job contract [S1-F02-I01]
```

### 11.2 Before an authorized commit

Before every authorized commit, inspect:

```bash
git status
git diff
git diff --staged
```

The agent must then show or summarize:

```text
Files to stage
Files excluded
Proposed commit message
Validation status
```

Stage only the approved files.

Do not use:

```bash
git add .
git add -A
```

without first reviewing and listing all affected files.

Authorization to create one commit applies only to the described commit. Additional commits require additional approval unless the user explicitly approves a named multi-commit plan.

The agent must not amend, squash, rebase, or rewrite commits unless explicitly authorized.

---

## 12. Push Rules and Approval Gate

The default behavior is not to push.

The developer may push manually after reviewing the issue implementation and commits.

The agent must not push unless the user explicitly authorizes the exact branch push.

Before requesting push permission, provide:

```text
Current branch
Remote destination
Commits to be pushed
Ahead/behind status
Working-tree status
Validation status
Known limitations
```

Authorized push format:

```bash
git push -u origin feature/<feature-id>-<short-description>
```

For later pushes:

```bash
git push origin feature/<feature-id>-<short-description>
```

The agent must never force-push.

A push authorization does not authorize creating a pull request or merging into `dev`.

---

## 13. Pull Request and Integration Rules

A feature should normally be integrated only after all of its related issues and feature-level acceptance criteria are complete.

Before proposing integration, the agent must provide a feature completion report:

```text
Feature identifier and title
Feature branch
Included issue identifiers
Completed acceptance criteria
Incomplete or deferred items
Commits
Files and modules changed
Database migrations
API changes
Frontend changes
Workflow or state-machine changes
Validation results
Manual verification results
Known limitations
Documentation updates
Risk assessment
```

The agent must not automatically create a pull request.

A pull request requires explicit permission.

The pull request should:

- target `dev`;
- use the feature branch as the source;
- list all included issues;
- describe scope and out-of-scope items;
- include validation evidence;
- disclose database, API, configuration, and migration impacts;
- identify remaining risks;
- avoid unrelated changes.

The agent must not merge the pull request or merge the feature branch into `dev`.

Merging into `dev` remains a human-controlled action unless the user creates a separate, explicit integration task that authorizes the exact merge after review.

Even when separately authorized, the agent must never push directly to `dev` without explicit permission for that exact push.

The agent must not delete the feature branch automatically after integration.

---

## 14. Feature Branch Lifecycle

A feature branch progresses through the following states:

```text
PROPOSED
AUTHORIZED
ACTIVE
ISSUE_REVIEW
FEATURE_REVIEW
READY_FOR_PR
INTEGRATED
ARCHIVED
```

Expected behavior:

1. `PROPOSED`
   - Feature and issues are identified.
   - Branch name and base commit are proposed.
   - No branch exists yet.

2. `AUTHORIZED`
   - The user explicitly approves branch creation.

3. `ACTIVE`
   - The branch exists.
   - One approved issue is being implemented.

4. `ISSUE_REVIEW`
   - The selected issue is implemented and validated.
   - Changes remain uncommitted by default.
   - The user decides whether to adjust, commit, push, or continue.

5. `FEATURE_REVIEW`
   - All intended issues are implemented.
   - Feature-level validation is complete.

6. `READY_FOR_PR`
   - The feature branch is committed and pushed with permission.
   - A pull request may be created only with separate permission.

7. `INTEGRATED`
   - A human-controlled integration into `dev` is complete.

8. `ARCHIVED`
   - Branch deletion or archival occurs only with explicit permission.

The agent must not create the next feature branch merely because the current feature is complete. It must present the completion status and ask the user which feature should be authorized next.

---

## 15. Required Execution Sequence

For each feature, follow this sequence:

```text
1. Inspect the repository and current Git state.
2. Confirm that no protected branch will be modified.
3. Switch to `dev`.
4. Fetch and prune origin.
5. Pull the latest `origin/dev` into local `dev` with fast-forward-only behavior.
6. Inspect the updated `dev` reference.
7. Read all relevant documentation.
8. Identify the feature and its related issues.
9. Check whether an appropriate feature branch already exists.
10. Present the proposed feature branch, issue set, scope, and base commit.
11. Ask for explicit branch-creation permission.
12. Create the feature branch from the synchronized local `dev` only after approval.
13. Select one issue from the authorized feature.
14. Confirm its acceptance criteria and dependencies.
15. Inspect the existing implementation and related tests.
16. Implement only that issue.
17. Add or update tests.
18. Update relevant documentation.
19. Run applicable validation.
20. Review the complete diff.
21. Present the issue review checkpoint.
22. Leave changes uncommitted by default.
23. Commit only after explicit permission, or allow the developer to commit manually.
24. Push only after explicit permission, or allow the developer to push manually.
25. Start the next issue in the same feature branch only after user direction.
26. Repeat the issue workflow until the feature is complete.
27. Run feature-level validation.
28. Present the feature completion report.
29. Create a pull request only after explicit permission.
30. Do not merge into or push directly to dev.
31. Do not create another feature branch without new explicit permission.
```

---

## 16. Required Final Report for Each Issue

At the end of each issue, provide:

```text
Feature identifier and title
Feature branch
Issue identifier and title
Summary of implemented changes
Files changed
Tests added or updated
Validation commands executed
Validation results
Current Git status
Whether changes are committed
Whether changes are pushed
Proposed commit plan
Known limitations
Recommended next step
```

Do not state that work is committed, pushed, merged, or synchronized unless the exact action was actually performed.

---

## 17. Recommended Repository Governance

The following repository controls are strongly recommended:

### 17.1 Protect `main` and `dev` remotely

Configure repository branch protection so that:

- direct pushes are blocked;
- force pushes are blocked;
- branch deletion is blocked;
- pull requests are required;
- required CI checks must pass;
- required reviews must approve;
- conversations must be resolved before merge;
- the source branch must be up to date before merge.

### 17.2 Add ownership rules

Add a `CODEOWNERS` file for sensitive areas such as:

```text
backend state and transitions
database migrations
command execution
sandbox security
LLM gateway
frontend workflow state
CI and deployment configuration
```

### 17.3 Standardize feature and issue traceability

Maintain clear identifiers across:

```text
backlog
documentation
feature branch
commit messages
pull requests
tests
release notes
```

A lightweight feature progress file may be kept under:

```text
docs/features/<feature-id>/progress.md
```

It should record completed issues, remaining issues, decisions, validation, and known risks without becoming an alternative source of authoritative runtime state.

### 17.4 Add pull-request templates

The pull-request template should require:

```text
feature and issue identifiers
scope
acceptance criteria
validation evidence
manual verification
database changes
API changes
configuration changes
security impact
rollback considerations
known limitations
documentation updates
```

### 17.5 Add required CI checks

At minimum, CI should verify the applicable:

```text
backend formatting and linting
backend type checking
backend tests
database migration validity
frontend formatting and linting
frontend type checking
frontend tests
frontend production build
secret scanning
dependency lockfile consistency
```

### 17.6 Record architectural decisions

Use Architecture Decision Records under:

```text
docs/adr/
```

Create an ADR for material decisions affecting architecture, security, execution authority, state ownership, external dependencies, or public contracts.

### 17.7 Keep local-only files out of Git

Maintain an accurate `.gitignore`.

Provide safe templates such as:

```text
.env.example
configuration examples
local development setup documentation
```

Never commit real secrets, tokens, credentials, private paths, generated sandboxes, runtime databases, or local artifacts unless the project explicitly requires a safe fixture.

### 17.8 Define merge strategy

Choose and document one repository-wide merge strategy for feature branches, such as:

```text
merge commit
squash merge
rebase merge
```

The selected strategy should preserve the desired issue traceability and must be applied by the human-controlled integration process.

### 17.9 Add release and rollback discipline

For changes that affect schemas, workflows, commands, or configuration, document:

```text
forward migration
backward compatibility
rollback limitations
data recovery
artifact compatibility
configuration migration
```

---

## 18. Priority of Instructions

When instructions conflict, use this priority:

```text
1. Explicit user instruction in the current task
2. This AGENT.md file
3. Approved project documentation in docs/
4. Existing repository conventions
5. General engineering best practices
```

No general instruction authorizes modification of `main` or `dev`.

No earlier permission authorizes a later branch, commit, push, pull-request, or merge operation.

When uncertain, the agent must preserve user work, keep protected branches untouched, avoid irreversible actions, and ask for a focused decision.
