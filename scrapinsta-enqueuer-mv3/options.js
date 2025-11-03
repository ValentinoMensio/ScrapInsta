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
    },
    (cfg) => {
      $("#api_base").value = cfg.api_base;
      $("#auth_mode").value = cfg.auth_mode;
      $("#api_token").value = cfg.api_token;
      $("#x_account").value = cfg.x_account;
      $("#x_client_id").value = cfg.x_client_id || "";
      $("#default_limit").value = cfg.default_limit;
    }
  );
}

function save() {
  const cfg = {
    api_base: $("#api_base").value.trim(),
    auth_mode: $("#auth_mode").value,
    api_token: $("#api_token").value.trim(),
    x_account: $("#x_account").value.trim(),
    x_client_id: $("#x_client_id").value.trim(),
    default_limit: parseInt($("#default_limit").value, 10) || 50,
  };
  chrome.storage.sync.set(cfg, () => {
    alert("Guardado ✅");
  });
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
document.addEventListener("DOMContentLoaded", load);
