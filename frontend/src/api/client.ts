/** Shared HTTP transport for frontend-to-backend API calls. */

export type FetchImplementation = typeof fetch;

export class ApiClientError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiClientError";
  }
}

export function getBackendBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
}

export function createApiClient(baseUrl = getBackendBaseUrl(), fetchImplementation: FetchImplementation = fetch) {
  async function get<T>(path: string): Promise<T> {
    const response = await fetchImplementation(`${baseUrl}${path}`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!response.ok) {
      throw new ApiClientError(`Backend request failed: GET ${path}`, response.status);
    }
    return response.json() as Promise<T>;
  }


  async function post<TResponse, TBody>(path: string, body: TBody): Promise<TResponse> {
    const response = await fetchImplementation(`${baseUrl}${path}`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store"
    });
    if (!response.ok) {
      throw new ApiClientError(`Backend request failed: POST ${path}`, response.status);
    }
    return response.json() as Promise<TResponse>;
  }

  return { get, post };
}

export const apiClient = createApiClient();
