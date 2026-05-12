import {
  get,
  post,
  showToast,
  formatBs,
  formatUsd,
  formatRate,
  formatTimeVE,
  nowVE,
} from "./api.js";
import { getCacheTasas, refreshHeaderTasas } from "./config.js";

const STORAGE_KEY = "hotel-pos-state-v1";

const CATEGORIAS_ORDEN = [
  "Piscina",
  "Para Picar",
  "Desayunos",
  "A la Carta",
  "Ligeras",
  "Cervezas",
  "Rones",
  "Whisky",
  "Licores",
  "Vinos",
  "Cockeles",
];

const state = {
  productos: [],
  porCategoria: new Map(),
  favoritos: [],
  carrito: new Map(),
  pedidoActivo: null,
  mesaActiva: null,
  mesaTipo: "restaurante",
  habitacionNumero: null,
  reservaId: null,
  mesasActivas: [],
  habitaciones: [],
  tasas: { bcv: 405.35, paralelo: 415.0 },
  tasaTipo: "bcv",
};

const els = {
  busqueda: document.getElementById("pos-busqueda"),
  favoritos: document.getElementById("pos-favoritos"),
  categorias: document.getElementById("pos-categorias"),
  mesasChips: document.getElementById("pos-mesas-chips"),
  btnNuevaMesa: document.getElementById("pos-btn-nueva-mesa"),
  btnRefrescarFavs: document.getElementById("pos-btn-refrescar-favs"),
  pedidoTitulo: document.getElementById("pos-pedido-titulo"),
  pedidoInfo: document.getElementById("pos-pedido-info"),
  horaActual: document.getElementById("pos-hora-actual"),
  carrito: document.getElementById("pos-carrito"),
  totalBs: document.getElementById("pos-total-bs"),
  totalUsd: document.getElementById("pos-total-usd"),
  tasa: document.getElementById("pos-tasa"),
  btnVaciar: document.getElementById("pos-btn-vaciar"),
  btnCobrar: document.getElementById("pos-btn-cobrar"),
  btnNuevo: document.getElementById("pos-btn-nuevo"),
  modalNuevaMesa: document.getElementById("modal-nueva-mesa"),
  formNuevaMesa: document.getElementById("form-nueva-mesa"),
  nuevaMesaCancelar: document.getElementById("nueva-mesa-cancelar"),
  reservaSelect: document.getElementById("pos-reserva"),
  bloqueMesa: document.getElementById("nueva-mesa-bloque-mesa"),
  bloqueHabitacion: document.getElementById("nueva-mesa-bloque-habitacion"),
  inputHabitacion: document.getElementById("pos-input-habitacion"),
  habitacionesList: document.getElementById("pos-habitaciones-list"),

  modalPago: document.getElementById("modal-pago"),
  formPago: document.getElementById("form-pago"),
  pagoCancelar: document.getElementById("pago-cancelar"),
  pagoResumen: document.getElementById("pago-resumen"),
  cuentaPago: document.getElementById("pago-cuenta"),
  pagoMetodo: document.getElementById("pago-metodo"),
  pagoTasaTipo: document.getElementById("pago-tasa-tipo"),
  pagoTasaInfo: document.getElementById("pago-tasa-info"),
};

let favRefreshTimer = null;
let horaTimer = null;

export async function initPedidos() {
  if (els.busqueda) els.busqueda.addEventListener("input", renderCatalogo);
  if (els.btnNuevaMesa) els.btnNuevaMesa.addEventListener("click", abrirNuevaMesa);
  if (els.nuevaMesaCancelar)
    els.nuevaMesaCancelar.addEventListener("click", cerrarNuevaMesa);
  if (els.formNuevaMesa) els.formNuevaMesa.addEventListener("submit", crearNuevaMesa);
  if (els.btnRefrescarFavs) els.btnRefrescarFavs.addEventListener("click", cargarFavoritos);
  if (els.btnVaciar) els.btnVaciar.addEventListener("click", vaciarCarrito);
  if (els.btnNuevo) els.btnNuevo.addEventListener("click", nuevoPedido);
  if (els.btnCobrar) els.btnCobrar.addEventListener("click", abrirModalPago);
  if (els.pagoCancelar) els.pagoCancelar.addEventListener("click", cerrarModalPago);
  if (els.formPago) els.formPago.addEventListener("submit", confirmarPago);
  if (els.pagoTasaTipo) {
    els.pagoTasaTipo.addEventListener("change", () => {
      state.tasaTipo = els.pagoTasaTipo.value || "bcv";
      actualizarInfoTasa();
    });
  }
  if (els.pagoMetodo) els.pagoMetodo.addEventListener("change", actualizarInfoTasa);

  document.addEventListener("tasas:actualizadas", actualizarTasasCache);

  restaurarLocal();

  if (els.formNuevaMesa) {
    els.formNuevaMesa
      .querySelectorAll('input[name="modo"]')
      .forEach((radio) => radio.addEventListener("change", actualizarModoNuevaMesa));
  }

  await Promise.all([
    cargarTasas(),
    cargarProductos(),
    cargarFavoritos(),
    cargarReservasActivas(),
    cargarCuentas(),
    cargarMesasActivas(),
    cargarHabitaciones(),
  ]);

  if (favRefreshTimer) clearInterval(favRefreshTimer);
  favRefreshTimer = setInterval(cargarFavoritos, 5 * 60 * 1000); // cada 5 min

  if (horaTimer) clearInterval(horaTimer);
  actualizarHora();
  horaTimer = setInterval(actualizarHora, 30 * 1000);
}

// --------------------------------------------------------------------------
// Tasas
// --------------------------------------------------------------------------
function actualizarTasasCache(event) {
  const detalle = event.detail || getCacheTasas();
  if (detalle?.bcv) state.tasas.bcv = Number(detalle.bcv);
  if (detalle?.paralelo) state.tasas.paralelo = Number(detalle.paralelo);
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

function actualizarHora() {
  if (els.horaActual) els.horaActual.textContent = `Hora Venezuela: ${nowVE()}`;
}

// --------------------------------------------------------------------------
// Productos / catálogo
// --------------------------------------------------------------------------
async function cargarProductos() {
  try {
    state.productos = await get("/productos/?para_venta=true&activo=true");
    indexarPorCategoria();
    renderCatalogo();
    reconstruirCarritoPendiente();
    await restaurarPedidoPendiente();
    refrescarUI();
  } catch (error) {
    showToast(`Error cargando productos: ${error.message}`, "error");
  }
}

async function restaurarPedidoPendiente() {
  if (!state._pendientePedidoId) return;
  try {
    const pedido = await get(`/pedidos/${state._pendientePedidoId}`);
    if (pedido?.estado === "abierto") {
      state.pedidoActivo = pedido;
      state.mesaActiva = pedido.mesa || state.mesaActiva;
      state.mesaTipo = pedido.tipo || state.mesaTipo;
    }
  } catch (_err) {
    /* el pedido pudo haberse cerrado: no es error */
  } finally {
    state._pendientePedidoId = null;
  }
}

function indexarPorCategoria() {
  state.porCategoria.clear();
  for (const p of state.productos) {
    const cat = p.categoria || "Otros";
    if (!state.porCategoria.has(cat)) state.porCategoria.set(cat, []);
    state.porCategoria.get(cat).push(p);
  }
}

async function cargarFavoritos() {
  if (!els.favoritos) return;
  try {
    state.favoritos = await get("/productos/favoritos?limit=10");
    renderFavoritos();
  } catch (error) {
    console.warn("Favoritos no disponibles", error);
  }
}

function renderFavoritos() {
  if (!els.favoritos) return;
  if (!state.favoritos.length) {
    els.favoritos.innerHTML = `<div class="empty-state">Aún no hay productos favoritos</div>`;
    return;
  }
  els.favoritos.innerHTML = state.favoritos
    .map((p) => productoButtonHtml(p, true))
    .join("");
  els.favoritos.querySelectorAll(".pos-prod-btn").forEach((btn) =>
    btn.addEventListener("click", () =>
      agregarAlCarrito(Number(btn.dataset.id)),
    ),
  );
}

function renderCatalogo() {
  if (!els.categorias) return;
  const filtro = (els.busqueda?.value || "").trim().toLowerCase();
  const categoriasUsadas = Array.from(state.porCategoria.keys()).sort((a, b) => {
    const ia = CATEGORIAS_ORDEN.indexOf(a);
    const ib = CATEGORIAS_ORDEN.indexOf(b);
    if (ia !== -1 && ib !== -1) return ia - ib;
    if (ia !== -1) return -1;
    if (ib !== -1) return 1;
    return a.localeCompare(b);
  });

  const partes = [];
  for (const cat of categoriasUsadas) {
    const productos = state.porCategoria
      .get(cat)
      .filter((p) => !filtro || p.nombre.toLowerCase().includes(filtro));
    if (!productos.length) continue;
    const open = filtro ? "open" : "";
    partes.push(`
      <details class="pos-categoria" ${open}>
        <summary>
          <span>${cat}</span>
          <span class="text-xs text-slate-500 mr-2">${productos.length}</span>
        </summary>
        <div class="pos-categoria-body pos-favoritos-grid">
          ${productos.map((p) => productoButtonHtml(p, false)).join("")}
        </div>
      </details>
    `);
  }
  els.categorias.innerHTML =
    partes.join("") ||
    `<div class="empty-state">Sin productos para "${filtro}"</div>`;

  els.categorias.querySelectorAll(".pos-prod-btn").forEach((btn) =>
    btn.addEventListener("click", () =>
      agregarAlCarrito(Number(btn.dataset.id)),
    ),
  );
}

function productoButtonHtml(p, esFavorito) {
  const badge = p.porcion ? `<span class="pos-prod-badge">${p.porcion}</span>` : "";
  const star = esFavorito ? "⭐ " : "";
  return `
    <button data-id="${p.id}" class="pos-prod-btn">
      ${badge}
      <span class="pos-prod-name">${star}${p.nombre}</span>
      <span class="pos-prod-price">${formatUsd(p.precio_usd)} · ${formatBs(p.precio_bs)}</span>
    </button>
  `;
}

// --------------------------------------------------------------------------
// Mesas activas
// --------------------------------------------------------------------------
async function cargarMesasActivas() {
  if (!els.mesasChips) return;
  try {
    state.mesasActivas = await get("/pedidos/activos");
    renderMesasChips();
  } catch (error) {
    showToast(`Error cargando mesas: ${error.message}`, "error");
  }
}

function renderMesasChips() {
  if (!els.mesasChips) return;
  if (!state.mesasActivas.length) {
    els.mesasChips.innerHTML = `<p class="empty-state text-xs">Sin mesas activas. Crea una con "+ Nueva mesa".</p>`;
    return;
  }
  els.mesasChips.innerHTML = state.mesasActivas
    .map((p) => {
      const activo = state.pedidoActivo?.id === p.id;
      const label = p.mesa ? p.mesa : `Pedido #${p.id}`;
      return `
        <button data-id="${p.id}" class="pos-mesa-chip ${activo ? "active" : ""}">
          <span>${label}</span>
          <span class="pos-mesa-total">${formatUsd(p.total_usd)}</span>
        </button>
      `;
    })
    .join("");
  els.mesasChips.querySelectorAll(".pos-mesa-chip").forEach((btn) =>
    btn.addEventListener("click", () => seleccionarMesa(Number(btn.dataset.id))),
  );
}

function abrirNuevaMesa() {
  els.formNuevaMesa?.reset();
  actualizarModoNuevaMesa();
  els.modalNuevaMesa?.classList.remove("hidden");
}

function cerrarNuevaMesa() {
  els.modalNuevaMesa?.classList.add("hidden");
}

function actualizarModoNuevaMesa() {
  const modo =
    els.formNuevaMesa?.querySelector('input[name="modo"]:checked')?.value || "mesa";
  if (els.bloqueMesa) els.bloqueMesa.classList.toggle("hidden", modo !== "mesa");
  if (els.bloqueHabitacion)
    els.bloqueHabitacion.classList.toggle("hidden", modo !== "habitacion");
}

async function cargarHabitaciones() {
  if (!els.habitacionesList) return;
  try {
    state.habitaciones = await get("/habitaciones/");
    els.habitacionesList.innerHTML = state.habitaciones
      .filter((h) => h.estado !== "inhabilitada")
      .map(
        (h) =>
          `<option value="${h.numero}">Hab ${h.numero} · ${h.estado}</option>`,
      )
      .join("");
  } catch (error) {
    console.warn("No se pudieron cargar habitaciones", error);
  }
}

async function crearNuevaMesa(event) {
  event.preventDefault();
  const formData = new FormData(els.formNuevaMesa);
  const modo = formData.get("modo")?.toString() || "mesa";
  const mesa = formData.get("mesa")?.toString().trim() || null;
  const habitacion = formData.get("habitacion_numero")?.toString().trim() || null;

  if (modo === "habitacion") {
    if (!habitacion) {
      showToast("Indique el número de habitación", "error");
      return;
    }
    const hab = state.habitaciones.find((h) => h.numero === habitacion);
    if (!hab) {
      showToast(`Habitación ${habitacion} no existe`, "error");
      return;
    }
    if (hab.estado === "inhabilitada") {
      showToast(
        `La habitación ${habitacion} está inhabilitada y no acepta consumos`,
        "error",
      );
      return;
    }
    state.habitacionNumero = habitacion;
    state.mesaActiva = `Hab ${habitacion}`;
    state.mesaTipo = "habitacion";
  } else {
    if (!mesa) {
      showToast("Indique mesa o cliente", "error");
      return;
    }
    state.habitacionNumero = null;
    state.mesaActiva = mesa;
    state.mesaTipo = formData.get("tipo")?.toString() || "restaurante";
  }
  state.reservaId = Number(formData.get("reserva_id")) || null;
  state.pedidoActivo = null;
  state.carrito.clear();
  cerrarNuevaMesa();
  refrescarUI();
  showToast(`Cuenta "${state.mesaActiva}" abierta. Añade productos.`, "info");
}

async function seleccionarMesa(pedidoId) {
  try {
    const pedido = await get(`/pedidos/${pedidoId}`);
    state.pedidoActivo = pedido;
    state.mesaActiva =
      pedido.mesa ||
      (pedido.habitacion_numero ? `Hab ${pedido.habitacion_numero}` : `Pedido #${pedido.id}`);
    state.mesaTipo = pedido.tipo;
    state.habitacionNumero = pedido.habitacion_numero || null;
    state.reservaId = pedido.reserva_id || null;
    state.carrito.clear();
    refrescarUI();
  } catch (error) {
    showToast(`Error cargando mesa: ${error.message}`, "error");
  }
}

// --------------------------------------------------------------------------
// Carrito
// --------------------------------------------------------------------------
function agregarAlCarrito(productoId) {
  const producto = state.productos.find((p) => p.id === productoId);
  if (!producto) return;
  if (!state.mesaActiva && !state.pedidoActivo) {
    // Auto-crear una "mesa rápida" para no obligar al modal en cada venta.
    state.mesaActiva = "Barra";
    state.mesaTipo = "general";
  }
  const actual = state.carrito.get(productoId) || { producto, cantidad: 0 };
  actual.cantidad += 1;
  state.carrito.set(productoId, actual);
  enviarItems(productoId);
}

function cambiarCantidad(productoId, delta) {
  const item = state.carrito.get(productoId);
  if (!item) return;
  item.cantidad += delta;
  if (item.cantidad <= 0) {
    state.carrito.delete(productoId);
    refrescarUI();
    return;
  }
  if (delta > 0) enviarItems(productoId);
  else refrescarUI();
}

function quitarDelCarrito(productoId) {
  state.carrito.delete(productoId);
  refrescarUI();
}

function vaciarCarrito() {
  state.carrito.clear();
  refrescarUI();
}

function nuevoPedido() {
  state.carrito.clear();
  state.pedidoActivo = null;
  state.mesaActiva = null;
  state.mesaTipo = "restaurante";
  state.habitacionNumero = null;
  state.reservaId = null;
  localStorage.removeItem(STORAGE_KEY);
  refrescarUI();
  showToast("Listo para nuevo pedido", "info");
}

function totalesCarrito() {
  let totalBs = 0;
  let totalUsd = 0;
  for (const item of state.carrito.values()) {
    totalBs += Number(item.producto.precio_bs) * item.cantidad;
    totalUsd += Number(item.producto.precio_usd) * item.cantidad;
  }
  return { totalBs, totalUsd };
}

function refrescarUI() {
  renderMesasChips();
  renderCarrito();
  renderPedidoInfo();
  persistirLocal();
}

function renderPedidoInfo() {
  if (!els.pedidoTitulo) return;
  const mesa = state.mesaActiva || (state.pedidoActivo?.mesa ?? "—");
  const tipoTxt = state.mesaTipo || "—";
  els.pedidoTitulo.textContent = state.pedidoActivo
    ? `Mesa: ${mesa} · ${tipoTxt} · #${state.pedidoActivo.id}`
    : state.mesaActiva
      ? `Mesa: ${mesa} · ${tipoTxt} (nueva)`
      : "Sin mesa seleccionada";
  if (els.pedidoInfo) {
    if (state.pedidoActivo) {
      const fecha = state.pedidoActivo.fecha;
      els.pedidoInfo.textContent = fecha
        ? `Abierta a las ${formatTimeVE(fecha)} · Total registrado ${formatUsd(state.pedidoActivo.total_usd)}`
        : "";
    } else {
      els.pedidoInfo.textContent = "";
    }
  }
  if (els.btnCobrar) {
    const cobrable = Boolean(state.pedidoActivo && state.pedidoActivo.estado === "abierto");
    els.btnCobrar.disabled = !cobrable;
  }
}

function renderCarrito() {
  if (!els.carrito) return;
  // Combinamos detalles del pedido (servidor) + items locales pendientes.
  const filasServidor = [];
  if (state.pedidoActivo?.detalles?.length) {
    for (const d of state.pedidoActivo.detalles) {
      const prod = state.productos.find((p) => p.id === d.producto_id);
      const nombre = prod?.nombre || `#${d.producto_id}`;
      filasServidor.push(`
        <tr class="bg-slate-50">
          <td>${nombre} <span class="text-xs text-slate-500">(guardado)</span></td>
          <td>${formatUsd(d.precio_unit_usd)}<br><span class="text-xs text-slate-500">${formatBs(d.precio_unit_bs)}</span></td>
          <td>${Number(d.cantidad).toFixed(2)}</td>
          <td>${formatUsd(d.subtotal_usd)}<br><span class="text-xs text-slate-500">${formatBs(d.subtotal_bs)}</span></td>
          <td></td>
        </tr>
      `);
    }
  }

  const filasCarrito = [];
  for (const item of state.carrito.values()) {
    const subBs = Number(item.producto.precio_bs) * item.cantidad;
    const subUsd = Number(item.producto.precio_usd) * item.cantidad;
    filasCarrito.push(`
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

  if (!filasServidor.length && !filasCarrito.length) {
    els.carrito.innerHTML = `<tr><td colspan="5"><div class="empty-state">Carrito vacío. Toca un producto para agregarlo.</div></td></tr>`;
  } else {
    els.carrito.innerHTML = [...filasServidor, ...filasCarrito].join("");
  }

  els.carrito.querySelectorAll(".btn-mas").forEach((btn) =>
    btn.addEventListener("click", () =>
      cambiarCantidad(Number(btn.dataset.id), 1),
    ),
  );
  els.carrito.querySelectorAll(".btn-menos").forEach((btn) =>
    btn.addEventListener("click", () =>
      cambiarCantidad(Number(btn.dataset.id), -1),
    ),
  );
  els.carrito.querySelectorAll(".btn-quitar").forEach((btn) =>
    btn.addEventListener("click", () =>
      quitarDelCarrito(Number(btn.dataset.id)),
    ),
  );

  const { totalBs, totalUsd } = totalesCarrito();
  const servidorBs = Number(state.pedidoActivo?.total_bs || 0);
  const servidorUsd = Number(state.pedidoActivo?.total_usd || 0);
  if (els.totalBs) els.totalBs.textContent = formatBs(totalBs + servidorBs);
  if (els.totalUsd) els.totalUsd.textContent = formatUsd(totalUsd + servidorUsd);
}

// --------------------------------------------------------------------------
// Persistencia servidor (auto-save de items)
// --------------------------------------------------------------------------
async function enviarItems(_productoIdAgregado) {
  // Estrategia: solo flush al servidor cuando explícitamente lo pedimos.
  // Por ahora solo refrescamos UI (los items locales se mandarán al crear/agregar).
  refrescarUI();
}

async function asegurarPedidoActivo() {
  if (state.pedidoActivo?.id) {
    if (state.carrito.size > 0) {
      // Mandar los items pendientes al pedido existente.
      const payload = {
        tipo: state.pedidoActivo.tipo || state.mesaTipo,
        items: Array.from(state.carrito.values()).map((item) => ({
          producto_id: item.producto.id,
          cantidad: item.cantidad,
        })),
      };
      const pedido = await post(
        `/pedidos/${state.pedidoActivo.id}/agregar`,
        payload,
      );
      state.pedidoActivo = pedido;
      state.carrito.clear();
    }
    return state.pedidoActivo;
  }

  // Crear pedido nuevo.
  if (!state.carrito.size) {
    throw new Error("Añade productos al carrito antes de cobrar");
  }
  const payload = {
    tipo: state.mesaTipo || "restaurante",
    mesa: state.habitacionNumero ? null : state.mesaActiva || null,
    habitacion_numero: state.habitacionNumero || null,
    reserva_id: state.reservaId || null,
    items: Array.from(state.carrito.values()).map((item) => ({
      producto_id: item.producto.id,
      cantidad: item.cantidad,
    })),
  };
  const pedido = await post("/pedidos/", payload);
  state.pedidoActivo = pedido;
  state.carrito.clear();
  return pedido;
}

// --------------------------------------------------------------------------
// Reservas y cuentas para el modal de pago
// --------------------------------------------------------------------------
async function cargarReservasActivas() {
  if (!els.reservaSelect) return;
  try {
    const reservas = await get("/reservas/activas");
    els.reservaSelect.innerHTML =
      `<option value="">Sin reserva</option>` +
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

// --------------------------------------------------------------------------
// Modal de pago (CERRAR Y COBRAR)
// --------------------------------------------------------------------------
async function abrirModalPago() {
  try {
    await asegurarPedidoActivo();
  } catch (error) {
    showToast(error.message || "Error preparando el pedido", "error");
    return;
  }
  if (!state.pedidoActivo) return;
  if (els.pagoResumen) {
    const p = state.pedidoActivo;
    els.pagoResumen.innerHTML = `
      <p><strong>Pedido #${p.id}</strong> · ${p.mesa ? p.mesa : p.tipo}</p>
      <p>Total Bs: ${formatBs(p.total_bs)}</p>
      <p>Total USD: ${formatUsd(p.total_usd)}</p>
    `;
  }
  els.formPago?.reset();
  if (els.pagoTasaTipo) els.pagoTasaTipo.value = state.tasaTipo;
  actualizarInfoTasa();
  els.modalPago?.classList.remove("hidden");
  refrescarUI();
  await cargarMesasActivas();
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
    let mensaje = `Pedido #${pedido.id} cobrado (${metodo_pago})`;
    if (vueltoBs > 0 || vueltoUsd > 0) {
      mensaje += ` · Vuelto ${formatBs(vueltoBs)} / ${formatUsd(vueltoUsd)}`;
    }
    showToast(mensaje, "success");
    cerrarModalPago();
    nuevoPedido();
    await Promise.all([cargarProductos(), cargarMesasActivas(), cargarFavoritos()]);
  } catch (error) {
    showToast(`Error en pago: ${error.message}`, "error");
  }
}

// --------------------------------------------------------------------------
// localStorage
// --------------------------------------------------------------------------
function persistirLocal() {
  try {
    const snapshot = {
      mesaActiva: state.mesaActiva,
      mesaTipo: state.mesaTipo,
      habitacionNumero: state.habitacionNumero,
      reservaId: state.reservaId,
      pedidoActivoId: state.pedidoActivo?.id || null,
      carrito: Array.from(state.carrito.values()).map((item) => ({
        producto_id: item.producto.id,
        cantidad: item.cantidad,
      })),
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  } catch (_err) {
    /* localStorage no disponible: ignorar */
  }
}

function restaurarLocal() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const snap = JSON.parse(raw);
    state.mesaActiva = snap.mesaActiva || null;
    state.mesaTipo = snap.mesaTipo || "restaurante";
    state.habitacionNumero = snap.habitacionNumero || null;
    state.reservaId = snap.reservaId || null;
    // El carrito local se reconstruye cuando lleguen los productos.
    state._pendiente = snap.carrito || [];
    state._pendientePedidoId = snap.pedidoActivoId || null;
  } catch (_err) {
    /* ignorar */
  }
}

function reconstruirCarritoPendiente() {
  if (!state._pendiente?.length) return;
  for (const it of state._pendiente) {
    const prod = state.productos.find((p) => p.id === it.producto_id);
    if (prod) state.carrito.set(prod.id, { producto: prod, cantidad: it.cantidad });
  }
  state._pendiente = [];
}
