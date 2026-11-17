// Battery-Sam: arranque, estado y actualización periódica.

import { api } from "./api.js";
import { HealthChart } from "./chart.js";
import { renderReading } from "./reading.js";
import { renderRenovation, renderRenovationError } from "./renovation.js";
import { renderLiveSession, renderSessions } from "./sessions.js";
import { renderStats } from "./summary.js";
import { $, hideError, setStatus, showError, withBusy } from "./ui.js";

const REFRESH_MS = Number(document.body.dataset.refreshMs) || 30_000;

const state = {
  model: $("model-select").value || document.body.dataset.defaultModel,
  // Sin modelo confirmado no se guarda: la capacidad de fábrica podría ser otra
  save: false,
  // Modelo que reportó el teléfono; solo con ese se guarda en el historial
  detected: null,
  unrecognized: false, // Samsung que el catálogo no reconoce
  probed: false, // ya respondió /api/device (con o sin modelo reconocido)
  detecting: false,
  // Hay una carga en curso: se sigue leyendo aunque la pestaña quede oculta
  charging: false,
  timer: null,
};
const chart = new HealthChart();

async function loadReading() {
  try {
    if (!state.probed && !state.detecting) {
      // El teléfono pudo conectarse después de abrir la página
      state.detecting = true;
      await detectDevice().finally(() => (state.detecting = false));
    }
    const reading = await api.current(state.model, state.save);
    hideError();
    setStatus("ok");
    renderReading(reading);
    chart.pushSession(reading);
    state.charging = renderLiveSession(reading.session);
  } catch (err) {
    showError(err.message);
    setStatus("error");
  }
}

async function loadStats() {
  try {
    renderStats(await api.stats(state.model));
  } catch (err) {
    // El historial no depende del teléfono: puede fallar aunque la lectura funcione
    showError(`Historial: ${err.message}`);
  }
}

async function loadSessions() {
  try {
    renderSessions(await api.sessions(state.model));
  } catch (err) {
    showError(`Sesiones: ${err.message}`);
  }
}

async function loadRenovation() {
  await withBusy($("reno-btn"), async () => {
    try {
      renderRenovation(await api.renovation(state.model));
    } catch (err) {
      renderRenovationError(err.message);
    }
  });
}

async function loadHistory(days) {
  try {
    chart.showHistory(days, await api.history(state.model, days));
  } catch (err) {
    showError(err.message);
  }
}

async function refreshAll() {
  await loadReading();
  await loadStats();
  await loadSessions();
  if (chart.range !== "session") await loadHistory(Number(chart.range));
}

// Solo consulta mientras la pestaña está visible, salvo con una carga en curso
function startTimer() {
  stopTimer();
  state.timer = setInterval(
    () => refreshAll().catch(console.error),
    REFRESH_MS,
  );
}

function stopTimer() {
  clearInterval(state.timer);
  state.timer = null;
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    if (!state.charging) stopTimer();
  } else {
    refreshAll().catch(console.error);
    startTimer();
  }
});

function selectTab(button) {
  for (const tab of document.querySelectorAll(".tab")) {
    tab.setAttribute("aria-selected", String(tab === button));
  }
  const range = button.dataset.range;
  if (range === "session") chart.showSession();
  else loadHistory(Number(range));
}

function setModel(model) {
  state.model = model;
  $("model-select").value = model;
  $("export-link").href = api.exportUrl(model);
}

$("model-select").addEventListener("change", async (e) => {
  setModel(e.target.value);
  // Samsung no reconocido: elegir el modelo es la confirmación y sí guarda.
  // Modelo detectado: elegir otro no guarda (la capacidad de fábrica no sería la del teléfono).
  state.save =
    state.unrecognized ||
    (state.detected !== null && e.target.value === state.detected);
  $("device-chip").classList.add("hidden");
  await refreshAll();
  loadRenovation();
});

$("refresh-btn").addEventListener("click", () =>
  withBusy($("refresh-btn"), refreshAll),
);
$("reno-btn").addEventListener("click", loadRenovation);
$("error-close").addEventListener("click", hideError);
for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => selectTab(tab));
}

async function detectDevice() {
  try {
    const device = await api.device();
    state.probed = true;
    const chip = $("device-chip");
    if (device.model) {
      state.detected = device.model;
      state.save = true;
      setModel(device.model);
    } else if (device.is_samsung) {
      state.save = false;
      state.unrecognized = true;
      chip.textContent = `${device.raw_model ?? "Modelo"} no reconocido: elige el tuyo`;
      chip.classList.remove("hidden");
    } else {
      state.save = false;
      chip.textContent = device.brand
        ? [device.brand, device.raw_model].filter(Boolean).join(" ")
        : "Otro teléfono";
      chip.classList.remove("hidden");
      $("model-select").classList.add("hidden");
    }
  } catch (_) {
    // Sin teléfono: se queda el modelo por defecto sin guardar; loadReading muestra el aviso.
    // Se vuelve a intentar en la siguiente lectura correcta.
    state.save = false;
  }
}

await detectDevice();
setModel(state.model);
await refreshAll();
startTimer();
loadRenovation();
