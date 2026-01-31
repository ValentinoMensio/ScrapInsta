// options.js (estilo popup + settings alineados)
const $ = (sel) => document.querySelector(sel);

function setCfgStatus(kind, text) {
  const dot = $("#cfgDot");
  const label = $("#cfgText");
  if (!dot || !label) return;

  dot.classList.remove("ok", "err", "warn");
  if (kind === "ok") dot.classList.add("ok");
  else if (kind === "err") dot.classList.add("err");
  else if (kind === "warn") dot.classList.add("warn");

  label.textContent = text || "—";
}

function setSaveStatus(msg, isErr = false) {
  const el = $("#save_status");
  if (!el) return;
  el.textContent = msg;
  el.className = isErr ? "status-line err" : "status-line ok";
}

function getUseJwt() {
  return !!$("#use_jwt")?.checked;
}

function normalizeBaseUrl(v) {
  const s = (v || "").trim();
  return s.replace(/\/+$/, ""); // sin slash final
}

function updateAuthMode() {
  const useJwt = getUseJwt();
  const authModeGroup = $("#auth_mode_group");
  const jwtInfo = $("#jwt_info");

  if (authModeGroup) authModeGroup.style.display = useJwt ? "none" : "block";
  if (jwtInfo) jwtInfo.style.display = useJwt ? "block" : "none";

  // Sync tokens: solo para que el usuario no se vuelva loco
  const apiToken = ($("#api_token")?.value || "").trim();
  const apiTokenJwt = ($("#api_token_jwt")?.value || "").trim();

  if (useJwt) {
    // si pasé token normal, lo copio al jwt si está vacío
    if (apiToken && !apiTokenJwt) $("#api_token_jwt").value = apiToken;
  } else {
    // si pasé token jwt, lo copio al normal si está vacío
    if (apiTokenJwt && !apiToken) $("#api_token").value = apiTokenJwt;
  }

  refreshCfgStatus();
}

function getClientIdEffective() {
  const src = $("#client_id_source")?.value || "jwt";
  if (src === "manual") return ($("#client_id_manual")?.value || "").trim();
  return ($("#client_id")?.value || "").trim();
}

function updateClientIdUI() {
  const src = $("#client_id_source")?.value || "jwt";
  const jwtGroup = $("#client_id_jwt_group");
  const manualGroup = $("#client_id_manual_group");
  if (jwtGroup) jwtGroup.style.display = src === "jwt" ? "block" : "none";
  if (manualGroup) manualGroup.style.display = src === "manual" ? "block" : "none";
  refreshCfgStatus();
}

function refreshCfgStatus() {
  const base = normalizeBaseUrl($("#api_base")?.value);
  const useJwt = getUseJwt();
  const token = useJwt ? ($("#api_token_jwt")?.value || "").trim() : ($("#api_token")?.value || "").trim();
  const xAcc = ($("#x_account")?.value || "").trim();
  const clientId = getClientIdEffective();

  if (!base) return setCfgStatus("err", "Falta API Base");
  if (!token) return setCfgStatus("warn", "Falta token");
  if (!xAcc) return setCfgStatus("warn", "Falta X-Account");
  if (!clientId) return setCfgStatus("warn", "Falta Client ID");
  return setCfgStatus("ok", "Listo");
}

function load() {
  chrome.storage.sync.get(
    {
      api_base: "",
      auth_mode: "x-api-key",
      api_token: "",
      x_account: "",
      client_id: "",
      client_id_manual: "",
      client_id_source: "jwt",
      default_limit: 50,
      chatgpt_prompt: "",

      use_jwt: false,
      jwt_token: "",
      jwt_expires_at: 0,
    },
    (cfg) => {
      // Migrar x_client_id legacy
      if (cfg.x_client_id) {
        cfg.client_id_manual = cfg.client_id_manual || cfg.x_client_id;
        cfg.client_id_source = "manual";
      }
      $("#api_base").value = cfg.api_base || "";
      $("#auth_mode").value = cfg.auth_mode || "x-api-key";

      $("#api_token").value = cfg.api_token || "";
      $("#api_token_jwt").value = cfg.api_token || "";

      $("#x_account").value = cfg.x_account || "";
      $("#default_limit").value = cfg.default_limit || 50;

      $("#use_jwt").checked = !!cfg.use_jwt;

      // Client ID unificado: migrar x_client_id legacy
      const manualVal = cfg.client_id_manual || cfg.x_client_id || "";
      const jwtVal = cfg.client_id || "";
      $("#client_id_source").value = cfg.client_id_source || "jwt";
      $("#client_id").value = jwtVal;
      $("#client_id_manual").value = manualVal;

      if ($("#login_result")) $("#login_result").value = "—";

      updateAuthMode();
      updateClientIdUI();

      // listeners
      ["api_base","api_token","api_token_jwt","x_account","client_id_manual","default_limit","chatgpt_prompt","auth_mode"].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener("input", refreshCfgStatus);
        if (el) el.addEventListener("change", refreshCfgStatus);
      });
      const srcEl = document.getElementById("client_id_source");
      if (srcEl) srcEl.addEventListener("change", updateClientIdUI);
    }
  );
}

function save() {
  const useJwt = getUseJwt();
  const base = normalizeBaseUrl($("#api_base").value);
  const apiToken = (useJwt ? $("#api_token_jwt").value : $("#api_token").value).trim();
  const clientIdSource = $("#client_id_source")?.value || "jwt";
  const clientIdManual = ($("#client_id_manual")?.value || "").trim();
  const clientIdJwt = ($("#client_id")?.value || "").trim();
  const clientIdEffective = clientIdSource === "manual" ? clientIdManual : clientIdJwt;

  const cfg = {
    api_base: base,
    auth_mode: $("#auth_mode").value,
    api_token: apiToken,

    x_account: $("#x_account").value.trim(),

    client_id: clientIdEffective,
    client_id_manual: clientIdManual,
    client_id_source: clientIdSource,

    default_limit: parseInt($("#default_limit").value, 10) || 50,
    chatgpt_prompt: ($("#chatgpt_prompt").value || "").trim(),

    use_jwt: useJwt,
  };

  chrome.storage.sync.set(cfg, () => {
    setSaveStatus("Guardado ✅");
    refreshCfgStatus();
  });
}

async function testLogin() {
  const base = normalizeBaseUrl($("#api_base").value);
  const apiKey = ($("#api_token_jwt").value || $("#api_token").value).trim();

  if (!base) return ($("#login_result").value = "Configura la API primero.");
  if (!apiKey) return ($("#login_result").value = "Configura el API token primero.");

  const url = new URL("/api/auth/login", base).toString();
  $("#login_result").value = "Probando login…";

  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey }),
    });

    const text = await r.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { raw: text }; }

    if (!r.ok) {
      $("#login_result").value = `Error ${r.status}: ${data?.detail || text}`;
      setCfgStatus("err", "Login JWT falló");
      return;
    }

    const expiresIn = data.expires_in || 3600;
    const expiresAt = Date.now() + (expiresIn * 1000);

    chrome.storage.sync.set(
      {
        jwt_token: data.access_token,
        jwt_expires_at: expiresAt,
        client_id: data.client_id || "",
        client_id_source: "jwt",
        api_token: apiKey,
        use_jwt: true,
      },
      () => {
        $("#client_id").value = data.client_id || "";
        $("#client_id_source").value = "jwt";
        $("#use_jwt").checked = true;
        updateAuthMode();
        updateClientIdUI();
        $("#login_result").value = `✅ Login OK · client_id: ${data.client_id || "—"}`;
        setCfgStatus("ok", "JWT OK");
      }
    );
  } catch (e) {
    console.error(e);
    $("#login_result").value = "Error de red/permisos.";
    setCfgStatus("err", "Sin conexión");
  }
}

async function test() {
  const base = normalizeBaseUrl($("#api_base").value);
  if (!base) return ($("#health_result").value = "Configura la API primero.");

  const url = new URL("/health", base).toString();
  $("#health_result").value = "Probando…";

  try {
    const r = await fetch(url);
    const t = await r.text();
    $("#health_result").value = `HTTP ${r.status} ${t.slice(0, 120)}`;
    if (r.ok) setCfgStatus("ok", "API OK");
    else setCfgStatus("warn", "API responde con error");
  } catch (e) {
    console.error(e);
    $("#health_result").value = "Error de red/permisos (revisá host_permissions).";
    setCfgStatus("err", "Sin conexión");
  }
}

document.addEventListener("DOMContentLoaded", load);
$("#save").addEventListener("click", save);
$("#test").addEventListener("click", test);
$("#test_login").addEventListener("click", testLogin);
$("#use_jwt").addEventListener("change", updateAuthMode);
