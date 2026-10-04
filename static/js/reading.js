// Lectura actual: medidor, métricas y alertas.

import { $, COLORS, animateNumber, healthColor, setNumber } from "./ui.js";

const CIRCUMF = 2 * Math.PI * 88; // radio del arco del medidor

const METHOD_LABELS = { sysfs: "sysfs directo", estimate: "estimación" };

function renderGauge(data) {
  const pct = data.health_pct;
  const arc = $("gauge-arc");
  const note = $("gauge-note");

  if (pct !== null && pct !== undefined) {
    arc.style.strokeDashoffset = CIRCUMF * (1 - Math.min(pct, 100) / 100);
    arc.style.stroke = healthColor(pct);
    animateNumber($("gauge-pct"), pct, 1, "%");
    $("gauge-label").textContent = data.health_label;
    $("gauge-label").style.color = healthColor(pct);
    note.classList.add("hidden");
  } else {
    arc.style.strokeDashoffset = CIRCUMF;
    $("gauge-pct").textContent = "—";
    delete $("gauge-pct").dataset.rawValue;
    $("gauge-label").textContent = "Sin datos";
    $("gauge-label").style.color = "";
    note.textContent = data.discarded_reason ?? "";
    note.classList.toggle("hidden", !data.discarded_reason);
  }

  $("gauge-mah").textContent = data.capacity_mah != null ? `${data.capacity_mah} mAh` : "— mAh";
  $("gauge-design").textContent = `${data.design_mah} mAh`;
  const method = $("gauge-method");
  method.textContent = METHOD_LABELS[data.method] ?? "—";
  method.title = data.method_detail ?? "";
}

function renderMetrics(data) {
  const level = data.level ?? 0;
  animateNumber($("m-level"), level, 0);
  const fill = $("level-bar-fill");
  fill.style.width = `${level}%`;
  fill.style.backgroundColor = level > 50 ? COLORS.accent : level > 20 ? COLORS.fair : COLORS.bad;

  $("m-status").textContent = data.status_name ?? "—";

  setNumber($("m-temp"), data.temp_c, 1);
  const temp = $("mc-temp");
  temp.classList.toggle("hot", data.temp_c > 40);
  temp.classList.toggle("warm", data.temp_c > 32 && data.temp_c <= 40);

  setNumber($("m-voltage"), data.voltage_mv || null, 0);
  setNumber($("m-counter"), data.charge_mah || null, 0);

  $("m-android").textContent = data.health_name ?? "—";
  $("mc-android").classList.toggle("good", data.health_code === 2);
}

function renderAlerts(data) {
  const alerts = [];
  if (data.temp_c > 40)
    alerts.push(["danger", `Temperatura muy alta: ${data.temp_c} °C. Deja de cargar y déjalo enfriar.`]);
  else if (data.temp_c > 35)
    alerts.push(["warn", `Temperatura alta: ${data.temp_c} °C.`]);

  if (data.health_pct != null && data.health_pct < 60)
    alerts.push(["danger", `Salud en ${data.health_pct} %. Conviene cambiar la batería.`]);
  else if (data.health_pct != null && data.health_pct < 80)
    alerts.push(["warn", `Salud por debajo del 80 % (${data.health_pct} %).`]);

  if (data.protect_note) alerts.push(["warn", data.protect_note]);

  const list = $("alerts-list");
  list.replaceChildren();
  if (alerts.length === 0) {
    const p = document.createElement("p");
    p.className = "no-alerts";
    p.textContent = "Sin alertas.";
    list.append(p);
    return;
  }
  for (const [level, text] of alerts) {
    const item = document.createElement("div");
    item.className = `alert-item alert-${level}`;
    const icon = document.createElement("span");
    icon.className = "alert-icon";
    icon.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.textContent = text;
    item.append(icon, label);
    list.append(item);
  }
}

export function renderReading(data) {
  renderGauge(data);
  renderMetrics(data);
  renderAlerts(data);
  $("last-update").textContent = `Última lectura: ${new Date().toLocaleTimeString("es-MX")}`;
}
