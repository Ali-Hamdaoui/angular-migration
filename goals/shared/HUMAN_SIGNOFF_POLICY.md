# Human Product Sign-off Policy

Agent manual validation proves reproducible technical behavior. Human sign-off validates product comprehensibility and governance UX.

Human sign-off is required before integrated acceptance for transformation review/G08, repair Apply/Reject/G10, final assurance/delivery/report G13–G15, and Goal 10 Phase B. It records reviewer identity, commit SHA, scenarios, decision, comments, and evidence references. It is never inferred from an agent result.

A normal feature branch may be pushed with `human_product_signoff=pending` when sign-off is explicitly integration-stage. It may not claim integrated/Jira completion until required human sign-off is `approved`.
