# MT-005: S3-F14 Authoritative Scenario — Seal G12, copy-forward

## Preconditions
- S3-F13 completed with G09 approved
- Backend/frontend running

## Steps
1. Navigate to StageSealPanel after G09 approval
2. Click "Complete Package" → verify cleanup + fingerprint
3. Verify STAGE_CLEANUP_COMPLETED event
4. Approve G12 → verify G12_APPROVED event
5. Click "Copy Forward" → verify next stage created
6. Verify NEXT_STAGE_CREATED/SANDBOX_READY events

## Negative test
Attempt copy-forward without G12 approval → expect rejection
