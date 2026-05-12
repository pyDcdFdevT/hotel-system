import { get, post, showToast, formatRate, formatDateOnly } from "./api.js";

const headerEls = {
  bcv: document.getElementById("header-tasa-bcv"),
  paralelo: document.getElementById("header-tasa-paralelo"),
  fecha: document.getElementById("header-tasa-fecha"),
  dashBcv: document.getElementById("dash-tasa-bcv"),
  dashParalelo: document.getElementById("dash-tasa-paralelo"),
};

const configEls = {
  form: document.getElementById("form-tasas"),
  inputBcv: document.getElementById("config-tasa-bcv"),
  inputParalelo: document.getElementById("config-tasa-paralelo"),
  feedback: document.getElementById("config-tasa-feedback"),
  tabla: document.getElementById("config-tabla-tasas"),
};

let cacheTasas = { bcv: null, paralelo: null, fecha: null };

export async function refreshHeaderTasas() {
  try {
    const tasas = await get("/tasa/actual");
    cacheTasas = {
      bcv: Number(tasas.bcv) || 0,
      paralelo: Number(tasas.paralelo) || 0,
      fecha: tasas.fecha,
    };
    if (headerEls.bcv) headerEls.bcv.textContent = formatRate(cacheTasas.bcv);
    if (headerEls.paralelo) headerEls.paralelo.textContent = formatRate(cacheTasas.paralelo);
    if (headerEls.fecha && cacheTasas.fecha) {
      headerEls.fecha.textContent = formatDateOnly(cacheTasas.fecha);
    }
    if (headerEls.dashBcv) headerEls.dashBcv.textContent = formatRate(cacheTasas.bcv);
    if (headerEls.dashParalelo) headerEls.dashParalelo.textContent = formatRate(cacheTasas.paralelo);
    document.dispatchEvent(
      new CustomEvent("tasas:actualizadas", { detail: cacheTasas }),
    );
    return cacheTasas;
  } catch (error) {
    console.warn("No se pudieron cargar las tasas", error);
    return cacheTasas;
  }
}

export function getCacheTasas() {
  return cacheTasas;
}

export async function initConfig() {
  await refreshHeaderTasas();
  if (configEls.inputBcv && cacheTasas.bcv) {
    configEls.inputBcv.value = Number(cacheTasas.bcv).toFixed(2);
  }
  if (configEls.inputParalelo && cacheTasas.paralelo) {
    configEls.inputParalelo.value = Number(cacheTasas.paralelo).toFixed(2);
  }
  if (configEls.form) {
    configEls.form.addEventListener("submit", guardarTasas);
  }
  await cargarHistorial();
}

async function guardarTasas(event) {
  event.preventDefault();
  const bcv = Number(configEls.inputBcv?.value || 0);
  const paralelo = Number(configEls.inputParalelo?.value || 0);
  const tareas = [];
  if (bcv > 0) tareas.push(post("/tasa/bcv", { usd_a_ves: bcv }));
  if (paralelo > 0) tareas.push(post("/tasa/paralelo", { usd_a_ves: paralelo }));
  if (!tareas.length) {
    showToast("Indique al menos una tasa válida", "error");
    return;
  }
  try {
    await Promise.all(tareas);
    if (configEls.feedback) {
      configEls.feedback.textContent = `Actualizado: BCV ${formatRate(bcv)} · Paralelo ${formatRate(paralelo)}`;
    }
    showToast("Tasas actualizadas", "success");
    await refreshHeaderTasas();
    await cargarHistorial();
  } catch (error) {
    showToast(`Error guardando tasas: ${error.message}`, "error");
  }
}

async function cargarHistorial() {
  if (!configEls.tabla) return;
  try {
    const tasas = await get("/tasa/");
    if (!tasas.length) {
      configEls.tabla.innerHTML = `<tr><td colspan="3"><div class="empty-state">Sin tasas registradas</div></td></tr>`;
      return;
    }
    configEls.tabla.innerHTML = tasas
      .map(
        (t) => `
        <tr>
          <td>${formatDateOnly(t.fecha)}</td>
          <td><span class="badge ${t.tipo === "bcv" ? "badge-success" : "badge-warning"}">${t.tipo}</span></td>
          <td>${formatRate(t.usd_a_ves)}</td>
        </tr>`,
      )
      .join("");
  } catch (error) {
    configEls.tabla.innerHTML = `<tr><td colspan="3"><div class="empty-state">${error.message}</div></td></tr>`;
  }
}
