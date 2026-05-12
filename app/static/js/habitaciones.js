import {
  get,
  post,
  patch,
  put,
  showToast,
  formatBs,
  formatUsd,
  formatDate,
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

  modalCheckout: document.getElementById("modal-checkout"),
  formCheckout: document.getElementById("form-checkout"),
  checkoutCancelar: document.getElementById("checkout-cancelar"),
  checkoutResumen: document.getElementById("checkout-resumen"),
  checkoutHabId: document.getElementById("checkout-habitacion-id"),
};

let habitaciones = [];

export async function initHabitaciones() {
  if (els.filtro) els.filtro.addEventListener("change", loadHabitaciones);
  if (els.btnNuevo) els.btnNuevo.addEventListener("click", () => abrirModal());
  if (els.cancelar) els.cancelar.addEventListener("click", cerrarModal);
  if (els.form) els.form.addEventListener("submit", onSubmit);

  if (els.checkinCancelar)
    els.checkinCancelar.addEventListener("click", cerrarCheckin);
  if (els.formCheckin)
    els.formCheckin.addEventListener("submit", confirmarCheckin);

  if (els.checkoutCancelar)
    els.checkoutCancelar.addEventListener("click", cerrarCheckout);
  if (els.formCheckout)
    els.formCheckout.addEventListener("submit", confirmarCheckout);

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
function abrirCheckin(habId) {
  const h = habitaciones.find((x) => x.id === habId);
  if (!h) return;
  if (!els.modalCheckin) return;
  els.formCheckin?.reset();
  if (els.checkinHabId) els.checkinHabId.value = h.id;
  if (els.checkinTitulo)
    els.checkinTitulo.textContent = `Check-in habitación #${h.numero}`;
  if (els.checkinTarifa) els.checkinTarifa.value = h.precio_usd;
  els.modalCheckin.classList.remove("hidden");
}

function cerrarCheckin() {
  els.modalCheckin?.classList.add("hidden");
}

async function confirmarCheckin(event) {
  event.preventDefault();
  const formData = new FormData(els.formCheckin);
  const habId = Number(formData.get("habitacion_id"));
  const payload = {
    huesped: formData.get("huesped")?.toString().trim(),
    documento: formData.get("documento")?.toString() || null,
    telefono: formData.get("telefono")?.toString() || null,
    fecha_checkin: formData.get("fecha_checkin") || null,
    fecha_checkout_estimado: formData.get("fecha_checkout_estimado") || null,
    noches: Number(formData.get("noches") || 1),
    tarifa_usd: Number(formData.get("tarifa_usd") || 0) || null,
    notas: formData.get("notas")?.toString() || null,
  };
  if (!payload.huesped) {
    showToast("Indique el nombre del huésped", "error");
    return;
  }
  try {
    const reserva = await post(`/habitaciones/${habId}/checkin`, payload);
    showToast(
      `Check-in OK · ${reserva.huesped} (reserva #${reserva.id})`,
      "success",
    );
    cerrarCheckin();
    await loadHabitaciones();
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
  els.checkoutResumen.innerHTML = `<p class="text-sm text-slate-500">Calculando total…</p>`;
  els.modalCheckout.classList.remove("hidden");
  try {
    const preview = await get(`/habitaciones/${habId}/checkout-preview`);
    els.checkoutResumen.innerHTML = renderPreview(preview);
  } catch (error) {
    els.checkoutResumen.innerHTML = `<p class="text-sm text-red-600">${error.message}</p>`;
  }
}

function renderPreview(p) {
  const pedidos = p.pedidos?.length
    ? `<p class="text-xs text-slate-500">Pedidos asociados: ${p.pedidos.map((id) => `#${id}`).join(", ")}</p>`
    : "";
  return `
    <p><strong>Habitación #${p.numero}</strong>${p.huesped ? ` · ${p.huesped}` : ""}</p>
    <ul class="text-sm space-y-1 mt-2">
      <li>Estadía (${p.noches} noche${p.noches === 1 ? "" : "s"}): ${formatUsd(p.tarifa_usd)} · ${formatBs(p.tarifa_bs)}</li>
      <li>Consumos: ${formatUsd(p.consumos_usd)} · ${formatBs(p.consumos_bs)}</li>
      <li class="border-t pt-1"><strong>Total a cobrar: ${formatUsd(p.total_usd)} · ${formatBs(p.total_bs)}</strong></li>
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
  const payload = {
    metodo_pago: formData.get("metodo_pago") || "bs",
    cuenta_banco_id: Number(formData.get("cuenta_banco_id")) || null,
    monto_recibido_bs: Number(formData.get("monto_recibido_bs") || 0),
    monto_recibido_usd: Number(formData.get("monto_recibido_usd") || 0),
    tasa_tipo: formData.get("tasa_tipo") || "bcv",
    notas: formData.get("notas")?.toString() || null,
  };
  try {
    const resp = await post(`/habitaciones/${habId}/checkout`, payload);
    showToast(
      `Check-out OK · Total ${formatUsd(resp.total_usd)} (${formatBs(resp.total_bs)})`,
      "success",
    );
    cerrarCheckout();
    await loadHabitaciones();
  } catch (error) {
    showToast(`Error en check-out: ${error.message}`, "error");
  }
}
