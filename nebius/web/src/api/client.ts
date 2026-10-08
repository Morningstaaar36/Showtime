/** Fetch wrapper: JSON in/out, designed errors ({code, message, hint}) surfaced as ApiError. */

export class ApiError extends Error {
  code: string;
  hint: string | null;
  status: number;
  details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, hint: string | null,
              details: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.hint = hint;
    this.details = details;
  }
}

const BASE = "/api/v1";

async function parse<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    // a proxy page (502/503 while the API starts or restarts) instead of our JSON
    if (res.status >= 500 || res.status === 0) {
      throw new ApiError(res.status, "network", "The Showtime server isn't reachable.",
                         "It may still be starting; this retries automatically. Otherwise start it with: make up");
    }
    throw new ApiError(res.status, "bad_response", `Unexpected response from the server (${res.status}).`, null);
  }
  if (!res.ok) {
    const b = (body ?? {}) as { code?: string; message?: string; hint?: string; details?: Record<string, unknown> };
    throw new ApiError(res.status, b.code ?? "http_error", b.message ?? `Request failed (${res.status})`,
                       b.hint ?? null, b.details ?? {});
  }
  return body as T;
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: body instanceof FormData ? undefined : { "Content-Type": "application/json" },
      body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "network", "The Showtime server isn't reachable.", "Start it with: make up");
  }
  return parse<T>(res);
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>("GET", path, undefined, signal),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body ?? {}),
  del: <T>(path: string) => request<T>("DELETE", path),
  upload: <T>(path: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<T>("POST", path, fd);
  },
  /** Raw binary (trajectories, density grids). */
  async binary(path: string, signal?: AbortSignal): Promise<ArrayBuffer> {
    const res = await fetch(`${BASE}${path}`, { signal });
    if (!res.ok) await parse<never>(res);
    return res.arrayBuffer();
  },
  url: (path: string) => `${BASE}${path}`,
};
