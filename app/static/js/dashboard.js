import { get, formatBs, formatUsd, showToast } from "./api.js";
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
};

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
  } catch (error) {
    showToast(`Error cargando dashboard: ${error.message}`, "error");
  }
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
