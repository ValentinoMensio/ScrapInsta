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

function refreshCfgStatus() {
  const base = normalizeBaseUrl($("#api_base")?.value);
  const useJwt = getUseJwt();
  const token = useJwt ? ($("#api_token_jwt")?.value || "").trim() : ($("#api_token")?.value || "").trim();
  const xAcc = ($("#x_account")?.value || "").trim();

  if (!base) return setCfgStatus("err", "Falta API Base");
  if (!token) return setCfgStatus("warn", "Falta token");
  if (!xAcc) return setCfgStatus("warn", "Falta X-Account");
  return setCfgStatus("ok", "Listo");
}

function load() {
  chrome.storage.sync.get(
    {
      api_base: "",
      auth_mode: "x-api-key",
      api_token: "",
      x_account: "",
      x_client_id: "",
      client_id: "",
      default_limit: 50,

      use_jwt: false,
      jwt_token: "",
      jwt_expires_at: 0, // <— popup.js lo usa
    },
    (cfg) => {
      $("#api_base").value = cfg.api_base || "";
      $("#auth_mode").value = cfg.auth_mode || "x-api-key";

      $("#api_token").value = cfg.api_token || "";
      $("#api_token_jwt").value = cfg.api_token || "";

      $("#x_account").value = cfg.x_account || "";
      $("#x_client_id").value = cfg.x_client_id || "";
      $("#default_limit").value = cfg.default_limit || 50;

      $("#use_jwt").checked = !!cfg.use_jwt;
      $("#client_id").value = cfg.client_id || "";

      // Limpio el resultado de login
      if ($("#login_result")) $("#login_result").value = "—";

      updateAuthMode();
      refreshCfgStatus();

      // listeners para status pill live
      ["api_base","api_token","api_token_jwt","x_account","x_client_id","default_limit","auth_mode"].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener("input", refreshCfgStatus);
        if (el) el.addEventListener("change", refreshCfgStatus);
      });
    }
  );
}

function save() {
  const useJwt = getUseJwt();
  const base = normalizeBaseUrl($("#api_base").value);
  const apiToken = (useJwt ? $("#api_token_jwt").value : $("#api_token").value).trim();

  const cfg = {
    api_base: base,
    auth_mode: $("#auth_mode").value,
    api_token: apiToken,

    x_account: $("#x_account").value.trim(),
    x_client_id: $("#x_client_id").value.trim(),

    default_limit: parseInt($("#default_limit").value, 10) || 50,

    use_jwt: useJwt,
    client_id: ($("#client_id")?.value || "").trim(),
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
        api_token: apiKey, // guardo la api_key usada para JWT
        use_jwt: true,
      },
      () => {
        $("#client_id").value = data.client_id || "";
        $("#use_jwt").checked = true;
        updateAuthMode();
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
