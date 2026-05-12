import {
  get,
  post,
  showToast,
  formatBs,
  formatUsd,
  formatDateOnly,
  todayIso,
} from "./api.js";

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

export async function initReservas() {
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
        const acciones =
          r.estado === "reservada"
            ? `<button data-id="${r.id}" data-hab="${r.habitacion_id}" class="btn-checkin-resv px-3 py-1 rounded bg-blue-600 text-white text-xs">Check-in</button>`
            : r.estado === "activa"
              ? `<span class="text-xs text-slate-500">Hacer check-out desde Habitaciones</span>`
              : "";
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
            <td>${acciones}</td>
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
    // Abrimos el modal de check-in pre-cargado.
    const { abrirCheckin } = await import("./habitaciones.js");
    if (typeof abrirCheckin !== "function") {
      showToast("Función de check-in no disponible", "error");
      return;
    }
    await abrirCheckin(habitacionId, { reserva, habitaciones: habs });
    // Cuando se confirme, habitaciones.js refresca la tabla; nos suscribimos
    // para refrescar también la lista de reservas.
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
