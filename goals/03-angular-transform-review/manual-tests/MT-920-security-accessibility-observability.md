# Security, Accessibility, and Observability

Execute applicable injection/path/forged-ID/secret-leak negatives, keyboard/focus/dialog/error behavior, and verify operators can identify run/stage/command/gate/artifact/correlation and recovery guidance.

## Security Negatives

### MT-920-SEC-01: Path traversal in evidence fetch
1. Send GET `/api/v1/runs/../../etc/passwd/stages/stage-1/transformation-evidence`
2. **Expected**: 422 (validation error) or 404 — no path traversal to filesystem allowed
3. Evidence: `--record` shows the API returns a structured error, not file content

### MT-920-SEC-02: Forged run ID
1. Send GET `/api/v1/runs/nonexistent-run/stages/stage-1/transformation-evidence`
2. **Expected**: 404 with `{"detail": "No evidence found"}` or similar
3. Evidence: `--record` shows error response body

### MT-920-SEC-03: Forged state version (stale write rejection)
1. Complete normal evidence generation flow; note the current `state_version`
2. Send POST `/api/v1/runs/{id}/stages/{stageId}/transformation-evidence` with an `expected_state_version` lower than the current version
3. **Expected**: 409 Conflict — the backend rejects stale writes
4. Evidence: `--record` shows the 409 response

### MT-920-SEC-04: Empty expected_state_version
1. Send POST `/api/v1/runs/{id}/stages/{stageId}/transformation-evidence` without `expected_state_version`
2. **Expected**: 422 Validation Error
3. Evidence: `--record` shows structured validation error

### MT-920-SEC-05: Secret leak in response bodies
1. Complete a full transformation evidence flow
2. Inspect all API responses and log output for any occurrence of `.env`, `secrets`, `password`, `token`, `credential` values
3. **Expected**: No secrets are echoed back in response bodies or logs
4. Evidence: `--record` grep of response payloads shows no leaked patterns

### MT-920-SEC-06: Injected classification (binary content in .ts file)
1. Create a file with `.ts` extension containing compressed/binary content (non-UTF-8 bytes)
2. Run classification
3. **Expected**: File is handled without error (content decoding failure is caught); classification falls back gracefully
4. Evidence: `--record` shows the file classified without crashing

### MT-920-SEC-07: Misclassified forbidden file
1. Add a file path matching a forbidden pattern (e.g., `.env`), but containing safe content
2. Run classification
3. **Expected**: File is still classified `FORBIDDEN` (path-based detection, not content-based)
4. Evidence: `--record` shows `classification: "forbidden"` regardless of content

## Accessibility

### MT-920-A11Y-01: Keyboard navigation of evidence viewer
1. Open the Transformation Evidence viewer
2. Tab through all interactive elements (Generate/Refresh buttons, classification filter dropdown, tab list)
3. **Expected**: Every interactive element receives focus; dropdown can be operated with arrow keys; tabs activate via Enter/Space
4. Evidence: `--record` terminal output shows focus order

### MT-920-A11Y-02: Screen reader labels
1. With a screen reader active (or inspect the DOM), examine the evidence panel
2. **Expected**: The panel has `role="region"` with `aria-label="Transformation Evidence Viewer"`; all file entries have `role="listitem"`; the tablist has `role="tablist"`; the filter has `aria-label="Filter by risk classification"`
3. Evidence: `--record` or DOM snapshot shows all required ARIA attributes

### MT-920-A11Y-03: Color-independent indicators
1. In the diff file list, verify that risk classification is conveyed via text labels (the classification badge text) in addition to color
2. **Expected**: Every file row displays a visible text classification label (e.g., "sensitive", "generated", "unknown"); color alone is not the only differentiator
3. Evidence: `--record` screenshot or DOM dump shows text labels

### MT-920-A11Y-04: Error announcements
1. Trigger an evidence fetch failure (e.g., stop the backend)
2. **Expected**: The error message is rendered inside `role="alert"` for immediate screen reader announcement
3. Evidence: `--record` shows the alert role present on the error element

### MT-920-A11Y-05: Reconnection status announcement
1. While the viewer is connected, restart the backend event stream
2. **Expected**: A reconnection banner with `role="alert"` and text "Reconnecting to backend..." appears
3. Evidence: `--record` shows the banner with the alert role

## Observability

### MT-920-OBS-01: Correlation ID propagation
1. Complete a full evidence generation flow
2. Inspect the evidence response
3. **Expected**: `correlation_id` is present and consistent with the run's correlation chain; same value visible in the frontend metadata section
4. Evidence: `--record` shows `correlation_id` in the response and frontend

### MT-920-OBS-02: Run and stage identification
1. In the evidence viewer, locate run ID and stage ID in the metadata section
2. **Expected**: Both `run_id` and `stage_id` are displayed in the metadata grid
3. Evidence: `--record` shows the run and stage IDs visible in the UI

### MT-920-OBS-03: Diff checksum display
1. Locate the checksum in the summary bar
2. **Expected**: A truncated `diff_checksum` is shown (first 16 characters) for quick cross-reference
3. Evidence: `--record` shows the checksum value

### MT-920-OBS-04: Artifact link resolution
1. Complete evidence generation with artifacts attached
2. Inspect the artifact links at the bottom of the viewer
3. **Expected**: Each `artifact_id` produces a clickable link to `/api/v1/artifacts/{id}`
4. Evidence: `--record` shows the rendered links with correct hrefs

### MT-920-OBS-05: Stale evidence visual indicator
1. Generate evidence successfully
2. Change the state version (simulate a conflicting update) and re-fetch
3. **Expected**: The viewer transitions to "stale" state with a yellow "Evidence is stale — refresh" bar and a Refresh button
4. Evidence: `--record` shows the stale indicator

### MT-920-OBS-06: Evidence completeness status pill
1. After evidence generation, observe the status pill in the header
2. **Expected**: A `StatusPill` shows either `PASSED` (complete) or `BLOCKED` (incomplete with reason)
3. Evidence: `--record` shows the pill value

### MT-920-OBS-07: Filter warning for hidden high-risk items
1. Apply a risk classification filter that hides high-risk or sensitive files
2. **Expected**: A warning banner appears: "Filter hides N high-risk finding(s)"
3. Evidence: `--record` shows the warning banner text
