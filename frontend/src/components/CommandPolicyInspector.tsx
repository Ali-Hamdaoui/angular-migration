"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiClientError } from "@/api/client";
import {
  listCommandTemplates,
  validateCommandPolicy,
} from "@/api/commands";
import type {
  CommandTemplateListDto,
  CommandTemplateDto,
  CommandPolicyValidateRequestDto,
  CommandPolicyValidateResponseDto,
} from "@/types/generated/api";
import styles from "./ControlTowerShell.module.css";

interface CommandPolicyInspectorProps {
  runId: string | null;
  stageId?: string | null;
  connectionStatus?: string;
}

export function CommandPolicyInspector({
  runId,
  stageId,
  connectionStatus,
}: CommandPolicyInspectorProps) {
  const [templates, setTemplates] = useState<CommandTemplateListDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<CommandTemplateDto | null>(null);
  const [validationResult, setValidationResult] = useState<CommandPolicyValidateResponseDto | null>(null);
  const [validating, setValidating] = useState(false);

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    listCommandTemplates()
      .then((value) => {
        setTemplates(value);
      })
      .catch((reason: unknown) => {
        setError(
          reason instanceof ApiClientError
            ? `Failed to load command templates: ${reason.status}`
            : "Failed to load command templates.",
        );
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleValidate(template: CommandTemplateDto) {
    if (!runId) return;
    setValidating(true);
    setError(null);
    setSelectedTemplate(template);
    try {
      const request: CommandPolicyValidateRequestDto = {
        run_id: runId,
        stage_id: stageId ?? null,
        command_id: template.command_id,
        executable: template.executable,
        arguments: template.arguments,
        working_directory_alias: "BASELINE_SANDBOX",
        execution_profile_id: "source-runtime-profile",
        network_profile: "none",
        cancellation_policy: "terminate_process_tree",
        timeout_seconds: 300,
        idempotency_key: `validate-${runId}-${template.command_id}-${Date.now()}`,
        requested_by: "control-tower",
      };
      const result = await validateCommandPolicy(request);
      setValidationResult(result);
    } catch (reason: unknown) {
      setError(
        reason instanceof ApiClientError
          ? `Validation failed: ${reason.message}`
          : "Command validation request failed.",
      );
    } finally {
      setValidating(false);
    }
  }

  return (
    <section className={styles.panel} aria-label="Command policy inspector">
      <div className={styles.previewHeader}>
        <div>
          <p className={styles.kicker}>S3-F01</p>
          <h2>Command Policy Inspector</h2>
        </div>
        {templates ? (
          <strong>
            {templates.total} registered
            {!runId ? " (no run selected)" : ""}
          </strong>
        ) : null}
      </div>

      {loading ? (
        <p className={styles.note}>Loading command templates...</p>
      ) : null}

      {error ? <p role="alert">{error}</p> : null}

      {!loading && templates && templates.templates.length === 0 ? (
        <p className={styles.note}>
          No command templates are registered in the structured registry.
        </p>
      ) : null}

      {!loading && templates && templates.templates.length > 0 ? (
        <>
          <h3>Registered Command Templates</h3>
          <ul className={styles.list}>
            {templates.templates.map((tpl) => (
              <li key={tpl.template_id}>
                <div>
                  <strong>{tpl.command_id}</strong>
                  <br />
                  <code>
                    {tpl.executable} {tpl.arguments.join(" ")}
                  </code>
                  {tpl.description ? (
                    <>
                      <br />
                      <span className={styles.note}>{tpl.description}</span>
                    </>
                  ) : null}
                </div>
                {tpl.executable_aliases.length > 0 ? (
                  <div>
                    <span className={styles.note}>
                      Aliases: {tpl.executable_aliases.join(", ")}
                    </span>
                  </div>
                ) : null}
                {runId ? (
                  <button
                    type="button"
                    onClick={() => handleValidate(tpl)}
                    disabled={validating}
                  >
                    {validating && selectedTemplate?.template_id === tpl.template_id
                      ? "Validating..."
                      : "Validate against policy"}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {validationResult ? (
        <>
          <h3>Validation Result</h3>
          <div
            className={styles.dimensionGrid}
            aria-label="Authorization decision"
          >
            <div>
              <span>Decision</span>
              <strong
                style={{
                  color:
                    validationResult.decision === "accepted"
                      ? "var(--color-success, #2ecc71)"
                      : "var(--color-error, #e74c3c)",
                }}
              >
                {validationResult.decision.toUpperCase()}
              </strong>
            </div>
            <div>
              <span>Authorization ID</span>
              <code>{validationResult.authorization_id}</code>
            </div>
            <div>
              <span>Command</span>
              <code>
                {validationResult.executable}{" "}
                {validationResult.arguments.join(" ")}
              </code>
            </div>
            <div>
              <span>Policy version</span>
              <code>{validationResult.policy_version}</code>
            </div>
          </div>
          {validationResult.reasons.length > 0 ? (
            <div role="alert">
              <p>Rejection reasons:</p>
              <ul className={styles.list}>
                {validationResult.reasons.map((reason, i) => (
                  <li key={i}>
                    <code>{reason}</code>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {validationResult.idempotent_replay ? (
            <p className={styles.note}>
              This result was replayed from a previous identical validation
              request (idempotent).
            </p>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
