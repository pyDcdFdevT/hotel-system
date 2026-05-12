import {
  get,
  post,
  put,
  del as deleteApi,
  showToast,
  formatBs,
  formatUsd,
  formatRate,
  formatTimeVE,
  nowVE,
} from "./api.js";
import { getCacheTasas, refreshHeaderTasas } from "./config.js";

const STORAGE_KEY = "hotel-pos-state-v2";

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
  favoritos: [],         // favoritos REALES del usuario (POST/DELETE)
  favoritosIds: new Set(), // ids de los favoritos REALES (no incluye fallback)
  favoritosFallback: [], // sugerencias (top-vendidos) cuando no hay favoritos
  carrito: new Map(),
  pedidoActivo: null,
  mesaActiva: null,
  mesaTipo: "restaurante",
  habitacionNumero: null,
  reservaId: null,
  cuentasPendientes: [],
  habitaciones: [],
  tasas: { bcv: 405.35, paralelo: 415.0 },
  tasaTipo: "bcv",
};

// Restaurar ids favoritos del localStorage (para que el catálogo no parpadee
// al cargar antes de que llegue la respuesta del backend).
try {
  const cache = JSON.parse(localStorage.getItem("hotel-pos-favoritos-ids") || "[]");
  if (Array.isArray(cache)) state.favoritosIds = new Set(cache);
} catch (_) {
  /* localStorage no disponible */
}

const els = {
  busqueda: document.getElementById("pos-busqueda"),
  favoritos: document.getElementById("pos-favoritos"),
  categorias: document.getElementById("pos-categorias"),
  cuentasLista: document.getElementById("pos-cuentas-lista"),
  cuentasCount: document.getElementById("pos-cuentas-count"),
  btnNuevaMesa: document.getElementById("pos-btn-nueva-mesa"),
  btnNuevaHabitacion: document.getElementById("pos-btn-nueva-habitacion"),
  btnCancelarCuenta: document.getElementById("pos-btn-cancelar-cuenta"),
  btnAparcar: document.getElementById("pos-btn-aparcar"),
  banner: document.getElementById("pos-banner"),
  bannerText: document.getElementById("pos-banner-text"),
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
  modalNuevaMesa: document.getElementById("modal-nueva-mesa"),
  formNuevaMesa: document.getElementById("form-nueva-mesa"),
  nuevaMesaCancelar: document.getElementById("nueva-mesa-cancelar"),
  nuevaMesaInput: document.getElementById("nueva-mesa-input"),
  nuevaMesaHint: document.getElementById("nueva-mesa-hint"),

  modalNuevaHabitacion: document.getElementById("modal-nueva-habitacion"),
  formNuevaHabitacion: document.getElementById("form-nueva-habitacion"),
  nuevaHabitacionCancelar: document.getElementById("nueva-habitacion-cancelar"),
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

let cuentasRefreshTimer = null;
let favRefreshTimer = null;
let horaTimer = null;

export async function initPedidos() {
  if (els.busqueda) els.busqueda.addEventListener("input", renderCatalogo);
  if (els.btnNuevaMesa)
    els.btnNuevaMesa.addEventListener("click", abrirNuevaMesa);
  if (els.btnNuevaHabitacion)
    els.btnNuevaHabitacion.addEventListener("click", abrirNuevaHabitacion);
  if (els.btnCancelarCuenta)
    els.btnCancelarCuenta.addEventListener("click", cancelarCuentaActiva);
  if (els.btnAparcar) els.btnAparcar.addEventListener("click", aparcarCuenta);
  if (els.nuevaMesaCancelar)
    els.nuevaMesaCancelar.addEventListener("click", cerrarNuevaMesa);
  if (els.formNuevaMesa)
    els.formNuevaMesa.addEventListener("submit", crearNuevaMesa);
  if (els.nuevaHabitacionCancelar)
    els.nuevaHabitacionCancelar.addEventListener("click", cerrarNuevaHabitacion);
  if (els.formNuevaHabitacion)
    els.formNuevaHabitacion.addEventListener("submit", crearNuevaHabitacion);
  if (els.btnRefrescarFavs) els.btnRefrescarFavs.addEventListener("click", cargarFavoritos);
  if (els.btnVaciar) els.btnVaciar.addEventListener("click", vaciarCarrito);
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

  await Promise.all([
    cargarTasas(),
    cargarProductos(),
    cargarFavoritos(),
    cargarReservasActivas(),
    cargarCuentas(),
    cargarCuentasPendientes(),
    cargarHabitaciones(),
  ]);

  if (favRefreshTimer) clearInterval(favRefreshTimer);
  favRefreshTimer = setInterval(cargarFavoritos, 5 * 60 * 1000);

  if (cuentasRefreshTimer) clearInterval(cuentasRefreshTimer);
  cuentasRefreshTimer = setInterval(cargarCuentasPendientes, 30 * 1000);

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

/**
 * Carga los favoritos del usuario actual.
 *
 * Distingue dos listas:
 *  - ``state.favoritos`` / ``state.favoritosIds``: los favoritos REALES del
 *    usuario (los que ha marcado con ⭐). Sólo estos pueden quitarse.
 *  - ``state.favoritosFallback``: sugerencias (top vendidos) que se muestran
 *    SÓLO cuando el usuario aún no ha marcado ninguno. No cuentan como
 *    favoritos reales (no se incluyen en ``favoritosIds``), por lo que el
 *    catálogo sigue mostrando el botón "＋⭐" para esos productos.
 */
async function cargarFavoritos() {
  if (!els.favoritos) return;
  try {
    const propios = await get("/productos/favoritos/mis-favoritos");
    if (Array.isArray(propios) && propios.length) {
      state.favoritos = propios;
      state.favoritosIds = new Set(propios.map((p) => p.id));
      state.favoritosFallback = [];
    } else {
      // Aún no hay favoritos reales: cargamos sugerencias para no dejar la
      // sección vacía, pero NO las contamos como favoritos del usuario.
      state.favoritos = [];
      state.favoritosIds = new Set();
      try {
        const top = await get("/productos/favoritos?limit=10");
        state.favoritosFallback = Array.isArray(top) ? top : [];
      } catch (_) {
        state.favoritosFallback = [];
      }
    }
    persistirFavoritosLocal();
    renderFavoritos();
    renderCatalogo();
  } catch (error) {
    console.warn("Favoritos no disponibles", error);
  }
}

/**
 * Guarda los ids de favoritos REALES en ``localStorage`` para que la UI no
 * "parpadee" al recargar (los botones ⭐ ya salen en estado correcto antes
 * de que el backend responda).
 */
function persistirFavoritosLocal() {
  try {
    localStorage.setItem(
      "hotel-pos-favoritos-ids",
      JSON.stringify([...state.favoritosIds]),
    );
  } catch (_) {
    /* localStorage puede fallar en modo privado */
  }
}

function renderFavoritos() {
  if (!els.favoritos) return;

  // Caso 1: el usuario tiene favoritos reales → mostrar con botón "✖ quitar".
  if (state.favoritos.length) {
    els.favoritos.innerHTML = state.favoritos
      .map((p) => productoButtonHtml(p, "favorito"))
      .join("");
    enlazarBotonesFavoritos(els.favoritos);
    return;
  }

  // Caso 2: vacío + hay sugerencias → mostrarlas con botón "＋⭐ agregar".
  if (state.favoritosFallback.length) {
    els.favoritos.innerHTML = `
      <p class="text-xs text-slate-500 mb-2">
        Sugerencias del top vendidos · marca tus propios favoritos con ⭐
      </p>
      ${state.favoritosFallback.map((p) => productoButtonHtml(p, "catalogo")).join("")}
    `;
    enlazarBotonesFavoritos(els.favoritos);
    return;
  }

  // Caso 3: nada que mostrar.
  els.favoritos.innerHTML = `<div class="empty-state">Aún no hay productos favoritos. Marca uno con ⭐ desde el catálogo.</div>`;
}

/**
 * Enlaza los listeners de los botones de productos dentro de ``contenedor``:
 *  - Click principal en la tarjeta → agregar al carrito.
 *  - Click en ``.btn-agregar-fav`` → agregar al backend + state local.
 *  - Click en ``.btn-quitar-fav``  → quitar del backend + state local.
 */
function enlazarBotonesFavoritos(contenedor) {
  contenedor.querySelectorAll(".pos-prod-btn").forEach((btn) =>
    btn.addEventListener("click", (ev) => {
      if (ev.target?.closest?.(".pos-fav-toggle")) return;
      agregarAlCarrito(Number(btn.dataset.id));
    }),
  );
  contenedor.querySelectorAll(".btn-quitar-fav").forEach((btn) =>
    btn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      ev.preventDefault();
      await quitarDeFavoritos(Number(btn.dataset.id));
    }),
  );
  contenedor.querySelectorAll(".btn-agregar-fav").forEach((btn) =>
    btn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      ev.preventDefault();
      await agregarAFavoritos(Number(btn.dataset.id));
    }),
  );
}

/**
 * Agrega un producto a los favoritos del usuario actual.
 *
 * Estrategia: actualiza inmediatamente el estado local en vez de re-pedir
 * la lista al backend, así evitamos race conditions donde un fallback de
 * top-vendidos termine "tapando" la edición del usuario.
 */
async function agregarAFavoritos(productoId) {
  if (state.favoritosIds.has(productoId)) return; // idempotente local

  try {
    const producto = await post("/productos/favoritos", {
      producto_id: productoId,
    });
    // El backend devuelve el producto completo (idempotente). Si falla, lanzará.
    const prod =
      producto && typeof producto === "object" && producto.id
        ? producto
        : state.productos.find((p) => p.id === productoId);
    if (!prod) {
      // No deberíamos llegar aquí, pero por seguridad refrescamos.
      await cargarFavoritos();
      return;
    }

    state.favoritos = [
      ...state.favoritos.filter((p) => p.id !== prod.id),
      prod,
    ];
    state.favoritosIds.add(prod.id);
    // Si estaba en la lista de sugerencias, la removemos para no duplicar.
    state.favoritosFallback = state.favoritosFallback.filter(
      (p) => p.id !== prod.id,
    );

    persistirFavoritosLocal();
    renderFavoritos();
    renderCatalogo();
    showToast(`⭐ ${prod.nombre} agregado a favoritos`, "success");
  } catch (error) {
    showToast(`Error agregando favorito: ${error.message}`, "error");
  }
}

/**
 * Quita un producto de los favoritos del usuario actual.
 *
 * - Mutamos ``state.favoritos`` / ``state.favoritosIds`` localmente.
 * - Si el usuario se queda sin favoritos reales, recargamos las sugerencias
 *   (top-vendidos) para no dejar la sección vacía, pero seguimos sin
 *   contarlas como favoritos del usuario.
 */
async function quitarDeFavoritos(productoId) {
  // Snapshot por si el backend falla y debemos restaurar.
  const snapshot = {
    favs: [...state.favoritos],
    ids: new Set(state.favoritosIds),
  };

  try {
    await deleteApi(`/productos/favoritos/${productoId}`);

    const removido =
      state.favoritos.find((p) => p.id === productoId) ||
      state.productos.find((p) => p.id === productoId);

    state.favoritos = state.favoritos.filter((p) => p.id !== productoId);
    state.favoritosIds.delete(productoId);
    persistirFavoritosLocal();

    // Si quedó vacía, traemos sugerencias para que el panel no se quede en
    // blanco, pero NO las agregamos a ``favoritosIds``.
    if (state.favoritos.length === 0) {
      try {
        const top = await get("/productos/favoritos?limit=10");
        state.favoritosFallback = Array.isArray(top)
          ? top.filter((p) => p.id !== productoId)
          : [];
      } catch (_) {
        state.favoritosFallback = [];
      }
    }

    renderFavoritos();
    renderCatalogo();
    showToast(
      removido
        ? `${removido.nombre} quitado de favoritos`
        : "Producto quitado de favoritos",
      "info",
    );
  } catch (error) {
    state.favoritos = snapshot.favs;
    state.favoritosIds = snapshot.ids;
    persistirFavoritosLocal();
    renderFavoritos();
    renderCatalogo();
    showToast(`Error quitando favorito: ${error.message}`, "error");
  }
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
          ${productos.map((p) => productoButtonHtml(p, "catalogo")).join("")}
        </div>
      </details>
    `);
  }
  els.categorias.innerHTML =
    partes.join("") ||
    `<div class="empty-state">Sin productos para "${filtro}"</div>`;

  // Reusa el mismo cableado que el panel de favoritos: click principal → al
  // carrito; click en ＋⭐ / ✖ → toggle de favorito (con stopPropagation).
  enlazarBotonesFavoritos(els.categorias);
}

/**
 * Renderiza un botón de producto.
 *
 * @param {object} p - producto
 * @param {"favorito"|"catalogo"} contexto
 *   - ``"favorito"``: el producto se está renderizando dentro del panel de
 *     favoritos REALES del usuario. Muestra el botón ``✖`` para quitarlo.
 *   - ``"catalogo"``: el producto está en el catálogo (o sugerencias). Si
 *     todavía no está en los favoritos del usuario, muestra ``＋⭐``.
 *
 * El estado "es favorito real" se determina por ``state.favoritosIds``,
 * que NO incluye las sugerencias / top-vendidos.
 */
function productoButtonHtml(p, contexto = "catalogo") {
  const badge = p.porcion ? `<span class="pos-prod-badge">${p.porcion}</span>` : "";
  const esFavoritoReal = state.favoritosIds.has(p.id);
  const star = esFavoritoReal || contexto === "favorito" ? "⭐ " : "";

  let accionFav = "";
  if (contexto === "favorito") {
    // Panel de favoritos reales → permitir quitar.
    accionFav = `<button class="btn-quitar-fav pos-fav-toggle" data-id="${p.id}" title="Quitar de favoritos" type="button" aria-label="Quitar de favoritos">✖</button>`;
  } else if (!esFavoritoReal) {
    // Catálogo / sugerencias → permitir agregar (sólo si aún no es favorito).
    accionFav = `<button class="btn-agregar-fav pos-fav-toggle" data-id="${p.id}" title="Agregar a favoritos" type="button" aria-label="Agregar a favoritos">＋⭐</button>`;
  }

  return `
    <button data-id="${p.id}" class="pos-prod-btn" type="button">
      ${badge}
      <span class="pos-prod-name">${star}${escapeHtmlPos(p.nombre)}</span>
      <span class="pos-prod-price">${formatUsd(p.precio_usd)} · ${formatBs(p.precio_bs)}</span>
      ${accionFav}
    </button>
  `;
}

function escapeHtmlPos(v) {
  if (v == null) return "";
  return String(v)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// --------------------------------------------------------------------------
// Cuentas pendientes (panel izquierdo)
// --------------------------------------------------------------------------
async function cargarCuentasPendientes() {
  if (!els.cuentasLista) return;
  try {
    state.cuentasPendientes = await get("/pedidos/activos");
    renderCuentasPendientes();
  } catch (error) {
    showToast(`Error cargando cuentas: ${error.message}`, "error");
  }
}

function renderCuentasPendientes() {
  if (!els.cuentasLista) return;
  const cuentas = state.cuentasPendientes || [];
  if (els.cuentasCount) {
    els.cuentasCount.textContent = cuentas.length
      ? `${cuentas.length} abierta${cuentas.length === 1 ? "" : "s"}`
      : "";
  }
  if (!cuentas.length) {
    els.cuentasLista.innerHTML = `<p class="empty-state text-xs">Sin cuentas abiertas. Crea una mesa o cuenta para empezar.</p>`;
    return;
  }
  els.cuentasLista.innerHTML = cuentas
    .map((p) => {
      const activo = state.pedidoActivo?.id === p.id;
      const etiqueta = p.mesa
        ? p.mesa
        : p.habitacion_numero
          ? `🏨 Hab ${p.habitacion_numero}`
          : `Pedido #${p.id}`;
      const ultima = p.ultima_actividad || p.fecha;
      const hora = ultima ? formatTimeVE(ultima) : "";
      const icono = activo ? "🟢" : "⚪";
      return `
        <button data-id="${p.id}" type="button" class="pos-cuenta-card ${activo ? "active" : ""}">
          <div class="pos-cuenta-info">
            <strong>${icono} ${etiqueta}</strong>
            <span class="pos-cuenta-meta">#${p.id} · ${hora || ""}</span>
          </div>
          <span class="pos-cuenta-total">${formatUsd(p.total_usd)}</span>
        </button>
      `;
    })
    .join("");
  els.cuentasLista.querySelectorAll(".pos-cuenta-card").forEach((btn) =>
    btn.addEventListener("click", () => seleccionarMesa(Number(btn.dataset.id))),
  );
}

function abrirNuevaMesa() {
  els.formNuevaMesa?.reset();
  actualizarHintNuevaMesa("");
  els.modalNuevaMesa?.classList.remove("hidden");
  // Foco automático en el único campo del modal.
  setTimeout(() => els.nuevaMesaInput?.focus(), 50);
}

function abrirNuevaHabitacion() {
  els.formNuevaHabitacion?.reset();
  els.modalNuevaHabitacion?.classList.remove("hidden");
  setTimeout(() => els.inputHabitacion?.focus(), 50);
}

/**
 * Devuelve true si ya existe una cuenta activa (estado "abierto") con el
 * mismo nombre normalizado (lower-case, trim). Se usa para evitar el ida
 * y vuelta al backend cuando es obvio que es duplicado.
 */
function existeMesaDuplicada(nombre) {
  if (!nombre) return false;
  const norm = nombre.trim().toLowerCase();
  return (state.cuentasPendientes || []).some(
    (c) =>
      (c.mesa || "").trim().toLowerCase() === norm &&
      c.estado === "abierto",
  );
}

function existeHabitacionDuplicada(numero) {
  if (!numero) return false;
  return (state.cuentasPendientes || []).some(
    (c) =>
      (c.habitacion_numero || "").trim() === numero.trim() &&
      c.estado === "abierto",
  );
}

function actualizarHintNuevaMesa(mensaje, esError = false) {
  if (!els.nuevaMesaHint) return;
  if (!mensaje) {
    els.nuevaMesaHint.textContent =
      "El nombre debe ser único entre las cuentas activas.";
    els.nuevaMesaHint.classList.remove("text-red-600");
    els.nuevaMesaHint.classList.add("text-slate-500");
    return;
  }
  els.nuevaMesaHint.textContent = mensaje;
  els.nuevaMesaHint.classList.toggle("text-red-600", esError);
  els.nuevaMesaHint.classList.toggle("text-slate-500", !esError);
}

function hayCuentaActiva() {
  return Boolean(state.pedidoActivo?.id || state.mesaActiva);
}

async function cancelarCuentaActiva() {
  if (!hayCuentaActiva()) return;
  const etiqueta =
    state.mesaActiva ||
    (state.pedidoActivo ? `Pedido #${state.pedidoActivo.id}` : "esta cuenta");
  if (!confirm(`¿Cancelar ${etiqueta} sin cobrar? Se devolverá el stock y no se puede deshacer.`)) {
    return;
  }
  try {
    if (state.pedidoActivo?.id) {
      await deleteApi(`/pedidos/${state.pedidoActivo.id}/cancelar`);
      showToast(`Cuenta ${etiqueta} cancelada`, "info");
    } else {
      showToast(`Cuenta ${etiqueta} descartada (no estaba guardada)`, "info");
    }
  } catch (error) {
    showToast(`Error cancelando: ${error.message}`, "error");
    return;
  }
  resetearEstadoCuenta();
  await Promise.all([cargarCuentasPendientes(), cargarProductos()]);
}

async function aparcarCuenta() {
  if (!state.pedidoActivo && state.carrito.size === 0 && !state.mesaActiva) {
    showToast("No hay nada para aparcar", "info");
    return;
  }
  try {
    // Si todavía no hay pedido en servidor, lo creamos primero con los items
    // que estén en el carrito local.
    if (!state.pedidoActivo?.id) {
      if (state.carrito.size === 0) {
        showToast("Añade productos antes de aparcar la cuenta", "info");
        return;
      }
      await asegurarPedidoActivo();
    } else if (state.carrito.size > 0) {
      // Hay nuevos items locales: los enviamos antes de aparcar.
      await asegurarPedidoActivo();
    }
    if (state.pedidoActivo?.id) {
      await post(`/pedidos/${state.pedidoActivo.id}/aparcar`, {});
      showToast(`Cuenta #${state.pedidoActivo.id} aparcada`, "info");
    }
    resetearEstadoCuenta();
    await cargarCuentasPendientes();
  } catch (error) {
    showToast(`Error aparcando: ${error.message}`, "error");
  }
}

function resetearEstadoCuenta() {
  state.carrito.clear();
  state.pedidoActivo = null;
  state.mesaActiva = null;
  state.mesaTipo = "restaurante";
  state.habitacionNumero = null;
  state.reservaId = null;
  localStorage.removeItem(STORAGE_KEY);
  refrescarUI();
}

function cerrarNuevaMesa() {
  els.modalNuevaMesa?.classList.add("hidden");
}

function cerrarNuevaHabitacion() {
  els.modalNuevaHabitacion?.classList.add("hidden");
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

/**
 * Crea una cuenta "mesa / cliente" simplificada.
 *
 * Validación: nombre único entre las cuentas activas. La verificación
 * primaria es local (rápida) pero el backend también rechaza duplicados
 * con 400 (defensa en profundidad).
 */
async function crearNuevaMesa(event) {
  event.preventDefault();
  const formData = new FormData(els.formNuevaMesa);
  const mesa = formData.get("mesa")?.toString().trim() || "";
  if (!mesa) {
    actualizarHintNuevaMesa("Indique el nombre de la mesa o cliente", true);
    return;
  }
  // Refrescamos la lista de pendientes para hacer la validación con datos
  // frescos (otra sesión puede haber creado la mesa entretanto).
  try {
    await cargarCuentasPendientes();
  } catch (_) {
    /* si falla, seguimos: el backend hará la última validación */
  }
  if (existeMesaDuplicada(mesa)) {
    actualizarHintNuevaMesa(
      `Ya existe una cuenta activa llamada "${mesa}". Elige otro nombre.`,
      true,
    );
    return;
  }

  state.habitacionNumero = null;
  state.mesaActiva = mesa;
  state.mesaTipo = "restaurante";
  state.reservaId = null;
  state.pedidoActivo = null;
  state.carrito.clear();
  cerrarNuevaMesa();
  refrescarUI();
  showToast(`Cuenta "${mesa}" abierta. Añade productos.`, "info");
}

/**
 * Crea una cuenta asociada a una habitación. Se mantiene como flujo
 * independiente: usa el número de habitación como identificador único.
 */
async function crearNuevaHabitacion(event) {
  event.preventDefault();
  const formData = new FormData(els.formNuevaHabitacion);
  const habitacion = formData.get("habitacion_numero")?.toString().trim() || "";
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
  try {
    await cargarCuentasPendientes();
  } catch (_) {
    /* si falla seguimos: el backend valida también */
  }
  if (existeHabitacionDuplicada(habitacion)) {
    showToast(
      `Ya existe una cuenta activa para la habitación ${habitacion}`,
      "error",
    );
    return;
  }

  state.habitacionNumero = habitacion;
  state.mesaActiva = `Hab ${habitacion}`;
  state.mesaTipo = "habitacion";
  state.reservaId = null;
  state.pedidoActivo = null;
  state.carrito.clear();
  cerrarNuevaHabitacion();
  refrescarUI();
  showToast(`Cuenta "${state.mesaActiva}" abierta. Añade productos.`, "info");
}

async function seleccionarMesa(pedidoId) {
  try {
    // Si hay un carrito local sin guardar, lo aparcamos antes de cambiar.
    if (state.pedidoActivo?.id && state.carrito.size > 0) {
      await asegurarPedidoActivo();
    }
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
    showToast(`Error cargando cuenta: ${error.message}`, "error");
  }
}

// --------------------------------------------------------------------------
// Carrito
// --------------------------------------------------------------------------
function agregarAlCarrito(productoId) {
  const producto = state.productos.find((p) => p.id === productoId);
  if (!producto) return;
  if (!hayCuentaActiva()) {
    showToast("Primero crea una nueva mesa o selecciona una cuenta pendiente", "info");
    return;
  }
  const actual = state.carrito.get(productoId) || { producto, cantidad: 0 };
  actual.cantidad += 1;
  state.carrito.set(productoId, actual);
  refrescarUI();
}

function cambiarCantidad(productoId, delta) {
  const item = state.carrito.get(productoId);
  if (!item) return;
  item.cantidad += delta;
  if (item.cantidad <= 0) {
    state.carrito.delete(productoId);
  }
  refrescarUI();
}

function quitarDelCarrito(productoId) {
  state.carrito.delete(productoId);
  refrescarUI();
}

function vaciarCarrito() {
  state.carrito.clear();
  refrescarUI();
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
  renderCuentasPendientes();
  renderCarrito();
  renderPedidoInfo();
  persistirLocal();
}

function renderPedidoInfo() {
  if (!els.pedidoTitulo) return;
  const mesa = state.mesaActiva || (state.pedidoActivo?.mesa ?? "—");
  els.pedidoTitulo.textContent = hayCuentaActiva()
    ? `🟢 Cuenta activa: ${mesa}`
    : "⚫ Sin cuenta activa";
  if (els.pedidoInfo) {
    if (state.pedidoActivo) {
      const fecha = state.pedidoActivo.fecha;
      els.pedidoInfo.textContent = fecha
        ? `Pedido #${state.pedidoActivo.id} · Abierta a las ${formatTimeVE(fecha)}`
        : `Pedido #${state.pedidoActivo.id}`;
    } else if (state.mesaActiva) {
      els.pedidoInfo.textContent = "Cuenta nueva (aún sin guardar)";
    } else {
      els.pedidoInfo.textContent = "";
    }
  }
  const totales = totalesCarrito();
  const totalGuardado = Number(state.pedidoActivo?.total_usd || 0);
  const hayProductos =
    state.carrito.size > 0 ||
    totales.totalUsd > 0 ||
    totalGuardado > 0 ||
    (state.pedidoActivo?.detalles?.length ?? 0) > 0;
  const cuenta = hayCuentaActiva();
  if (els.btnCobrar) els.btnCobrar.disabled = !(cuenta && hayProductos);
  if (els.btnAparcar) els.btnAparcar.disabled = !(cuenta && hayProductos);
  actualizarBannerCuenta();
}

function actualizarBannerCuenta() {
  if (!els.banner || !els.bannerText) return;
  if (hayCuentaActiva()) {
    const etiqueta =
      state.mesaActiva ||
      (state.habitacionNumero
        ? `Hab ${state.habitacionNumero}`
        : `Pedido #${state.pedidoActivo?.id}`);
    const desde = state.pedidoActivo?.fecha
      ? ` · abierta ${formatTimeVE(state.pedidoActivo.fecha)}`
      : " · sin guardar";
    els.bannerText.textContent = `🟢 Cuenta activa: ${etiqueta}${desde}`;
    els.banner.classList.remove("pos-banner-inactive");
    els.banner.classList.add("pos-banner-active");
    if (els.btnCancelarCuenta) els.btnCancelarCuenta.classList.remove("hidden");
  } else {
    els.bannerText.textContent =
      "⚫ Ninguna cuenta activa. Crea una mesa o cuenta para comenzar.";
    els.banner.classList.add("pos-banner-inactive");
    els.banner.classList.remove("pos-banner-active");
    if (els.btnCancelarCuenta) els.btnCancelarCuenta.classList.add("hidden");
  }
}

/**
 * Iconos por estado del detalle. Se muestran junto al nombre en el carrito
 * para que el mesero sepa qué ítems puede entregar.
 */
const ESTADO_DETALLE_ICONO = {
  pendiente: "⏳",
  en_preparacion: "🔪",
  listo: "✅",
  entregado: "✅✅",
};
const ESTADO_DETALLE_LABEL = {
  pendiente: "Pendiente",
  en_preparacion: "En preparación",
  listo: "Listo",
  entregado: "Entregado",
};

function renderCarrito() {
  if (!els.carrito) return;
  const filasServidor = [];
  if (state.pedidoActivo?.detalles?.length) {
    for (const d of state.pedidoActivo.detalles) {
      const prod = state.productos.find((p) => p.id === d.producto_id);
      const nombre = prod?.nombre || `#${d.producto_id}`;
      const estado = d.estado || "pendiente";
      const icono = ESTADO_DETALLE_ICONO[estado] || "⏳";
      const label = ESTADO_DETALLE_LABEL[estado] || estado;
      const accion =
        estado === "listo"
          ? `<button class="btn-entregar text-xs text-emerald-700 underline" data-detalle-id="${d.id}" title="Marcar como entregado al cliente">Entregar</button>`
          : estado === "entregado"
            ? `<span class="text-xs text-slate-400">Entregado</span>`
            : "";
      filasServidor.push(`
        <tr class="bg-slate-50">
          <td>
            ${escapeHtmlPos(nombre)}
            <span class="text-xs text-slate-500" title="${label}">${icono} ${label}</span>
          </td>
          <td>${formatUsd(d.precio_unit_usd)}<br><span class="text-xs text-slate-500">${formatBs(d.precio_unit_bs)}</span></td>
          <td>${Number(d.cantidad).toFixed(2)}</td>
          <td>${formatUsd(d.subtotal_usd)}<br><span class="text-xs text-slate-500">${formatBs(d.subtotal_bs)}</span></td>
          <td>${accion}</td>
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
  els.carrito.querySelectorAll(".btn-entregar").forEach((btn) =>
    btn.addEventListener("click", () =>
      marcarDetalleEntregado(Number(btn.dataset.detalleId)),
    ),
  );

  const { totalBs, totalUsd } = totalesCarrito();
  const servidorBs = Number(state.pedidoActivo?.total_bs || 0);
  const servidorUsd = Number(state.pedidoActivo?.total_usd || 0);
  if (els.totalBs) els.totalBs.textContent = formatBs(totalBs + servidorBs);
  if (els.totalUsd) els.totalUsd.textContent = formatUsd(totalUsd + servidorUsd);
}

/**
 * Marca un detalle del pedido activo como ``entregado``.
 *
 * Permisos backend: admin, mesero, recepcion. La cocina marca "listo";
 * quien entrega al cliente cierra el ciclo aquí.
 */
async function marcarDetalleEntregado(detalleId) {
  if (!state.pedidoActivo?.id) return;
  try {
    const detalleActualizado = await put(
      `/pedidos/${state.pedidoActivo.id}/detalles/${detalleId}/estado`,
      { estado: "entregado" },
    );
    // Refrescamos sólo el detalle correspondiente en el pedido activo.
    const lista = state.pedidoActivo.detalles || [];
    const idx = lista.findIndex((x) => x.id === detalleId);
    if (idx >= 0) lista[idx] = { ...lista[idx], ...detalleActualizado };
    showToast("Producto marcado como entregado ✅", "success");
    refrescarUI();
  } catch (error) {
    showToast(`Error marcando entregado: ${error.message}`, "error");
  }
}

// --------------------------------------------------------------------------
// Persistencia servidor (auto-save de items)
// --------------------------------------------------------------------------
async function asegurarPedidoActivo() {
  if (state.pedidoActivo?.id) {
    if (state.carrito.size > 0) {
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
// Modal de pago (Cobrar)
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
  await cargarCuentasPendientes();
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
    resetearEstadoCuenta();
    await Promise.all([
      cargarProductos(),
      cargarCuentasPendientes(),
      cargarFavoritos(),
    ]);
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

// Exportado para que `put` no se reporte como import sin uso si el compilador
// es estricto; lo usaremos en el endpoint de items cuando se requiera.
export { put };
