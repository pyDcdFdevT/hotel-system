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
  checkinTasaTipo: document.getElementById("checkin-tasa-tipo"),
  checkinTotalNoches: document.getElementById("checkin-total-noches"),
  checkinTotalUnit: document.getElementById("checkin-total-unit"),
  checkinTotalUsd: document.getElementById("checkin-total-usd"),
  checkinTotalBs: document.getElementById("checkin-total-bs"),
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

  // Sub-formulario "pago anticipado" del check-in.
  checkinPagoDetalle: document.getElementById("checkin-pago-detalle"),
  checkinPagoMoneda: document.getElementById("checkin-pago-moneda"),
  checkinPagoUsd: document.getElementById("checkin-pago-usd"),
  checkinPagoBs: document.getElementById("checkin-pago-bs"),
  checkinPagoUsdRow: document.getElementById("checkin-pago-usd-row"),
  checkinPagoBsRow: document.getElementById("checkin-pago-bs-row"),
  checkinSubmit: document.getElementById("checkin-submit"),
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
          ) ||
          e.target.id === "checkin-tasa-tipo"
        ) {
          recalcCheckin();
        }
        if (e.target.name === "pago_anticipado") {
          actualizarVisibilidadPagoAnticipado();
        }
        if (e.target.id === "checkin-pago-moneda") {
          actualizarVisibilidadPagoAnticipado();
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

  await loadHabitaciones();
}

export async function loadHabitaciones() {
  if (!els.grid) return;
  try {
    const estado = els.filtro ? els.filtro.value : "";
    const query = estado ? `?estado=${encodeURIComponent(estado)}` : "";
    habitaciones = await get(`/habitaciones/${query}`);
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
  return `
    <div class="hab-card room-tile room-${h.estado}">
      <div class="flex items-center justify-between">
        <span class="hab-numero">#${h.numero}</span>
        <span class="estado-pill estado-${h.estado}">${h.estado}</span>
      </div>
      <p class="hab-precio">${formatUsd(h.precio_usd)} · ${formatBs(h.precio_bs)}</p>
      ${h.notas ? `<p class="text-xs italic text-slate-500">${h.notas}</p>` : ""}
      <div class="hab-acciones">
        ${acciones}
      </div>
    </div>
  `;
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
  actualizarVisibilidadPagoAnticipado();
  els.modalCheckin.classList.remove("hidden");
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
async function recalcCheckin() {
  if (!els.formCheckin || !els.checkinHabId) return;
  const habId = Number(els.checkinHabId.value);
  if (!habId) return;
  const fd = new FormData(els.formCheckin);
  const fechaIn = fd.get("fecha_checkin")?.toString() || "";
  const fechaOut = fd.get("fecha_checkout_estimado")?.toString() || "";
  // Si hay ambas fechas y se cambió alguna, sincronizamos `noches`.
  const nochesPorFecha = diferenciaNoches(fechaIn, fechaOut);
  if (nochesPorFecha && els.checkinNoches) {
    els.checkinNoches.value = nochesPorFecha;
  }
  const noches = Math.max(1, Number(els.checkinNoches?.value || 1));
  const tarifa = Number(els.checkinTarifa?.value || 0) || null;
  const tasaTipo = els.checkinTasaTipo?.value || "bcv";

  // Debounce simple para no inundar el backend mientras se tipea.
  if (recalcTimer) clearTimeout(recalcTimer);
  recalcTimer = setTimeout(async () => {
    try {
      const params = new URLSearchParams({
        noches: String(noches),
        tasa_tipo: tasaTipo,
      });
      if (tarifa) params.set("tarifa_usd", String(tarifa));
      const url = `/habitaciones/${habId}/checkin-cotizacion?${params}`;
      const cot = await get(url);
      if (els.checkinTotalNoches)
        els.checkinTotalNoches.textContent = cot.noches;
      if (els.checkinTotalUnit)
        els.checkinTotalUnit.textContent = formatUsd(cot.precio_unit_usd);
      if (els.checkinTotalUsd)
        els.checkinTotalUsd.textContent = formatUsd(cot.total_usd);
      if (els.checkinTotalBs)
        els.checkinTotalBs.textContent = formatBs(cot.total_bs);
      if (els.checkinTasaInfo)
        els.checkinTasaInfo.textContent = `Tasa ${cot.tasa_tipo.toUpperCase()}: ${Number(cot.tasa_aplicada).toFixed(2)} Bs/USD`;
    } catch (error) {
      if (els.checkinTasaInfo)
        els.checkinTasaInfo.textContent = `Error: ${error.message}`;
    }
  }, 150);
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
    payload.tasa_tipo = els.checkinTasaTipo?.value || "bcv";
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
async function abrirCheckout(habId) {
  if (!els.modalCheckout) return;
  els.formCheckout?.reset();
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
    if (els.checkoutResumen) {
      els.checkoutResumen.innerHTML = renderPreview(preview, moneda);
    }
    if (moneda === "mixto" && els.checkoutMixtoUsd && els.checkoutMixtoBs) {
      const recibidoUsd = Number(els.checkoutMixtoUsd.value || 0);
      const objetivoUsd = Number(preview.pendiente_usd ?? preview.total_usd ?? 0);
      const faltanteUsd = Math.max(0, objetivoUsd - recibidoUsd);
      els.checkoutMixtoBs.value = (
        faltanteUsd * Number(preview.tasa_aplicada || 0)
      ).toFixed(2);
    }
  } catch (error) {
    if (els.checkoutResumen) {
      els.checkoutResumen.innerHTML = `<p class="text-sm text-red-600">${error.message}</p>`;
    }
  }
}

function renderPreview(p, moneda = "usd") {
  const pedidos = p.pedidos?.length
    ? `<p class="text-xs text-slate-500">Pedidos asociados: ${p.pedidos.map((id) => `#${id}`).join(", ")}</p>`
    : "";
  const pendienteUsd = Number(p.pendiente_usd ?? p.total_usd ?? 0);
  const pendienteBs = Number(p.pendiente_bs ?? p.total_bs ?? 0);
  let totalDestacado;
  if (moneda === "bs") {
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

  const abonadoUsd = Number(p.pagado_parcial_usd || 0);
  const abonadoBs = Number(p.pagado_parcial_bs || 0);
  const abono =
    abonadoUsd > 0 || abonadoBs > 0
      ? `<li class="text-emerald-700">💰 Pagado por adelantado:
            ${abonadoUsd > 0 ? formatUsd(abonadoUsd) : ""}
            ${abonadoUsd > 0 && abonadoBs > 0 ? " · " : ""}
            ${abonadoBs > 0 ? formatBs(abonadoBs) : ""}
         </li>`
      : "";

  return `
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
}

function cerrarCheckout() {
  els.modalCheckout?.classList.add("hidden");
}

async function confirmarCheckout(event) {
  event.preventDefault();
  const formData = new FormData(els.formCheckout);
  const habId = Number(formData.get("habitacion_id"));
  const { clave, moneda } = opcionActual();

  const payload = {
    opcion_pago: clave,
    tasa_tipo:
      moneda === "bs" || moneda === "mixto"
        ? formData.get("tasa_tipo") || "bcv"
        : "bcv",
    cuenta_banco_id: Number(formData.get("cuenta_banco_id")) || null,
    notas: formData.get("notas")?.toString() || null,
    hora_salida: formData.get("hora_salida")?.toString() || "13:00",
  };
  if (moneda === "mixto") {
    payload.monto_recibido_usd = Number(formData.get("monto_recibido_usd") || 0);
    payload.monto_recibido_bs = Number(formData.get("monto_recibido_bs") || 0);
  }
  try {
    const resp = await post(`/habitaciones/${habId}/checkout`, payload);
    let msg;
    if (moneda === "usd") {
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
