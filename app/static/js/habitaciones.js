import { get, post, patch, showToast, formatBs, formatUsd } from "./api.js";

const ESTADOS = ["disponible", "ocupada", "limpieza", "mantenimiento", "bloqueada"];

const els = {
  grid: document.getElementById("habs-grid"),
  filtro: document.getElementById("habs-filtro"),
  btnNuevo: document.getElementById("habs-btn-nuevo"),
  modal: document.getElementById("modal-habitacion"),
  form: document.getElementById("form-habitacion"),
  cancelar: document.getElementById("habs-modal-cancelar"),
};

export async function initHabitaciones() {
  if (els.filtro) {
    els.filtro.addEventListener("change", loadHabitaciones);
  }
  if (els.btnNuevo) {
    els.btnNuevo.addEventListener("click", () => abrirModal());
  }
  if (els.cancelar) {
    els.cancelar.addEventListener("click", cerrarModal);
  }
  if (els.form) {
    els.form.addEventListener("submit", onSubmit);
  }
  await loadHabitaciones();
}

export async function loadHabitaciones() {
  if (!els.grid) return;
  try {
    const estado = els.filtro ? els.filtro.value : "";
    const query = estado ? `?estado=${encodeURIComponent(estado)}` : "";
    const habitaciones = await get(`/habitaciones/${query}`);
    if (!habitaciones.length) {
      els.grid.innerHTML = `<div class="empty-state">No hay habitaciones registradas.</div>`;
      return;
    }
    els.grid.innerHTML = habitaciones
      .map(
        (h) => `
        <div class="room-tile room-${h.estado} p-4 rounded-lg">
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-xl font-bold">#${h.numero}</h3>
            <span class="badge ${badgeForEstado(h.estado)}">${h.estado}</span>
          </div>
          <p class="text-xs text-slate-600 uppercase">${h.tipo}</p>
          <p class="text-sm mt-2">${formatUsd(h.precio_usd)} · ${formatBs(h.precio_bs)}</p>
          ${h.notas ? `<p class="text-xs italic mt-1 text-slate-500">${h.notas}</p>` : ""}
          <div class="mt-3 flex gap-2 flex-wrap">
            ${ESTADOS.map(
              (estado) =>
                `<button data-id="${h.id}" data-estado="${estado}" class="btn-cambiar-estado text-xs px-2 py-1 rounded border ${
                  estado === h.estado ? "bg-slate-800 text-white" : "bg-white"
                }">${estado}</button>`,
            ).join("")}
          </div>
        </div>`,
      )
      .join("");

    els.grid.querySelectorAll(".btn-cambiar-estado").forEach((btn) =>
      btn.addEventListener("click", () =>
        cambiarEstado(btn.dataset.id, btn.dataset.estado),
      ),
    );
  } catch (error) {
    showToast(`Error cargando habitaciones: ${error.message}`, "error");
  }
}

function badgeForEstado(estado) {
  switch (estado) {
    case "disponible":
      return "badge-success";
    case "ocupada":
      return "badge-danger";
    case "limpieza":
      return "badge-warning";
    case "mantenimiento":
      return "badge-info";
    default:
      return "";
  }
}

async function cambiarEstado(id, estado) {
  try {
    await patch(`/habitaciones/${id}/estado`, { estado });
    showToast(`Habitación #${id} → ${estado}`, "success");
    await loadHabitaciones();
  } catch (error) {
    showToast(`Error cambiando estado: ${error.message}`, "error");
  }
}

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
