import {
  get,
  post,
  put,
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
  modalCheckout: document.getElementById("modal-checkout"),
  formCheckout: document.getElementById("form-checkout"),
  checkoutResumen: document.getElementById("checkout-resumen"),
  checkoutCancelar: document.getElementById("checkout-cancelar"),
  cuentaSelect: document.getElementById("checkout-cuenta"),
};

let reservaEnCheckout = null;

export async function initReservas() {
  if (els.form) {
    els.form.addEventListener("submit", crearCheckin);
  }
  if (els.formCheckout) {
    els.formCheckout.addEventListener("submit", confirmarCheckout);
  }
  if (els.checkoutCancelar) {
    els.checkoutCancelar.addEventListener("click", cerrarModalCheckout);
  }
  await Promise.all([cargarHabitacionesDisponibles(), cargarCuentas(), loadReservas()]);
}

async function cargarHabitacionesDisponibles() {
  if (!els.habitacionSelect) return;
  try {
    const habs = await get("/habitaciones/?estado=disponible");
    els.habitacionSelect.innerHTML =
      `<option value="">Seleccione habitación...</option>` +
      habs
        .map(
          (h) =>
            `<option value="${h.id}" data-bs="${h.precio_bs}" data-usd="${h.precio_usd}">#${h.numero} · ${h.tipo} (${formatUsd(h.precio_usd)})</option>`,
        )
        .join("");
  } catch (error) {
    showToast(`Error cargando habitaciones: ${error.message}`, "error");
  }
}

async function cargarCuentas() {
  if (!els.cuentaSelect) return;
  try {
    const cuentas = await get("/cuentas/");
    els.cuentaSelect.innerHTML =
      `<option value="">Sin registrar a banco</option>` +
      cuentas
        .map(
          (c) => `<option value="${c.id}">${c.nombre} (${c.moneda})</option>`,
        )
        .join("");
  } catch (error) {
    console.warn("No se pudieron cargar cuentas", error);
  }
}

export async function loadReservas() {
  if (!els.tabla) return;
  try {
    const reservas = await get("/reservas/activas");
    if (!reservas.length) {
      els.tabla.innerHTML = `<tr><td colspan="8"><div class="empty-state">Sin reservas activas</div></td></tr>`;
      return;
    }
    els.tabla.innerHTML = reservas
      .map(
        (r) => `
        <tr>
          <td>#${r.id}</td>
          <td>${r.huesped}</td>
          <td>${r.habitacion_id}</td>
          <td>${formatDateOnly(r.fecha_checkin)}</td>
          <td>${formatDateOnly(r.fecha_checkout_estimado)}</td>
          <td>${r.noches}</td>
          <td>${formatUsd(r.total_final_usd)}<br><span class="text-xs text-slate-500">${formatBs(r.total_final_bs)}</span></td>
          <td>
            <button data-id="${r.id}" class="btn-checkout px-3 py-1 rounded bg-emerald-600 text-white text-xs">Checkout</button>
          </td>
        </tr>`,
      )
      .join("");
    els.tabla.querySelectorAll(".btn-checkout").forEach((btn) =>
      btn.addEventListener("click", () => abrirModalCheckout(btn.dataset.id)),
    );
  } catch (error) {
    showToast(`Error cargando reservas: ${error.message}`, "error");
  }
}

async function crearCheckin(event) {
  event.preventDefault();
  const formData = new FormData(els.form);
  const habitacion_id = Number(formData.get("habitacion_id"));
  const noches = Number(formData.get("noches") || 1);
  const payload = {
    habitacion_id,
    huesped: formData.get("huesped")?.toString().trim(),
    documento: formData.get("documento")?.toString() || null,
    telefono: formData.get("telefono")?.toString() || null,
    fecha_checkin: formData.get("fecha_checkin") || todayIso(),
    fecha_checkout_estimado: formData.get("fecha_checkout"),
    noches,
    tarifa_bs: Number(formData.get("tarifa_bs") || 0),
    tarifa_usd: Number(formData.get("tarifa_usd") || 0),
  };
  if (!payload.habitacion_id || !payload.huesped || !payload.fecha_checkout_estimado) {
    showToast("Complete habitación, huésped y fecha de salida", "error");
    return;
  }
  try {
    await post("/reservas/", payload);
    showToast("Check-in registrado", "success");
    els.form.reset();
    await Promise.all([cargarHabitacionesDisponibles(), loadReservas()]);
  } catch (error) {
    showToast(`Error en check-in: ${error.message}`, "error");
  }
}

async function abrirModalCheckout(reservaId) {
  try {
    const reserva = await get(`/reservas/${reservaId}`);
    reservaEnCheckout = reserva;
    if (els.checkoutResumen) {
      els.checkoutResumen.innerHTML = `
        <p><strong>Huésped:</strong> ${reserva.huesped}</p>
        <p><strong>Habitación:</strong> ${reserva.habitacion_id}</p>
        <p><strong>Noches:</strong> ${reserva.noches}</p>
        <p><strong>Tarifa:</strong> ${formatUsd(reserva.tarifa_usd)} · ${formatBs(reserva.tarifa_bs)}</p>
        <p><strong>Consumos:</strong> ${formatUsd(reserva.total_consumos_usd)} · ${formatBs(reserva.total_consumos_bs)}</p>
        <p class="font-semibold text-base">Total: ${formatUsd(reserva.total_final_usd)} · ${formatBs(reserva.total_final_bs)}</p>
      `;
    }
    els.formCheckout?.reset();
    els.modalCheckout?.classList.remove("hidden");
  } catch (error) {
    showToast(`Error cargando reserva: ${error.message}`, "error");
  }
}

function cerrarModalCheckout() {
  reservaEnCheckout = null;
  els.modalCheckout?.classList.add("hidden");
}

async function confirmarCheckout(event) {
  event.preventDefault();
  if (!reservaEnCheckout) return;
  const formData = new FormData(els.formCheckout);
  const payload = {
    metodo_pago: formData.get("metodo_pago") || "bs",
    cuenta_banco_id: Number(formData.get("cuenta_banco_id")) || null,
    monto_recibido_bs: Number(formData.get("monto_bs") || 0),
    monto_recibido_usd: Number(formData.get("monto_usd") || 0),
    notas: formData.get("notas")?.toString() || null,
  };
  try {
    await put(`/reservas/${reservaEnCheckout.id}/checkout`, payload);
    showToast("Checkout exitoso", "success");
    cerrarModalCheckout();
    await Promise.all([cargarHabitacionesDisponibles(), loadReservas()]);
  } catch (error) {
    showToast(`Error en checkout: ${error.message}`, "error");
  }
}
