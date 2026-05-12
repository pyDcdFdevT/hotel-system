import {
  get,
  formatBs,
  formatUsd,
  formatFechaHoraVe,
  showToast,
} from "./api.js";
import { refreshHeaderTasas } from "./config.js";

const els = {
  ventasBs: document.getElementById("dash-ventas-bs"),
  ventasUsd: document.getElementById("dash-ventas-usd"),
  gastosBs: document.getElementById("dash-gastos-bs"),
  gastosUsd: document.getElementById("dash-gastos-usd"),
  pedidos: document.getElementById("dash-pedidos"),
  ocupacion: document.getElementById("dash-ocupacion"),
  habsOcupadas: document.getElementById("dash-habs-ocupadas"),
  tablaTx: document.getElementById("dash-tabla-transacciones"),
  txActualizado: document.getElementById("dash-tx-actualizado"),
  areasMetodos: document.getElementById("dash-areas-metodos"),
  areasActualizado: document.getElementById("dash-areas-actualizado"),
  areasTotalUsd: document.getElementById("dash-areas-total-usd"),
  areasTotalBs: document.getElementById("dash-areas-total-bs"),
};

const AREA_META = {
  habitaciones: { titulo: "🏨 Habitaciones", clase: "area-habitaciones" },
  bar: { titulo: "🍸 Bar", clase: "area-bar" },
  cocina: { titulo: "🍳 Cocina", clase: "area-cocina" },
  piscina: { titulo: "🏊 Piscina", clase: "area-piscina" },
};

// Orden visible de las áreas: tal como pide el usuario.
const AREAS_ORDEN = ["habitaciones", "bar", "cocina", "piscina"];

const METODOS_ORDEN = [
  "efectivo_usd",
  "efectivo_bs",
  "transferencia_bs",
  "pagomovil_bs",
  "mixto",
];

const TX_BADGES = {
  checkout: { etiqueta: "Check-out", clase: "badge-info" },
  habitacion: { etiqueta: "Consumo hab.", clase: "badge-warning" },
  piscina: { etiqueta: "Piscina", clase: "badge-success" },
  bar: { etiqueta: "Bar", clase: "badge-info" },
  restaurante: { etiqueta: "Cocina", clase: "badge-success" },
  cocina: { etiqueta: "Cocina", clase: "badge-success" },
};

let txTimer = null;

export async function loadDashboard() {
  try {
    const resumen = await get("/reportes/resumen-dia");
    await refreshHeaderTasas();
    if (els.ventasBs) els.ventasBs.textContent = formatBs(resumen.ventas_bs);
    if (els.ventasUsd) els.ventasUsd.textContent = formatUsd(resumen.ventas_usd);
    if (els.gastosBs) els.gastosBs.textContent = formatBs(resumen.gastos_bs);
    if (els.gastosUsd) els.gastosUsd.textContent = formatUsd(resumen.gastos_usd);
    if (els.pedidos) els.pedidos.textContent = resumen.pedidos_cantidad;
    if (els.ocupacion)
      els.ocupacion.textContent = `${resumen.ocupacion_porcentaje.toFixed(1)} %`;
    if (els.habsOcupadas) {
      els.habsOcupadas.textContent = `${resumen.habitaciones_ocupadas} / ${resumen.habitaciones_totales}`;
    }

    await loadVentasPorAreaConMetodos();
    await loadUltimasTransacciones();
    iniciarPolling();
  } catch (error) {
    showToast(`Error cargando dashboard: ${error.message}`, "error");
  }
}

function iniciarPolling() {
  if (txTimer) return;
  txTimer = setInterval(() => {
    loadUltimasTransacciones().catch(() => {});
    loadVentasPorAreaConMetodos().catch(() => {});
  }, 30_000);
}

export async function loadVentasPorAreaConMetodos() {
  if (!els.areasMetodos) return;
  try {
    const data = await get("/reportes/ventas-por-area-con-metodos");
    els.areasMetodos.innerHTML = AREAS_ORDEN.map((clave) =>
      renderAreaCard(clave, data[clave]),
    ).join("");
    // TOTAL GENERAL = suma de USD y Bs de las 4 áreas.
    let totalUsd = 0;
    let totalBs = 0;
    for (const clave of AREAS_ORDEN) {
      const area = data[clave] || {};
      totalUsd += Number(area.total_usd || 0);
      totalBs += Number(area.total_bs || 0);
    }
    if (els.areasTotalUsd) els.areasTotalUsd.textContent = formatUsd(totalUsd);
    if (els.areasTotalBs) els.areasTotalBs.textContent = formatBs(totalBs);
    if (els.areasActualizado) {
      els.areasActualizado.textContent = `Actualizado ${formatFechaHoraVe(new Date())}`;
    }
  } catch (error) {
    els.areasMetodos.innerHTML = `<div class="text-sm text-red-600">${error.message}</div>`;
  }
}

function renderAreaCard(clave, datos) {
  const meta = AREA_META[clave] || { titulo: clave, clase: "" };
  const totalUsd = Number(datos?.total_usd || 0);
  const totalBs = Number(datos?.total_bs || 0);
  const vacia = totalUsd === 0 && totalBs === 0;
  const metodos = datos?.metodos || {};
  const claves = [
    ...METODOS_ORDEN.filter((k) => metodos[k]),
    ...Object.keys(metodos).filter((k) => !METODOS_ORDEN.includes(k)),
  ];
  const filas = claves
    .map((k) => {
      const m = metodos[k];
      const usd = Number(m.usd || 0);
      const bs = Number(m.bs || 0);
      const partes = [];
      if (usd > 0) partes.push(formatUsd(usd));
      if (bs > 0) partes.push(formatBs(bs));
      return `<li>
        <span>${m.label || k}</span>
        <span class="font-medium">${partes.join(" · ") || "-"}</span>
      </li>`;
    })
    .join("");
  return `
    <div class="area-card ${meta.clase} ${vacia ? "empty" : ""}">
      <div class="area-title">
        <h3>${meta.titulo}</h3>
        <span class="font-semibold">${formatUsd(totalUsd)} · ${formatBs(totalBs)}</span>
      </div>
      ${
        vacia
          ? `<p class="area-totales">Sin ventas hoy</p>`
          : `<ul class="area-metodos">${filas}</ul>`
      }
    </div>
  `;
}

async function loadUltimasTransacciones() {
  if (!els.tablaTx) return;
  try {
    const filas = await get("/reportes/ultimas-transacciones?limite=20");
    if (!filas.length) {
      els.tablaTx.innerHTML = `<tr><td colspan="6"><div class="empty-state">Sin transacciones registradas todavía.</div></td></tr>`;
    } else {
      els.tablaTx.innerHTML = filas.map(renderTxFila).join("");
    }
    if (els.txActualizado) {
      els.txActualizado.textContent = `Actualizado ${formatFechaHoraVe(new Date())}`;
    }
  } catch (error) {
    els.tablaTx.innerHTML = `<tr><td colspan="6"><div class="empty-state">${error.message}</div></td></tr>`;
  }
}

function renderTxFila(tx) {
  const fecha = tx.fecha ? formatFechaHoraVe(tx.fecha) : "-";
  const badge = TX_BADGES[tx.tipo] || {
    etiqueta: tx.tipo || "venta",
    clase: "badge-info",
  };
  return `
    <tr>
      <td class="text-xs whitespace-nowrap">${fecha}</td>
      <td><span class="badge ${badge.clase}">${badge.etiqueta}</span></td>
      <td>${tx.concepto || "-"}</td>
      <td class="text-right">${formatUsd(tx.monto_usd)}</td>
      <td class="text-right">${formatBs(tx.monto_bs)}</td>
      <td class="text-xs text-slate-500">${tx.usuario_nombre || "-"}</td>
    </tr>
  `;
}
