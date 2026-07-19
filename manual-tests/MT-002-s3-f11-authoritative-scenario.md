# MT-002: S3-F11 Authoritative Scenario — Run and inspect the required stage build matrix

## Preconditions
- S3-F10 completed successfully
- Backend/frontend running

## Steps
1. Navigate to StageBuildPanel after install/static checks pass
2. Click "Run Build Matrix"
3. Observe per-target progress, diagnostic drill-down
4. Verify build matrix, full logs, compiler diagnostics artifacts
5. Verify STAGE_BUILD_STARTED, TARGET_COMPLETED, COMPLETED events

## Negative test
Submit with missing target configuration → expect blocked status

## Cleanup
Cancel or complete test run.
