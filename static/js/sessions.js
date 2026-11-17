// Sesiones de carga (/api/sessions) y la sesión en curso de la lectura actual.

import { $, healthColor } from "./ui.js";

const STATUS_LABELS = {
  open: "en curso",
  complete: "completa",
  incomplete: "incompleta",
};

const dateFmt = new Intl.DateTimeFormat("es-MX", {
  dateStyle: "short",
  timeStyle: "short",
});

function duration(min) {
  if (min < 60) return `${min} min`;
  return `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")} min`;
}

function cell(text, className) {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  return td;
}

export function renderSessions(data) {
  const { sessions, summary } = data;
  $("ss-last").textContent =
    summary.last_health != null ? `${summary.last_health}%` : "—";
  $("ss-last").style.color =
    summary.last_health != null ? healthColor(summary.last_health) : "";
  $("ss-total").textContent = summary.total;

  const body = $("sessions-body");
  body.replaceChildren();
  if (sessions.length === 0) {
    const tr = document.createElement("tr");
    const td = cell(
      "Todavía no hay sesiones. Conecta el teléfono por USB cuando empieces a cargar (con 20 % o menos).",
      "muted",
    );
    td.colSpan = 8;
    tr.append(td);
    body.append(tr);
    return;
  }
  for (const s of sessions) {
    const tr = document.createElement("tr");
    const health = cell(s.health_pct != null ? `${s.health_pct}%` : "—");
    if (s.health_pct != null) health.style.color = healthColor(s.health_pct);
    else if (s.health_note && s.status !== "open") health.title = s.health_note;
    const status = cell(
      (STATUS_LABELS[s.status] ?? s.status) + (s.counted ? " · cuenta" : ""),
      "session-status",
    );
    status.dataset.status = s.status;
    if (s.end_reason) status.title = s.end_reason;
    tr.append(
      cell(dateFmt.format(new Date(s.started_at))),
      cell(`${s.start_level} → ${s.end_level}%`),
      cell(`${s.added_mah} mAh`),
      cell(s.capacity_mah != null ? `${s.capacity_mah} mAh` : "—"),
      health,
      cell(`${s.max_temp_c} °C`),
      cell(duration(s.duration_min)),
      status,
    );
    body.append(tr);
  }
}

// Línea de la carga en curso; retorna true si hay una sesión abierta
export function renderLiveSession(session) {
  const live = $("session-live");
  if (!session || session.status !== "open") {
    live.classList.add("hidden");
    return false;
  }
  live.textContent =
    `Carga en curso: ${session.start_level} → ${session.end_level}%, ` +
    `${session.added_mah} mAh en ${duration(session.duration_min)}. ` +
    "Deja el teléfono conectado hasta 100 % (o vuelve a conectarlo al terminar).";
  live.classList.remove("hidden");
  return true;
}
