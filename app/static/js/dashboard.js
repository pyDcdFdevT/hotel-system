import { get, formatBs, formatUsd, formatRate, showToast } from "./api.js";

const els = {
  ventasBs: document.getElementById("dash-ventas-bs"),
  ventasUsd: document.getElementById("dash-ventas-usd"),
  gastosBs: document.getElementById("dash-gastos-bs"),
  gastosUsd: document.getElementById("dash-gastos-usd"),
  pedidos: document.getElementById("dash-pedidos"),
  ocupacion: document.getElementById("dash-ocupacion"),
  habsOcupadas: document.getElementById("dash-habs-ocupadas"),
  bajoStock: document.getElementById("dash-bajo-stock"),
  tasaDia: document.getElementById("dash-tasa-dia"),
  tablaBajoStock: document.getElementById("dash-tabla-bajo-stock"),
};

export async function loadDashboard() {
  try {
    const resumen = await get("/reportes/resumen-dia");
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
    if (els.tasaDia) els.tasaDia.textContent = formatRate(resumen.tasa_dia);

    await loadBajoStockTabla();
  } catch (error) {
    showToast(`Error cargando dashboard: ${error.message}`, "error");
  }
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
