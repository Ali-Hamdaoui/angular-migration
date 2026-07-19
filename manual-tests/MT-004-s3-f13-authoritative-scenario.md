# MT-004: S3-F13 Authoritative Scenario — Compare parity evidence, display assurance, decide G09

## Preconditions
- S3-F10, S3-F11, S3-F12 completed
- Backend/frontend running

## Steps
1. Navigate to StageAssurancePanel after all validation steps pass
2. Click "Compare Parity"
3. Review route/API deltas, assurance cards, proof labels
4. Verify PARITY_COMPARISON_COMPLETED event
5. If all checks pass → approve G09
6. Verify G09_APPROVED event and gate transition

## Negative test
Attempt G09 approval with failed core gate → expect rejection
