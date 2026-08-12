import inspect

from app.services.angular_transformation_evidence_service import (
    AngularTransformationEvidenceService,
)

print("=== MODULE FILE ===")
print(inspect.getsourcefile(AngularTransformationEvidenceService))

print("\n=== CURRENT _line_version SOURCE ===")
print(inspect.getsource(AngularTransformationEvidenceService._line_version))
