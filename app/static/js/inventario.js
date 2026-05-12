import {
  get,
  post,
  put,
  del,
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
  modalEditar: document.getElementById("modal-producto"),
  formEditar: document.getElementById("form-editar-producto"),
  btnCancelarEditar: document.getElementById("editar-producto-cancelar"),
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
  if (els.formEditar) {
    els.formEditar.addEventListener("submit", guardarEdicion);
  }
  if (els.btnCancelarEditar) {
    els.btnCancelarEditar.addEventListener("click", cerrarModalEditar);
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
      els.tablaProductos.innerHTML = `<tr><td colspan="9"><div class="empty-state">Sin productos</div></td></tr>`;
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
            <td>
              <div class="flex gap-1">
                <button data-id="${p.id}" class="btn-editar-prod text-xs px-2 py-1 rounded bg-blue-600 text-white">✏️ Editar</button>
                <button data-id="${p.id}" class="btn-borrar-prod text-xs px-2 py-1 rounded bg-red-600 text-white">🗑️ Eliminar</button>
              </div>
            </td>
          </tr>`;
      })
      .join("");
    els.tablaProductos.querySelectorAll(".btn-editar-prod").forEach((btn) =>
      btn.addEventListener("click", () => abrirModalEditar(Number(btn.dataset.id))),
    );
    els.tablaProductos.querySelectorAll(".btn-borrar-prod").forEach((btn) =>
      btn.addEventListener("click", () => eliminarProducto(Number(btn.dataset.id))),
    );
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

function abrirModalEditar(productoId) {
  const producto = productosCache.find((p) => p.id === productoId);
  if (!producto || !els.formEditar) return;
  const form = els.formEditar;
  form.querySelector('[name="id"]').value = producto.id;
  form.querySelector('[name="nombre"]').value = producto.nombre || "";
  form.querySelector('[name="categoria"]').value = producto.categoria || "general";
  form.querySelector('[name="unidad"]').value = producto.unidad || "unidad";
  form.querySelector('[name="precio_bs"]').value = Number(producto.precio_bs || 0);
  form.querySelector('[name="precio_usd"]').value = Number(producto.precio_usd || 0);
  form.querySelector('[name="costo_bs"]').value = Number(producto.costo_bs || 0);
  form.querySelector('[name="stock_actual"]').value = Number(producto.stock_actual || 0);
  form.querySelector('[name="stock_minimo"]').value = Number(producto.stock_minimo || 0);
  form.querySelector('[name="es_para_venta"]').checked = Boolean(producto.es_para_venta);
  form.querySelector('[name="activo"]').checked = Boolean(producto.activo);
  els.modalEditar?.classList.remove("hidden");
}

function cerrarModalEditar() {
  els.modalEditar?.classList.add("hidden");
  els.formEditar?.reset();
}

async function guardarEdicion(event) {
  event.preventDefault();
  if (!els.formEditar) return;
  const formData = new FormData(els.formEditar);
  const id = Number(formData.get("id"));
  if (!id) {
    showToast("Producto inválido", "error");
    return;
  }
  const payload = {
    nombre: formData.get("nombre")?.toString().trim(),
    categoria: formData.get("categoria")?.toString() || "general",
    unidad: formData.get("unidad")?.toString() || "unidad",
    precio_bs: Number(formData.get("precio_bs") || 0),
    precio_usd: Number(formData.get("precio_usd") || 0),
    costo_bs: Number(formData.get("costo_bs") || 0),
    stock_actual: Number(formData.get("stock_actual") || 0),
    stock_minimo: Number(formData.get("stock_minimo") || 0),
    es_para_venta: formData.get("es_para_venta") === "on",
    activo: formData.get("activo") === "on",
  };
  try {
    await put(`/productos/${id}`, payload);
    showToast("Producto actualizado", "success");
    cerrarModalEditar();
    await loadProductos();
  } catch (error) {
    showToast(`Error actualizando producto: ${error.message}`, "error");
  }
}

async function eliminarProducto(productoId) {
  const producto = productosCache.find((p) => p.id === productoId);
  if (!producto) return;
  const mensaje =
    `¿Eliminar el producto "${producto.nombre}"?\n\n` +
    `Si tiene pedidos o movimientos, se marcará como inactivo en lugar de borrarse.`;
  if (!window.confirm(mensaje)) return;
  try {
    const resp = await del(`/productos/${productoId}`);
    const msg = resp?.mensaje || "Producto eliminado";
    showToast(msg, "success");
    await loadProductos();
  } catch (error) {
    showToast(`Error eliminando producto: ${error.message}`, "error");
  }
}
