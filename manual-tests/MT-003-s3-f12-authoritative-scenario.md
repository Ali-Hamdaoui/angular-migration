# MT-003: S3-F12 Authoritative Scenario — Run complete stage tests and conditional lint

## Preconditions
- S3-F11 completed successfully
- Backend/frontend running

## Steps
1. Navigate to StageTestPanel after builds pass
2. Click "Run Tests + Lint"
3. Observe test/lint progress, baseline comparison, known-failure delta
4. Verify test/lint logs, structured results, comparison artifacts
5. Verify STAGE_TESTS_COMPLETED and STAGE_LINT_COMPLETED events

## Negative test
Submit with tampered checksum → expect rejection
