import {
  get,
  post,
  showToast,
  formatBs,
  formatUsd,
  formatDate,
} from "./api.js";

const els = {
  tablaProductos: document.getElementById("inv-tabla-productos"),
  formProducto: document.getElementById("form-producto"),
  filtroCategoria: document.getElementById("inv-filtro-categoria"),
  tablaMovimientos: document.getElementById("inv-tabla-movimientos"),
  formMovimiento: document.getElementById("form-movimiento"),
  productoSelect: document.getElementById("mov-producto"),
};

let productosCache = [];

export async function initInventario() {
  if (els.formProducto) {
    els.formProducto.addEventListener("submit", crearProducto);
  }
  if (els.filtroCategoria) {
    els.filtroCategoria.addEventListener("change", loadProductos);
  }
  if (els.formMovimiento) {
    els.formMovimiento.addEventListener("submit", registrarMovimiento);
  }
  await Promise.all([loadProductos(), loadMovimientos()]);
}

export async function loadProductos() {
  if (!els.tablaProductos) return;
  try {
    const categoria = els.filtroCategoria?.value || "";
    const query = categoria ? `?categoria=${encodeURIComponent(categoria)}` : "";
    productosCache = await get(`/productos/${query}`);
    if (els.productoSelect) {
      els.productoSelect.innerHTML =
        `<option value="">Seleccione producto...</option>` +
        productosCache
          .map((p) => `<option value="${p.id}">${p.nombre}</option>`)
          .join("");
    }
    if (!productosCache.length) {
      els.tablaProductos.innerHTML = `<tr><td colspan="8"><div class="empty-state">Sin productos</div></td></tr>`;
      return;
    }
    els.tablaProductos.innerHTML = productosCache
      .map((p) => {
        const bajo = Number(p.stock_actual) <= Number(p.stock_minimo);
        return `
          <tr class="${bajo ? "bg-red-50" : ""}">
            <td>${p.nombre}</td>
            <td>${p.categoria}</td>
            <td>${formatUsd(p.precio_usd)}<br><span class="text-xs text-slate-500">${formatBs(p.precio_bs)}</span></td>
            <td>${formatBs(p.costo_bs)}</td>
            <td>${Number(p.stock_actual).toFixed(2)} ${p.unidad}</td>
            <td>${Number(p.stock_minimo).toFixed(2)}</td>
            <td>${p.es_para_venta ? "Sí" : "No"}</td>
            <td><span class="badge ${p.activo ? "badge-success" : "badge-danger"}">${p.activo ? "Activo" : "Inactivo"}</span></td>
          </tr>`;
      })
      .join("");
  } catch (error) {
    showToast(`Error cargando productos: ${error.message}`, "error");
  }
}

async function loadMovimientos() {
  if (!els.tablaMovimientos) return;
  try {
    const movs = await get("/inventario/movimientos?limit=50");
    if (!movs.length) {
      els.tablaMovimientos.innerHTML = `<tr><td colspan="6"><div class="empty-state">Sin movimientos</div></td></tr>`;
      return;
    }
    els.tablaMovimientos.innerHTML = movs
      .map(
        (m) => `
        <tr>
          <td>${formatDate(m.fecha)}</td>
          <td>${m.producto_id}</td>
          <td><span class="badge ${m.tipo === "entrada" ? "badge-success" : "badge-warning"}">${m.tipo}</span></td>
          <td>${Number(m.cantidad).toFixed(2)}</td>
          <td>${Number(m.stock_anterior).toFixed(2)} → ${Number(m.stock_nuevo).toFixed(2)}</td>
          <td>${m.motivo || "-"}</td>
        </tr>`,
      )
      .join("");
  } catch (error) {
    showToast(`Error cargando movimientos: ${error.message}`, "error");
  }
}

async function crearProducto(event) {
  event.preventDefault();
  const formData = new FormData(els.formProducto);
  const payload = {
    nombre: formData.get("nombre")?.toString().trim(),
    categoria: formData.get("categoria")?.toString() || "general",
    descripcion: formData.get("descripcion")?.toString() || null,
    precio_bs: Number(formData.get("precio_bs") || 0),
    precio_usd: Number(formData.get("precio_usd") || 0),
    costo_bs: Number(formData.get("costo_bs") || 0),
    stock_actual: Number(formData.get("stock_actual") || 0),
    stock_minimo: Number(formData.get("stock_minimo") || 0),
    unidad: formData.get("unidad")?.toString() || "unidad",
    es_para_venta: formData.get("es_para_venta") === "on",
    activo: true,
  };
  if (!payload.nombre) {
    showToast("Indique el nombre del producto", "error");
    return;
  }
  try {
    await post("/productos/", payload);
    showToast("Producto creado", "success");
    els.formProducto.reset();
    await loadProductos();
  } catch (error) {
    showToast(`Error creando producto: ${error.message}`, "error");
  }
}

async function registrarMovimiento(event) {
  event.preventDefault();
  const formData = new FormData(els.formMovimiento);
  const payload = {
    producto_id: Number(formData.get("producto_id")),
    tipo: formData.get("tipo")?.toString() || "entrada",
    cantidad: Number(formData.get("cantidad") || 0),
    motivo: formData.get("motivo")?.toString() || null,
  };
  if (!payload.producto_id || payload.cantidad <= 0) {
    showToast("Indique producto y cantidad", "error");
    return;
  }
  try {
    await post("/inventario/movimientos", payload);
    showToast("Movimiento registrado", "success");
    els.formMovimiento.reset();
    await Promise.all([loadProductos(), loadMovimientos()]);
  } catch (error) {
    showToast(`Error en movimiento: ${error.message}`, "error");
  }
}
