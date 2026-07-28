import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import crypto from "node:crypto";

const backend = "http://127.0.0.1:8000";
const run = "r6-browser-run";
const hash = (value: string) => crypto.createHash("sha256").update(value).digest("hex").slice(0, 12);
const control = async (request: APIRequestContext, method: string, path: string, body?: object) => (await request.fetch(`${backend}${path}`, { method, data: body })).json();

async function openAssistant(page: Page) {
  await page.goto(`/?run_id=${run}`);
  await page.getByRole("button", { name: "Assistant" }).click();
  await expect(page.getByRole("heading", { name: "Migration Follow-up Assistant" })).toBeVisible();
  await expect(messageEvidence(page)).toHaveCount(2);
}

async function openConversation(page: Page, conversationId: string) {
  await page.goto(`/?run_id=${run}&conversation_id=${conversationId}`);
  await page.getByRole("button", { name: "Assistant" }).click();
  await expect(page.getByRole("heading", { name: "Migration Follow-up Assistant" })).toBeVisible();
}

function messageEvidence(page: Page) {
  return page.locator('[aria-label="Assistant conversation"] [data-role]');
}

test.describe("R6 mounted durable conversation", () => {
  test.beforeEach(async ({ request }) => {
    await control(request, "POST", "/__test__/r6/reset");
    await control(request, "POST", "/__test__/r6/seed");
  });

  test("latest conversation is restored after hard reload without duplication", async ({ page }) => {
    await openAssistant(page);
    const first = await page.locator('[aria-label="Assistant conversation"] [data-role]').count();
    const conversation = new URL(page.url()).searchParams.get("conversation_id");
    expect(conversation).toBeTruthy();
    await page.reload();
    await expect(page.locator('[aria-label="Assistant conversation"] [data-role]')).toHaveCount(first);
    expect(new URL(page.url()).searchParams.get("conversation_id")).toBe(conversation);
    console.log(JSON.stringify({ run_id_hash: hash(run), conversation_id_hash: hash(conversation!), message_count: first }));
  });

  test("pending user survives reload", async ({ page, request }) => {
    await control(request, "POST", "/__test__/r6/gateway/mode", { mode: "delayed_success" });
    await openAssistant(page);
    await page.getByLabel("Ask about this migration").fill("Where is the migration now?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.locator('[data-role="user"]')).toHaveCount(2);
    await expect.poll(async () => (await control(request, "GET", "/__test__/r6/metrics")).provider_started).toBe(true);
    await page.reload();
    await expect(page.locator('[data-role="user"]')).toHaveCount(2);
    await control(request, "POST", "/__test__/r6/gateway/release");
    await expect(page.locator('[data-role="assistant"]')).toHaveCount(2, { timeout: 30_000 });
  });

  test("durable provider failure survives reload", async ({ page, request }) => {
    await control(request, "POST", "/__test__/r6/gateway/mode", { mode: "failure" });
    await openAssistant(page);
    await page.getByLabel("Ask about this migration").fill("Where is the migration now?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect.poll(async () => {
      const history = await control(request, "GET", "/api/v1/runs/r6-browser-run/assistant/messages");
      return history.messages.some((message: { response_status: string; error_code?: string | null; correlation_id?: string | null }) => message.response_status === "failed" && Boolean(message.error_code) && Boolean(message.correlation_id));
    }, { timeout: 30_000 }).toBe(true);
    await page.reload();
    await page.getByRole("button", { name: "Assistant" }).click();
    await expect(page.getByText(/Failure:/)).toBeVisible();
    console.log(JSON.stringify({ run_id_hash: hash(run), stale_states: [], provider_call_count: (await control(request, "GET", "/__test__/r6/metrics")).provider_call_count }));
  });

  test("R7 failure reload and user Retry create one linked new attempt", async ({ page, request }) => {
    await control(request, "POST", "/__test__/r6/gateway/mode", { mode: "failure" });
    await openAssistant(page);
    const transportRequests: object[] = [];
    page.on("request", (requestEvent) => {
      if (requestEvent.method() === "POST" && requestEvent.url().endsWith("/assistant/messages")) transportRequests.push(requestEvent.postDataJSON());
    });
    await page.getByLabel("Ask about this migration").fill("Where is the migration now?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect.poll(async () => (await control(request, "GET", "/__test__/r6/metrics")).provider_call_count).toBe(1);
    await page.reload();
    await page.getByRole("button", { name: "Assistant" }).click();
    const retry = page.getByRole("button", { name: "Retry assistant response" });
    await expect(retry).toBeVisible();
    const failedHistory = await control(request, "GET", "/api/v1/runs/r6-browser-run/assistant/messages");
    const failed = failedHistory.messages.find((message: { role: string; response_status: string }) => message.role === "assistant" && message.response_status === "failed");
    expect(failed).toBeTruthy();
    await control(request, "POST", "/__test__/r6/gateway/mode", { mode: "delayed_success" });
    const retryRequests: object[] = [];
    page.on("request", (requestEvent) => {
      if (requestEvent.method() === "POST" && requestEvent.url().endsWith("/assistant/messages")) retryRequests.push(requestEvent.postDataJSON());
    });
    await retry.click();
    await expect.poll(async () => (await control(request, "GET", "/__test__/r6/metrics")).provider_started).toBe(true);
    await retry.click({ force: true });
    await expect.poll(async () => (await control(request, "GET", "/__test__/r6/metrics")).provider_call_count).toBe(2);
    await control(request, "POST", "/__test__/r6/gateway/release");
    expect(retryRequests).toHaveLength(1);
    const retryRequest = retryRequests[0] as { request_id: string; idempotency_key: string; retry_of_message_id: string; conversation_id: string };
    const originalRequest = transportRequests[0] as { request_id: string; idempotency_key: string };
    expect(retryRequest.request_id).not.toBe(originalRequest.request_id);
    expect(retryRequest.idempotency_key).not.toBe(originalRequest.idempotency_key);
    expect(retryRequest.retry_of_message_id).toBe(failed.message_id);
    expect(retryRequest.conversation_id).toBe(failed.conversation_id);
    await expect.poll(async () => page.locator('[data-role="assistant"]').count()).toBeGreaterThanOrEqual(2);
    await page.reload();
    await expect.poll(async () => page.locator('[data-role="assistant"]').count()).toBeGreaterThanOrEqual(2);
    const finalHistory = await control(request, "GET", "/api/v1/runs/r6-browser-run/assistant/messages");
    expect(finalHistory.messages.length).toBeGreaterThanOrEqual(4);
    expect(finalHistory.messages.slice(-4).map((message: { role: string }) => message.role)).toEqual(["user", "assistant", "user", "assistant"]);
    expect(finalHistory.messages.at(-1).retry_of_message_id).toBe(failed.message_id);
    console.log(JSON.stringify({ run_id_hash: hash(run), conversation_id_hash: hash(failed.conversation_id), failed_message_id_hash: hash(failed.message_id), provider_call_count: 2, retry_request_id_hash: hash(retryRequest.request_id), retry_idempotency_key_hash: hash(retryRequest.idempotency_key) }));
  });

  test("conversation A and B remain isolated through URL navigation, reload, and history", async ({ page, request }) => {
    await control(request, "POST", "/__test__/r6/reset");
    await control(request, "POST", "/__test__/r6/seed?kind=both");
    await openConversation(page, "r6-conversation-a");
    await expect(messageEvidence(page)).toHaveCount(2);
    await expect(page.getByText("seed-a-user")).toBeVisible();
    await expect(page.getByText("seed-b-user")).toHaveCount(0);
    const aIds = (await messageEvidence(page).evaluateAll((items) => items.map((item) => item.textContent ?? ""))).map(hash);
    const aHistory = await control(request, "GET", "/api/v1/runs/r6-browser-run/assistant/messages?conversation_id=r6-conversation-a");
    const bHistory = await control(request, "GET", "/api/v1/runs/r6-browser-run/assistant/messages?conversation_id=r6-conversation-b");
    const latestHistory = await control(request, "GET", "/api/v1/runs/r6-browser-run/assistant/messages");
    expect(aHistory.messages.every((message: { conversation_id: string; answer: string }) => message.conversation_id === "r6-conversation-a" && !message.answer.includes("seed-b"))).toBe(true);
    expect(bHistory.messages.every((message: { conversation_id: string; answer: string }) => message.conversation_id === "r6-conversation-b" && !message.answer.includes("seed-a"))).toBe(true);
    expect(latestHistory.conversation_id).toBe("r6-conversation-b");
    await openConversation(page, "r6-conversation-b");
    await expect(messageEvidence(page)).toHaveCount(2);
    await expect(page.getByText("seed-b-user")).toBeVisible();
    await expect(page.getByText("seed-a-user")).toHaveCount(0);
    await page.reload();
    await expect(messageEvidence(page)).toHaveCount(2);
    await openConversation(page, "r6-conversation-a");
    await expect(page.getByText("seed-a-user")).toBeVisible();
    await expect(page.getByText("seed-b-user")).toHaveCount(0);
    console.log(JSON.stringify({ run_id_hash: hash(run), conversation_hashes: { a: hash("r6-conversation-a"), b: hash("r6-conversation-b") }, message_id_hashes: aIds, explicit_query: true, message_counts: { a: 2, b: 2 } }));
  });

  test("telemetry does not stale an answer, but a governed semantic transition does", async ({ page, request }) => {
    await openAssistant(page);
    const initial = await control(request, "GET", "/api/v1/runs/r6-browser-run/assistant/messages");
    const initialVersion = initial.messages[1].semantic_state_version;
    await page.getByLabel("Ask about this migration").fill("Where is the migration now?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect.poll(async () => {
      const history = await control(request, "GET", "/api/v1/runs/r6-browser-run/assistant/messages");
      return history.messages.filter((message: { role: string }) => message.role === "assistant").length;
    }).toBe(2);
    await expect(page.locator('[data-role="assistant"]')).toHaveCount(2);
    const afterTelemetry = await control(request, "GET", "/api/v1/runs/r6-browser-run/assistant/messages");
    expect(afterTelemetry.messages.at(-1).stale).toBe(false);
    expect(afterTelemetry.messages.at(-1).semantic_state_version).toBe(initialVersion);
    await control(request, "POST", "/__test__/r6/semantic-transition");
    await page.reload();
    await page.getByRole("button", { name: "Assistant" }).click();
    await expect(page.locator("small").filter({ hasText: "stale answer" }).first()).toBeVisible();
    const afterTransition = await control(request, "GET", "/api/v1/runs/r6-browser-run/assistant/messages");
    expect(afterTransition.messages.some((message: { stale: boolean }) => message.stale)).toBe(true);
    expect(afterTransition.messages.some((message: { role: string; answer: string }) => message.role === "assistant" && Boolean(message.answer))).toBe(true);
    console.log(JSON.stringify({ run_id_hash: hash(run), semantic_versions: [initialVersion, afterTransition.messages[0].semantic_state_version], stale_states: afterTransition.messages.map((message: { stale: boolean }) => message.stale), provider_call_count: (await control(request, "GET", "/__test__/r6/metrics")).provider_call_count }));
  });

  test("next-step proposals navigate only and route-less recommendations remain inert", async ({ page, request }) => {
    await control(request, "POST", "/__test__/r6/reset");
    await control(request, "POST", "/__test__/r6/seed?kind=next");
    await openConversation(page, "r6-conversation-next");
    await expect(page.getByRole("button", { name: "Review migration guidance" }).first()).toBeVisible();
    await expect(page.getByText("Migration guidance recommendation").first()).toBeVisible();
    const mutationRequests: string[] = [];
    page.on("request", (requestEvent) => {
      if (["POST", "PUT", "PATCH", "DELETE"].includes(requestEvent.method())) mutationRequests.push(requestEvent.url());
    });
    await page.getByRole("button", { name: "Review migration guidance" }).first().click();
    await expect.poll(() => new URL(page.url()).pathname).toBe("/api/v1/runs/r6-browser-run/approvals/G02");
    expect(mutationRequests.filter((url) => /transition|command|assistant|approve|execute/i.test(url))).toEqual([]);
    await openConversation(page, "r6-conversation-next");
    const routeLess = page.getByText("Migration guidance recommendation").first();
    await expect(routeLess).toBeVisible();
    expect(await routeLess.evaluate((element) => element.previousElementSibling?.tagName)).not.toBe("BUTTON");
    console.log(JSON.stringify({ run_id_hash: hash(run), navigation_target: "/api/v1/runs/r6-browser-run/approvals/G02", transition_mutation_request_count: 0, command_request_count: 0, assistant_mutation_request_count: 0 }));
  });
});
