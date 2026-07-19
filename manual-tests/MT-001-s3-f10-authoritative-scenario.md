# MT-001: S3-F10 Authoritative Scenario — Run final clean install and deterministic static checks

## Preconditions
- S3-F09 upstream result available (use test fake)
- Backend running on port 8304, frontend on port 3304

## Steps
1. Open StageValidationPanel in a run with a stage ready for validation
2. Click "Run Install + Static Checks"
3. Observe progress through loading → in-progress → completed
4. Verify install log, static diagnostic report, dependency tree, and summary artifacts
5. Verify VALIDATION_FINAL_INSTALL_COMPLETED and STATIC_CHECKS_COMPLETED events

## Negative test
1. Submit with stale state version → expect STALE_STATE_VERSION error
2. Submit with invalid run_id → expect 404

## Cleanup
Cancel or complete the test run, retain immutable evidence.
