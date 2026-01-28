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
  
  if (cfg.x_account) {
    headers["X-Account"] = cfg.x_account;
  }
  
  if (cfg.use_jwt && cfg.jwt_token && cfg.jwt_expires_at > Date.now()) {
    headers["Authorization"] = `Bearer ${cfg.jwt_token}`;
    return headers;
  }
  
  if (cfg.use_jwt && cfg.api_token) {
    const token = await getJwtToken(cfg.api_base, cfg.api_token);
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
      return headers;
    }
  }
  
  if (cfg.auth_mode === "bearer") {
    if (cfg.api_token) {
      headers["Authorization"] = "Bearer " + cfg.api_token;
    }
  } else {
    if (cfg.api_token) {
      headers["X-Api-Key"] = cfg.api_token;
    }
  }
  
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

  const headers = await getAuthHeaders(cfg);
  
  if (!headers["Authorization"] && !headers["X-Api-Key"]) {
    return setStatus("Falta token de autenticación. Configura en Opciones.", true);
  }
  
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
      
      if (jobId && jobId !== "(sin id)") {
        showJobStatusSection(jobId);
        setTimeout(async () => {
          await refreshJobStatus();
          startAutoRefresh(5000);
        }, 1000);
      }
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
    const totalItems = data?.total_items || usernames.length;
    setStatus(`Encolado analyze ✅ Job: ${jobId} (${totalItems} perfiles)`);
    
    if (jobId && jobId !== "(sin id)") {
      showJobStatusSection(jobId);
      setTimeout(async () => {
        await refreshJobStatus();
        startAutoRefresh(5000);
      }, 1000);
    }
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

let currentJobId = null;
let statusCheckInterval = null;

function showJobStatusSection(jobId) {
  currentJobId = jobId;
  $("#last_job_id").value = jobId;
  $("#job_status_section").style.display = "block";
  $("#job_progress").style.display = "none";
  chrome.storage.local.set({ last_job_id: jobId });
}

async function fetchJobSummary(cfg, headers, jid) {
  const url = new URL(`/jobs/${encodeURIComponent(jid)}/summary`, cfg.api_base).toString();
  try {
    const resp = await fetch(url, { headers });
    if (!resp.ok) {
      if (resp.status === 401) {
        return { _error: "auth", status: 401 };
      }
      if (resp.status === 404) {
        return { _error: "not_found", status: 404 };
      }
      return null;
    }
    const text = await resp.text();
    try { return JSON.parse(text); } catch { return null; }
  } catch {
    return null;
  }
}

async function checkJobStatus(jobId = null) {
  const cfg = await loadSettings();
  const jid = jobId || currentJobId || $("#last_job_id").value;
  
  if (!jid) {
    setStatus("No hay job para verificar", true);
    return null;
  }
  
  if (!cfg.api_base) {
    setStatus("Configura la API primero", true);
    return null;
  }
  
  const headers = await getAuthHeaders(cfg);
  
  const mainStats = await fetchJobSummary(cfg, headers, jid);
  
  if (mainStats?._error === "auth") {
    setStatus("⚠️ Token expirado. Re-autentica en Opciones.", true);
    if (cfg.use_jwt) {
      await saveSettings({ jwt_token: "", jwt_expires_at: 0 });
    }
    return null;
  }
  
  if (!mainStats || mainStats._error) {
    setStatus(`Job no encontrado: ${jid}`, true);
    return null;
  }
  
  const analyzeJobId = `analyze:${jid}`;
  const analyzeStats = await fetchJobSummary(cfg, headers, analyzeJobId);
  
  const hasAnalyze = analyzeStats && !analyzeStats._error;
  
  const combined = {
    queued: (mainStats.queued || 0) + (hasAnalyze ? (analyzeStats.queued || 0) : 0),
    sent: (mainStats.sent || 0) + (hasAnalyze ? (analyzeStats.sent || 0) : 0),
    ok: (mainStats.ok || 0) + (hasAnalyze ? (analyzeStats.ok || 0) : 0),
    error: (mainStats.error || 0) + (hasAnalyze ? (analyzeStats.error || 0) : 0),
    hasAnalyzeJob: hasAnalyze,
  };
  
  return combined;
}

function updateJobProgress(stats) {
  if (!stats) return;
  
  const queued = stats.queued || 0;
  const sent = stats.sent || 0;
  const ok = stats.ok || 0;
  const error = stats.error || 0;
  const total = queued + sent + ok + error;
  const completed = ok + error;
  const hasAnalyze = stats.hasAnalyzeJob;
  const isFinished = queued === 0 && sent === 0 && total > 0 && hasAnalyze;
  
  $("#stat_queued").textContent = queued;
  $("#stat_sent").textContent = sent;
  $("#stat_ok").textContent = ok;
  $("#stat_error").textContent = error;
  
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
  $("#progress_fill").style.width = `${percent}%`;
  
  let statusText = "";
  if (isFinished) {
    statusText = `✅ Completado: ${ok} OK, ${error} errores`;
    stopAutoRefresh();
  } else if (!hasAnalyze && queued === 0 && sent === 0 && ok > 0) {
    statusText = `⏳ Esperando análisis...`;
  } else if (sent > 0) {
    statusText = `🚀 Procesando: ${completed}/${total} (${percent}%)`;
  } else if (queued > 0) {
    statusText = `⏳ En cola: ${queued} pendientes`;
  } else {
    statusText = `Esperando...`;
  }
  
  $("#progress_text").textContent = statusText;
  $("#job_progress").style.display = "block";
}

async function refreshJobStatus() {
  const stats = await checkJobStatus();
  if (stats) {
    updateJobProgress(stats);
    setStatus(`Actualizado: ${new Date().toLocaleTimeString()}`);
  }
}

function startAutoRefresh(intervalMs = 5000) {
  stopAutoRefresh();
  statusCheckInterval = setInterval(refreshJobStatus, intervalMs);
}

function stopAutoRefresh() {
  if (statusCheckInterval) {
    clearInterval(statusCheckInterval);
    statusCheckInterval = null;
  }
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
  
  const checkStatusBtn = $("#check_status");
  if (checkStatusBtn) {
    checkStatusBtn.addEventListener("click", async () => {
      setStatus("Verificando estado...");
      const stats = await checkJobStatus();
      if (stats) {
        updateJobProgress(stats);
        setStatus(`Actualizado: ${new Date().toLocaleTimeString()}`);
      }
    });
  }
  
  chrome.storage.local.get({ last_job_id: null }, (data) => {
    if (data.last_job_id) {
      showJobStatusSection(data.last_job_id);
    }
  });
  
  const env = $("#env");
  const authInfo = cfg.use_jwt ? " (JWT)" : cfg.auth_mode === "bearer" ? " (Bearer)" : " (X-Api-Key)";
  const clientInfo = cfg.x_client_id ? ` — ClientId: ${cfg.x_client_id}` : "";
  const accountInfo = cfg.x_account ? ` — Cuenta: ${cfg.x_account}` : "";
  env.textContent = cfg.api_base 
    ? `API: ${cfg.api_base}${authInfo}${accountInfo}${clientInfo}` 
    : "API sin configurar";
}

document.addEventListener("DOMContentLoaded", main);
