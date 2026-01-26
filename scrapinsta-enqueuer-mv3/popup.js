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
        use_jwt: false,
        jwt_token: "",
        jwt_expires_at: 0,
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

async function getJwtToken(apiBase, apiKey) {
  if (!apiBase || !apiKey) return null;
  try {
    const url = new URL("/api/auth/login", apiBase).toString();
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey }),
    });
    if (!resp.ok) {
      console.error("[JWT login] HTTP", resp.status);
      return null;
    }
    const data = await resp.json();
    const expiresIn = data.expires_in || 3600;
    const expiresAt = Date.now() + (expiresIn * 1000);
    await saveSettings({
      jwt_token: data.access_token,
      jwt_expires_at: expiresAt,
      client_id: data.client_id,
    });
    return data.access_token;
  } catch (e) {
    console.error("[JWT login] Error:", e);
    return null;
  }
}

async function getAuthHeaders(cfg) {
  const headers = { "Content-Type": "application/json" };
  
  // Agregar X-Account si está configurado
  if (cfg.x_account) {
    headers["X-Account"] = cfg.x_account;
  }
  
  // Si se usa JWT y tenemos token válido
  if (cfg.use_jwt && cfg.jwt_token && cfg.jwt_expires_at > Date.now()) {
    headers["Authorization"] = `Bearer ${cfg.jwt_token}`;
    return headers;
  }
  
  // Si se usa JWT pero el token expiró o no existe, intentar renovarlo
  if (cfg.use_jwt && cfg.api_token) {
    const token = await getJwtToken(cfg.api_base, cfg.api_token);
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
      return headers;
    }
    // Si falla el login JWT, continuar con API key como fallback
  }
  
  // Usar API key directa (modo tradicional)
  if (cfg.auth_mode === "bearer") {
    if (cfg.api_token) {
      headers["Authorization"] = "Bearer " + cfg.api_token;
    }
  } else {
    if (cfg.api_token) {
      headers["X-Api-Key"] = cfg.api_token;
    }
  }
  
  // X-Client-Id es opcional
  if (cfg.x_client_id) {
    headers["X-Client-Id"] = cfg.x_client_id;
  }
  
  return headers;
}

async function enqueue() {
  const cfg = await loadSettings();
  const mode = ("#mode" in window ? $("#mode").value : "followings");
  if (!cfg.api_base) return setStatus("Configura la API en Opciones.", true);
  if (!cfg.api_token && !cfg.use_jwt) return setStatus("Configura tu API token en Opciones.", true);

  // Obtener headers de autenticación (JWT o API key)
  const headers = await getAuthHeaders(cfg);
  
  // Validar que tenemos algún método de autenticación
  if (!headers["Authorization"] && !headers["X-Api-Key"]) {
    return setStatus("Falta token de autenticación. Configura en Opciones.", true);
  }
  
  // X-Account es requerido solo para followings
  if (mode === "followings" && !cfg.x_account) {
    return setStatus("Configura tu X-Account en Opciones.", true);
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
  const authInfo = cfg.use_jwt ? " (JWT)" : cfg.auth_mode === "bearer" ? " (Bearer)" : " (X-Api-Key)";
  const clientInfo = cfg.x_client_id ? ` — ClientId: ${cfg.x_client_id}` : "";
  const accountInfo = cfg.x_account ? ` — Cuenta: ${cfg.x_account}` : "";
  env.textContent = cfg.api_base 
    ? `API: ${cfg.api_base}${authInfo}${accountInfo}${clientInfo}` 
    : "API sin configurar";
}

document.addEventListener("DOMContentLoaded", main);
