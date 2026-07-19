import { AcceptanceChecklist } from "@/components/AcceptanceChecklist";
import { getAcceptanceStatus } from "@/api/acceptance";

export const dynamic = "force-dynamic";

export default async function AcceptancePage() {
  let initialStatus = null;
  let fetchError: string | null = null;

  try {
    initialStatus = await getAcceptanceStatus();
  } catch (e) {
    fetchError = e instanceof Error ? e.message : "Failed to fetch acceptance status";
  }

  if (fetchError) {
    return (
      <main style={{ maxWidth: "1220px", margin: "0 auto", padding: "2rem" }}>
        <div
          style={{
            background: "rgba(231,76,60,0.1)",
            border: "1px solid rgba(231,76,60,0.3)",
            borderRadius: "0.5rem",
            padding: "1rem",
            color: "#e74c3c",
          }}
        >
          <h2>Backend Unreachable</h2>
          <p>{fetchError}</p>
          <a
            href="/acceptance"
            style={{
              color: "#5a8cff",
              textDecoration: "underline",
              fontWeight: 600,
            }}
          >
            Retry
          </a>
        </div>
      </main>
    );
  }

  return (
    <main>
      <AcceptanceChecklist initialStatus={initialStatus} />
    </main>
  );
}
