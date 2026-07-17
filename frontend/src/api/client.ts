/** Shared HTTP transport for frontend-to-backend API calls. */

export type FetchImplementation = typeof fetch;

export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly method = "unknown",
    public readonly path = "unknown",
    public readonly responseBody: string | null = null,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

export function getBackendBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
}

export function createApiClient(baseUrl = getBackendBaseUrl(), fetchImplementation: FetchImplementation = fetch) {
  async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
    const response = await fetchImplementation(`${baseUrl}${path}`, {
      method,
      headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) },
      cache: "no-store",
      body: body ? JSON.stringify(body) : undefined,
    });
    const responseBody = await response.text();
    if (!response.ok) {
      throw new ApiClientError(
        `Backend request failed: ${method} ${path} (${response.status})`,
        response.status,
        method,
        path,
        responseBody || null,
      );
    }
    try {
      return JSON.parse(responseBody) as T;
    } catch {
      throw new ApiClientError(
        `Backend returned invalid JSON: ${method} ${path}`,
        response.status,
        method,
        path,
        responseBody || null,
      );
    }
  }

  return {
    get: <T>(path: string) => request<T>("GET", path),
    post: <T>(path: string, body: unknown) => request<T>("POST", path, body),
  };
}

export const apiClient = createApiClient();