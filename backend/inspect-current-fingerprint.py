from pathlib import Path
from app.services.workspace_fingerprint import STAGE_FINGERPRINT_PROFILE

workspace = Path(
    r"C:\a\angular-crud-poc-angular-21-1757fa11ce9e\.migration-factory\runs\run-a2a348a950bb\stage-sandboxes\angular-20-to-21--1269ed5e61c08196"
)

print("WORKSPACE:", workspace)
print("CURRENT FINGERPRINT:")
print(STAGE_FINGERPRINT_PROFILE.fingerprint(workspace))
