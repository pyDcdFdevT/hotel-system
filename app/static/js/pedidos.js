import {
  get,
  post,
  put,
  showToast,
  formatBs,
  formatUsd,
  formatRate,
} from "./api.js";
import { getCacheTasas, refreshHeaderTasas } from "./config.js";

const state = {
  productos: [],
  carrito: new Map(),
  tipo: "restaurante",
  reservaId: null,
  pedidoActivo: null,
  tasas: { bcv: 405.35, paralelo: 415.0 },
  tasaTipo: "bcv",
};

const els = {
  tipo: document.getElementById("pos-tipo"),
  reserva: document.getElementById("pos-reserva"),
  mesa: document.getElementById("pos-mesa"),
  busqueda: document.getElementById("pos-busqueda"),
  productos: document.getElementById("pos-productos"),
  carrito: document.getElementById("pos-carrito"),
  totalBs: document.getElementById("pos-total-bs"),
  totalUsd: document.getElementById("pos-total-usd"),
  tasa: document.getElementById("pos-tasa"),
  btnCrear: document.getElementById("pos-btn-crear"),
  btnCargar: document.getElementById("pos-btn-cargar"),
  btnVaciar: document.getElementById("pos-btn-vaciar"),
  pedidoInfo: document.getElementById("pos-pedido-info"),
  modalPago: document.getElementById("modal-pago"),
  formPago: document.getElementById("form-pago"),
  pagoCancelar: document.getElementById("pago-cancelar"),
  pagoResumen: document.getElementById("pago-resumen"),
  cuentaPago: document.getElementById("pago-cuenta"),
  btnPagar: document.getElementById("pos-btn-pagar"),
  pedidosActivos: document.getElementById("pos-pedidos-activos"),
  pagoMetodo: document.getElementById("pago-metodo"),
  pagoTasaTipo: document.getElementById("pago-tasa-tipo"),
  pagoTasaInfo: document.getElementById("pago-tasa-info"),
};

export async function initPedidos() {
  if (els.tipo) {
    els.tipo.addEventListener("change", () => {
      state.tipo = els.tipo.value;
    });
  }
  if (els.reserva) {
    els.reserva.addEventListener("change", () => {
      state.reservaId = Number(els.reserva.value) || null;
    });
  }
  if (els.busqueda) {
    els.busqueda.addEventListener("input", renderProductos);
  }
  if (els.btnCrear) {
    els.btnCrear.addEventListener("click", () => crearPedido({ cargarAHabitacion: false }));
  }
  if (els.btnCargar) {
    els.btnCargar.addEventListener("click", () => crearPedido({ cargarAHabitacion: true }));
  }
  if (els.btnVaciar) {
    els.btnVaciar.addEventListener("click", vaciarCarrito);
  }
  if (els.btnPagar) {
    els.btnPagar.addEventListener("click", abrirModalPago);
  }
  if (els.pagoCancelar) {
    els.pagoCancelar.addEventListener("click", cerrarModalPago);
  }
  if (els.formPago) {
    els.formPago.addEventListener("submit", confirmarPago);
  }
  if (els.pagoTasaTipo) {
    els.pagoTasaTipo.addEventListener("change", () => {
      state.tasaTipo = els.pagoTasaTipo.value || "bcv";
      actualizarInfoTasa();
    });
  }
  if (els.pagoMetodo) {
    els.pagoMetodo.addEventListener("change", actualizarInfoTasa);
  }
  document.addEventListener("tasas:actualizadas", actualizarTasasCache);

  await Promise.all([
    cargarTasas(),
    cargarProductos(),
    cargarReservasActivas(),
    cargarCuentas(),
    cargarPedidosActivos(),
  ]);
}

function actualizarTasasCache(event) {
  const detalle = event.detail || getCacheTasas();
  if (detalle.bcv) state.tasas.bcv = Number(detalle.bcv);
  if (detalle.paralelo) state.tasas.paralelo = Number(detalle.paralelo);
  if (els.tasa) {
    els.tasa.textContent = `BCV ${formatRate(state.tasas.bcv)} · Paralelo ${formatRate(state.tasas.paralelo)} Bs/USD`;
  }
  actualizarInfoTasa();
}

async function cargarTasas() {
  try {
    const tasas = await refreshHeaderTasas();
    actualizarTasasCache({ detail: tasas });
  } catch (error) {
    showToast(`Tasas no disponibles: ${error.message}`, "info");
  }
}

async function cargarProductos() {
  try {
    state.productos = await get("/productos/?para_venta=true&activo=true");
    renderProductos();
  } catch (error) {
    showToast(`Error cargando productos: ${error.message}`, "error");
  }
}

async function cargarReservasActivas() {
  if (!els.reserva) return;
  try {
    const reservas = await get("/reservas/activas");
    els.reserva.innerHTML =
      `<option value="">Sin reserva (consumo directo)</option>` +
      reservas
        .map(
          (r) =>
            `<option value="${r.id}">Hab. ${r.habitacion_id} · ${r.huesped}</option>`,
        )
        .join("");
  } catch (error) {
    console.warn("No se pudieron cargar reservas", error);
  }
}

async function cargarCuentas() {
  if (!els.cuentaPago) return;
  try {
    const cuentas = await get("/cuentas/");
    els.cuentaPago.innerHTML =
      `<option value="">Sin registrar a banco</option>` +
      cuentas
        .map(
          (c) => `<option value="${c.id}">${c.nombre} (${c.moneda})</option>`,
        )
        .join("");
  } catch (error) {
    console.warn("Cuentas no disponibles", error);
  }
}

async function cargarPedidosActivos() {
  if (!els.pedidosActivos) return;
  try {
    const pedidos = await get("/pedidos/activos");
    if (!pedidos.length) {
      els.pedidosActivos.innerHTML = `<tr><td colspan="6"><div class="empty-state">Sin pedidos abiertos</div></td></tr>`;
      return;
    }
    els.pedidosActivos.innerHTML = pedidos
      .map(
        (p) => `
        <tr>
          <td>#${p.id}</td>
          <td>${p.tipo}</td>
          <td>${p.mesa || "-"}</td>
          <td>${formatUsd(p.total_usd)}<br><span class="text-xs text-slate-500">${formatBs(p.total_bs)}</span></td>
          <td>${p.estado}</td>
          <td>
            <button data-id="${p.id}" class="btn-cobrar text-xs px-2 py-1 rounded bg-emerald-600 text-white">Cobrar</button>
          </td>
        </tr>`,
      )
      .join("");
    els.pedidosActivos.querySelectorAll(".btn-cobrar").forEach((btn) =>
      btn.addEventListener("click", () => seleccionarPedido(btn.dataset.id)),
    );
  } catch (error) {
    showToast(`Error cargando pedidos activos: ${error.message}`, "error");
  }
}

function renderProductos() {
  if (!els.productos) return;
  const filtro = (els.busqueda?.value || "").toLowerCase();
  const lista = state.productos.filter(
    (p) =>
      !filtro ||
      p.nombre.toLowerCase().includes(filtro) ||
      p.categoria.toLowerCase().includes(filtro),
  );
  if (!lista.length) {
    els.productos.innerHTML = `<div class="empty-state">Sin productos disponibles</div>`;
    return;
  }
  els.productos.innerHTML = lista
    .map(
      (p) => `
      <button data-id="${p.id}" class="btn-add-prod card text-left p-3 hover:border-emerald-500">
        <p class="font-semibold">${p.nombre}</p>
        <p class="text-xs uppercase text-slate-500">${p.categoria}</p>
        <p class="text-sm mt-1">${formatUsd(p.precio_usd)} · ${formatBs(p.precio_bs)}</p>
        <p class="text-xs text-slate-500">Stock: ${Number(p.stock_actual).toFixed(2)}</p>
      </button>`,
    )
    .join("");
  els.productos.querySelectorAll(".btn-add-prod").forEach((btn) =>
    btn.addEventListener("click", () => agregarAlCarrito(Number(btn.dataset.id))),
  );
}

function agregarAlCarrito(productoId) {
  const producto = state.productos.find((p) => p.id === productoId);
  if (!producto) return;
  const actual = state.carrito.get(productoId) || { producto, cantidad: 0 };
  actual.cantidad += 1;
  state.carrito.set(productoId, actual);
  renderCarrito();
}

function cambiarCantidad(productoId, delta) {
  const item = state.carrito.get(productoId);
  if (!item) return;
  item.cantidad += delta;
  if (item.cantidad <= 0) {
    state.carrito.delete(productoId);
  } else {
    state.carrito.set(productoId, item);
  }
  renderCarrito();
}

function quitarDelCarrito(productoId) {
  state.carrito.delete(productoId);
  renderCarrito();
}

function vaciarCarrito() {
  state.carrito.clear();
  renderCarrito();
}

function renderCarrito() {
  if (!els.carrito) return;
  if (!state.carrito.size) {
    els.carrito.innerHTML = `<tr><td colspan="5"><div class="empty-state">Carrito vacío</div></td></tr>`;
    actualizarTotales(0, 0);
    return;
  }
  let totalBs = 0;
  let totalUsd = 0;
  const filas = [];
  for (const item of state.carrito.values()) {
    const subBs = Number(item.producto.precio_bs) * item.cantidad;
    const subUsd = Number(item.producto.precio_usd) * item.cantidad;
    totalBs += subBs;
    totalUsd += subUsd;
    filas.push(`
      <tr>
        <td>${item.producto.nombre}</td>
        <td>${formatUsd(item.producto.precio_usd)}<br><span class="text-xs text-slate-500">${formatBs(item.producto.precio_bs)}</span></td>
        <td>
          <div class="flex items-center gap-1">
            <button data-id="${item.producto.id}" class="btn-menos px-2 py-0.5 border rounded">−</button>
            <span class="w-8 text-center">${item.cantidad}</span>
            <button data-id="${item.producto.id}" class="btn-mas px-2 py-0.5 border rounded">+</button>
          </div>
        </td>
        <td>${formatUsd(subUsd)}<br><span class="text-xs text-slate-500">${formatBs(subBs)}</span></td>
        <td><button data-id="${item.producto.id}" class="btn-quitar text-red-600 text-xs">Quitar</button></td>
      </tr>
    `);
  }
  els.carrito.innerHTML = filas.join("");
  els.carrito.querySelectorAll(".btn-mas").forEach((btn) =>
    btn.addEventListener("click", () => cambiarCantidad(Number(btn.dataset.id), 1)),
  );
  els.carrito.querySelectorAll(".btn-menos").forEach((btn) =>
    btn.addEventListener("click", () => cambiarCantidad(Number(btn.dataset.id), -1)),
  );
  els.carrito.querySelectorAll(".btn-quitar").forEach((btn) =>
    btn.addEventListener("click", () => quitarDelCarrito(Number(btn.dataset.id))),
  );
  actualizarTotales(totalBs, totalUsd);
}

function actualizarTotales(totalBs, totalUsd) {
  if (els.totalBs) els.totalBs.textContent = formatBs(totalBs);
  if (els.totalUsd) els.totalUsd.textContent = formatUsd(totalUsd);
}

async function crearPedido({ cargarAHabitacion }) {
  if (!state.carrito.size) {
    showToast("El carrito está vacío", "error");
    return;
  }
  if (cargarAHabitacion && !state.reservaId) {
    showToast("Seleccione una reserva para cargar el pedido", "error");
    return;
  }
  const payload = {
    tipo: state.tipo || "restaurante",
    mesa: els.mesa?.value?.toString() || null,
    reserva_id: cargarAHabitacion ? state.reservaId : null,
    items: Array.from(state.carrito.values()).map((item) => ({
      producto_id: item.producto.id,
      cantidad: item.cantidad,
    })),
  };
  try {
    const pedido = await post("/pedidos/", payload);
    showToast(`Pedido #${pedido.id} creado`, "success");
    state.pedidoActivo = pedido;
    if (cargarAHabitacion) {
      await put(`/pedidos/${pedido.id}/cargo-habitacion`, { reserva_id: state.reservaId });
      showToast("Pedido cargado a habitación", "success");
      state.pedidoActivo = null;
    } else {
      mostrarPedidoActivo(pedido);
    }
    vaciarCarrito();
    await Promise.all([cargarProductos(), cargarPedidosActivos()]);
  } catch (error) {
    showToast(`Error creando pedido: ${error.message}`, "error");
  }
}

function mostrarPedidoActivo(pedido) {
  if (!els.pedidoInfo) return;
  els.pedidoInfo.innerHTML = `
    <p><strong>Pedido #${pedido.id}</strong> · ${pedido.tipo}</p>
    <p>Total: ${formatUsd(pedido.total_usd)} · ${formatBs(pedido.total_bs)}</p>
    <p class="text-xs text-slate-500">Tasa registrada: ${formatRate(pedido.tasa_usd_del_dia)} Bs/USD</p>
  `;
  els.pedidoInfo.classList.remove("hidden");
  if (els.btnPagar) els.btnPagar.disabled = false;
}

async function seleccionarPedido(pedidoId) {
  try {
    const pedido = await get(`/pedidos/${pedidoId}`);
    state.pedidoActivo = pedido;
    mostrarPedidoActivo(pedido);
    abrirModalPago();
  } catch (error) {
    showToast(`Error cargando pedido: ${error.message}`, "error");
  }
}

function tasaActual() {
  return state.tasaTipo === "paralelo" ? state.tasas.paralelo : state.tasas.bcv;
}

function actualizarInfoTasa() {
  if (!els.pagoTasaInfo || !state.pedidoActivo) return;
  const tasa = tasaActual();
  const total_bs = Number(state.pedidoActivo.total_bs || 0);
  const total_usd = Number(state.pedidoActivo.total_usd || 0);
  const equivalente_bs = total_usd * tasa;
  els.pagoTasaInfo.innerHTML = `
    Tasa ${state.tasaTipo.toUpperCase()}: <strong>${formatRate(tasa)} Bs/USD</strong> ·
    Equivalente: ${formatBs(equivalente_bs || total_bs)}
  `;
}

function abrirModalPago() {
  if (!state.pedidoActivo) {
    showToast("Cree un pedido primero", "error");
    return;
  }
  if (els.pagoResumen) {
    const p = state.pedidoActivo;
    els.pagoResumen.innerHTML = `
      <p><strong>Pedido #${p.id}</strong></p>
      <p>Total Bs: ${formatBs(p.total_bs)}</p>
      <p>Total USD: ${formatUsd(p.total_usd)}</p>
    `;
  }
  els.formPago?.reset();
  if (els.pagoTasaTipo) {
    els.pagoTasaTipo.value = state.tasaTipo;
  }
  actualizarInfoTasa();
  els.modalPago?.classList.remove("hidden");
}

function cerrarModalPago() {
  els.modalPago?.classList.add("hidden");
}

async function confirmarPago(event) {
  event.preventDefault();
  if (!state.pedidoActivo) return;
  const formData = new FormData(els.formPago);
  const monto_bs = Number(formData.get("monto_bs") || 0);
  const monto_usd = Number(formData.get("monto_usd") || 0);
  const metodo_pago = formData.get("metodo_pago") || "bs";
  const cuenta_banco_id = Number(formData.get("cuenta_banco_id")) || null;
  const tasa_tipo = formData.get("tasa_tipo") || state.tasaTipo || "bcv";
  try {
    const pedido = await post(`/pedidos/${state.pedidoActivo.id}/pagar`, {
      metodo_pago,
      monto_bs,
      monto_usd,
      cuenta_banco_id,
      tasa_tipo,
    });
    const vueltoBs = Number(pedido.vuelto_bs || 0);
    const vueltoUsd = Number(pedido.vuelto_usd || 0);
    let mensaje = `Pedido #${pedido.id} pagado (${metodo_pago})`;
    if (vueltoBs > 0 || vueltoUsd > 0) {
      mensaje += ` · Vuelto ${formatBs(vueltoBs)} / ${formatUsd(vueltoUsd)}`;
    }
    showToast(mensaje, "success");
    cerrarModalPago();
    state.pedidoActivo = null;
    if (els.pedidoInfo) els.pedidoInfo.innerHTML = "";
    if (els.btnPagar) els.btnPagar.disabled = true;
    await cargarPedidosActivos();
  } catch (error) {
    showToast(`Error en pago: ${error.message}`, "error");
  }
}
