// Utilidades de interfaz compartidas.

export const $ = (id) => document.getElementById(id);

// Colores de salud desaturados (son datos: verde → ámbar → rojo)
export const COLORS = {
  ok: "#8ED1A5", good: "#B7D39A", fair: "#E3C38A", poor: "#E4A57C", bad: "#E39A9A",
  none: "#545C64", accent: "#A3C4DC", soft: "#AAB2B9", mute: "#7E878F",
  line: "rgba(37, 42, 47, 0.9)", panel: "#15181B",
};

export function healthColor(pct) {
  if (pct === null || pct === undefined) return COLORS.none;
  if (pct >= 85) return COLORS.ok;
  if (pct >= 80) return COLORS.good;
  if (pct >= 70) return COLORS.fair;
  if (pct >= 60) return COLORS.poor;
  return COLORS.bad;
}

export function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Cuenta del valor anterior al nuevo; sin animación si el usuario la desactivó
export function animateNumber(el, toValue, decimals = 1, suffix = "") {
  const from = parseFloat(el.dataset.rawValue ?? toValue) || 0;
  el.dataset.rawValue = toValue;
  const final = toValue.toFixed(decimals) + suffix;

  if (reducedMotion || Math.abs(from - toValue) < 0.05) {
    el.textContent = final;
    return;
  }
  if (el.classList.contains("metric-value")) {
    el.classList.remove("value-pop");
    void el.offsetWidth; // reinicia la animación
    el.classList.add("value-pop");
    el.addEventListener("animationend", () => el.classList.remove("value-pop"), { once: true });
  }

  const duration = 700;
  const start = performance.now();
  function tick(now) {
    const t = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = (t < 1 ? (from + (toValue - from) * eased).toFixed(decimals) + suffix : final);
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

export function setNumber(el, value, decimals = 0) {
  if (value === null || value === undefined) {
    el.textContent = "—";
    delete el.dataset.rawValue;
  } else {
    animateNumber(el, value, decimals);
  }
}

export function showError(message) {
  $("error-message").textContent = message;
  $("error-banner").classList.remove("hidden");
}

export function hideError() {
  $("error-banner").classList.add("hidden");
}

export function setStatus(state) {
  const dot = $("status-dot");
  dot.className = `status-dot status-${state}`;
  dot.textContent = state === "ok" ? "teléfono conectado" : "sin conexión";
}

export async function withBusy(button, fn) {
  button.classList.add("loading");
  button.disabled = true;
  try {
    return await fn();
  } finally {
    button.classList.remove("loading");
    button.disabled = false;
  }
}
