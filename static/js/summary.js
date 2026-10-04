// Historial y degradación (/api/stats).

import { $ } from "./ui.js";

const pct = (v) => (v != null ? `${v}%` : "—");

export function renderStats(stats) {
  $("s-total").textContent = stats.total_readings;
  $("s-first-date").textContent = stats.first_date ?? "Sin datos";
  $("s-first-health").textContent = pct(stats.first_health);
  $("s-last-health").textContent = pct(stats.last_health);
  $("s-max-temp").textContent = stats.max_temp_c != null ? `${stats.max_temp_c} °C` : "—";

  const monthly = stats.monthly_degradation;
  $("s-monthly").textContent = monthly != null
    ? `${monthly >= 0 ? "−" : "+"}${Math.abs(monthly).toFixed(3)}% / mes`
    : "—";

  const note = $("trend-note");
  note.textContent = stats.trend_note ?? "";
  note.classList.toggle("hidden", !stats.trend_note);

  const wrap = $("projection-wrap");
  if (stats.months_to_80 != null) {
    const months = stats.months_to_80;
    $("s-to-80").textContent = months >= 12 ? `~${(months / 12).toFixed(1)} años` : `~${months} meses`;

    const first = stats.first_health ?? 100;
    const current = stats.last_health ?? 100;
    const range = Math.max(first - 80, 1);
    const used = Math.min(Math.max(first - current, 0), range);
    $("proj-fill").style.width = `${100 - (used / range) * 100}%`;
    $("proj-current-label").textContent = `${current}%`;
    wrap.classList.remove("hidden");
  } else {
    wrap.classList.add("hidden");
    $("s-to-80").textContent = monthly != null && monthly <= 0 ? "no está bajando" : "—";
  }
}
