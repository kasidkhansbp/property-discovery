// Thin fetch wrapper for the gateway. One place that knows the base URL, turns
// non-2xx responses into a typed error (surfacing FastAPI's `detail`), and
// parses JSON — every endpoint module builds on this.

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiGet<T>(
  path: string,
  params?: URLSearchParams,
  signal?: AbortSignal,
): Promise<T> {
  const query = params && [...params.keys()].length ? `?${params.toString()}` : "";
  const res = await fetch(`${API_BASE_URL}${path}${query}`, {
    signal,
    headers: { Accept: "application/json" },
  });

  if (!res.ok) {
    // FastAPI returns `{ "detail": ... }` on 422/4xx; fall back to the status text.
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json())?.detail ?? res.statusText;
    } catch {
      /* body was not JSON */
    }
    const message = typeof detail === "string" ? detail : JSON.stringify(detail);
    throw new ApiError(res.status, message);
  }

  return (await res.json()) as T;
}
