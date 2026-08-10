import { presentArtifact, type ArtifactCategory } from "@/presentation/artifacts";
import { makeArtifact } from "@/test/authoritativeFixtures";

describe("presentArtifact", () => {
  it.each([
    ["patch", "evidence/repair/attempt-2/reviewed.patch", "diff"],
    ["diff", "evidence/stage-18-19/angular.diff", "diff"],
    ["report", "delivery/final-report.md", "report"],
    ["command_log", "commands/npm-ci.log", "command"],
  ] as const)("uses explicit artifact type %s before path heuristics", (artifactType, relativePath, category) => {
    const presentation = presentArtifact(makeArtifact({
      artifact_type: artifactType,
      relative_path: relativePath,
    }));

    expect(presentation.category).toBe(category);
  });

  it.each([
    ["03_analysis/g04_approval_package.json", null, "gate"],
    ["commands/build/stdout.txt", "stage-18-19", "command"],
    ["stage-19-20/validation/parity-evidence.json", "stage-19-20", "validation"],
    ["delivery/migration-summary.json", null, "report"],
    ["01_source_snapshot/source-manifest.json", null, "snapshot"],
    ["diagnostics/worker_failure.json", null, "diagnostic"],
  ] as Array<[string, string | null, ArtifactCategory]>)("maps stable path %s to %s", (relativePath, stageId, category) => {
    const presentation = presentArtifact(makeArtifact({ relative_path: relativePath, stage_id: stageId }));

    expect(presentation.category).toBe(category);
  });

  it("produces a human title, stage label, attempt label, and raw provenance", () => {
    const artifact = makeArtifact({
      artifact_id: "repair-diff-2",
      artifact_type: "diff",
      stage_id: "stage-20-21",
      relative_path: "stages/stage-20-21/repair_attempt_2/reviewed_repair.diff",
      checksum: "sha256:repair-two",
    });

    expect(presentArtifact(artifact)).toEqual({
      artifact,
      title: "Reviewed repair",
      category: "diff",
      stageLabel: "Angular 20 to 21",
      attemptLabel: "Attempt 2",
      rawPath: "stages/stage-20-21/repair_attempt_2/reviewed_repair.diff",
      searchableText: "Reviewed repair stages/stage-20-21/repair_attempt_2/reviewed_repair.diff sha256:repair-two diff Angular 20 to 21 Attempt 2",
    });
  });

  it("keeps unknown paths selectable under Other", () => {
    const presentation = presentArtifact(makeArtifact({
      artifact_type: "json",
      relative_path: "future_backend/new_evidence_shape.json",
    }));

    expect(presentation).toMatchObject({
      title: "New evidence shape",
      category: "other",
      rawPath: "future_backend/new_evidence_shape.json",
    });
  });

  it.each([
    "reporter_notes.json",
    "errorless.json",
    "commandments.json",
    "patchouli.json",
    "validationish.json",
    "snapshotting.json",
    "different.json",
  ])("does not promote ambiguous filename token %s", (filename) => {
    const presentation = presentArtifact(makeArtifact({
      artifact_type: "json",
      relative_path: `future_backend/${filename}`,
    }));

    expect(presentation.category).toBe("other");
  });
});
