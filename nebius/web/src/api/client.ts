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

/** An error's message with the API's hint after it (what to do), for toasts and banners. */
export function errorText(e: Error): string {
  const hint = e instanceof ApiError ? e.hint : null;
  return hint ? `${e.message} ${hint}` : e.message;
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

/** How long a request may take before it fails with a clear error. Writes wait longer: some
 * start an agent (designing a venue, an edit) that may take a few minutes on a free model.
 * The server sets both (WEB_READ_TIMEOUT_S, WEB_WRITE_TIMEOUT_S, sent in /health); these are
 * its defaults, used only until the first /health answer arrives. */
export const REQUEST_TIMEOUT_MS = { read: 60_000, write: 330_000 };

/** Apply the server's timeouts (from GET /health → client). */
export function configureTimeouts(c: { read_timeout_s?: number; write_timeout_s?: number } | null | undefined): void {
  if (c?.read_timeout_s && c.read_timeout_s > 0) REQUEST_TIMEOUT_MS.read = c.read_timeout_s * 1000;
  if (c?.write_timeout_s && c.write_timeout_s > 0) REQUEST_TIMEOUT_MS.write = c.write_timeout_s * 1000;
}

/** A signal that aborts on the caller's own cancel or when the request runs out of time. */
function withTimeout(ms: number, signal?: AbortSignal): { signal: AbortSignal; timedOut: () => boolean; done: () => void } {
  const ctrl = new AbortController();
  let expired = false;
  const timer = setTimeout(() => { expired = true; ctrl.abort(); }, ms);
  const cancel = () => ctrl.abort();
  if (signal?.aborted) ctrl.abort();
  else signal?.addEventListener("abort", cancel, { once: true });
  return { signal: ctrl.signal, timedOut: () => expired, done: () => { clearTimeout(timer); signal?.removeEventListener("abort", cancel); } };
}

function timeoutError(ms: number): ApiError {
  return new ApiError(0, "timeout", `The server took too long to answer (over ${Math.round(ms / 1000)} s).`,
                      "Try again. If it keeps happening, check the provider badges at the top right.");
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const ms = method === "GET" ? REQUEST_TIMEOUT_MS.read : REQUEST_TIMEOUT_MS.write;
  const t = withTimeout(ms, signal);
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: body instanceof FormData ? undefined : { "Content-Type": "application/json" },
      body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
      signal: t.signal,
    });
  } catch (e) {
    if (t.timedOut()) throw timeoutError(ms);
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "network", "The Showtime server isn't reachable.", "Start it with: make up");
  } finally {
    t.done();
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
    const t = withTimeout(REQUEST_TIMEOUT_MS.read * 2, signal); // trajectories can be large
    try {
      const res = await fetch(`${BASE}${path}`, { signal: t.signal });
      if (!res.ok) await parse<never>(res);
      return await res.arrayBuffer();
    } catch (e) {
      if (t.timedOut()) throw timeoutError(REQUEST_TIMEOUT_MS.read * 2);
      throw e;
    } finally {
      t.done();
    }
  },
  url: (path: string) => `${BASE}${path}`,
};
