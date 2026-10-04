// Llamadas a la API. Los errores llegan como { error: { code, message } }.

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function getJson(path, params = {}) {
  const query = new URLSearchParams(params).toString();
  let res;
  try {
    res = await fetch(query ? `${path}?${query}` : path);
  } catch (_) {
    throw new ApiError(0, "offline", "No se pudo conectar con el servidor. ¿Está corriendo Battery-Sam?");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const err = body?.error ?? {};
    throw new ApiError(res.status, err.code ?? "http_error", err.message ?? `Error ${res.status} del servidor.`);
  }
  return body;
}

export const api = {
  device: () => getJson("/api/device"),
  current: (model, save = true) => getJson("/api/current", { model, save }),
  renovation: (model) => getJson("/api/renovation", { model }),
  stats: (model) => getJson("/api/stats", { model }),
  history: (model, days) => getJson("/api/history", { model, days }),
  exportUrl: (model) => `/api/export.csv?${new URLSearchParams({ model })}`,
};
