/** Durable stage/G07 events emitted by the post-AMFA-171 backend. */
export const STAGE_G07_EVENT_TYPES = [
  "STAGE_CREATED",
  "STAGE_PREPARING",
  "STAGE_PLAN_LOCKED",
  "STAGE_WAITING_APPROVAL",
  "STAGE_SANDBOX_READY",
  "G07_CREATED",
  "G07_APPROVED",
  "G07_MODIFICATION_REQUESTED",
  "G07_REJECTED",
  "G07_STALE",
] as const;

export type StageG07EventType = (typeof STAGE_G07_EVENT_TYPES)[number];
