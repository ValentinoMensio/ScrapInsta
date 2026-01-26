// options.js
const $ = (sel) => document.querySelector(sel);

function load() {
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
      client_id: "",
    },
    (cfg) => {
      $("#api_base").value = cfg.api_base;
      $("#auth_mode").value = cfg.auth_mode;
      $("#api_token").value = cfg.api_token;
      $("#api_token_jwt").value = cfg.api_token; // Sincronizar
      $("#x_account").value = cfg.x_account;
      $("#x_client_id").value = cfg.x_client_id || "";
      $("#default_limit").value = cfg.default_limit;
      $("#use_jwt").checked = cfg.use_jwt || false;
      $("#client_id").value = cfg.client_id || "";
      updateAuthMode();
    }
  );
}

function updateAuthMode() {
  const useJwt = $("#use_jwt").checked;
  const authModeGroup = $("#auth_mode_group");
  const jwtInfo = $("#jwt_info");
  
  if (useJwt) {
    authModeGroup.style.display = "none";
    jwtInfo.style.display = "block";
    // Sincronizar api_token con api_token_jwt
    const apiToken = $("#api_token").value;
    if (apiToken && !$("#api_token_jwt").value) {
      $("#api_token_jwt").value = apiToken;
    }
  } else {
    authModeGroup.style.display = "block";
    jwtInfo.style.display = "none";
    // Sincronizar api_token_jwt con api_token
    const apiTokenJwt = $("#api_token_jwt").value;
    if (apiTokenJwt && !$("#api_token").value) {
      $("#api_token").value = apiTokenJwt;
    }
  }
}

function save() {
  const useJwt = $("#use_jwt").checked;
  const apiToken = useJwt ? $("#api_token_jwt").value.trim() : $("#api_token").value.trim();
  
  const cfg = {
    api_base: $("#api_base").value.trim(),
    auth_mode: $("#auth_mode").value,
    api_token: apiToken,
    x_account: $("#x_account").value.trim(),
    x_client_id: $("#x_client_id").value.trim(),
    default_limit: parseInt($("#default_limit").value, 10) || 50,
    use_jwt: useJwt,
    client_id: $("#client_id").value.trim(),
  };
  chrome.storage.sync.set(cfg, () => {
    alert("Guardado ✅");
  });
}

async function testLogin() {
  const base = $("#api_base").value.trim();
  const apiKey = $("#api_token_jwt").value.trim() || $("#api_token").value.trim();
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
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text };
    }
    
    if (!r.ok) {
      $("#login_result").value = `Error ${r.status}: ${data?.detail || text}`;
      return;
    }
    
    // Guardar token y client_id
    const expiresIn = data.expires_in || 3600;
    const expiresAt = Date.now() + (expiresIn * 1000);
    chrome.storage.sync.set({
      jwt_token: data.access_token,
      jwt_expires_at: expiresAt,
      client_id: data.client_id,
    }, () => {
      $("#client_id").value = data.client_id;
      $("#login_result").value = `✅ Login exitoso! Client ID: ${data.client_id}`;
    });
  } catch (e) {
    $("#login_result").value = "Error de red/permisos.";
    console.error(e);
  }
}

async function test() {
  const base = $("#api_base").value.trim();
  if (!base) return ($("#health_result").value = "Configura la API primero.");
  const url = new URL("/health", base).toString();
  $("#health_result").value = "Probando…";
  try {
    const r = await fetch(url);
    const t = await r.text();
    $("#health_result").value = `HTTP ${r.status} ${t.slice(0, 80)}`;
  } catch (e) {
    $("#health_result").value = "Error de red/permisos (revisá host_permissions).";
  }
}

$("#save").addEventListener("click", save);
$("#test").addEventListener("click", test);
$("#test_login").addEventListener("click", testLogin);
$("#use_jwt").addEventListener("change", updateAuthMode);
document.addEventListener("DOMContentLoaded", load);
