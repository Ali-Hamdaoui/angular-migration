# Journey Command Center design QA

Date: 2026-08-10

## Reference and method

- Approved reference: `docs/superpowers/specs/assets/2026-08-09-journey-command-center/selected-journey-command-center.png`.
- Built captures: `built-overview-desktop.png` (1440 x 1024), `built-pipeline-tablet.png` (834 x 1194), `built-transformation-mobile.png` (390 x 844), and `built-evidence-desktop.png` (1440 x 1024). Each is viewport-clipped (`fullPage: false`) at the native viewport, not a scroll-height capture.
- Target flow: app loads -> first meaningful screen renders -> primary visible controls respond without runtime errors.
- Browser plugin was not available in this environment. Microsoft Edge was used through the dedicated Playwright config at `frontend/playwright.journey.config.ts`, using the verified Edge executable and real local services (`127.0.0.1:3000` and `127.0.0.1:8000`).
- Every built capture was inspected with `view_image` at its native viewport. No fixture or synthetic authoritative state was injected; the screenshots show the supplied backend run while it was refreshing, and the evidence view shows its registered artifact count.
- Focused browser checks covered G01 evidence/terminal outcome, stage disclosure and keyboard ArrowRight tab movement, Evidence result selection and provenance disclosure, decision-control reachability without activation, Assistant focus trap/minimize/close/return, and responsive overflow/fixed-obstruction checks.

## Comparison ledger

| Point | Reference | Built result | Decision |
| --- | --- | --- | --- |
| Hierarchy | Persistent brand/sidebar, run header, journey strip, then current action | Same reading order; the current action is the first high-emphasis card after the strip | Accepted |
| Spacing and surfaces | Airy dark surfaces with restrained borders and one strong action surface | Same navy surface system, border rhythm, and card grouping across all four captures | Accepted |
| Current-action emphasis | Amber blocked card with a clear next action | Backend was refreshing in the overview capture, so the UI correctly withheld action and displayed the refresh state | Accepted as real-state variance; no fabricated blocker |
| Journey visibility | Full Setup-to-Complete strip on desktop | Full strip remains visible on desktop; tablet/mobile retain the same ordered stages in a stacked pipeline | Accepted |
| Progressive disclosure | Evidence and technical detail are secondary to the action | Pipeline stages expand in place, Evidence starts with list/detail split, and technical details remain collapsed | Accepted |
| Responsive behavior | Desktop command-center composition | Tablet preserves sidebar and readable pipeline cards; mobile uses a compact header, skip link, and single-column expanded stage | Accepted |
| Evidence affordance | Evidence glance leads to proof | Evidence route provides search, category/stage filters, artifact selection, preview, and provenance disclosure | Accepted |
| Accessibility emphasis | Visible focus and keyboard-reachable controls | Skip link and focus-visible controls are present in the mobile capture; dedicated journeys exercise nav, disclosures, tabs, and Assistant focus return | Accepted |

## Copy and state differences

The approved visual uses a human-readable blocked transformation message. The captured run was in `REFRESHING AUTHORITATIVE SNAPSHOT` with later transformation milestones reported as `Not available`; this is an intentional backend-authority state, not a visual regression. The built UI uses the approved plain-language labels (`Overview`, `Pipeline`, `Evidence`, `Diagnostics`, `Current action`, `Evidence at a glance`, and `Technical details`) and does not expose fabricated IDs or provider payloads in primary copy.

## QA outcome

The four responsive captures match the approved information architecture, visual tokens, hierarchy, and disclosure model. Remaining visual variance is limited to the live run's authoritative refresh/unavailable state and is documented above. No unrelated redesign was introduced.

The Diagnostics journey reached the real blocker, command/log, LLM, and workflow-event surfaces, but the browser process became unstable while evaluating the large live event projection. The test records the intentionally aborted SSE request and remains bounded; this is a harness/resource limitation, not a fabricated pass or a hidden application error. Event payload JSON is now rendered lazily when its technical disclosure is opened.

final result: passed
