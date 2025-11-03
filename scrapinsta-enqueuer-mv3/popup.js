// popup.js
const $ = (sel) => document.querySelector(sel);

function loadSettings() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(
      {
        api_base: "",
        auth_mode: "x-api-key",
        api_token: "",
        x_account: "",
        x_client_id: "",
        default_limit: 50,
      },
      (cfg) => resolve(cfg)
    );
  });
}

function saveSettings(patch) {
  return new Promise((resolve) => {
    chrome.storage.sync.set(patch, () => resolve());
  });
}

async function enqueue() {
  const cfg = await loadSettings();
  const mode = ("#mode" in window ? $("#mode").value : "followings");
  if (!cfg.api_base) return setStatus("Configura la API en Opciones.", true);
  if (!cfg.x_account) return setStatus("Configura tu X-Account en Opciones.", true);

  const headers = { "Content-Type": "application/json", "X-Account": cfg.x_account };
  if (cfg.x_client_id) headers["X-Client-Id"] = cfg.x_client_id;
  if (cfg.auth_mode === "bearer") {
    if (!cfg.api_token) return setStatus("Falta token Bearer en Opciones.", true);
    headers["Authorization"] = "Bearer " + cfg.api_token;
  } else {
    if (!cfg.api_token) return setStatus("Falta X-Api-Key en Opciones.", true);
    headers["X-Api-Key"] = cfg.api_token;
  }

  if (mode === "followings") {
    const target = $("#target").value.trim();
    let limit = parseInt($("#limit").value, 10);
    if (!target) return setStatus("Ingresá un target.", true);
    if (!Number.isFinite(limit) || limit <= 0) limit = cfg.default_limit || 50;
    const url = new URL("/ext/followings/enqueue", cfg.api_base).toString();
    setStatus("Enviando…");
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify({ target_username: target, limit }),
      });
      const text = await resp.text();
      let data; try { data = JSON.parse(text); } catch { data = { raw: text }; }
      if (!resp.ok) {
        console.error("[enqueue followings] HTTP", resp.status, data);
        return setStatus(`Error ${resp.status}: ${data?.detail || text}`, true);
      }
      const jobId = data?.job_id || "(sin id)";
      setStatus(`Encolado ✅ Job: ${jobId}`);
      await saveSettings({ default_limit: limit });
    } catch (e) {
      console.error(e);
      setStatus("Fallo de red/permiso. Revisá permisos de host y URL de API.", true);
    }
    return;
  }

  // analyze
  const raw = $("#usernames").value || "";
  const usernames = raw
    .split(/[\n,]/)
    .map((s) => s.trim().toLowerCase())
    .filter((s) => s.length > 0);
  if (usernames.length === 0) return setStatus("Ingresá al menos un username.", true);
  let batchSize = parseInt($("#batch_size").value, 10);
  if (!Number.isFinite(batchSize) || batchSize <= 0) batchSize = 25;
  const url = new URL("/ext/analyze/enqueue", cfg.api_base).toString();
  setStatus("Enviando…");
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({ usernames, batch_size: batchSize }),
    });
    const text = await resp.text();
    let data; try { data = JSON.parse(text); } catch { data = { raw: text }; }
    if (!resp.ok) {
      console.error("[enqueue analyze] HTTP", resp.status, data);
      return setStatus(`Error ${resp.status}: ${data?.detail || text}`, true);
    }
    const jobId = data?.job_id || "(sin id)";
    setStatus(`Encolado analyze ✅ Job: ${jobId}`);
  } catch (e) {
    console.error(e);
    setStatus("Fallo de red/permiso. Revisá permisos de host y URL de API.", true);
  }
}

function setStatus(msg, isErr = false) {
  const el = $("#status");
  el.textContent = msg;
  el.className = isErr ? "err" : "ok";
}

async function main() {
  const cfg = await loadSettings();
  $("#limit").value = cfg.default_limit || 50;
  $("#target").focus();
  $("#enqueue").addEventListener("click", enqueue);
  const enqueueAnalyzeBtn = $("#enqueue_analyze");
  if (enqueueAnalyzeBtn) enqueueAnalyzeBtn.addEventListener("click", enqueue);
  const modeSel = $("#mode");
  if (modeSel) {
    modeSel.addEventListener("change", () => {
      const m = modeSel.value;
      $("#followings_fields").style.display = m === "followings" ? "block" : "none";
      $("#analyze_fields").style.display = m === "analyze" ? "block" : "none";
    });
  }
  const env = $("#env");
  const clientInfo = cfg.x_client_id ? ` — ClientId: ${cfg.x_client_id}` : "";
  env.textContent = cfg.api_base ? `API: ${cfg.api_base} — Cuenta: ${cfg.x_account || "—"}${clientInfo}` : "API sin configurar";
}

document.addEventListener("DOMContentLoaded", main);
