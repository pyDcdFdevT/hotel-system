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
  bajoStock: document.getElementById("dash-bajo-stock"),
  tablaBajoStock: document.getElementById("dash-tabla-bajo-stock"),
  areaHabUsd: document.getElementById("dash-area-habitaciones-usd"),
  areaHabBs: document.getElementById("dash-area-habitaciones-bs"),
  areaBarUsd: document.getElementById("dash-area-bar-usd"),
  areaBarBs: document.getElementById("dash-area-bar-bs"),
  areaCocinaUsd: document.getElementById("dash-area-cocina-usd"),
  areaCocinaBs: document.getElementById("dash-area-cocina-bs"),
  areaTotalUsd: document.getElementById("dash-area-total-usd"),
  areaTotalBs: document.getElementById("dash-area-total-bs"),
  tablaTx: document.getElementById("dash-tabla-transacciones"),
  txActualizado: document.getElementById("dash-tx-actualizado"),
  areasMetodos: document.getElementById("dash-areas-metodos"),
  areasActualizado: document.getElementById("dash-areas-actualizado"),
};

const AREA_META = {
  habitaciones: { titulo: "🏨 Habitaciones", clase: "area-habitaciones" },
  bar: { titulo: "🍸 Bar", clase: "area-bar" },
  cocina: { titulo: "🍳 Cocina", clase: "area-cocina" },
  piscina: { titulo: "🏊 Piscina", clase: "area-piscina" },
};

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
    const [resumen, ventasArea] = await Promise.all([
      get("/reportes/resumen-dia"),
      get("/reportes/ventas-por-area"),
      refreshHeaderTasas(),
    ]);
    if (els.ventasBs) els.ventasBs.textContent = formatBs(resumen.ventas_bs);
    if (els.ventasUsd) els.ventasUsd.textContent = formatUsd(resumen.ventas_usd);
    if (els.gastosBs) els.gastosBs.textContent = formatBs(resumen.gastos_bs);
    if (els.gastosUsd) els.gastosUsd.textContent = formatUsd(resumen.gastos_usd);
    if (els.pedidos) els.pedidos.textContent = resumen.pedidos_cantidad;
    if (els.ocupacion) els.ocupacion.textContent = `${resumen.ocupacion_porcentaje.toFixed(1)} %`;
    if (els.habsOcupadas) {
      els.habsOcupadas.textContent = `${resumen.habitaciones_ocupadas} / ${resumen.habitaciones_totales}`;
    }
    if (els.bajoStock) els.bajoStock.textContent = resumen.productos_bajo_stock;

    renderVentasArea(ventasArea);
    await loadBajoStockTabla();
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
    const areas = ["habitaciones", "bar", "cocina", "piscina"];
    els.areasMetodos.innerHTML = areas
      .map((clave) => renderAreaCard(clave, data[clave]))
      .join("");
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
  // Ordenamos los métodos según METODOS_ORDEN; cualquier extra (otros) al final.
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

function renderVentasArea(data) {
  if (!data || !Array.isArray(data.areas)) return;
  const map = Object.fromEntries(
    data.areas.map((a) => [a.area, a]),
  );
  const setArea = (elUsd, elBs, area) => {
    const v = map[area] || { ventas_bs: 0, ventas_usd: 0 };
    if (elUsd) elUsd.textContent = formatUsd(v.ventas_usd);
    if (elBs) elBs.textContent = formatBs(v.ventas_bs);
  };
  setArea(els.areaHabUsd, els.areaHabBs, "habitaciones");
  setArea(els.areaBarUsd, els.areaBarBs, "bar");
  setArea(els.areaCocinaUsd, els.areaCocinaBs, "cocina");
  if (els.areaTotalUsd) els.areaTotalUsd.textContent = formatUsd(data.total_usd);
  if (els.areaTotalBs) els.areaTotalBs.textContent = formatBs(data.total_bs);
}

async function loadBajoStockTabla() {
  if (!els.tablaBajoStock) return;
  try {
    const productos = await get("/inventario/bajo-stock");
    if (!productos.length) {
      els.tablaBajoStock.innerHTML = `<tr><td colspan="4"><div class="empty-state">Sin productos bajo el mínimo</div></td></tr>`;
      return;
    }
    els.tablaBajoStock.innerHTML = productos
      .map(
        (p) => `
        <tr>
          <td>${p.nombre}</td>
          <td>${p.categoria}</td>
          <td>${Number(p.stock_actual).toFixed(2)} ${p.unidad}</td>
          <td>${Number(p.stock_minimo).toFixed(2)}</td>
        </tr>`,
      )
      .join("");
  } catch (error) {
    els.tablaBajoStock.innerHTML = `<tr><td colspan="4"><div class="empty-state">${error.message}</div></td></tr>`;
  }
}
