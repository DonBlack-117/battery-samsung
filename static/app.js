/* ═══════════════════════════════════════════════════════════
   Battery Health Monitor — Frontend Logic
   ══════════════════════════════════════════════════════════ */

"use strict";

// ── Config ────────────────────────────────────────────────
const REFRESH_MS   = 30_000; // Auto-refresh interval
const CIRCUMF      = 552.92; // 2π × 88  (gauge SVG radius)
const RT_MAX_PTS   = 120;    // Máx. puntos en tiempo real (~1 h a 30 s)

// ── State ─────────────────────────────────────────────────
let chart         = null;
let refreshTimer  = null;
let currentModel  = document.getElementById("model-select").value;
let sessionStart  = null;
const rtBuffer    = []; // buffer de lecturas de la sesión actual

// ── DOM helpers ───────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const el = (id) => document.getElementById(id);

// ── Count-up animation ────────────────────────────────────
function animateNumber(el, toValue, suffix = "", decimals = 1) {
  const from = parseFloat(el.dataset.rawValue ?? toValue) || 0;
  el.dataset.rawValue = toValue;

  if (Math.abs(from - toValue) < 0.05) {
    el.textContent = toValue.toFixed(decimals) + suffix;
    return;
  }

  // Pop animation on metric-value elements
  if (el.classList.contains("metric-value")) {
    el.classList.remove("value-pop");
    void el.offsetWidth; // force reflow
    el.classList.add("value-pop");
    el.addEventListener("animationend", () => el.classList.remove("value-pop"), { once: true });
  }

  const duration = 700;
  const start = performance.now();

  function tick(now) {
    const t      = Math.min((now - start) / duration, 1);
    const eased  = 1 - Math.pow(1 - t, 3);
    const current = from + (toValue - from) * eased;
    el.textContent = current.toFixed(decimals) + suffix;
    if (t < 1) requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
}

// ── Health color ──────────────────────────────────────────
// Colores de salud desaturados (son datos: verde → ámbar → rojo)
const COLORS = {
  ok: "#8ED1A5", fair: "#E3C38A", poor: "#E4A57C", bad: "#E39A9A",
  none: "#545C64", accent: "#A3C4DC", soft: "#AAB2B9", mute: "#7E878F",
  line: "rgba(37, 42, 47, 0.9)", panel: "#15181B",
};

function healthColor(pct) {
  if (pct === null || pct === undefined) return COLORS.none;
  if (pct >= 85) return COLORS.ok;
  if (pct >= 80) return "#B7D39A";
  if (pct >= 70) return COLORS.fair;
  if (pct >= 60) return COLORS.poor;
  return COLORS.bad;
}

// ══════════════════════════════════════════════════════════
//  API CALLS
// ══════════════════════════════════════════════════════════

async function loadCurrentData() {
  try {
    const res = await fetch(`/api/current/${encodeURIComponent(currentModel)}`);
    const data = await res.json();

    if (!res.ok || data.error) {
      showError(data.error || "Error al obtener datos del dispositivo.");
      setStatus("error");
      return;
    }

    hideError();
    setStatus("ok");
    updateGauge(data);
    updateCards(data);
    updateAlerts(data);
    updateFooter();
    pushRealtime(data);
    renderChart();
    updateChartSubtitle();
  } catch (err) {
    showError("No se pudo conectar con el servidor. ¿Está corriendo app.py?");
    setStatus("error");
  }
}

async function loadStats() {
  try {
    const res = await fetch("/api/stats");
    const stats = await res.json();
    updateStats(stats);
  } catch (_) {
    /* silently ignore */
  }
}

// ══════════════════════════════════════════════════════════
//  UI UPDATES — GAUGE
// ══════════════════════════════════════════════════════════

function updateGauge(data) {
  const pct = data.health_pct;
  const arc = $("gauge-arc");

  if (pct !== null && pct !== undefined) {
    const offset = CIRCUMF * (1 - pct / 100);
    arc.style.strokeDashoffset = offset;
    arc.style.stroke = healthColor(pct);

    // Sync outer glow arc
    const arcGlow = $("gauge-arc-glow");
    if (arcGlow) {
      arcGlow.style.strokeDashoffset = offset;
      arcGlow.style.stroke = healthColor(pct);
    }

    animateNumber($("gauge-pct"), pct, "%", 1);
    $("gauge-label").textContent = data.health_label || "—";
    $("gauge-label").style.color = healthColor(pct);

    const mah = data.full_mah_est
      ? Math.round(data.full_mah_est)
      : (data.current_mah ?? null);
    $("gauge-mah").textContent = mah !== null ? `${mah} mAh` : "— mAh";
  } else {
    arc.style.strokeDashoffset = CIRCUMF;
    $("gauge-pct").textContent = "—";
    $("gauge-label").textContent = "Sin datos";
  }

  $("gauge-design").textContent = `${data.design_mah ?? 5000} mAh`;
  const methodShort = !data.method_used
    ? "—"
    : data.method_used.includes("sysfs")
      ? "sysfs directo"
      : data.method_used.includes("estimaci")
        ? "estimación"
        : data.method_used;
  const methodEl = $("gauge-method");
  methodEl.textContent = methodShort;
  methodEl.title = data.method_used ?? "";
}

// ══════════════════════════════════════════════════════════
//  UI UPDATES — METRIC CARDS
// ══════════════════════════════════════════════════════════

function updateCards(data) {
  // Las unidades ya están en el HTML (.metric-unit): aquí solo va el número
  const lvl = data.level ?? 0;
  animateNumber($("m-level"), lvl, "", 0);
  const barFill = $("level-bar-fill");
  barFill.style.width = `${lvl}%`;
  barFill.style.backgroundColor = lvl > 50 ? COLORS.accent : lvl > 20 ? COLORS.fair : COLORS.bad;

  // Status
  $("m-status").textContent = data.status_name ?? "—";

  // Temperature — count-up
  const temp = data.temp_c;
  if (temp !== null && temp !== undefined) {
    animateNumber($("m-temp"), temp, "", 1);
  } else {
    $("m-temp").textContent = "—";
  }
  const mc = $("mc-temp");
  mc.classList.remove("warm", "hot");
  if (temp > 40) mc.classList.add("hot");
  else if (temp > 32) mc.classList.add("warm");

  // Voltage — count-up
  if (data.voltage_mv) {
    animateNumber($("m-voltage"), data.voltage_mv, "", 0);
  } else {
    $("m-voltage").textContent = "—";
  }

  // Charge counter → show as current mAh — count-up
  const mah =
    data.current_mah ??
    (data.charge_counter ? Math.round(data.charge_counter / 1000) : null);
  if (mah !== null) {
    animateNumber($("m-counter"), mah, "", 0);
  } else {
    $("m-counter").textContent = "—";
  }

  // Android health
  $("m-android").textContent = data.health_name ?? "—";
  $("mc-android").classList.toggle("good", data.health_name === "Bueno");
}

// ══════════════════════════════════════════════════════════
//  UI UPDATES — ALERTS
// ══════════════════════════════════════════════════════════

function updateAlerts(data) {
  const alerts = [];

  if (data.temp_c > 40)
    alerts.push({ level: "danger", text: `Temperatura muy alta: ${data.temp_c} °C. Deja de cargar y déjalo enfriar.` });
  else if (data.temp_c > 35)
    alerts.push({ level: "warn", text: `Temperatura alta: ${data.temp_c} °C.` });

  if (data.health_pct !== null && data.health_pct < 60)
    alerts.push({ level: "danger", text: `Salud en ${data.health_pct} %. Conviene cambiar la batería.` });
  else if (data.health_pct !== null && data.health_pct < 80)
    alerts.push({ level: "warn", text: `Salud por debajo del 80 % (${data.health_pct} %).` });

  if (data.protect_note)
    alerts.push({ level: "warn", text: "Protección de batería activa: la carga se limita al 80–85 %." });

  const list = $("alerts-list");
  if (alerts.length === 0) {
    list.innerHTML = '<p class="no-alerts">Sin alertas.</p>';
    return;
  }

  list.innerHTML = alerts
    .map((a) => `
    <div class="alert-item alert-${a.level}">
      <span class="alert-icon" aria-hidden="true"></span>
      <span>${a.text}</span>
    </div>`)
    .join("");
}

// ══════════════════════════════════════════════════════════
//  UI UPDATES — STATS
// ══════════════════════════════════════════════════════════

function updateStats(stats) {
  $("s-total").textContent = stats.total_readings ?? "—";
  $("s-first-date").textContent = stats.first_date ?? "Sin datos";
  $("s-first-health").textContent =
    stats.first_health != null ? `${stats.first_health}%` : "—";
  $("s-last-health").textContent =
    stats.last_health != null ? `${stats.last_health}%` : "—";
  $("s-max-temp").textContent =
    stats.max_temp_c != null ? `${stats.max_temp_c} °C` : "—";

  if (stats.monthly_degradation != null) {
    const sign = stats.monthly_degradation >= 0 ? "−" : "+";
    $("s-monthly").textContent =
      `${sign}${Math.abs(stats.monthly_degradation).toFixed(3)}% / mes`;
  } else {
    $("s-monthly").textContent = "—";
  }

  if (stats.months_to_80 != null) {
    const months = stats.months_to_80;
    if (months >= 12) {
      $("s-to-80").textContent = `~${(months / 12).toFixed(1)} años`;
    } else {
      $("s-to-80").textContent = `~${months} meses`;
    }

    // Projection bar: fill = current - 80 / first - 80
    const pWrap = $("projection-wrap");
    pWrap.classList.remove("hidden");

    const first = stats.first_health ?? stats.last_health ?? 100;
    const current = stats.last_health ?? 100;
    const range = Math.max(first - 80, 1);
    const done = Math.min(Math.max(first - current, 0), range);
    const pct = (done / range) * 100;

    $("proj-fill").style.width = `${100 - pct}%`;
    $("proj-current-label").textContent = `${current}%`;
  } else {
    $("projection-wrap").classList.add("hidden");
    $("s-to-80").textContent =
      stats.total_readings < 2
        ? "faltan lecturas"
        : stats.monthly_degradation != null && stats.monthly_degradation <= 0
          ? "no está bajando"
          : "—";
  }
}

// ══════════════════════════════════════════════════════════
//  REALTIME BUFFER
// ══════════════════════════════════════════════════════════

function pushRealtime(data) {
  if (!sessionStart) sessionStart = new Date();
  const now = new Date();
  rtBuffer.push({
    time: now.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    health_pct: data.health_pct,
    level: data.level,
  });
  if (rtBuffer.length > RT_MAX_PTS) rtBuffer.shift();
}

// ══════════════════════════════════════════════════════════
//  CHART — tiempo real
// ══════════════════════════════════════════════════════════

function renderChart() {
  const canvas = $("health-chart");
  const empty  = $("chart-empty");

  if (rtBuffer.length === 0) {
    canvas.classList.add("hidden");
    empty.classList.remove("hidden");
    return;
  }

  canvas.classList.remove("hidden");
  empty.classList.add("hidden");

  const labels     = rtBuffer.map((r) => r.time);
  const healthData = rtBuffer.map((r) => r.health_pct);
  const levelData  = rtBuffer.map((r) => r.level);

  const ctx = canvas.getContext("2d");

  const grad = ctx.createLinearGradient(0, 0, 0, 280);
  grad.addColorStop(0, "rgba(163, 196, 220, 0.16)");
  grad.addColorStop(1, "rgba(163, 196, 220, 0)");

  const pr = rtBuffer.length < 12 ? 3 : 0;

  const datasets = [
    {
      label: "Salud (%)",
      data: healthData,
      borderColor: COLORS.accent,
      backgroundColor: grad,
      borderWidth: 2,
      pointRadius: pr,
      pointHoverRadius: 4,
      pointBackgroundColor: COLORS.accent,
      pointBorderColor: COLORS.panel,
      pointBorderWidth: 2,
      tension: 0.3,
      fill: true,
    },
    {
      label: "Carga (%)",
      data: levelData,
      borderColor: COLORS.soft,
      backgroundColor: "transparent",
      borderWidth: 1.25,
      pointRadius: 0,
      tension: 0.3,
      fill: false,
      borderDash: [4, 3],
    },
  ];

  if (chart) {
    chart.data.labels        = labels;
    chart.data.datasets      = datasets;
    chart.options.scales.y.min = _yMin(healthData, levelData);
    chart.update("active");
    return;
  }

  chart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 500 },
      interaction: { mode: "index", intersect: false },
      plugins: {
        // La leyenda está en el HTML (#realtime-badge)
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(21, 24, 27, 0.96)",
          borderColor: "rgba(47, 53, 59, 1)",
          borderWidth: 1,
          titleColor: "#E8ECEF",
          bodyColor: COLORS.soft,
          titleFont: { family: "Geist", weight: "600" },
          bodyFont: { family: "Geist Mono", size: 12 },
          padding: 12,
          cornerRadius: 10,
          displayColors: true,
          boxWidth: 8,
          boxHeight: 8,
          boxPadding: 4,
          callbacks: {
            label: (c) => ` ${c.dataset.label}: ${c.parsed.y?.toFixed(1) ?? "—"}%`,
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            color: COLORS.mute,
            font: { family: "Geist Mono", size: 11 },
            maxTicksLimit: 6,
            maxRotation: 0,
          },
          border: { display: false },
        },
        y: {
          min: _yMin(healthData, levelData),
          max: 102,
          grid: { color: COLORS.line },
          ticks: {
            color: COLORS.mute,
            font: { family: "Geist Mono", size: 11 },
            maxTicksLimit: 5,
            // 102 es solo margen superior: no se etiqueta
            callback: (v) => (v > 100 ? "" : v + "%"),
          },
          border: { display: false },
        },
      },
    },
  });
}

function _yMin(healthData, levelData) {
  const all = [...healthData, ...levelData].filter((v) => v !== null && v !== undefined);
  // Mínimo redondeado a la decena inferior, con 5 puntos de margen (p. ej. 79 → 70)
  return all.length ? Math.max(0, Math.floor((Math.min(...all) - 5) / 10) * 10) : 0;
}

function updateChartSubtitle() {
  const sub = $("chart-subtitle");
  if (!sessionStart || rtBuffer.length === 0) {
    sub.textContent = "Esperando primera lectura…";
    return;
  }
  const n       = rtBuffer.length;
  const mins    = Math.floor((Date.now() - sessionStart.getTime()) / 60000);
  const inicio  = sessionStart.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
  const durStr  = mins > 0 ? `${mins} min · ` : "";
  sub.textContent = `${n} lectura${n !== 1 ? "s" : ""} · ${durStr}desde las ${inicio}`;
}

// ══════════════════════════════════════════════════════════
//  STATUS / FOOTER
// ══════════════════════════════════════════════════════════

function setStatus(state) {
  const dot = $("status-dot");
  dot.className = `status-dot status-${state}`;
  dot.textContent = state === "ok" ? "teléfono conectado" : "sin conexión";
}

function updateFooter() {
  const now = new Date();
  $("last-update").textContent =
    `Última lectura: ${now.toLocaleTimeString("es-ES")}`;
}

function showError(msg) {
  $("error-message").textContent = msg;
  $("error-banner").classList.remove("hidden");
}

function hideError() {
  $("error-banner").classList.add("hidden");
}

// ══════════════════════════════════════════════════════════
//  ¿REACONDICIONADO? — /api/renovation (bajo demanda, no cada 30 s)
// ══════════════════════════════════════════════════════════

const RENO_SUMMARY = {
  Bajo:  "Nada indica que haya sido reparado o reacondicionado.",
  Medio: "Hay alguna señal que conviene revisar antes de fiarse.",
  Alto:  "Varias señales apuntan a un equipo usado, reparado o reacondicionado.",
};

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fillList(id, items, emptyText) {
  $(id).innerHTML = items && items.length
    ? items.map((t) => `<li>${escapeHtml(t)}</li>`).join("")
    : `<li class="muted">${emptyText}</li>`;
}

function setFact(id, text, state) {
  const dd = $(id);
  dd.textContent = text;
  dd.classList.toggle("is-bad", state === "bad");
  dd.classList.toggle("is-good", state === "good");
}

async function loadRenovation() {
  const btn = $("reno-btn");
  btn.classList.add("loading");
  btn.disabled = true;
  try {
    const res  = await fetch(`/api/renovation/${encodeURIComponent(currentModel)}`);
    const data = await res.json();
    if (!res.ok || data.error) {
      $("reno-level").textContent = "—";
      $("reno-level").dataset.level = "";
      $("reno-summary").textContent = data.error || "No se pudo analizar el teléfono.";
      return;
    }

    $("reno-level").textContent   = data.risk_level;
    $("reno-level").dataset.level = data.risk_level;
    const pending = (data.unverified || []).map((u) => u.split(":")[0].toLowerCase());
    $("reno-summary").textContent = (RENO_SUMMARY[data.risk_level] ?? "") +
      (pending.length ? ` Sin verificar: ${pending.join(", ")}.` : "");

    // Solo se afirma "intacto" si el teléfono respondió 0; si no, es falta de datos
    const knox = (raw, bad, good) =>
      raw === "1" ? [bad, "bad"] : raw === "0" ? [good, "good"] : ["sin acceso", null];

    setFact("reno-cycles", data.cycle_count ?? "sin acceso");
    setFact("reno-warranty", ...knox(data.warranty_bit, "activado (1)", "intacto (0)"));
    setFact("reno-fuse", ...knox(data.knox_fuse, "quemado (1)", "intacto (0)"));

    // El número de serie se enmascara; completo en el tooltip
    const serial = data.serial || "";
    $("reno-serial").textContent = serial ? `•••• ${serial.slice(-4)}` : "—";
    $("reno-serial").title = serial;

    fillList("reno-risks", data.risk_factors, "Ninguna.");
    fillList("reno-flags", data.green_flags, "Ninguna.");
  } catch (_) {
    $("reno-summary").textContent = "No se pudo conectar con el servidor.";
  } finally {
    btn.classList.remove("loading");
    btn.disabled = false;
  }
}

// ══════════════════════════════════════════════════════════
//  AUTO-REFRESH
// ══════════════════════════════════════════════════════════

function startRefresh() {
  stopRefresh();
  refreshTimer = setInterval(refreshAll, REFRESH_MS);
}

function stopRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
}

async function refreshAll() {
  await loadCurrentData();
  await loadStats();
}

// ══════════════════════════════════════════════════════════
//  EVENT LISTENERS
// ══════════════════════════════════════════════════════════

// Model selector
$("model-select").addEventListener("change", async (e) => {
  currentModel = e.target.value;
  await refreshAll();
  loadRenovation();
});

$("reno-btn").addEventListener("click", loadRenovation);

// Manual refresh button
$("refresh-btn").addEventListener("click", async () => {
  const btn = $("refresh-btn");
  btn.classList.add("loading");
  btn.disabled = true;
  await refreshAll();
  btn.classList.remove("loading");
  btn.disabled = false;
});

// ══════════════════════════════════════════════════════════
//  INIT
// ══════════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", async () => {
  try {
    const res = await fetch("/api/detect");
    const { modelo, brand, raw_model, is_samsung } = await res.json();
    if (modelo) {
      const sel = $("model-select");
      sel.value = modelo;
      currentModel = modelo;
    }
    const chip = $("device-chip");
    const sel  = $("model-select");
    if (!is_samsung) {
      const label = brand
        ? (raw_model ? `${brand} ${raw_model}` : brand)
        : "Otro teléfono";
      chip.textContent = label;
      chip.classList.remove("hidden");
      sel.classList.add("hidden");
    }
  } catch (_) { /* si falla, usa el primer modelo de la lista */ }

  await refreshAll();
  startRefresh();
  loadRenovation();
});
