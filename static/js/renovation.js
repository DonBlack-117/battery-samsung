// Panel «¿Es reacondicionado?» (bajo demanda, no en cada actualización).

import { $ } from "./ui.js";

const SUMMARY = {
  Bajo: "Nada indica que haya sido reparado o reacondicionado.",
  Medio: "Hay alguna señal que conviene revisar antes de fiarse.",
  Alto: "Varias señales apuntan a un equipo usado, reparado o reacondicionado.",
};

function fillList(id, items) {
  const list = $(id);
  list.replaceChildren();
  for (const text of items.length ? items : ["Ninguna."]) {
    const li = document.createElement("li");
    li.textContent = text;
    if (!items.length) li.className = "muted";
    list.append(li);
  }
}

function setFact(id, text, state = null) {
  const dd = $(id);
  dd.textContent = text;
  dd.classList.toggle("is-bad", state === "bad");
  dd.classList.toggle("is-good", state === "good");
}

// Solo se dice «intacto» si el teléfono respondió 0; si no, es falta de datos
const knox = (raw, bad, good) => (raw === "1" ? [bad, "bad"] : raw === "0" ? [good, "good"] : ["sin acceso"]);

export function renderRenovation(data) {
  $("reno-level").textContent = data.risk_level;
  $("reno-level").dataset.level = data.risk_level;
  const pending = data.unverified.map((u) => u.split(":")[0].toLowerCase());
  $("reno-summary").textContent = SUMMARY[data.risk_level] + (pending.length ? ` Sin verificar: ${pending.join(", ")}.` : "");

  setFact("reno-cycles", data.cycle_count ?? "sin acceso");
  setFact("reno-warranty", ...knox(data.warranty_bit, "activado (1)", "intacto (0)"));
  setFact("reno-fuse", ...knox(data.knox_fuse, "quemado (1)", "intacto (0)"));

  // El número de serie se enmascara; completo en el tooltip
  const serial = data.serial ?? "";
  $("reno-serial").textContent = serial ? `•••• ${serial.slice(-4)}` : "—";
  $("reno-serial").title = serial;

  fillList("reno-risks", data.risk_factors);
  fillList("reno-flags", data.green_flags);
}

export function renderRenovationError(message) {
  $("reno-level").textContent = "—";
  $("reno-level").dataset.level = "";
  $("reno-summary").textContent = message;
}
