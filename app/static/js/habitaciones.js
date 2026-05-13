import {
  get,
  post,
  patch,
  put,
  showToast,
  formatBs,
  formatUsd,
  formatDate,
  formatFechaHoraVe,
} from "./api.js";

const ESTADOS = [
  "disponible",
  "ocupada",
  "reservada",
  "limpieza",
  "inhabilitada",
];

const els = {
  grid: document.getElementById("habs-grid"),
  filtro: document.getElementById("habs-filtro"),
  btnNuevo: document.getElementById("habs-btn-nuevo"),
  modal: document.getElementById("modal-habitacion"),
  form: document.getElementById("form-habitacion"),
  cancelar: document.getElementById("habs-modal-cancelar"),

  modalCheckin: document.getElementById("modal-checkin"),
  formCheckin: document.getElementById("form-checkin"),
  checkinCancelar: document.getElementById("checkin-cancelar"),
  checkinTitulo: document.getElementById("checkin-titulo"),
  checkinHabId: document.getElementById("checkin-habitacion-id"),
  checkinTarifa: document.getElementById("checkin-tarifa"),
  checkinNoches: document.getElementById("checkin-noches"),
  checkinFechaIn: null,
  checkinFechaOut: null,
  checkinTotalNoches: document.getElementById("checkin-total-noches"),
  checkinTotalUnit: document.getElementById("checkin-total-unit"),
  checkinTotalUsd: document.getElementById("checkin-total-usd"),
  checkinTasaInfo: document.getElementById("checkin-tasa-info"),

  modalCheckout: document.getElementById("modal-checkout"),
  formCheckout: document.getElementById("form-checkout"),
  checkoutCancelar: document.getElementById("checkout-cancelar"),
  checkoutResumen: document.getElementById("checkout-resumen"),
  checkoutHabId: document.getElementById("checkout-habitacion-id"),
  checkoutOpcionInput: document.getElementById("checkout-opcion-pago"),
  checkoutOpciones: document.getElementById("checkout-opciones"),
  checkoutTasaRow: document.getElementById("checkout-tasa-row"),
  checkoutTasaTipo: document.getElementById("checkout-tasa-tipo"),
  checkoutMixtoRow: document.getElementById("checkout-mixto-row"),
  checkoutMixtoUsd: document.getElementById("checkout-mixto-usd"),
  checkoutMixtoBs: document.getElementById("checkout-mixto-bs"),
  checkoutHora: document.getElementById("checkout-hora"),
  /** Preferir ``obtenerCheckoutMetodosEl()`` en runtime (evita null si el DOM aún no existía). */
  checkoutMetodos: document.querySelector("#form-checkout .checkout-metodos"),
  checkoutSubmitBtn: document.getElementById("checkout-submit-btn"),

  // Sub-formulario "pago anticipado" del check-in.
  checkinPagoDetalle: document.getElementById("checkin-pago-detalle"),
  checkinPagoMoneda: document.getElementById("checkin-pago-moneda"),
  checkinPagoUsd: document.getElementById("checkin-pago-usd"),
  checkinPagoBs: document.getElementById("checkin-pago-bs"),
  checkinPagoUsdRow: document.getElementById("checkin-pago-usd-row"),
  checkinPagoBsRow: document.getElementById("checkin-pago-bs-row"),
  checkinPagoTasaRow: document.getElementById("checkin-pago-tasa-row"),
  checkinPagoTasaTipo: document.getElementById("checkin-pago-tasa-tipo"),
  checkinPagoTasaInfo: document.getElementById("checkin-pago-tasa-info"),
  checkinSubmit: document.getElementById("checkin-submit"),

  // Editar huésped (post check-in)
  modalEditarHuesped: document.getElementById("modal-editar-huesped"),
  formEditarHuesped: document.getElementById("form-editar-huesped"),
  editarHuespedCancelar: document.getElementById("editar-huesped-cancelar"),
  editarHuespedTitulo: document.getElementById("editar-huesped-titulo"),
  editarHuespedHabId: document.getElementById("editar-huesped-habitacion-id"),

  // Cancelar check-in
  modalCancelarCheckin: document.getElementById("modal-cancelar-checkin"),
  formCancelarCheckin: document.getElementById("form-cancelar-checkin"),
  cancelarCheckinCerrar: document.getElementById("cancelar-checkin-cerrar"),
  cancelarCheckinHabId: document.getElementById("cancelar-checkin-habitacion-id"),
};

// Mapeo opción → {moneda, metodo} (espejo del backend).
const OPCIONES_PAGO = {
  efectivo_usd: { moneda: "usd", metodo: "efectivo" },
  efectivo_bs: { moneda: "bs", metodo: "efectivo" },
  transferencia_bs: { moneda: "bs", metodo: "transferencia" },
  pagomovil_bs: { moneda: "bs", metodo: "pagomovil" },
  mixto: { moneda: "mixto", metodo: "mixto" },
};

let habitaciones = [];
// Mapa habitacion_id -> reserva activa (para mostrar info del huésped en la tarjeta).
let reservasActivasPorHab = {};
let pedidosPreviewMeta = {};
/** Última respuesta de ``checkout-preview`` (confirmar sin método si saldo = 0). */
let ultimoPreviewCheckout = null;

export async function initHabitaciones() {
  if (els.filtro) els.filtro.addEventListener("change", loadHabitaciones);
  if (els.btnNuevo) els.btnNuevo.addEventListener("click", () => abrirModal());
  if (els.cancelar) els.cancelar.addEventListener("click", cerrarModal);
  if (els.form) els.form.addEventListener("submit", onSubmit);

  if (els.checkinCancelar)
    els.checkinCancelar.addEventListener("click", cerrarCheckin);
  if (els.formCheckin) {
    els.formCheckin.addEventListener("submit", confirmarCheckin);
    // Cálculo automático: cualquier cambio recotiza.
    ["change", "input"].forEach((evt) =>
      els.formCheckin.addEventListener(evt, (e) => {
        if (
          ["fecha_checkin", "fecha_checkout_estimado", "noches", "tarifa_usd"].includes(
            e.target.name,
          )
        ) {
          recalcCheckin();
        }
        if (e.target.name === "pago_anticipado") {
          actualizarVisibilidadPagoAnticipado();
          autocompletarMontoPagoAnticipado();
        }
        if (e.target.id === "checkin-pago-moneda") {
          actualizarVisibilidadPagoAnticipado();
          autocompletarMontoPagoAnticipado();
        }
        if (e.target.id === "checkin-pago-tasa-tipo") {
          autocompletarMontoPagoAnticipado();
        }
      }),
    );
  }

  if (els.checkoutCancelar)
    els.checkoutCancelar.addEventListener("click", cerrarCheckout);
  if (els.formCheckout) {
    els.formCheckout.addEventListener("submit", confirmarCheckout);
    if (els.checkoutTasaTipo)
      els.checkoutTasaTipo.addEventListener("change", recargarPreviewCheckout);
  }
  if (els.checkoutOpciones) {
    els.checkoutOpciones
      .querySelectorAll(".checkout-opcion")
      .forEach((btn) =>
        btn.addEventListener("click", () => seleccionarOpcionPago(btn)),
      );
  }
  if (els.checkoutMixtoUsd)
    els.checkoutMixtoUsd.addEventListener("input", recargarPreviewCheckout);
  if (els.checkoutHora)
    els.checkoutHora.addEventListener("change", recargarPreviewCheckout);

  if (els.editarHuespedCancelar)
    els.editarHuespedCancelar.addEventListener("click", cerrarEditarHuesped);
  if (els.formEditarHuesped)
    els.formEditarHuesped.addEventListener("submit", confirmarEditarHuesped);
  if (els.cancelarCheckinCerrar)
    els.cancelarCheckinCerrar.addEventListener("click", cerrarCancelarCheckin);
  if (els.formCancelarCheckin)
    els.formCancelarCheckin.addEventListener("submit", confirmarCancelarCheckin);

  await loadHabitaciones();
}

export async function loadHabitaciones() {
  if (!els.grid) return;
  try {
    const estado = els.filtro ? els.filtro.value : "";
    const query = estado ? `?estado=${encodeURIComponent(estado)}` : "";
    // En paralelo: habitaciones + reservas activas (para mostrar huésped en tarjeta).
    const [habs, reservas] = await Promise.all([
      get(`/habitaciones/${query}`),
      get("/reservas/activas").catch(() => []),
    ]);
    habitaciones = habs;
    reservasActivasPorHab = {};
    for (const r of reservas || []) {
      if (r && r.habitacion_id) reservasActivasPorHab[r.habitacion_id] = r;
    }
    if (!habitaciones.length) {
      els.grid.innerHTML = `<div class="empty-state">No hay habitaciones registradas.</div>`;
      return;
    }
    els.grid.innerHTML = habitaciones.map(renderHabitacion).join("");
    enlazarBotones();
  } catch (error) {
    showToast(`Error cargando habitaciones: ${error.message}`, "error");
  }
}

function renderHabitacion(h) {
  const acciones = botonesPorEstado(h);
  const huespedHtml = renderInfoHuesped(h);
  return `
    <div class="hab-card room-tile room-${h.estado}">
      <div class="flex items-center justify-between">
        <span class="hab-numero">#${h.numero}</span>
        <span class="estado-pill estado-${h.estado}">${h.estado}</span>
      </div>
      <p class="hab-precio">${formatUsd(h.precio_usd)} · ${formatBs(h.precio_bs)}</p>
      ${huespedHtml}
      ${h.notas ? `<p class="text-xs italic text-slate-500">${h.notas}</p>` : ""}
      <div class="hab-acciones">
        ${acciones}
      </div>
    </div>
  `;
}

/**
 * Devuelve el HTML con los datos del huésped (nombre, país/documento,
 * vehículo) para una habitación ocupada. Si la habitación no está ocupada
 * o no hay reserva activa devuelve cadena vacía.
 */
function renderInfoHuesped(h) {
  if (h.estado !== "ocupada") return "";
  const reserva = reservasActivasPorHab[h.id];
  if (!reserva) return "";
  const partes = [];
  const nombre = (reserva.huesped || "").trim();
  if (nombre) partes.push(`<strong>${escapeHtml(nombre)}</strong>`);
  const pais = (reserva.pais_origen || "").trim();
  const tipo = (reserva.tipo_documento || "").trim();
  if (pais || tipo) {
    const tipoTxt = tipo ? ` (${escapeHtml(tipo)})` : "";
    partes.push(`${escapeHtml(pais || "—")}${tipoTxt}`);
  }
  const modelo = (reserva.vehiculo_modelo || "").trim();
  const placa = (reserva.vehiculo_placa || "").trim();
  let vehiculo = "";
  if (modelo || placa) {
    vehiculo = `🚗 ${escapeHtml(modelo || "—")}${placa ? ` · ${escapeHtml(placa)}` : ""}`;
  }
  const linea1 = partes.length
    ? `<p class="hab-huesped text-xs text-slate-700">${partes.join(" · ")}</p>`
    : "";
  const linea2 = vehiculo
    ? `<p class="hab-vehiculo text-xs text-slate-500">${vehiculo}</p>`
    : "";
  return linea1 + linea2;
}

function escapeHtml(value) {
  if (value == null) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function botonesPorEstado(h) {
  switch (h.estado) {
    case "disponible":
      return `
        <button data-id="${h.id}" class="btn-checkin btn-accion-checkin">Check-in</button>
        <button data-id="${h.id}" data-estado="reservada" class="btn-checkin-resv btn-cambiar-estado">Marcar reservada</button>
      `;
    case "ocupada":
      return `
        <button data-id="${h.id}" class="btn-checkout btn-accion-checkout">Check-out</button>
        <button data-id="${h.id}" class="btn-editar-huesped btn-accion-editar">✏️ Editar huésped</button>
        <button data-id="${h.id}" class="btn-cancelar-checkin btn-accion-cancelar-checkin">🚫 Cancelar check-in</button>
      `;
    case "reservada":
      return `
        <button data-id="${h.id}" class="btn-checkin-resv btn-accion-checkin">Check-in</button>
        <button data-id="${h.id}" data-estado="disponible" class="btn-cancelar btn-cambiar-estado">Cancelar reserva</button>
      `;
    case "limpieza":
      return `
        <button data-id="${h.id}" data-estado="disponible" class="btn-limpieza-ok btn-cambiar-estado">Marcar disponible</button>
      `;
    case "inhabilitada":
      return `
        <button data-id="${h.id}" data-estado="disponible" class="btn-habilitar btn-cambiar-estado">Habilitar</button>
      `;
    default:
      return ESTADOS.map(
        (estado) =>
          `<button data-id="${h.id}" data-estado="${estado}" class="btn-cambiar-estado text-xs px-2 py-1 rounded border bg-white">${estado}</button>`,
      ).join("");
  }
}

function enlazarBotones() {
  els.grid.querySelectorAll(".btn-cambiar-estado").forEach((btn) =>
    btn.addEventListener("click", () =>
      cambiarEstado(btn.dataset.id, btn.dataset.estado),
    ),
  );
  els.grid.querySelectorAll(".btn-accion-checkin").forEach((btn) =>
    btn.addEventListener("click", () => abrirCheckin(Number(btn.dataset.id))),
  );
  els.grid.querySelectorAll(".btn-accion-checkout").forEach((btn) =>
    btn.addEventListener("click", () => abrirCheckout(Number(btn.dataset.id))),
  );
  els.grid.querySelectorAll(".btn-accion-editar").forEach((btn) =>
    btn.addEventListener("click", () =>
      abrirEditarHuesped(Number(btn.dataset.id)),
    ),
  );
  els.grid.querySelectorAll(".btn-accion-cancelar-checkin").forEach((btn) =>
    btn.addEventListener("click", () =>
      cancelarCheckinHabitacion(Number(btn.dataset.id)),
    ),
  );
}

async function cambiarEstado(id, estado) {
  try {
    await put(`/habitaciones/${id}/estado`, { estado });
    showToast(`Habitación #${id} → ${estado}`, "success");
    await loadHabitaciones();
  } catch (error) {
    showToast(`Error cambiando estado: ${error.message}`, "error");
  }
}

// ---------------------------------------------------------------------------
// Modal crear habitación (existente)
// ---------------------------------------------------------------------------
function abrirModal() {
  if (!els.modal) return;
  els.form?.reset();
  els.modal.classList.remove("hidden");
}

function cerrarModal() {
  els.modal?.classList.add("hidden");
}

async function onSubmit(event) {
  event.preventDefault();
  const formData = new FormData(els.form);
  const payload = {
    numero: formData.get("numero")?.toString().trim(),
    tipo: formData.get("tipo")?.toString() || "standard",
    precio_bs: Number(formData.get("precio_bs") || 0),
    precio_usd: Number(formData.get("precio_usd") || 0),
    estado: formData.get("estado") || "disponible",
    notas: formData.get("notas")?.toString() || null,
  };
  if (!payload.numero) {
    showToast("Indique el número de habitación", "error");
    return;
  }
  try {
    await post("/habitaciones/", payload);
    showToast("Habitación creada", "success");
    cerrarModal();
    await loadHabitaciones();
  } catch (error) {
    showToast(`Error creando habitación: ${error.message}`, "error");
  }
}

// ---------------------------------------------------------------------------
// Check-in
// ---------------------------------------------------------------------------
/**
 * Abre el modal de check-in.
 * @param {number} habId - id de la habitación.
 * @param {{reserva?: object, habitaciones?: object[]}} [opts]
 */
export function abrirCheckin(habId, opts = {}) {
  if (Array.isArray(opts.habitaciones) && opts.habitaciones.length) {
    habitaciones = opts.habitaciones;
  }
  const h = habitaciones.find((x) => x.id === habId);
  if (!h) return;
  if (!els.modalCheckin) return;
  els.formCheckin?.reset();
  const reserva = opts.reserva || null;
  const reservaInput = document.getElementById("checkin-reserva-id");
  if (reservaInput) reservaInput.value = reserva?.id || "";
  if (els.checkinHabId) els.checkinHabId.value = h.id;
  if (els.checkinTitulo) {
    els.checkinTitulo.textContent = reserva
      ? `Check-in de reserva #${reserva.id} · habitación #${h.numero}`
      : `Check-in habitación #${h.numero}`;
  }
  if (els.checkinTarifa)
    els.checkinTarifa.value = reserva?.tarifa_usd
      ? Number(reserva.tarifa_usd) / Math.max(1, reserva.noches || 1)
      : h.precio_usd;
  if (els.checkinNoches) els.checkinNoches.value = reserva?.noches || 1;
  // Por defecto, hoy → mañana (o lo que dijera la reserva).
  const hoy = new Date();
  const hoyIso = hoy.toISOString().slice(0, 10);
  const mananaIso = new Date(hoy.getTime() + 86400000)
    .toISOString()
    .slice(0, 10);
  const inputIn = els.formCheckin.querySelector('input[name="fecha_checkin"]');
  const inputOut = els.formCheckin.querySelector(
    'input[name="fecha_checkout_estimado"]',
  );
  if (inputIn) inputIn.value = reserva?.fecha_checkin || hoyIso;
  if (inputOut) inputOut.value = reserva?.fecha_checkout_estimado || mananaIso;
  // Pre-cargar datos del huésped.
  if (reserva) {
    const setVal = (name, v) => {
      const el = els.formCheckin.querySelector(`[name="${name}"]`);
      if (el && v != null) el.value = v;
    };
    setVal("huesped", reserva.huesped);
    setVal("documento", reserva.documento);
    setVal("telefono", reserva.telefono);
    setVal("pais_origen", reserva.pais_origen);
    setVal("numero_documento", reserva.numero_documento);
    setVal("vehiculo_modelo", reserva.vehiculo_modelo);
    setVal("vehiculo_color", reserva.vehiculo_color);
    setVal("vehiculo_placa", reserva.vehiculo_placa);
    setVal("hora_ingreso", reserva.hora_ingreso);
    const tipo = reserva.tipo_documento || "N";
    const tipoRadio = els.formCheckin.querySelector(
      `input[name="tipo_documento"][value="${tipo}"]`,
    );
    if (tipoRadio) tipoRadio.checked = true;
  }
  // Reseteamos el sub-bloque de pago anticipado (oculto por defecto).
  const radio = els.formCheckin?.querySelector(
    'input[name="pago_anticipado"][value="0"]',
  );
  if (radio) radio.checked = true;
  if (els.checkinPagoUsd) els.checkinPagoUsd.value = 0;
  if (els.checkinPagoBs) els.checkinPagoBs.value = 0;
  if (els.checkinPagoMoneda) els.checkinPagoMoneda.value = "usd";
  if (els.checkinPagoTasaTipo) els.checkinPagoTasaTipo.value = "bcv";
  actualizarVisibilidadPagoAnticipado();
  els.modalCheckin.classList.remove("hidden");
  // Cargamos las tasas actuales en paralelo para autocompletar Bs cuando aplique.
  cargarTasasCheckin().then(autocompletarMontoPagoAnticipado);
  recalcCheckin();
}

function diferenciaNoches(fechaIn, fechaOut) {
  if (!fechaIn || !fechaOut) return null;
  const d1 = new Date(fechaIn);
  const d2 = new Date(fechaOut);
  if (Number.isNaN(d1.getTime()) || Number.isNaN(d2.getTime())) return null;
  const diff = Math.round((d2 - d1) / 86400000);
  return diff > 0 ? diff : null;
}

let recalcTimer = null;
// Estado de cotización actual (lo usamos para autocompletar montos en Bs).
let cotizacionCheckin = {
  total_usd: 0,
  total_bs: 0,
  precio_unit_usd: 0,
  tasa_aplicada: 0,
  tasa_tipo: "bcv",
};
// Tasas conocidas (consultadas a /tasa/actual) usadas al cambiar BCV/Paralelo
// en el sub-formulario de pago anticipado.
let tasasCheckin = { bcv: 0, paralelo: 0 };

async function recalcCheckin() {
  if (!els.formCheckin || !els.checkinHabId) return;
  const habId = Number(els.checkinHabId.value);
  if (!habId) return;
  const fd = new FormData(els.formCheckin);
  const fechaIn = fd.get("fecha_checkin")?.toString() || "";
  const fechaOut = fd.get("fecha_checkout_estimado")?.toString() || "";
  const nochesPorFecha = diferenciaNoches(fechaIn, fechaOut);
  if (nochesPorFecha && els.checkinNoches) {
    els.checkinNoches.value = nochesPorFecha;
  }
  const noches = Math.max(1, Number(els.checkinNoches?.value || 1));
  const tarifa = Number(els.checkinTarifa?.value || 0) || null;

  if (recalcTimer) clearTimeout(recalcTimer);
  recalcTimer = setTimeout(async () => {
    try {
      const params = new URLSearchParams({ noches: String(noches) });
      if (tarifa) params.set("tarifa_usd", String(tarifa));
      const url = `/habitaciones/${habId}/checkin-cotizacion?${params}`;
      const cot = await get(url);
      cotizacionCheckin = {
        total_usd: Number(cot.total_usd || 0),
        total_bs: Number(cot.total_bs || 0),
        precio_unit_usd: Number(cot.precio_unit_usd || 0),
        tasa_aplicada: Number(cot.tasa_aplicada || 0),
        tasa_tipo: cot.tasa_tipo || "bcv",
      };
      if (els.checkinTotalNoches)
        els.checkinTotalNoches.textContent = cot.noches;
      if (els.checkinTotalUnit)
        els.checkinTotalUnit.textContent = formatUsd(cot.precio_unit_usd);
      if (els.checkinTotalUsd)
        els.checkinTotalUsd.textContent = formatUsd(cot.total_usd);
      if (els.checkinTasaInfo) {
        els.checkinTasaInfo.textContent = "La tasa se elige al cobrar.";
      }
      autocompletarMontoPagoAnticipado();
    } catch (error) {
      if (els.checkinTasaInfo)
        els.checkinTasaInfo.textContent = `Error: ${error.message}`;
    }
  }, 150);
}

async function cargarTasasCheckin() {
  try {
    const data = await get("/tasa/actual");
    tasasCheckin = {
      bcv: Number(data?.bcv ?? data?.tasa_bcv ?? 0),
      paralelo: Number(data?.paralelo ?? data?.tasa_paralelo ?? 0),
    };
  } catch (error) {
    // Si no se puede cargar, dejamos los valores en 0 y mostramos un mensaje.
    tasasCheckin = { bcv: 0, paralelo: 0 };
  }
}

/**
 * Cuando se elige "Pagar ahora" + moneda Bs, autocompleta el campo
 * "Monto Bs" con el total de la estadía convertido usando la tasa
 * seleccionada (BCV o Paralelo). Si el usuario ya escribió un valor
 * diferente al total convertido previo, se respeta su edición manual.
 */
function autocompletarMontoPagoAnticipado() {
  if (!pagoAnticipadoActivo()) return;
  const moneda = els.checkinPagoMoneda?.value || "usd";
  if (moneda !== "bs") return;
  const tipo = els.checkinPagoTasaTipo?.value || "bcv";
  const tasa = Number(tasasCheckin[tipo] || cotizacionCheckin.tasa_aplicada || 0);
  const totalUsd = Number(cotizacionCheckin.total_usd || 0);
  const totalBs = Number((totalUsd * tasa).toFixed(2));
  if (els.checkinPagoBs) {
    els.checkinPagoBs.value = totalBs;
  }
  if (els.checkinPagoTasaInfo) {
    els.checkinPagoTasaInfo.textContent = tasa
      ? `${tipo.toUpperCase()} ${tasa.toFixed(2)} Bs/USD · Total: ${formatBs(totalBs)}`
      : "Tasa no disponible";
  }
}

function cerrarCheckin() {
  els.modalCheckin?.classList.add("hidden");
}

function pagoAnticipadoActivo() {
  const radio = els.formCheckin?.querySelector(
    'input[name="pago_anticipado"]:checked',
  );
  return radio?.value === "1";
}

function actualizarVisibilidadPagoAnticipado() {
  const activo = pagoAnticipadoActivo();
  if (els.checkinPagoDetalle) {
    els.checkinPagoDetalle.classList.toggle("hidden", !activo);
  }
  if (els.checkinSubmit) {
    els.checkinSubmit.textContent = activo
      ? "Check-in y pagar"
      : "Solo check-in";
  }
  // Mostrar input USD vs Bs según moneda seleccionada.
  const moneda = els.checkinPagoMoneda?.value || "usd";
  if (els.checkinPagoUsdRow)
    els.checkinPagoUsdRow.classList.toggle("hidden", moneda !== "usd");
  if (els.checkinPagoBsRow)
    els.checkinPagoBsRow.classList.toggle("hidden", moneda !== "bs");
  // El selector de tasa SOLO aparece cuando se paga ahora en Bs.
  if (els.checkinPagoTasaRow) {
    const mostrarTasa = activo && moneda === "bs";
    els.checkinPagoTasaRow.classList.toggle("hidden", !mostrarTasa);
  }
}

async function confirmarCheckin(event) {
  event.preventDefault();
  const formData = new FormData(els.formCheckin);
  const habId = Number(formData.get("habitacion_id"));
  const reservaIdRaw = formData.get("reserva_id");
  const reservaId = reservaIdRaw ? Number(reservaIdRaw) : null;
  const pagoAnticipado = pagoAnticipadoActivo();
  const payload = {
    huesped: formData.get("huesped")?.toString().trim(),
    documento: formData.get("documento")?.toString() || null,
    telefono: formData.get("telefono")?.toString() || null,
    fecha_checkin: formData.get("fecha_checkin") || null,
    fecha_checkout_estimado: formData.get("fecha_checkout_estimado") || null,
    noches: Number(formData.get("noches") || 1),
    tarifa_usd: Number(formData.get("tarifa_usd") || 0) || null,
    notas: formData.get("notas")?.toString() || null,
    vehiculo_modelo: formData.get("vehiculo_modelo")?.toString().trim() || null,
    vehiculo_color: formData.get("vehiculo_color")?.toString().trim() || null,
    vehiculo_placa: formData.get("vehiculo_placa")?.toString().trim() || null,
    hora_ingreso: formData.get("hora_ingreso")?.toString() || null,
    pais_origen: formData.get("pais_origen")?.toString().trim() || null,
    tipo_documento: formData.get("tipo_documento")?.toString() || null,
    numero_documento:
      formData.get("numero_documento")?.toString().trim() || null,
    pago_anticipado: pagoAnticipado,
    reserva_id: reservaId,
  };
  if (pagoAnticipado) {
    payload.moneda_pago = formData.get("moneda_pago") || "usd";
    payload.metodo_pago = formData.get("metodo_pago") || "efectivo";
    payload.monto_recibido_usd = Number(formData.get("monto_recibido_usd") || 0);
    payload.monto_recibido_bs = Number(formData.get("monto_recibido_bs") || 0);
    // La tasa solo aplica si se pagó en Bs; si no, fallback a BCV.
    payload.tasa_tipo = els.checkinPagoTasaTipo?.value || "bcv";
  }
  if (!payload.huesped) {
    showToast("Indique el nombre del huésped", "error");
    return;
  }
  try {
    const reserva = await post(`/habitaciones/${habId}/checkin`, payload);
    let mensaje = `Check-in OK · ${reserva.huesped} (reserva #${reserva.id})`;
    if (reserva.estado_pago === "pagado") {
      mensaje += " · 💰 estadía pagada por adelantado";
    } else if (reserva.estado_pago === "parcial") {
      mensaje += " · pago parcial registrado";
    }
    showToast(mensaje, "success");
    cerrarCheckin();
    await loadHabitaciones();
    // Permite que otras pestañas (ej. reservas) se enteren y refresquen.
    document.dispatchEvent(
      new CustomEvent("checkin:confirmado", { detail: { reserva } }),
    );
  } catch (error) {
    showToast(`Error en check-in: ${error.message}`, "error");
  }
}

// ---------------------------------------------------------------------------
// Check-out
// ---------------------------------------------------------------------------
function numSaldoCheckout(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

/** True si no hay nada que cobrar (API: ``saldo_pendiente_*`` o ``pendiente_*``). */
function checkoutSinSaldoPendiente(p) {
  if (!p) return false;
  const u = numSaldoCheckout(
    p.saldo_pendiente_usd != null ? p.saldo_pendiente_usd : p.pendiente_usd,
  );
  const b = numSaldoCheckout(
    p.saldo_pendiente_bs != null ? p.saldo_pendiente_bs : p.pendiente_bs,
  );
  return u <= 0 && b <= 0;
}

function obtenerCheckoutMetodosEl() {
  return (
    els.formCheckout?.querySelector(".checkout-metodos") ||
    document.querySelector("#modal-checkout .checkout-metodos") ||
    document.querySelector(".checkout-metodos")
  );
}

function obtenerCheckoutSubmitBtn() {
  return (
    document.getElementById("checkout-submit-btn") ||
    els.formCheckout?.querySelector('button[type="submit"]')
  );
}

/**
 * Oculta/muestra métodos de pago y el texto del botón según saldo del preview.
 * Usa ``hidden`` nativo + ``display`` + clase Tailwind por compatibilidad.
 */
function aplicarCheckoutMetodosUI(preview) {
  const wrap = obtenerCheckoutMetodosEl();
  const btn = obtenerCheckoutSubmitBtn();
  const sinSaldo = preview ? checkoutSinSaldoPendiente(preview) : false;

  if (wrap) {
    if (!preview) {
      wrap.removeAttribute("hidden");
      wrap.style.removeProperty("display");
      wrap.classList.remove("hidden");
    } else if (sinSaldo) {
      wrap.setAttribute("hidden", "");
      wrap.style.display = "none";
      wrap.classList.add("hidden");
    } else {
      wrap.removeAttribute("hidden");
      wrap.style.removeProperty("display");
      wrap.classList.remove("hidden");
    }
  }

  if (btn) {
    if (!preview) {
      btn.textContent = "Cobrar y cerrar";
    } else {
      btn.textContent = sinSaldo ? "Confirmar salida" : "Cobrar y cerrar";
    }
  }
}

async function abrirCheckout(habId) {
  if (!els.modalCheckout) return;
  els.formCheckout?.reset();
  ultimoPreviewCheckout = null;
  aplicarCheckoutMetodosUI(null);
  if (els.checkoutHabId) els.checkoutHabId.value = habId;
  // Hora de salida estándar (cambio manual permitido).
  if (els.checkoutHora) els.checkoutHora.value = "13:00";
  // Reseteamos al estado inicial: Efectivo USD.
  seleccionarOpcionPagoPorClave("efectivo_usd");
  if (els.checkoutResumen) {
    els.checkoutResumen.innerHTML = `<p class="text-sm text-slate-500">Calculando total…</p>`;
  }
  els.modalCheckout.classList.remove("hidden");
  await recargarPreviewCheckout();
}

function opcionActual() {
  const clave = els.checkoutOpcionInput?.value || "efectivo_usd";
  return { clave, ...(OPCIONES_PAGO[clave] || OPCIONES_PAGO.efectivo_usd) };
}

function seleccionarOpcionPagoPorClave(clave) {
  const btn = els.checkoutOpciones?.querySelector(
    `.checkout-opcion[data-opcion="${clave}"]`,
  );
  if (btn) seleccionarOpcionPago(btn);
}

function seleccionarOpcionPago(btn) {
  if (!btn || !els.checkoutOpciones) return;
  els.checkoutOpciones
    .querySelectorAll(".checkout-opcion")
    .forEach((b) => b.classList.remove("activa"));
  btn.classList.add("activa");

  const clave = btn.dataset.opcion;
  const moneda = btn.dataset.moneda;
  if (els.checkoutOpcionInput) els.checkoutOpcionInput.value = clave;

  // Tasa visible cuando aplica Bs (incluye mixto).
  if (els.checkoutTasaRow) {
    els.checkoutTasaRow.classList.toggle(
      "hidden",
      !(moneda === "bs" || moneda === "mixto"),
    );
  }
  // Inputs mixto sólo cuando moneda === mixto.
  if (els.checkoutMixtoRow) {
    els.checkoutMixtoRow.classList.toggle("hidden", moneda !== "mixto");
  }
  recargarPreviewCheckout();
}

async function recargarPreviewCheckout() {
  const habId = Number(els.checkoutHabId?.value);
  if (!habId) return;
  const { moneda } = opcionActual();
  const tasaTipo = els.checkoutTasaTipo?.value || "bcv";
  const horaSalida = els.checkoutHora?.value || "13:00";
  try {
    const params = new URLSearchParams({
      tasa_tipo: tasaTipo,
      hora_salida: horaSalida,
    });
    const preview = await get(
      `/habitaciones/${habId}/checkout-preview?${params}`,
    );
    ultimoPreviewCheckout = preview;
    pedidosPreviewMeta = await cargarPedidosPreviewMeta(preview.pedidos || []);
    if (els.checkoutResumen) {
      els.checkoutResumen.innerHTML = renderPreview(preview, moneda);
    }
    aplicarCheckoutMetodosUI(preview);
    if (moneda === "mixto" && els.checkoutMixtoUsd && els.checkoutMixtoBs) {
      const recibidoUsd = Number(els.checkoutMixtoUsd.value || 0);
      const objetivoUsd = Number(
        preview.saldo_pendiente_usd ?? preview.pendiente_usd ?? preview.total_usd ?? 0,
      );
      const faltanteUsd = Math.max(0, objetivoUsd - recibidoUsd);
      els.checkoutMixtoBs.value = (
        faltanteUsd * Number(preview.tasa_aplicada || 0)
      ).toFixed(2);
    }
  } catch (error) {
    ultimoPreviewCheckout = null;
    aplicarCheckoutMetodosUI(null);
    if (els.checkoutResumen) {
      els.checkoutResumen.innerHTML = `<p class="text-sm text-red-600">${error.message}</p>`;
    }
  }
}

async function cargarPedidosPreviewMeta(ids = []) {
  const unicos = [...new Set((ids || []).map((x) => Number(x)).filter(Boolean))];
  if (!unicos.length) return {};
  const resultados = await Promise.all(
    unicos.map(async (id) => {
      try {
        const p = await get(`/pedidos/${id}`);
        const cuenta = p?.mesa
          ? `Mesa ${p.mesa}`
          : p?.habitacion_numero
            ? `Hab ${p.habitacion_numero}`
            : "General";
        return [id, `Pedido #${id} - ${cuenta}`];
      } catch (_error) {
        return [id, `Pedido #${id}`];
      }
    }),
  );
  return Object.fromEntries(resultados);
}

function renderPreview(p, moneda = "usd") {
  const pedidos = p.pedidos?.length
    ? `<p class="text-xs text-slate-500">Consumos asociados: ${p.pedidos
        .map((id) => pedidosPreviewMeta[id] || `Pedido #${id}`)
        .join(", ")}</p>`
    : "";
  const pendienteUsd = Number(p.saldo_pendiente_usd ?? p.pendiente_usd ?? p.total_usd ?? 0);
  const pendienteBs = Number(p.saldo_pendiente_bs ?? p.pendiente_bs ?? p.total_bs ?? 0);
  const sinSaldo = checkoutSinSaldoPendiente(p);
  let totalDestacado;
  if (sinSaldo) {
    totalDestacado = `<p class="text-emerald-700 font-medium">✅ El huésped pagó el total por adelantado. No hay saldo pendiente.</p>`;
  } else if (moneda === "bs") {
    totalDestacado = `<strong>Saldo a cobrar: ${formatBs(pendienteBs)}</strong>
      <p class="text-xs text-slate-500">Tasa ${p.tasa_tipo?.toUpperCase()}: ${Number(p.tasa_aplicada || 0).toFixed(2)} Bs/USD · equivalente ${formatUsd(pendienteUsd)}</p>`;
  } else if (moneda === "mixto") {
    totalDestacado = `<strong>Saldo a cobrar: ${formatUsd(pendienteUsd)} · ${formatBs(pendienteBs)}</strong>
      <p class="text-xs text-slate-500">Ingrese USD recibidos; el resto se cobra en Bs (tasa ${p.tasa_tipo?.toUpperCase()}: ${Number(p.tasa_aplicada || 0).toFixed(2)})</p>`;
  } else {
    totalDestacado = `<strong>Saldo a cobrar: ${formatUsd(pendienteUsd)}</strong>
      <p class="text-xs text-slate-500">Sin tasa (efectivo en dólares)</p>`;
  }
  const extras =
    Number(p.horas_extra || 0) > 0
      ? `<li class="text-amber-700">⏰ Late check-out: ${p.horas_extra} h × $5
           = ${formatUsd(p.recarga_extra_usd)}${moneda !== "usd" ? ` · ${formatBs(p.recarga_extra_bs)}` : ""}
           <span class="text-xs text-slate-500">(salida ${p.hora_salida || ""}, estándar ${p.hora_salida_estandar || "13:00"})</span>
         </li>`
      : `<li class="text-xs text-slate-500">Salida ${p.hora_salida || p.hora_salida_estandar || "13:00"} · sin recargo</li>`;

  const abonadoUsd = Number(p.pagado_por_adelantado_usd ?? p.pagado_parcial_usd ?? 0);
  const abonadoBs = Number(p.pagado_por_adelantado_bs ?? p.pagado_parcial_bs ?? 0);
  const abono =
    abonadoUsd > 0 || abonadoBs > 0
      ? `<li class="text-emerald-700">💰 Pagado por adelantado:
            ${abonadoUsd > 0 ? formatUsd(abonadoUsd) : ""}
            ${abonadoUsd > 0 && abonadoBs > 0 ? " · " : ""}
            ${abonadoBs > 0 ? formatBs(abonadoBs) : ""}
         </li>`
      : "";

  const html = `
    <p><strong>Habitación #${p.numero}</strong>${p.huesped ? ` · ${p.huesped}` : ""}</p>
    <ul class="text-sm space-y-1 mt-2">
      <li>Estadía (${p.noches} noche${p.noches === 1 ? "" : "s"}): ${formatUsd(p.tarifa_usd)}${moneda !== "usd" ? ` · ${formatBs(p.tarifa_bs)}` : ""}</li>
      <li>Consumos: ${formatUsd(p.consumos_usd)}${moneda !== "usd" ? ` · ${formatBs(p.consumos_bs)}` : ""}</li>
      ${extras}
      ${abono}
      <li class="text-xs text-slate-500">Total estadía: ${formatUsd(p.total_usd)}${moneda !== "usd" ? ` · ${formatBs(p.total_bs)}` : ""}</li>
      <li class="border-t pt-1">${totalDestacado}</li>
    </ul>
    ${pedidos}
  `;
  // Tras pintar el resumen, alinear botones de pago con el saldo (por si el contenedor no se resolvió antes).
  queueMicrotask(() => aplicarCheckoutMetodosUI(p));
  return html;
}

function cerrarCheckout() {
  els.modalCheckout?.classList.add("hidden");
}

async function confirmarCheckout(event) {
  event.preventDefault();
  const formData = new FormData(els.formCheckout);
  const habId = Number(formData.get("habitacion_id"));
  const { clave, moneda } = opcionActual();
  const sinSaldo = checkoutSinSaldoPendiente(ultimoPreviewCheckout);

  const payload = {
    tasa_tipo:
      moneda === "bs" || moneda === "mixto"
        ? formData.get("tasa_tipo") || "bcv"
        : "bcv",
    cuenta_banco_id: Number(formData.get("cuenta_banco_id")) || null,
    notas: formData.get("notas")?.toString() || null,
    hora_salida: formData.get("hora_salida")?.toString() || "13:00",
  };
  if (!sinSaldo) {
    payload.opcion_pago = clave;
    if (moneda === "mixto") {
      payload.monto_recibido_usd = Number(formData.get("monto_recibido_usd") || 0);
      payload.monto_recibido_bs = Number(formData.get("monto_recibido_bs") || 0);
    }
  }
  try {
    const resp = await post(`/habitaciones/${habId}/checkout`, payload);
    let msg;
    if (sinSaldo) {
      msg = "Salida confirmada · Sin cobro adicional (total pagado por adelantado)";
    } else if (moneda === "usd") {
      msg = `Check-out OK · Cobrado ${formatUsd(resp.total_usd)} en USD`;
    } else if (moneda === "bs") {
      msg = `Check-out OK · Cobrado ${formatBs(resp.total_bs)} (tasa ${resp.tasa_tipo?.toUpperCase()})`;
    } else {
      msg = `Check-out OK · Mixto: ${formatUsd(resp.total_usd)} + ${formatBs(resp.total_bs)}`;
    }
    showToast(msg, "success");
    cerrarCheckout();
    await loadHabitaciones();
  } catch (error) {
    showToast(`Error en check-out: ${error.message}`, "error");
  }
}

// ---------------------------------------------------------------------------
// Editar huésped (post check-in)
// ---------------------------------------------------------------------------
function setFormValue(form, name, value) {
  if (!form) return;
  const el = form.querySelector(`[name="${name}"]`);
  if (!el) return;
  if (el.type === "radio") {
    const radio = form.querySelector(`[name="${name}"][value="${value}"]`);
    if (radio) radio.checked = true;
  } else if (value != null) {
    el.value = value;
  } else {
    el.value = "";
  }
}

async function abrirEditarHuesped(habId) {
  const h = habitaciones.find((x) => x.id === habId);
  if (!h) {
    showToast("Habitación no encontrada", "error");
    return;
  }
  if (h.estado !== "ocupada") {
    showToast("La habitación no está ocupada", "info");
    return;
  }
  let reserva = null;
  try {
    const reservas = await get("/reservas/activas");
    reserva = (reservas || []).find((r) => r.habitacion_id === habId) || null;
  } catch (error) {
    showToast(`No se pudo cargar la reserva: ${error.message}`, "error");
    return;
  }
  if (!reserva) {
    showToast("No hay reserva activa asociada a la habitación", "error");
    return;
  }
  if (!els.modalEditarHuesped || !els.formEditarHuesped) return;
  els.formEditarHuesped.reset();
  if (els.editarHuespedHabId) els.editarHuespedHabId.value = String(habId);
  if (els.editarHuespedTitulo) {
    els.editarHuespedTitulo.textContent = `Editar huésped · Hab #${h.numero}`;
  }
  const form = els.formEditarHuesped;
  setFormValue(form, "huesped", reserva.huesped);
  setFormValue(form, "documento", reserva.documento);
  setFormValue(form, "telefono", reserva.telefono);
  setFormValue(form, "pais_origen", reserva.pais_origen);
  setFormValue(form, "tipo_documento", reserva.tipo_documento || "N");
  setFormValue(form, "numero_documento", reserva.numero_documento);
  setFormValue(form, "vehiculo_modelo", reserva.vehiculo_modelo);
  setFormValue(form, "vehiculo_color", reserva.vehiculo_color);
  setFormValue(form, "vehiculo_placa", reserva.vehiculo_placa);
  setFormValue(form, "fecha_checkin", reserva.fecha_checkin);
  setFormValue(form, "hora_ingreso", reserva.hora_ingreso);
  setFormValue(form, "fecha_checkout_estimado", reserva.fecha_checkout_estimado);
  setFormValue(form, "hora_salida", reserva.hora_salida);
  els.modalEditarHuesped.classList.remove("hidden");
}

function cerrarEditarHuesped() {
  els.modalEditarHuesped?.classList.add("hidden");
}

async function confirmarEditarHuesped(event) {
  event.preventDefault();
  if (!els.formEditarHuesped || !els.editarHuespedHabId) return;
  const habId = Number(els.editarHuespedHabId.value);
  if (!habId) return;
  const fd = new FormData(els.formEditarHuesped);
  const payload = {};
  for (const [key, value] of fd.entries()) {
    if (key === "habitacion_id") continue;
    const txt = value?.toString().trim() ?? "";
    if (txt) payload[key] = txt;
  }
  if (!payload.huesped) {
    showToast("El nombre es obligatorio", "error");
    return;
  }
  try {
    await put(`/habitaciones/${habId}/huesped`, payload);
    showToast("Datos del huésped actualizados", "success");
    cerrarEditarHuesped();
    await loadHabitaciones();
  } catch (error) {
    showToast(`Error guardando huésped: ${error.message}`, "error");
  }
}

// ---------------------------------------------------------------------------
// Cancelar check-in (admin)
// ---------------------------------------------------------------------------
function cancelarCheckinHabitacion(habId) {
  const h = habitaciones.find((x) => x.id === habId);
  if (!h) return;
  if (h.estado !== "ocupada") {
    showToast("La habitación no está ocupada", "info");
    return;
  }
  if (!els.modalCancelarCheckin || !els.formCancelarCheckin) return;
  els.formCancelarCheckin.reset();
  if (els.cancelarCheckinHabId) els.cancelarCheckinHabId.value = String(habId);
  els.modalCancelarCheckin.classList.remove("hidden");
}

function cerrarCancelarCheckin() {
  els.modalCancelarCheckin?.classList.add("hidden");
}

async function confirmarCancelarCheckin(event) {
  event.preventDefault();
  if (!els.formCancelarCheckin || !els.cancelarCheckinHabId) return;
  const habId = Number(els.cancelarCheckinHabId.value);
  if (!habId) return;
  const fd = new FormData(els.formCancelarCheckin);
  const motivo = (fd.get("motivo") || "").toString().trim();
  if (!motivo) {
    showToast("Indique un motivo", "error");
    return;
  }
  const eliminar = fd.get("eliminar_consumos") === "1";
  if (eliminar && !confirm(
    "¿Eliminar TODOS los consumos abiertos? Se devolverá el stock. Esta acción no se puede deshacer.",
  )) {
    return;
  }
  try {
    const resp = await post(`/habitaciones/${habId}/cancelar-checkin`, {
      eliminar_consumos: eliminar,
      motivo,
    });
    showToast(
      `Check-in cancelado. Consumos ${eliminar ? "eliminados" : "preservados"} (${resp.consumos_cancelados || resp.consumos_abiertos_restantes || 0}).`,
      "success",
    );
    cerrarCancelarCheckin();
    await loadHabitaciones();
  } catch (error) {
    showToast(`Error cancelando check-in: ${error.message}`, "error");
  }
}
