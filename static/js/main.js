// Battery-Sam: arranque, estado y actualización periódica.

import { api } from "./api.js";
import { HealthChart } from "./chart.js";
import { renderReading } from "./reading.js";
import { renderRenovation, renderRenovationError } from "./renovation.js";
import { renderStats } from "./summary.js";
import { $, hideError, setStatus, showError, withBusy } from "./ui.js";

const REFRESH_MS = Number(document.body.dataset.refreshMs) || 30_000;

const state = {
  model: $("model-select").value || document.body.dataset.defaultModel,
  // Sin modelo confirmado no se guarda: la capacidad de fábrica podría ser otra
  save: true,
  timer: null,
};
const chart = new HealthChart();

async function loadReading() {
  try {
    const reading = await api.current(state.model, state.save);
    hideError();
    setStatus("ok");
    renderReading(reading);
    chart.pushSession(reading);
  } catch (err) {
    showError(err.message);
    setStatus("error");
  }
}

async function loadStats() {
  try {
    renderStats(await api.stats(state.model));
  } catch (_) {
    // El historial no depende del teléfono; si falla, el aviso ya lo dio loadReading
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
  if (chart.range !== "session") await loadHistory(Number(chart.range));
}

// Solo consulta mientras la pestaña está visible
function startTimer() {
  stopTimer();
  state.timer = setInterval(refreshAll, REFRESH_MS);
}

function stopTimer() {
  clearInterval(state.timer);
  state.timer = null;
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    stopTimer();
  } else {
    refreshAll();
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
  state.save = true;
  $("device-chip").classList.add("hidden");
  await refreshAll();
  loadRenovation();
});

$("refresh-btn").addEventListener("click", () => withBusy($("refresh-btn"), refreshAll));
$("reno-btn").addEventListener("click", loadRenovation);
$("error-close").addEventListener("click", hideError);
for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => selectTab(tab));
}

async function detectDevice() {
  try {
    const device = await api.device();
    const chip = $("device-chip");
    if (device.model) {
      setModel(device.model);
    } else if (device.is_samsung) {
      state.save = false;
      chip.textContent = `${device.raw_model ?? "Modelo"} no reconocido: elige el tuyo`;
      chip.classList.remove("hidden");
    } else {
      state.save = false;
      chip.textContent = device.brand ? [device.brand, device.raw_model].filter(Boolean).join(" ") : "Otro teléfono";
      chip.classList.remove("hidden");
      $("model-select").classList.add("hidden");
    }
  } catch (_) {
    // Sin teléfono: se queda el modelo por defecto y loadReading muestra el aviso
  }
}

await detectDevice();
setModel(state.model);
await refreshAll();
startTimer();
loadRenovation();
