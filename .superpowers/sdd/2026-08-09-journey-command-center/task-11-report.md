# Task 11 report: subordinate accessible Assistant drawer

## Scope

The Assistant is now a support surface for the migration journey. It has closed, minimized, and expanded states; an expanded drawer exposes `role="dialog"` and `aria-modal="true"`, supports Escape dismissal, focus trapping, focus return, reduced-motion styling, and a full-height mobile sheet. Responses lead with current state, waiting condition, blocker, next permitted action, and evidence. Technical metadata remains under Response details. Existing persisted conversation, API retry lifecycle, citations, and route proposals remain supported.

## Strict RED evidence

The new accessibility and hierarchy tests failed before implementation:

```text
Test Files: 2 failed
Tests: 4 failed, 13 passed
```

Failures covered missing `aria-modal`, missing Escape/focus trap behavior, and missing shared Evidence/response hierarchy titles.

## Focused GREEN evidence

```text
npm test -- --run src/components/__tests__/AssistantPanel.test.tsx src/components/__tests__/AssistantPanel.r7.test.tsx src/components/__tests__/AssistantEvidenceDrawer.test.tsx
Test Files: 3 passed
Tests: 18 passed

npm run typecheck
Exit code: 0

npm run lint
Exit code: 0

git diff --check
Exit code: 0
```

The full frontend suite was intentionally not run. No backend files or API contracts changed.

## Review fix round 1

The Assistant popup now portals to `document.body`, keeping the mobile sheet viewport-wide even when the sidebar is transformed. Expanded focus scope redirects focus from the background, traps Tab, marks background siblings `aria-hidden`, and restores the exact opener. The visible header kicker is plain-language `Read-only assistant`; the internal `AMFA-221` identifier is no longer rendered in user-facing chrome. Model, usage, and technical identifiers are kept in Response details. Evidence titles resolve registered artifact IDs through `presentArtifact`; checksum and locator values remain technical details.

```text
npm test -- --run src/components/__tests__/AssistantPanel.test.tsx src/components/__tests__/AssistantPanel.r7.test.tsx src/components/__tests__/AssistantEvidenceDrawer.test.tsx
Test Files: 3 passed
Tests: 22 passed

npm run typecheck
Exit code: 0

npm run lint
Exit code: 0

git diff --check
Exit code: 0
```

The full frontend suite remains intentionally unrun.

The focused review assertion also verifies that `AMFA-221` is absent from the rendered Assistant panel.
