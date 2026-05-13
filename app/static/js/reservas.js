import {
  get,
  post,
  showToast,
  formatBs,
  formatUsd,
  formatDateOnly,
  todayIso,
} from "./api.js";
import { abrirCheckin } from "./habitaciones.js";

const els = {
  tabla: document.getElementById("reservas-tabla"),
  form: document.getElementById("form-reserva"),
  habitacionSelect: document.getElementById("reserva-habitacion"),
  filtroEstado: document.getElementById("reservas-filtro-estado"),

  fechaIn: document.getElementById("reserva-fecha-in"),
  fechaOut: document.getElementById("reserva-fecha-out"),
  horaIn: document.getElementById("reserva-hora-in"),
  horaOut: document.getElementById("reserva-hora-out"),
  resumenNoches: document.getElementById("reserva-noches"),
  resumenPrecioUnit: document.getElementById("reserva-precio-unit"),
  resumenTotalUsd: document.getElementById("reserva-total-usd"),
  resumenTotalBs: document.getElementById("reserva-total-bs"),

  pagoDetalle: document.getElementById("reserva-pago-detalle"),
  pagoMoneda: document.getElementById("reserva-pago-moneda"),
  pagoUsdRow: document.getElementById("reserva-pago-usd-row"),
  pagoBsRow: document.getElementById("reserva-pago-bs-row"),
  pagoUsd: document.getElementById("reserva-pago-usd"),
  pagoBs: document.getElementById("reserva-pago-bs"),
};

let habitaciones = [];
let tasaBcv = 405.35;
let reservaCanceladaListenerRegistrado = false;

export async function initReservas() {
  if (!reservaCanceladaListenerRegistrado) {
    reservaCanceladaListenerRegistrado = true;
    document.addEventListener("reserva:cancelada", () => {
      void loadReservas();
    });
  }
  if (els.form) {
    els.form.addEventListener("submit", crearReserva);
    els.form.addEventListener("change", manejarCambioForm);
    els.form.addEventListener("input", manejarCambioForm);
  }
  if (els.filtroEstado) {
    els.filtroEstado.addEventListener("change", loadReservas);
  }
  if (els.fechaIn && !els.fechaIn.value) els.fechaIn.value = todayIso();
  if (els.fechaOut && !els.fechaOut.value) {
    const m = new Date();
    m.setDate(m.getDate() + 1);
    els.fechaOut.value = m.toISOString().slice(0, 10);
  }
  await Promise.all([cargarHabitacionesDisponibles(), cargarTasa(), loadReservas()]);
  recalcularResumen();
  actualizarVisibilidadPago();
}

async function cargarTasa() {
  try {
    const tasas = await get("/tasa/actual");
    if (tasas?.bcv) tasaBcv = Number(tasas.bcv);
  } catch (_err) {
    // mantener default
  }
}

async function cargarHabitacionesDisponibles() {
  if (!els.habitacionSelect) return;
  try {
    const habs = await get("/habitaciones/");
    habitaciones = habs;
    // Mostramos las disponibles para reservar (no inhabilitadas ni ocupadas).
    const ofrecibles = habs.filter((h) =>
      ["disponible", "reservada", "limpieza"].includes(h.estado),
    );
    els.habitacionSelect.innerHTML =
      `<option value="">Seleccione habitación...</option>` +
      ofrecibles
        .map(
          (h) =>
            `<option value="${h.id}" data-bs="${h.precio_bs}" data-usd="${h.precio_usd}">#${h.numero} · ${h.tipo} (${formatUsd(h.precio_usd)})</option>`,
        )
        .join("");
  } catch (error) {
    showToast(`Error cargando habitaciones: ${error.message}`, "error");
  }
}

export async function loadReservas() {
  if (!els.tabla) return;
  try {
    const filtroEstado = els.filtroEstado?.value || "";
    const query = filtroEstado ? `?estado=${encodeURIComponent(filtroEstado)}` : "";
    const reservas = await get(`/reservas/${query}`);
    // Si no se pidió filtro, mostramos sólo reservadas y activas (no cerradas).
    const visibles = filtroEstado
      ? reservas
      : reservas.filter((r) => ["reservada", "activa"].includes(r.estado));
    if (!visibles.length) {
      els.tabla.innerHTML = `<tr><td colspan="10"><div class="empty-state">Sin reservas</div></td></tr>`;
      return;
    }
    els.tabla.innerHTML = visibles
      .map((r) => {
        const doc = r.numero_documento
          ? `${r.tipo_documento || ""} ${r.numero_documento}`.trim()
          : r.documento || "-";
        const habNumero = habitacionNumero(r.habitacion_id);
        const acciones = [];
        if (r.estado === "reservada") {
          acciones.push(
            `<button data-id="${r.id}" data-hab="${r.habitacion_id}" class="btn-checkin-resv px-3 py-1 rounded bg-blue-600 text-white text-xs">Check-in</button>`,
          );
        }
        if (r.estado === "activa") {
          acciones.push(
            `<span class="text-xs text-slate-500">Check-out desde Habitaciones</span>`,
          );
        }
        if (r.estado === "reservada" || r.estado === "activa") {
          const abonoUsd = Number(r.pagado_parcial_usd || 0);
          const abonoBs = Number(r.pagado_parcial_bs || 0);
          acciones.push(
            `<button data-id="${r.id}" data-abono-usd="${abonoUsd}" data-abono-bs="${abonoBs}" data-huesped="${(r.huesped || "").replace(/"/g, "&quot;")}" class="btn-cancelar-reserva px-3 py-1 rounded bg-red-100 text-red-700 text-xs">🗑️ Cancelar</button>`,
          );
        }
        return `
          <tr>
            <td>#${r.id}</td>
            <td>${r.huesped}</td>
            <td>${doc}</td>
            <td>${habNumero}</td>
            <td>${formatDateOnly(r.fecha_checkin)} ${r.hora_ingreso || ""}</td>
            <td>${formatDateOnly(r.fecha_checkout_estimado)}</td>
            <td>${r.noches}</td>
            <td><span class="estado-pill estado-${r.estado}">${r.estado}</span></td>
            <td>${formatUsd(r.tarifa_usd)}<br><span class="text-xs text-slate-500">${formatBs(r.tarifa_bs)}</span></td>
            <td>${acciones.join(" ")}</td>
          </tr>`;
      })
      .join("");
    els.tabla
      .querySelectorAll(".btn-checkin-resv")
      .forEach((btn) =>
        btn.addEventListener("click", () =>
          checkInDesdeReserva(Number(btn.dataset.id), Number(btn.dataset.hab)),
        ),
      );
    els.tabla.querySelectorAll(".btn-cancelar-reserva").forEach((btn) =>
      btn.addEventListener("click", () =>
        abrirCancelarReserva({
          id: Number(btn.dataset.id),
          huesped: btn.dataset.huesped,
          abonoUsd: Number(btn.dataset.abonoUsd || 0),
          abonoBs: Number(btn.dataset.abonoBs || 0),
        }),
      ),
    );
  } catch (error) {
    showToast(`Error cargando reservas: ${error.message}`, "error");
  }
}

function habitacionNumero(id) {
  const hab = habitaciones.find((h) => h.id === id);
  return hab ? `#${hab.numero}` : `#${id}`;
}

function manejarCambioForm(event) {
  if (
    event?.target?.name === "pago_anticipado" ||
    event?.target?.id === "reserva-pago-moneda"
  ) {
    actualizarVisibilidadPago();
    return;
  }
  recalcularResumen();
}

function actualizarVisibilidadPago() {
  const activo =
    els.form?.querySelector('input[name="pago_anticipado"]:checked')?.value === "1";
  if (els.pagoDetalle) els.pagoDetalle.classList.toggle("hidden", !activo);
  const moneda = els.pagoMoneda?.value || "usd";
  if (els.pagoUsdRow)
    els.pagoUsdRow.classList.toggle("hidden", moneda !== "usd");
  if (els.pagoBsRow)
    els.pagoBsRow.classList.toggle("hidden", moneda !== "bs");
}

function calcularNoches() {
  const inIso = els.fechaIn?.value;
  const outIso = els.fechaOut?.value;
  if (!inIso || !outIso) return 1;
  const d1 = new Date(inIso);
  const d2 = new Date(outIso);
  if (Number.isNaN(d1.getTime()) || Number.isNaN(d2.getTime())) return 1;
  const diff = Math.round((d2 - d1) / 86400000);
  return Math.max(1, diff);
}

function recalcularResumen() {
  const noches = calcularNoches();
  // Precio por noche: tomar de la habitación seleccionada.
  const habSelect = els.habitacionSelect;
  const opt = habSelect?.options[habSelect.selectedIndex];
  const precioUsd = opt && opt.dataset.usd ? Number(opt.dataset.usd) : 0;
  const totalUsd = precioUsd * noches;
  const totalBs = totalUsd * tasaBcv;
  if (els.resumenNoches) els.resumenNoches.textContent = noches;
  if (els.resumenPrecioUnit)
    els.resumenPrecioUnit.textContent = formatUsd(precioUsd);
  if (els.resumenTotalUsd) els.resumenTotalUsd.textContent = formatUsd(totalUsd);
  if (els.resumenTotalBs) els.resumenTotalBs.textContent = formatBs(totalBs);
}

async function crearReserva(event) {
  event.preventDefault();
  const fd = new FormData(els.form);
  const noches = calcularNoches();
  const habSelect = els.habitacionSelect;
  const opt = habSelect?.options[habSelect.selectedIndex];
  const precioUsd = opt && opt.dataset.usd ? Number(opt.dataset.usd) : 0;
  const pagoAnticipado =
    els.form?.querySelector('input[name="pago_anticipado"]:checked')?.value === "1";

  const payload = {
    habitacion_id: Number(fd.get("habitacion_id")),
    huesped: fd.get("huesped")?.toString().trim(),
    documento: fd.get("documento")?.toString() || null,
    telefono: fd.get("telefono")?.toString() || null,
    fecha_checkin: fd.get("fecha_checkin") || todayIso(),
    fecha_checkout_estimado: fd.get("fecha_checkout_estimado"),
    noches,
    tarifa_usd: precioUsd || 0,
    hora_ingreso: fd.get("hora_ingreso")?.toString() || null,
    hora_salida: fd.get("hora_salida")?.toString() || null,
    pais_origen: fd.get("pais_origen")?.toString().trim() || null,
    tipo_documento: fd.get("tipo_documento")?.toString() || null,
    numero_documento: fd.get("numero_documento")?.toString().trim() || null,
    vehiculo_modelo: fd.get("vehiculo_modelo")?.toString().trim() || null,
    vehiculo_color: fd.get("vehiculo_color")?.toString().trim() || null,
    vehiculo_placa: fd.get("vehiculo_placa")?.toString().trim() || null,
    pago_anticipado: pagoAnticipado,
  };
  if (pagoAnticipado) {
    payload.moneda_pago = fd.get("moneda_pago") || "usd";
    payload.metodo_pago = fd.get("metodo_pago") || "efectivo";
    payload.monto_recibido_usd = Number(fd.get("monto_recibido_usd") || 0);
    payload.monto_recibido_bs = Number(fd.get("monto_recibido_bs") || 0);
    payload.tasa_tipo = "bcv";
  }
  if (
    !payload.habitacion_id ||
    !payload.huesped ||
    !payload.fecha_checkout_estimado
  ) {
    showToast("Complete habitación, huésped y fecha de salida", "error");
    return;
  }
  try {
    const reserva = await post("/reservas/", payload);
    let msg = `Reserva #${reserva.id} creada para ${reserva.huesped}`;
    if (reserva.estado_pago === "pagado") {
      msg += " · 💰 estadía pagada por adelantado";
    } else if (reserva.estado_pago === "parcial") {
      msg += " · pago parcial registrado";
    }
    showToast(msg, "success");
    els.form.reset();
    if (els.fechaIn) els.fechaIn.value = todayIso();
    if (els.fechaOut) {
      const m = new Date();
      m.setDate(m.getDate() + 1);
      els.fechaOut.value = m.toISOString().slice(0, 10);
    }
    if (els.horaIn) els.horaIn.value = "15:00";
    if (els.horaOut) els.horaOut.value = "13:00";
    actualizarVisibilidadPago();
    recalcularResumen();
    await Promise.all([cargarHabitacionesDisponibles(), loadReservas()]);
  } catch (error) {
    showToast(`Error creando reserva: ${error.message}`, "error");
  }
}

async function checkInDesdeReserva(reservaId, habitacionId) {
  try {
    const reserva = await get(`/reservas/${reservaId}`);
    const habs = await get("/habitaciones/");
    const hab = habs.find((h) => h.id === habitacionId);
    if (!hab) {
      showToast("La habitación de la reserva no existe", "error");
      return;
    }
    // Modal en index.html (habitaciones.js): mismo flujo sin cambiar de pestaña.
    abrirCheckin(habitacionId, { reserva, habitaciones: habs });
    document.addEventListener("checkin:confirmado", refrescarTrasCheckin, {
      once: true,
    });
  } catch (error) {
    showToast(`Error preparando check-in: ${error.message}`, "error");
  }
}

async function refrescarTrasCheckin() {
  await Promise.all([cargarHabitacionesDisponibles(), loadReservas()]);
}

// ---------------------------------------------------------------------------
// Cancelar reserva con reembolso porcentual
// ---------------------------------------------------------------------------
const modalCancel = {
  fondo: null,
  form: null,
  idInput: null,
  porcentajeInput: null,
  porcentajeOutput: null,
  resumen: null,
  abonoUsd: 0,
  abonoBs: 0,
};

function asegurarModalCancelarReserva() {
  if (modalCancel.fondo) return;
  modalCancel.fondo = document.getElementById("modal-cancelar-reserva");
  if (!modalCancel.fondo) {
    // Si el HTML aún no fue insertado, lo creamos dinámicamente.
    const div = document.createElement("div");
    div.id = "modal-cancelar-reserva";
    div.className = "modal-backdrop hidden";
    div.innerHTML = `
      <form id="form-cancelar-reserva" class="card p-5 w-full max-w-md space-y-3">
        <h3 class="text-lg font-semibold text-red-700">🗑️ Cancelar reserva</h3>
        <input type="hidden" id="cancelar-reserva-id" />
        <p class="text-sm text-slate-600" id="cancelar-reserva-resumen"></p>
        <div>
          <label class="text-xs uppercase text-slate-500">% Reembolso (0–100)</label>
          <div class="flex items-center gap-2">
            <input type="range" min="0" max="100" step="5" value="0" id="cancelar-reserva-porcentaje" class="flex-1" />
            <span id="cancelar-reserva-porcentaje-val" class="text-sm font-semibold w-12 text-right">0%</span>
          </div>
        </div>
        <div>
          <label class="text-xs uppercase text-slate-500">Método de reembolso</label>
          <select name="metodo_pago_reembolso" class="w-full border rounded px-2 py-1">
            <option value="">— No aplica —</option>
            <option value="efectivo">Efectivo</option>
            <option value="transferencia">Transferencia</option>
            <option value="pagomovil">Pago Móvil</option>
          </select>
        </div>
        <div>
          <label class="text-xs uppercase text-slate-500">Nota (opcional)</label>
          <textarea name="nota" rows="2" class="w-full border rounded px-2 py-1"
            placeholder="Motivo o detalles del reembolso"></textarea>
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button type="button" id="cancelar-reserva-cerrar" class="px-3 py-1 border rounded">Volver</button>
          <button type="submit" class="px-3 py-1 bg-red-600 text-white rounded">Confirmar cancelación</button>
        </div>
      </form>
    `;
    document.body.appendChild(div);
    modalCancel.fondo = div;
  }
  modalCancel.form = document.getElementById("form-cancelar-reserva");
  modalCancel.idInput = document.getElementById("cancelar-reserva-id");
  modalCancel.porcentajeInput = document.getElementById(
    "cancelar-reserva-porcentaje",
  );
  modalCancel.porcentajeOutput = document.getElementById(
    "cancelar-reserva-porcentaje-val",
  );
  modalCancel.resumen = document.getElementById("cancelar-reserva-resumen");

  document.getElementById("cancelar-reserva-cerrar")?.addEventListener(
    "click",
    () => modalCancel.fondo.classList.add("hidden"),
  );
  modalCancel.porcentajeInput?.addEventListener("input", actualizarResumenCancel);
  modalCancel.form?.addEventListener("submit", confirmarCancelarReserva);
}

function actualizarResumenCancel() {
  const pct = Number(modalCancel.porcentajeInput?.value || 0);
  if (modalCancel.porcentajeOutput) {
    modalCancel.porcentajeOutput.textContent = `${pct}%`;
  }
  if (modalCancel.resumen) {
    const reembUsd = (modalCancel.abonoUsd * pct) / 100;
    const reembBs = (modalCancel.abonoBs * pct) / 100;
    modalCancel.resumen.innerHTML = `
      <strong>Pago anticipado:</strong> ${formatUsd(modalCancel.abonoUsd)} / ${formatBs(modalCancel.abonoBs)}<br>
      <strong>Reembolso (${pct}%):</strong> ${formatUsd(reembUsd)} / ${formatBs(reembBs)}
    `;
  }
}

function abrirCancelarReserva({ id, huesped, abonoUsd, abonoBs }) {
  asegurarModalCancelarReserva();
  if (!modalCancel.fondo) return;
  if (modalCancel.idInput) modalCancel.idInput.value = String(id);
  modalCancel.abonoUsd = Number(abonoUsd || 0);
  modalCancel.abonoBs = Number(abonoBs || 0);
  if (modalCancel.porcentajeInput) modalCancel.porcentajeInput.value = "0";
  if (modalCancel.form) {
    const tituloHuesped = (huesped || "huésped").replace(/<[^>]+>/g, "");
    const ph = modalCancel.form.querySelector('textarea[name="nota"]');
    if (ph) ph.value = "";
    modalCancel.form
      .querySelector('select[name="metodo_pago_reembolso"]')
      ?.setAttribute("data-huesped", tituloHuesped);
  }
  actualizarResumenCancel();
  modalCancel.fondo.classList.remove("hidden");
}

async function confirmarCancelarReserva(event) {
  event.preventDefault();
  if (!modalCancel.form || !modalCancel.idInput) return;
  const id = Number(modalCancel.idInput.value);
  if (!id) return;
  const fd = new FormData(modalCancel.form);
  const porcentaje = Math.max(
    0,
    Math.min(100, Number(modalCancel.porcentajeInput?.value || 0)),
  );
  const payload = {
    porcentaje_reembolso: porcentaje,
    nota: fd.get("nota")?.toString() || null,
    metodo_pago_reembolso:
      fd.get("metodo_pago_reembolso")?.toString() || null,
  };
  try {
    const resp = await post(`/reservas/${id}/cancelar`, payload);
    modalCancel.fondo?.classList.add("hidden");
    const reemb = Number(resp.reembolso_usd || 0);
    const reembBs = Number(resp.reembolso_bs || 0);
    let msg = `Reserva #${id} cancelada`;
    if (reemb > 0 || reembBs > 0) {
      msg += ` · Reembolso ${formatUsd(reemb)} / ${formatBs(reembBs)} (${porcentaje}%)`;
    }
    showToast(msg, "success");
    await Promise.all([cargarHabitacionesDisponibles(), loadReservas()]);
  } catch (error) {
    showToast(`Error cancelando reserva: ${error.message}`, "error");
  }
}
