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
  checkoutTasaRow: document.getElementById("checkout-tasa-row"),
  checkoutTasaTipo: document.getElementById("checkout-tasa-tipo"),
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
      }),
    );
  }

  if (els.checkoutCancelar)
    els.checkoutCancelar.addEventListener("click", cerrarCheckout);
  if (els.formCheckout) {
    els.formCheckout.addEventListener("submit", confirmarCheckout);
    els.formCheckout
      .querySelectorAll('input[name="moneda_pago"]')
      .forEach((r) => r.addEventListener("change", actualizarMonedaCheckout));
    if (els.checkoutTasaTipo)
      els.checkoutTasaTipo.addEventListener("change", recargarPreviewCheckout);
  }

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
  if (els.checkinNoches) els.checkinNoches.value = 1;
  // Por defecto, hoy → mañana.
  const hoy = new Date();
  const hoyIso = hoy.toISOString().slice(0, 10);
  const mananaIso = new Date(hoy.getTime() + 86400000)
    .toISOString()
    .slice(0, 10);
  const inputIn = els.formCheckin.querySelector('input[name="fecha_checkin"]');
  const inputOut = els.formCheckin.querySelector(
    'input[name="fecha_checkout_estimado"]',
  );
  if (inputIn && !inputIn.value) inputIn.value = hoyIso;
  if (inputOut && !inputOut.value) inputOut.value = mananaIso;
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
  // Reset radios: USD por defecto.
  const radioUsd = els.formCheckout.querySelector(
    'input[name="moneda_pago"][value="usd"]',
  );
  if (radioUsd) radioUsd.checked = true;
  if (els.checkoutTasaRow) els.checkoutTasaRow.classList.add("hidden");
  els.checkoutResumen.innerHTML = `<p class="text-sm text-slate-500">Calculando total…</p>`;
  els.modalCheckout.classList.remove("hidden");
  await recargarPreviewCheckout();
}

async function recargarPreviewCheckout() {
  const habId = Number(els.checkoutHabId?.value);
  if (!habId) return;
  const moneda =
    els.formCheckout.querySelector('input[name="moneda_pago"]:checked')?.value ||
    "usd";
  const tasaTipo = els.checkoutTasaTipo?.value || "bcv";
  try {
    const preview = await get(
      `/habitaciones/${habId}/checkout-preview?tasa_tipo=${tasaTipo}`,
    );
    els.checkoutResumen.innerHTML = renderPreview(preview, moneda);
  } catch (error) {
    els.checkoutResumen.innerHTML = `<p class="text-sm text-red-600">${error.message}</p>`;
  }
}

function actualizarMonedaCheckout() {
  const moneda =
    els.formCheckout.querySelector('input[name="moneda_pago"]:checked')?.value ||
    "usd";
  if (els.checkoutTasaRow) {
    els.checkoutTasaRow.classList.toggle("hidden", moneda !== "bs");
  }
  recargarPreviewCheckout();
}

function renderPreview(p, moneda = "usd") {
  const pedidos = p.pedidos?.length
    ? `<p class="text-xs text-slate-500">Pedidos asociados: ${p.pedidos.map((id) => `#${id}`).join(", ")}</p>`
    : "";
  const totalDestacado =
    moneda === "bs"
      ? `<strong>Total a cobrar: ${formatBs(p.total_bs)}</strong>
         <p class="text-xs text-slate-500">Tasa ${p.tasa_tipo?.toUpperCase()}: ${Number(p.tasa_aplicada || 0).toFixed(2)} Bs/USD · equivalente ${formatUsd(p.total_usd)}</p>`
      : `<strong>Total a cobrar: ${formatUsd(p.total_usd)}</strong>
         <p class="text-xs text-slate-500">Sin tasa (efectivo en dólares)</p>`;
  return `
    <p><strong>Habitación #${p.numero}</strong>${p.huesped ? ` · ${p.huesped}` : ""}</p>
    <ul class="text-sm space-y-1 mt-2">
      <li>Estadía (${p.noches} noche${p.noches === 1 ? "" : "s"}): ${formatUsd(p.tarifa_usd)}${moneda === "bs" ? ` · ${formatBs(p.tarifa_bs)}` : ""}</li>
      <li>Consumos: ${formatUsd(p.consumos_usd)}${moneda === "bs" ? ` · ${formatBs(p.consumos_bs)}` : ""}</li>
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
  const moneda = formData.get("moneda_pago")?.toString() || "usd";
  const payload = {
    moneda_pago: moneda,
    metodo_pago: formData.get("metodo_pago")?.toString() || "efectivo",
    tasa_tipo: moneda === "bs" ? formData.get("tasa_tipo") || "bcv" : "bcv",
    cuenta_banco_id: Number(formData.get("cuenta_banco_id")) || null,
    notas: formData.get("notas")?.toString() || null,
  };
  try {
    const resp = await post(`/habitaciones/${habId}/checkout`, payload);
    const msg =
      moneda === "usd"
        ? `Check-out OK · Cobrado ${formatUsd(resp.total_usd)} en USD`
        : `Check-out OK · Cobrado ${formatBs(resp.total_bs)} (tasa ${resp.tasa_tipo?.toUpperCase()})`;
    showToast(msg, "success");
    cerrarCheckout();
    await loadHabitaciones();
  } catch (error) {
    showToast(`Error en check-out: ${error.message}`, "error");
  }
}
