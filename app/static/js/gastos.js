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
  form: document.getElementById("form-gasto"),
  categoria: document.getElementById("gasto-categoria"),
  cuenta: document.getElementById("gasto-cuenta"),
  fecha: document.getElementById("gasto-fecha"),
  tabla: document.getElementById("gastos-tabla"),
  formCategoria: document.getElementById("form-categoria"),
  tablaCategorias: document.getElementById("tabla-categorias"),
};

let categoriasCache = [];

export async function initGastos() {
  if (els.fecha && !els.fecha.value) {
    els.fecha.value = todayIso();
  }
  if (els.form) {
    els.form.addEventListener("submit", crearGasto);
  }
  if (els.formCategoria) {
    els.formCategoria.addEventListener("submit", crearCategoria);
  }
  await Promise.all([cargarCategorias(), cargarCuentas(), loadGastos()]);
}

async function cargarCategorias() {
  try {
    categoriasCache = await get("/gastos/categorias");
    if (els.categoria) {
      els.categoria.innerHTML =
        `<option value="">Seleccione categoría...</option>` +
        categoriasCache
          .map((c) => `<option value="${c.id}">${c.nombre}</option>`)
          .join("");
    }
    if (els.tablaCategorias) {
      els.tablaCategorias.innerHTML = categoriasCache.length
        ? categoriasCache
            .map(
              (c) => `
              <tr>
                <td>${c.nombre}</td>
                <td>${c.tipo}</td>
                <td>${c.descripcion || ""}</td>
              </tr>`,
            )
            .join("")
        : `<tr><td colspan="3"><div class="empty-state">Sin categorías</div></td></tr>`;
    }
  } catch (error) {
    showToast(`Error cargando categorías: ${error.message}`, "error");
  }
}

async function cargarCuentas() {
  if (!els.cuenta) return;
  try {
    const cuentas = await get("/cuentas/");
    els.cuenta.innerHTML =
      `<option value="">Sin afectar banco</option>` +
      cuentas
        .map(
          (c) => `<option value="${c.id}">${c.nombre} (${c.moneda})</option>`,
        )
        .join("");
  } catch (error) {
    console.warn("No se pudieron cargar cuentas", error);
  }
}

async function loadGastos() {
  if (!els.tabla) return;
  try {
    const gastos = await get("/gastos/?limit=20");
    if (!gastos.length) {
      els.tabla.innerHTML = `<tr><td colspan="7"><div class="empty-state">Sin gastos registrados</div></td></tr>`;
      return;
    }
    const catById = Object.fromEntries(categoriasCache.map((c) => [c.id, c.nombre]));
    els.tabla.innerHTML = gastos
      .map(
        (g) => `
        <tr>
          <td>${formatDateOnly(g.fecha)}</td>
          <td>${catById[g.categoria_id] || g.categoria_id}</td>
          <td>${g.descripcion}</td>
          <td>${formatBs(g.monto_bs)}</td>
          <td>${formatUsd(g.monto_usd)}</td>
          <td>${g.beneficiario || "-"}</td>
          <td>${g.referencia || "-"}</td>
        </tr>`,
      )
      .join("");
  } catch (error) {
    showToast(`Error cargando gastos: ${error.message}`, "error");
  }
}

async function crearGasto(event) {
  event.preventDefault();
  const formData = new FormData(els.form);
  const payload = {
    fecha: formData.get("fecha") || todayIso(),
    categoria_id: Number(formData.get("categoria_id")),
    descripcion: formData.get("descripcion")?.toString().trim(),
    monto_bs: Number(formData.get("monto_bs") || 0),
    monto_usd: Number(formData.get("monto_usd") || 0),
    cuenta_banco_id: Number(formData.get("cuenta_banco_id")) || null,
    beneficiario: formData.get("beneficiario")?.toString() || null,
    referencia: formData.get("referencia")?.toString() || null,
    notas: formData.get("notas")?.toString() || null,
  };
  if (!payload.categoria_id || !payload.descripcion) {
    showToast("Complete categoría y descripción", "error");
    return;
  }
  if (payload.monto_bs <= 0 && payload.monto_usd <= 0) {
    showToast("Indique monto en Bs o USD", "error");
    return;
  }
  try {
    await post("/gastos/", payload);
    showToast("Gasto registrado", "success");
    els.form.reset();
    if (els.fecha) els.fecha.value = todayIso();
    await loadGastos();
  } catch (error) {
    showToast(`Error registrando gasto: ${error.message}`, "error");
  }
}

async function crearCategoria(event) {
  event.preventDefault();
  const formData = new FormData(els.formCategoria);
  const payload = {
    nombre: formData.get("nombre")?.toString().trim(),
    tipo: formData.get("tipo")?.toString() || "operativo",
    descripcion: formData.get("descripcion")?.toString() || null,
  };
  if (!payload.nombre) {
    showToast("Indique el nombre de la categoría", "error");
    return;
  }
  try {
    await post("/gastos/categorias", payload);
    showToast("Categoría creada", "success");
    els.formCategoria.reset();
    await cargarCategorias();
  } catch (error) {
    showToast(`Error creando categoría: ${error.message}`, "error");
  }
}
