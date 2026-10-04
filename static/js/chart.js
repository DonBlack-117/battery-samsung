// Gráfica de salud y carga: lecturas de esta sesión o historial guardado.

import { $, COLORS } from "./ui.js";

const SESSION_MAX_POINTS = 120;

const timeFmt = new Intl.DateTimeFormat("es-MX", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const dateFmt = new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

function yMin(values) {
  const all = values.filter((v) => v !== null && v !== undefined);
  // Decena inferior con 5 puntos de margen (p. ej. 79 → 70)
  return all.length ? Math.max(0, Math.floor((Math.min(...all) - 5) / 10) * 10) : 0;
}

export class HealthChart {
  constructor() {
    this.canvas = $("health-chart");
    this.chart = null;
    this.session = [];
    this.sessionStart = null;
    this.range = "session";
    this.history = [];
  }

  pushSession(reading) {
    this.sessionStart ??= new Date();
    this.session.push({ time: new Date(), health: reading.health_pct, level: reading.level });
    if (this.session.length > SESSION_MAX_POINTS) this.session.shift();
    if (this.range === "session") this.render();
  }

  showSession() {
    this.range = "session";
    this.render();
  }

  showHistory(days, readings) {
    this.range = String(days);
    this.history = readings.map((r) => ({ time: new Date(r.timestamp), health: r.health_pct, level: r.level }));
    this.render();
  }

  points() {
    return this.range === "session" ? this.session : this.history;
  }

  subtitle(points) {
    if (this.range !== "session") {
      if (!points.length) return `Sin lecturas guardadas en los últimos ${this.range} días.`;
      const days = new Set(points.map((p) => p.time.toDateString())).size;
      return `${points.length} lecturas guardadas en ${days} día${days !== 1 ? "s" : ""}`;
    }
    if (!points.length) return "Esperando la primera lectura…";
    const mins = Math.floor((Date.now() - this.sessionStart.getTime()) / 60000);
    const since = this.sessionStart.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
    return `${points.length} lectura${points.length !== 1 ? "s" : ""} · ${mins > 0 ? `${mins} min · ` : ""}desde las ${since}`;
  }

  render() {
    const points = this.points();
    $("chart-subtitle").textContent = this.subtitle(points);
    const empty = $("chart-empty");
    $("chart-empty-text").textContent = this.range === "session"
      ? "Conecta el teléfono por USB. El historial guarda una lectura cada 10 min."
      : "Cambia de periodo o deja la web abierta con el teléfono conectado.";

    if (!points.length) {
      this.canvas.classList.add("hidden");
      empty.classList.remove("hidden");
      return;
    }
    this.canvas.classList.remove("hidden");
    empty.classList.add("hidden");

    const fmt = this.range === "session" ? timeFmt : dateFmt;
    const labels = points.map((p) => fmt.format(p.time));
    const health = points.map((p) => p.health);
    const level = points.map((p) => p.level);
    const datasets = this.datasets(health, level, points.length);

    if (this.chart) {
      this.chart.data.labels = labels;
      this.chart.data.datasets = datasets;
      this.chart.options.scales.y.min = yMin([...health, ...level]);
      this.chart.update();
      return;
    }
    this.chart = this.create(labels, datasets, yMin([...health, ...level]));
  }

  datasets(health, level, count) {
    const ctx = this.canvas.getContext("2d");
    const grad = ctx.createLinearGradient(0, 0, 0, 280);
    grad.addColorStop(0, "rgba(163, 196, 220, 0.16)");
    grad.addColorStop(1, "rgba(163, 196, 220, 0)");
    return [
      {
        label: "Salud (%)",
        data: health,
        borderColor: COLORS.accent,
        backgroundColor: grad,
        borderWidth: 2,
        pointRadius: count < 12 ? 3 : 0,
        pointHoverRadius: 4,
        pointBackgroundColor: COLORS.accent,
        pointBorderColor: COLORS.panel,
        pointBorderWidth: 2,
        tension: 0.3,
        fill: true,
      },
      {
        label: "Carga (%)",
        data: level,
        borderColor: COLORS.soft,
        backgroundColor: "transparent",
        borderWidth: 1.25,
        pointRadius: 0,
        tension: 0.3,
        fill: false,
        borderDash: [4, 3],
      },
    ];
  }

  create(labels, datasets, min) {
    const mono = { family: "Geist Mono", size: 11 };
    return new window.Chart(this.canvas.getContext("2d"), {
      type: "line",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 500 },
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false }, // la leyenda está en el HTML
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
            boxWidth: 8,
            boxHeight: 8,
            boxPadding: 4,
            callbacks: { label: (c) => ` ${c.dataset.label}: ${c.parsed.y?.toFixed(1) ?? "—"}%` },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: COLORS.mute, font: mono, maxTicksLimit: 6, maxRotation: 0 },
            border: { display: false },
          },
          y: {
            min,
            max: 102,
            grid: { color: COLORS.line },
            ticks: {
              color: COLORS.mute,
              font: mono,
              maxTicksLimit: 5,
              callback: (v) => (v > 100 ? "" : `${v}%`), // 102 es solo margen
            },
            border: { display: false },
          },
        },
      },
    });
  }
}
