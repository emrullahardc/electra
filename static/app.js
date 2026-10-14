/**
 * ElectroStock Web Arayüzü JavaScript Mantığı
 */

const CATEGORY_NAMES = {
  resistor: "Direnç",
  capacitor: "Kondansatör",
  diode_led: "Diyot & LED",
  transistor: "Transistör & MOSFET",
  ic_mcu: "Entegre & MCU",
  sensor: "Sensör",
  module: "Modül & Kart",
  connector: "Konnektör & Kablo",
  power: "Güç & Batarya",
  passive_other: "Pasif & Diğer",
  broken_scrap: "Arızalı / Çıkma"
};

const STATUS_CONFIG = {
  working: { text: "Sağlam", class: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30", icon: "fa-circle-check" },
  defective: { text: "Arızalı", class: "bg-rose-500/10 text-rose-400 border-rose-500/30", icon: "fa-triangle-exclamation" },
  untested: { text: "Test Bekliyor", class: "bg-amber-500/10 text-amber-400 border-amber-500/30", icon: "fa-clock" },
  salvage: { text: "Çıkma/Hurda", class: "bg-orange-500/10 text-orange-400 border-orange-500/30", icon: "fa-recycle" }
};

let currentTab = "inventory";
let searchTimer = null;
let allComponentsCache = [];

// Fetch Interceptor: Her isteğe otomatik Bearer token ekler ve 401 durumunda login ekranını açar
const originalFetch = window.fetch;
window.fetch = async function(input, init) {
  init = init || {};
  
  const token = localStorage.getItem("electra_auth_token");
  if (token) {
    if (typeof input === "object" && input instanceof Request) {
      if (!input.headers.has("Authorization")) {
        input.headers.set("Authorization", `Bearer ${token}`);
      }
    } else {
      if (!init.headers) {
        init.headers = {};
      }
      if (init.headers instanceof Headers) {
        if (!init.headers.has("Authorization")) {
          init.headers.set("Authorization", `Bearer ${token}`);
        }
      } else if (Array.isArray(init.headers)) {
        init.headers.push(["Authorization", `Bearer ${token}`]);
      } else {
        if (!init.headers["Authorization"]) {
          init.headers["Authorization"] = `Bearer ${token}`;
        }
      }
    }
  }

  const res = await originalFetch(input, init);

  if (res.status === 401) {
    let urlStr = "";
    if (typeof input === "string") urlStr = input;
    else if (input instanceof URL) urlStr = input.pathname;
    else if (typeof input === "object" && input) urlStr = input.url || input.href || "";

    if (!urlStr.includes("/api/auth/login") && !urlStr.includes("/api/auth/check")) {
      console.warn("401 Unauthorized for URL:", urlStr);
      localStorage.removeItem("electra_auth_token");
      showLoginScreen("Oturum süreniz doldu veya giriş yapmanız gerekiyor.");
    }
  }
  return res;
};

document.addEventListener("DOMContentLoaded", async () => {
  await checkAuthStatus();
});

async function checkAuthStatus() {
  try {
    const res = await fetch("/api/auth/check");
    const data = await res.json();
    if (data.authenticated) {
      hideLoginScreen(data.username);
      loadStats();
      loadComponents();
      loadCartBadge();
      loadDraftsBadge();

      if (window.location.hash === "#developer" || window.location.pathname === "/developer") {
        switchTab("developer");
      }
    } else {
      showLoginScreen();
    }
  } catch (err) {
    showLoginScreen();
  }
}

function showLoginScreen(errorMsg = "") {
  const screen = document.getElementById("login-screen");
  if (screen) {
    screen.style.setProperty("display", "flex", "important");
    screen.classList.remove("hidden");
  }
  const badge = document.getElementById("auth-user-badge");
  if (badge) badge.classList.add("hidden");
  
  const errBox = document.getElementById("login-error-box");
  const errMsgSpan = document.getElementById("login-error-msg");
  if (errorMsg && errBox && errMsgSpan) {
    errMsgSpan.innerText = errorMsg;
    errBox.classList.remove("hidden");
  } else if (errBox) {
    errBox.classList.add("hidden");
  }
}

function hideLoginScreen(username = "admin") {
  const screen = document.getElementById("login-screen");
  if (screen) {
    screen.style.setProperty("display", "none", "important");
    screen.classList.add("hidden");
  }
  const badge = document.getElementById("auth-user-badge");
  if (badge) badge.classList.remove("hidden");
  const userSpan = document.getElementById("current-username");
  if (userSpan) userSpan.innerText = username;
}

async function handleLoginSubmit(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const usernameInput = document.getElementById("login-username");
  const passwordInput = document.getElementById("login-password");
  const errBox = document.getElementById("login-error-box");
  const errMsg = document.getElementById("login-error-msg");
  const submitBtn = document.getElementById("login-submit-btn");

  const username = usernameInput ? usernameInput.value.trim() : "admin";
  const password = passwordInput ? passwordInput.value : "";

  if (!username || !password) return false;

  submitBtn.disabled = true;
  submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Giriş Yapılıyor...';
  if (errBox) errBox.classList.add("hidden");

  try {
    const res = await originalFetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      localStorage.setItem("electra_auth_token", data.token);
      hideLoginScreen(data.username);
      showToast(`Hoş geldin, ${data.username}! Giriş başarılı.`);
      loadStats();
      loadComponents();
      loadCartBadge();
      loadDraftsBadge();
    } else {
      if (errBox) errBox.classList.remove("hidden");
      if (errMsg) errMsg.innerText = data.error || "Giriş başarısız. Lütfen bilgilerinizi kontrol edin.";
    }
  } catch (err) {
    console.error("Login hatası:", err);
    if (errBox) errBox.classList.remove("hidden");
    if (errMsg) errMsg.innerText = "Sunucuya bağlanılamadı. Lütfen tekrar deneyin.";
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = '<i class="fa-solid fa-arrow-right-to-bracket"></i> <span>Giriş Yap</span>';
  }
  return false;
}

async function logout() {
  if (!confirm("Oturumu kapatmak istediğinizden emin misiniz?")) return;
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch (err) {}
  localStorage.removeItem("electra_auth_token");
  showLoginScreen("Oturum kapatıldı.");
}

function openChangePasswordModal() {
  document.getElementById("change-password-modal").classList.remove("hidden");
  document.getElementById("change-password-form").reset();
  document.getElementById("cp-error-box").classList.add("hidden");
}

function closeChangePasswordModal() {
  document.getElementById("change-password-modal").classList.add("hidden");
}

async function handleChangePasswordSubmit(e) {
  e.preventDefault();
  const oldPass = document.getElementById("cp-old-password").value;
  const newPass = document.getElementById("cp-new-password").value;
  const confirmPass = document.getElementById("cp-confirm-password").value;
  const errBox = document.getElementById("cp-error-box");
  const errMsg = document.getElementById("cp-error-msg");

  if (newPass !== confirmPass) {
    errBox.classList.remove("hidden");
    errMsg.innerText = "Yeni şifreler birbiriyle eşleşmiyor!";
    return;
  }

  try {
    const res = await fetch("/api/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_password: oldPass, new_password: newPass })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      closeChangePasswordModal();
      showToast("Şifreniz başarıyla güncellendi!");
    } else {
      errBox.classList.remove("hidden");
      errMsg.innerText = data.error || "Şifre güncellenemedi.";
    }
  } catch (err) {
    errBox.classList.remove("hidden");
    errMsg.innerText = "Sunucu hatası oluştu.";
  }
}

function togglePasswordVisibility(inputId) {
  const input = document.getElementById(inputId);
  const icon = document.getElementById(`${inputId}-eye`);
  if (!input) return;
  if (input.type === "password") {
    input.type = "text";
    if (icon) {
      icon.classList.remove("fa-eye");
      icon.classList.add("fa-eye-slash");
    }
  } else {
    input.type = "password";
    if (icon) {
      icon.classList.remove("fa-eye-slash");
      icon.classList.add("fa-eye");
    }
  }
}


// Sekme Değiştirme
function switchTab(tabId) {
  currentTab = tabId;
  document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active-tab"));
  document.querySelectorAll(".tab-content").forEach(c => c.classList.add("hidden"));

  const targetBtn = document.getElementById(`tab-btn-${tabId}`);
  if (targetBtn) targetBtn.classList.add("active-tab");

  const targetContent = document.getElementById(`tab-${tabId}`);
  if (targetContent) targetContent.classList.remove("hidden");

  if (tabId === "inventory") loadComponents();
  else if (tabId === "defective") loadDefectiveComponents();
  else if (tabId === "lowstock") loadLowStockComponents();
  else if (tabId === "cart") loadCart();
  else if (tabId === "drafts") loadDraftOrders();
}


// İstatistikleri Yükle
async function loadStats() {
  try {
    const res = await fetch("/api/stats");
    const data = await res.json();

    document.getElementById("stat-total-items").innerText = data.total_items || 0;
    document.getElementById("stat-total-qty").innerText = data.total_quantity || 0;
    document.getElementById("stat-working-count").innerText = data.working_count || 0;
    document.getElementById("stat-defective-count").innerText = data.defective_count || 0;
    document.getElementById("stat-low-stock-count").innerText = data.low_stock_count || 0;

    document.getElementById("badge-defective-count").innerText = data.defective_count || 0;
    document.getElementById("badge-lowstock-count").innerText = data.low_stock_count || 0;

    // Lokasyon Filtrelerini Doldur
    const locSelect = document.getElementById("filter-location");
    const currentLoc = locSelect.value;
    locSelect.innerHTML = '<option value="all">Tüm Saklama Yerleri</option>';
    if (data.locations) {
      data.locations.forEach(loc => {
        const opt = document.createElement("option");
        opt.value = loc;
        opt.innerText = loc;
        locSelect.appendChild(opt);
      });
      locSelect.value = currentLoc;
    }
  } catch (err) {
    console.error("İstatistik yüklenirken hata:", err);
  }
}

// Parçaları Yükle ve Filtrele
async function loadComponents() {
  const query = document.getElementById("search-input").value;
  const category = document.getElementById("filter-category").value;
  const status = document.getElementById("filter-status").value;
  const location = document.getElementById("filter-location").value;

  const url = new URL("/api/components", window.location.origin);
  if (query) url.searchParams.set("q", query);
  if (category && category !== "all") url.searchParams.set("category", category);
  if (status && status !== "all") url.searchParams.set("status", status);
  if (location && location !== "all") url.searchParams.set("location", location);

  try {
    const res = await fetch(url);
    const components = await res.json();
    allComponentsCache = components;
    renderComponentsTable(components);
  } catch (err) {
    console.error("Parçalar yüklenirken hata:", err);
  }
}

function debounceSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    loadComponents();
  }, 250);
}

// Parça Tablosunu Render Et
function renderComponentsTable(components) {
  const tbody = document.getElementById("components-tbody");

  if (!components || components.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="py-12 text-center text-slate-500">
          <i class="fa-solid fa-box-open text-3xl mb-2 text-slate-600"></i>
          <p class="font-medium text-slate-400">Aramanıza uygun bileşen bulunamadı</p>
          <p class="text-xs text-slate-500 mt-1">Filtreleri sıfırlayabilir veya yeni parça ekleyebilirsiniz.</p>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = components.map(c => {
    const stConfig = STATUS_CONFIG[c.status] || STATUS_CONFIG.working;
    const catName = CATEGORY_NAMES[c.category] || c.category;
    const isLowStock = c.quantity <= c.min_quantity;

    return `
      <tr class="hover:bg-slate-800/40 transition">
        <td class="py-3 px-4">
          <div class="font-medium text-slate-100 flex items-center gap-2">
            ${c.name}
            ${isLowStock ? '<span class="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">Kritik</span>' : ''}
          </div>
          <div class="text-xs text-slate-400 mt-0.5 flex items-center gap-1.5">
            <span class="px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 text-[11px]">${catName}</span>
            ${c.notes ? `<span class="truncate max-w-[200px] text-slate-500 italic" title="${escapeHtml(c.notes)}">• ${escapeHtml(c.notes)}</span>` : ''}
          </div>
        </td>
        <td class="py-3 px-3 font-mono text-emerald-400">${c.value || '-'}</td>
        <td class="py-3 px-3 text-slate-300 text-xs">${c.package || '-'}</td>
        <td class="py-3 px-3">
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border font-medium ${stConfig.class}">
            <i class="fa-solid ${stConfig.icon} text-[10px]"></i> ${stConfig.text}
          </span>
        </td>
        <td class="py-3 px-3 text-xs text-slate-300">
          ${c.location ? `<span class="flex items-center gap-1"><i class="fa-solid fa-folder-closed text-slate-500"></i> ${escapeHtml(c.location)}</span>` : '<span class="text-slate-600">-</span>'}
        </td>
        <td class="py-3 px-3">
          <div class="flex items-center justify-center gap-1.5">
            <button onclick="adjustQty(${c.id}, -1)" class="w-6 h-6 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center justify-center text-xs transition" title="1 Azalt">-</button>
            <span class="w-8 text-center font-bold ${isLowStock ? 'text-rose-400' : 'text-slate-100'}">${c.quantity}</span>
            <button onclick="adjustQty(${c.id}, 1)" class="w-6 h-6 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center justify-center text-xs transition" title="1 Artır">+</button>
          </div>
        </td>
        <td class="py-3 px-4 text-right space-x-1">
          <button onclick="editComponent(${c.id})" class="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-cyan-400 transition" title="Düzenle">
            <i class="fa-solid fa-pen-to-square"></i>
          </button>
          <button onclick="deleteComponent(${c.id}, '${escapeHtml(c.name)}')" class="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-rose-400 transition" title="Sil">
            <i class="fa-solid fa-trash"></i>
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

// Hızlı Stok Miktarı Değiştirme
async function adjustQty(compId, delta) {
  try {
    const res = await fetch(`/api/components/${compId}/adjust`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ delta, reason: delta > 0 ? "Web Arayüzünden Eklendi" : "Web Arayüzünden Azaltıldı" })
    });
    if (res.ok) {
      loadStats();
      loadComponents();
      showToast(delta > 0 ? "+1 eklendi" : "-1 azaltıldı");
    }
  } catch (err) {
    console.error("Miktar güncellenirken hata:", err);
  }
}

// Parça Silme
async function deleteComponent(compId, name) {
  if (!confirm(`"${name}" adlı parçayı envanterden silmek istediğinize emin misiniz?`)) return;

  try {
    const res = await fetch(`/api/components/${compId}`, { method: "DELETE" });
    if (res.ok) {
      loadStats();
      loadComponents();
      showToast("Parça envanterden silindi");
    }
  } catch (err) {
    console.error("Silme hatası:", err);
  }
}

// Arızalı Parçalar Sekmesini Yükle
async function loadDefectiveComponents() {
  const container = document.getElementById("defective-list-container");
  container.innerHTML = '<div class="col-span-full py-8 text-center text-slate-500"><i class="fa-solid fa-spinner fa-spin text-xl text-amber-500 mb-2"></i><p>Arızalı parçalar listeleniyor...</p></div>';

  try {
    const res = await fetch("/api/defective");
    const items = await res.json();

    if (!items || items.length === 0) {
      container.innerHTML = `
        <div class="col-span-full py-12 text-center text-slate-500">
          <i class="fa-solid fa-circle-check text-3xl mb-2 text-emerald-500"></i>
          <p class="font-medium text-slate-300">Harika! Kayıtlı hiçbir arızalı veya bozuk parçanız yok.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = items.map(item => {
      const stConfig = STATUS_CONFIG[item.status] || STATUS_CONFIG.defective;
      return `
        <div class="bg-slate-900 border border-slate-800 hover:border-amber-500/40 rounded-xl p-4 space-y-3 transition">
          <div class="flex items-start justify-between">
            <div>
              <h4 class="font-bold text-slate-100">${escapeHtml(item.name)}</h4>
              <p class="text-xs text-slate-400">${item.value || 'Değer belirtilmemiş'} • ${item.package || 'Kılıf yok'}</p>
            </div>
            <span class="px-2 py-0.5 rounded text-xs border font-medium ${stConfig.class}">
              ${stConfig.text}
            </span>
          </div>

          <div class="bg-slate-950/70 rounded-lg p-2.5 text-xs text-amber-200/90 border border-amber-500/20">
            <span class="font-semibold text-amber-400 block mb-0.5">Arıza / Durum Notu:</span>
            ${escapeHtml(item.notes || 'Arıza detayı belirtilmemiş')}
          </div>

          <div class="flex items-center justify-between text-xs text-slate-400 pt-2 border-t border-slate-800">
            <span class="flex items-center gap-1.5">
              <i class="fa-solid fa-location-dot text-amber-400"></i> 
              <b>${escapeHtml(item.location || 'Arızalı Kutusu')}</b>
            </span>
            <div class="space-x-1">
              <button onclick="markAsWorking(${item.id})" class="px-2 py-1 rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 transition" title="Tamir edildi olarak işaretle">
                Tamir Edildi
              </button>
              <button onclick="editComponent(${item.id})" class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition">
                Düzenle
              </button>
            </div>
          </div>
        </div>
      `;
    }).join("");
  } catch (err) {
    console.error("Arızalı parçalar yüklenirken hata:", err);
  }
}

// Kritik Stok Sekmesini Yükle
async function loadLowStockComponents() {
  const container = document.getElementById("lowstock-list-container");
  container.innerHTML = '<div class="col-span-full py-8 text-center text-slate-500"><i class="fa-solid fa-spinner fa-spin text-xl text-rose-500 mb-2"></i><p>Kritik stok kontrol ediliyor...</p></div>';

  try {
    const res = await fetch("/api/low-stock");
    const items = await res.json();

    if (!items || items.length === 0) {
      container.innerHTML = `
        <div class="col-span-full py-12 text-center text-slate-500">
          <i class="fa-solid fa-circle-check text-3xl mb-2 text-emerald-500"></i>
          <p class="font-medium text-slate-300">Tüm parçalarınız kritik stok seviyesinin üzerinde!</p>
        </div>
      `;
      return;
    }

    container.innerHTML = items.map(item => {
      return `
        <div class="bg-slate-900 border border-slate-800 hover:border-rose-500/40 rounded-xl p-4 space-y-3 transition">
          <div class="flex items-start justify-between">
            <div>
              <h4 class="font-bold text-slate-100">${escapeHtml(item.name)}</h4>
              <p class="text-xs text-slate-400">${item.value || ''} • ${CATEGORY_NAMES[item.category] || item.category}</p>
            </div>
            <div class="text-right">
              <span class="text-lg font-black text-rose-400">${item.quantity}</span>
              <span class="text-xs text-slate-500 block">Min: ${item.min_quantity}</span>
            </div>
          </div>

          <div class="flex items-center justify-between text-xs text-slate-400 pt-2 border-t border-slate-800">
            <span>Konum: <b>${escapeHtml(item.location || 'Belirtilmemiş')}</b></span>
            <button onclick="searchRobotistanForPart('${escapeHtml(item.name)}')" class="px-2.5 py-1 rounded bg-orange-500/10 hover:bg-orange-500/20 text-orange-400 border border-orange-500/30 flex items-center gap-1 transition">
              <i class="fa-solid fa-cart-shopping"></i> Robotistan'da Bul
            </button>
          </div>
        </div>
      `;
    }).join("");
  } catch (err) {
    console.error("Kritik stok yüklenirken hata:", err);
  }
}

// Proje Analizi (AI BOM & Robotistan Matcher)
async function analyzeProject() {
  const desc = document.getElementById("project-desc-input").value.trim();
  if (!desc) {
    alert("Lütfen yapmak istediğiniz proje açıklamasını yazın.");
    return;
  }

  const btn = document.getElementById("btn-analyze-project");
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> <span>Stok & Robotistan taranıyor...</span>';

  const resultsWrapper = document.getElementById("project-results-wrapper");
  resultsWrapper.classList.remove("hidden");

  try {
    const res = await fetch("/api/match-project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_description: desc, check_robotistan: true })
    });
    if (!res.ok) {
      const errText = await res.text();
      let errMsg = `Sunucu hatası (${res.status})`;
      try {
        const errJson = JSON.parse(errText);
        if (errJson.error) errMsg = errJson.error;
      } catch (_) {}
      throw new Error(errMsg);
    }
    const analysis = await res.json();

    // 1. Sağlam Olanlar
    const workingList = document.getElementById("project-working-list");
    if (!analysis.available_working || analysis.available_working.length === 0) {
      workingList.innerHTML = '<p class="text-slate-500 col-span-full">Bu proje için stokta doğrudan eşleşen sağlam parça bulunamadı.</p>';
    } else {
      workingList.innerHTML = analysis.available_working.map(aw => `
        <div class="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1">
          <p class="font-semibold text-emerald-400 text-xs">${escapeHtml(aw.required_role)}</p>
          ${aw.matched_parts.map(p => `
            <div class="text-xs text-slate-300 flex items-center justify-between">
              <span>• <b>${escapeHtml(p.name)}</b> (${p.quantity} Adet)</span>
              <span class="text-slate-500 text-[11px]"><i class="fa-solid fa-location-dot"></i> ${escapeHtml(p.location)}</span>
            </div>
          `).join("")}
        </div>
      `).join("");
    }

    // 2. Arızalı Uyarıları
    const defCard = document.getElementById("project-defective-card");
    const defList = document.getElementById("project-defective-list");
    if (!analysis.defective_warnings || analysis.defective_warnings.length === 0) {
      defCard.classList.add("hidden");
    } else {
      defCard.classList.remove("hidden");
      defList.innerHTML = analysis.defective_warnings.map(dw => `
        <div class="bg-amber-950/20 border border-amber-500/30 rounded-lg p-3 space-y-1.5">
          <p class="font-semibold text-amber-300 text-xs">${escapeHtml(dw.required_role)} için arızalı kayıtlarınız var:</p>
          ${dw.parts.map(p => `
            <div class="text-xs text-amber-200/90 pl-2 border-l-2 border-amber-500/50">
              <b>${escapeHtml(p.name)}</b> [${p.status}] • Konum: ${escapeHtml(p.location)}<br>
              <i class="text-slate-400">Arıza Notu: ${escapeHtml(p.notes)}</i>
            </div>
          `).join("")}
        </div>
      `).join("");
    }

    // 3. Eksik Parçalar ve Robotistan Canlı Fiyatları
    const robList = document.getElementById("project-robotistan-list");
    document.getElementById("project-cost-badge").innerText = `Tahmini Robotistan Tutarı: ~${analysis.estimated_robotistan_cost_tl || 0} TL`;

    if (!analysis.missing_items || analysis.missing_items.length === 0) {
      robList.innerHTML = `
        <div class="py-6 text-center text-emerald-400">
          <i class="fa-solid fa-circle-check text-3xl mb-2"></i>
          <p class="font-bold">Elinizdeki stok proje için tamamen yeterli!</p>
          <p class="text-xs text-slate-400 mt-0.5">Hiçbir ek parça satın almanıza gerek yok.</p>
        </div>
      `;
    } else {
      robList.innerHTML = analysis.robotistan_recommendations.map(rec => `
        <div class="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
          <div class="flex items-center justify-between">
            <h5 class="font-bold text-sm text-slate-200 flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-rose-500"></span>
              Eksik Parça: ${escapeHtml(rec.missing_part_role)}
            </h5>
            <span class="text-xs text-slate-400">Arama: "${escapeHtml(rec.searched_query)}"</span>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 pt-1">
            ${rec.found_products && rec.found_products.length > 0 ? rec.found_products.map(p => `
              <div class="bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-lg p-2.5 flex flex-col justify-between">
                <div>
                  <div class="flex items-start justify-between gap-2">
                    <p class="text-xs font-medium text-slate-200 line-clamp-2">${escapeHtml(p.title)}</p>
                    <span class="text-[10px] px-1.5 py-0.5 rounded ${p.in_stock ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'} whitespace-nowrap">
                      ${p.stock_status}
                    </span>
                  </div>
                  <p class="text-sm font-bold text-emerald-400 mt-2">${p.price}</p>
                </div>
                <div class="mt-2.5 flex items-center gap-1.5">
                  <button onclick="addToCartFromProduct('${escapeHtml(p.title)}', '${p.url}', '${p.price}', ${p.price_value || 0}, ${p.product_id || 'null'})" class="flex-1 text-center text-xs py-1.5 px-2 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-medium transition">
                    <i class="fa-solid fa-cart-plus"></i> Sepete Ekle
                  </button>
                  <a href="${p.url}" target="_blank" class="text-center text-xs p-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition" title="Robotistan'da Gör">
                    <i class="fa-solid fa-arrow-up-right-from-square"></i>
                  </a>
                </div>
              </div>
            `).join("") : '<p class="text-xs text-slate-500 col-span-full">Robotistan stoklarında uygun ürün bulunamadı.</p>'}
          </div>
        </div>
      `).join("");
    }

  } catch (err) {
    console.error("Proje analizi hatası:", err);
    alert("Proje analizi sırasında bir hata oluştu: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> <span>Stok & Robotistan\'ı Tara</span>';
  }
}

function fillProjectExample(text) {
  document.getElementById("project-desc-input").value = text;
  analyzeProject();
}

// Robotistan Doğrudan Canlı Arama
async function searchRobotistanDirect() {
  const query = document.getElementById("rob-search-input").value.trim();
  const onlyStock = document.getElementById("rob-only-stock").checked;
  if (!query) return;

  const btn = document.getElementById("btn-rob-search");
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

  const container = document.getElementById("rob-results-container");
  container.innerHTML = '<div class="col-span-full py-12 text-center text-slate-500"><i class="fa-solid fa-spinner fa-spin text-2xl text-orange-500 mb-2"></i><p>Robotistan canlı taranıyor...</p></div>';

  try {
    const url = new URL("/api/robotistan/search", window.location.origin);
    url.searchParams.set("q", query);
    url.searchParams.set("only_in_stock", onlyStock ? "1" : "0");
    url.searchParams.set("limit", "15");

    const res = await fetch(url);
    if (!res.ok) {
      const errText = await res.text();
      let errMsg = `Sunucu hatası (${res.status})`;
      try {
        const errJson = JSON.parse(errText);
        if (errJson.error) errMsg = errJson.error;
      } catch (_) {}
      throw new Error(errMsg);
    }
    const data = await res.json();
    const results = data.results || [];

    if (results.length === 0) {
      container.innerHTML = `
        <div class="col-span-full py-12 text-center text-slate-500">
          <i class="fa-solid fa-box-open text-3xl mb-2 text-slate-600"></i>
          <p class="font-medium text-slate-300">"${escapeHtml(query)}" için Robotistan'da ürün bulunamadı.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = results.map(item => `
      <div class="bg-slate-900 border border-slate-800 hover:border-orange-500/40 rounded-xl p-3.5 flex flex-col justify-between space-y-3 transition">
        <div class="space-y-2">
          <div class="flex items-start justify-between gap-2">
            <h4 class="font-semibold text-slate-200 text-sm line-clamp-2">${escapeHtml(item.title)}</h4>
            <span class="text-[10px] px-2 py-0.5 rounded-full font-medium ${item.in_stock ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'} whitespace-nowrap">
              ${item.stock_status}
            </span>
          </div>
          <p class="text-base font-bold text-emerald-400 font-mono">${item.price}</p>
        </div>

        <div class="pt-2 border-t border-slate-800/80 flex items-center justify-between gap-1.5">
          <button onclick="addToCartFromProduct('${escapeHtml(item.title)}', '${item.url}', '${item.price}', ${item.price_value || 0}, ${item.product_id || 'null'})" class="text-xs px-2.5 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-medium flex items-center gap-1 transition">
            <i class="fa-solid fa-cart-plus"></i> Sepete Ekle
          </button>
          <button onclick="addRobotistanItemToInventory('${escapeHtml(item.title)}')" class="text-xs px-2.5 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition" title="Stoğa Ekle">
            + Stoğa Ekle
          </button>
          <a href="${item.url}" target="_blank" class="text-xs px-2.5 py-1.5 rounded bg-orange-600/20 hover:bg-orange-600/30 text-orange-400 border border-orange-500/30 font-medium flex items-center gap-1 transition" title="Robotistan'da İncele">
            <i class="fa-solid fa-arrow-up-right-from-square"></i>
          </a>
        </div>
      </div>
    `).join("");

  } catch (err) {
    console.error("Robotistan arama hatası:", err);
    container.innerHTML = `<div class="col-span-full py-8 text-center text-rose-400">Arama sırasında bir hata oluştu: ${err.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> Ara';
  }
}

function searchRobotistanForPart(partName) {
  switchTab("robotistan");
  document.getElementById("rob-search-input").value = partName;
  searchRobotistanDirect();
}

function addRobotistanItemToInventory(title) {
  openAddModal();
  document.getElementById("form-name").value = title;
}

// Modal Yönetimi
function openAddModal() {
  document.getElementById("modal-title").innerText = "Yeni Elektronik Parça Ekle";
  document.getElementById("form-comp-id").value = "";
  document.getElementById("component-form").reset();
  document.getElementById("form-quantity").value = 1;
  document.getElementById("form-min-quantity").value = 2;
  document.getElementById("component-modal").classList.remove("hidden");
}

function editComponent(compId) {
  const comp = allComponentsCache.find(c => c.id === compId);
  if (!comp) return;

  document.getElementById("modal-title").innerText = "Elektronik Parçayı Düzenle";
  document.getElementById("form-comp-id").value = comp.id;
  document.getElementById("form-name").value = comp.name;
  document.getElementById("form-category").value = comp.category;
  document.getElementById("form-status").value = comp.status;
  document.getElementById("form-value").value = comp.value || "";
  document.getElementById("form-package").value = comp.package || "";
  document.getElementById("form-quantity").value = comp.quantity;
  document.getElementById("form-min-quantity").value = comp.min_quantity;
  document.getElementById("form-location").value = comp.location || "";
  document.getElementById("form-notes").value = comp.notes || "";

  document.getElementById("component-modal").classList.remove("hidden");
}

function closeModal() {
  document.getElementById("component-modal").classList.add("hidden");
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeModal();
    closeChangePasswordModal();
  }
});

async function markAsWorking(compId) {
  if (!confirm("Bu parçayı tamir edildi / sağlam durumuna geçirmek istediğinize emin misiniz?")) return;
  try {
    const res = await fetch(`/api/components/${compId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "working", notes: "Tamir edildi ve testten geçti." })
    });
    if (res.ok) {
      loadStats();
      loadDefectiveComponents();
      showToast("Parça durumu 'Sağlam' olarak güncellendi");
    }
  } catch (err) {
    console.error("Durum güncelleme hatası:", err);
  }
}

async function saveComponent(e) {
  e.preventDefault();
  const compId = document.getElementById("form-comp-id").value;
  const payload = {
    name: document.getElementById("form-name").value.trim(),
    category: document.getElementById("form-category").value,
    status: document.getElementById("form-status").value,
    value: document.getElementById("form-value").value.trim(),
    package: document.getElementById("form-package").value.trim(),
    quantity: parseInt(document.getElementById("form-quantity").value, 10),
    min_quantity: parseInt(document.getElementById("form-min-quantity").value, 10),
    location: document.getElementById("form-location").value.trim(),
    notes: document.getElementById("form-notes").value.trim()
  };

  try {
    const isEdit = !!compId;
    const url = isEdit ? `/api/components/${compId}` : "/api/components";
    const method = isEdit ? "PUT" : "POST";

    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      closeModal();
      loadStats();
      loadComponents();
      showToast(isEdit ? "Parça güncellendi" : "Yeni parça envantere eklendi");
    } else {
      const err = await res.json();
      alert("Hata: " + (err.error || "Kayıt başarısız"));
    }
  } catch (err) {
    console.error("Kayıt hatası:", err);
  }
}

// Veri Dışa Aktarma
async function exportData() {
  try {
    const res = await fetch("/api/export");
    const data = await res.json();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `electrostock_yedek_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("Veritabanı yedeği indirildi");
  } catch (err) {
    console.error("Export hatası:", err);
  }
}

// Tüm Verileri Sıfırla / Temizle
async function clearAllDataPrompt() {
  const confirmed = confirm("DİKKAT: Veritabanındaki tüm parçalar, stok logları ve kayıtlar kalıcı olarak silinecek. Sıfırdan başlamak için onaylıyor musunuz?");
  if (!confirmed) return;

  try {
    const res = await fetch("/api/clear", { method: "POST" });
    if (res.ok) {
      loadStats();
      loadComponents();
      showToast("Tüm veriler temizlendi, envanter sıfırlandı");
    }
  } catch (err) {
    console.error("Veri temizleme hatası:", err);
  }
}

function showToast(msg) {
  const toast = document.getElementById("toast");
  document.getElementById("toast-text").innerText = msg;
  toast.classList.remove("translate-y-20", "opacity-0");
  setTimeout(() => {
    toast.classList.add("translate-y-20", "opacity-0");
  }, 3000);
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// ==========================================
// 🛒 ROBOTİSTAN ATÖLYE SEPETİ YÖNETİMİ
// ==========================================

let currentCartData = { items: [], total_items_count: 0, total_quantity: 0, total_price_tl: 0 };

async function loadCartBadge() {
  try {
    const res = await fetch("/api/cart");
    const data = await res.json();
    currentCartData = data;
    const badge = document.getElementById("badge-cart-count");
    if (badge) badge.innerText = data.total_quantity || 0;
  } catch (err) {
    console.error("Sepet rozeti yüklenirken hata:", err);
  }
}

async function loadCart() {
  const tbody = document.getElementById("cart-tbody");
  tbody.innerHTML = '<tr><td colspan="5" class="py-8 text-center text-slate-500"><i class="fa-solid fa-spinner fa-spin text-xl text-emerald-500 mb-2"></i><p>Sepet yükleniyor...</p></td></tr>';

  try {
    const res = await fetch("/api/cart");
    const data = await res.json();
    currentCartData = data;

    document.getElementById("cart-summary-items").innerText = data.total_items_count || 0;
    document.getElementById("cart-summary-qty").innerText = data.total_quantity || 0;
    document.getElementById("cart-summary-total").innerText = `${data.total_price_tl || 0} TL`;

    const badge = document.getElementById("badge-cart-count");
    if (badge) badge.innerText = data.total_quantity || 0;

    const items = data.items || [];
    if (items.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" class="py-12 text-center text-slate-500">
            <i class="fa-solid fa-cart-shopping text-3xl mb-2 text-slate-600"></i>
            <p class="font-medium text-slate-300">Sepetiniz şu anda boş.</p>
            <p class="text-xs text-slate-500 mt-1">Robotistan Canlı Arama veya Proje Asistanı üzerinden eksik parçaları ekleyebilirsiniz.</p>
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = items.map(item => {
      const itemTotal = ((item.price_value || 0) * item.quantity).toFixed(2);
      return `
        <tr class="hover:bg-slate-800/40 transition">
          <td class="py-3 px-4">
            <a href="${item.url}" target="_blank" class="font-medium text-slate-100 hover:text-emerald-400 flex items-center gap-1.5 transition">
              ${escapeHtml(item.title)}
              <i class="fa-solid fa-arrow-up-right-from-square text-[10px] text-slate-500"></i>
            </a>
            ${item.product_id ? `<span class="text-[10px] text-slate-500 font-mono">T-Soft PID: ${item.product_id}</span>` : ''}
          </td>
          <td class="py-3 px-3 font-mono text-slate-300 text-xs">${item.price}</td>
          <td class="py-3 px-3">
            <div class="flex items-center justify-center gap-1.5">
              <button onclick="updateCartItemQty(${item.id}, ${item.quantity - 1})" class="w-6 h-6 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center justify-center text-xs transition">-</button>
              <span class="w-8 text-center font-bold text-slate-100">${item.quantity}</span>
              <button onclick="updateCartItemQty(${item.id}, ${item.quantity + 1})" class="w-6 h-6 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center justify-center text-xs transition">+</button>
            </div>
          </td>
          <td class="py-3 px-3 font-mono text-emerald-400 font-bold">${itemTotal} TL</td>
          <td class="py-3 px-4 text-right">
            <button onclick="deleteCartItem(${item.id})" class="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-rose-400 transition" title="Sepetten Çıkar">
              <i class="fa-solid fa-trash"></i>
            </button>
          </td>
        </tr>
      `;
    }).join("");

  } catch (err) {
    console.error("Sepet yükleme hatası:", err);
  }
}

async function addToCartFromProduct(title, url, price, priceValue, productId) {
  try {
    const res = await fetch("/api/cart", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        url,
        price,
        price_value: priceValue,
        product_id: productId,
        quantity: 1
      })
    });
    if (res.ok) {
      loadCartBadge();
      showToast(`🛒 "${title}" sepete eklendi!`);
    }
  } catch (err) {
    console.error("Sepete ekleme hatası:", err);
  }
}

async function updateCartItemQty(cartId, qty) {
  try {
    const res = await fetch(`/api/cart/${cartId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quantity: qty })
    });
    if (res.ok) {
      loadCart();
    }
  } catch (err) {
    console.error("Sepet güncelleme hatası:", err);
  }
}

async function deleteCartItem(cartId) {
  try {
    const res = await fetch(`/api/cart/${cartId}`, { method: "DELETE" });
    if (res.ok) {
      loadCart();
      showToast("Ürün sepetten çıkarıldı");
    }
  } catch (err) {
    console.error("Sepet silme hatası:", err);
  }
}

async function clearCartPrompt() {
  if (!confirm("Sepetteki tüm ürünleri temizlemek istediğinize emin misiniz?")) return;
  try {
    const res = await fetch("/api/cart", { method: "DELETE" });
    if (res.ok) {
      loadCart();
      showToast("Sepet tamamen boşaltıldı");
    }
  } catch (err) {
    console.error("Sepet temizleme hatası:", err);
  }
}

function openAllCartUrls() {
  const items = currentCartData.items || [];
  if (items.length === 0) {
    alert("Sepetinizde ürün bulunmuyor.");
    return;
  }
  items.forEach(item => {
    window.open(item.url, "_blank");
  });
}

function exportToRobotistanCart() {
  const items = currentCartData.items || [];
  if (items.length === 0) {
    alert("Sepetinizde ürün bulunmuyor.");
    return;
  }

  // T-Soft MultiCart script kodu
  const pids = [];
  const qtys = [];
  items.forEach(item => {
    if (item.product_id) {
      pids.push(item.product_id);
      qtys.push(item.quantity);
    }
  });

  const scriptCode = `
// Robotistan.com konsolunda (F12) çalıştırarak tüm ürünleri tek tıkla sepete ekleyin:
const pids = ${JSON.stringify(pids)};
const qtys = ${JSON.stringify(qtys)};
if (typeof addToCart === 'function') {
  addToCart({
    productId: pids,
    variantId: pids.map(() => 0),
    quantity: qtys,
    redirect: '/sepet'
  });
  console.log('Tüm parçalar Robotistan sepetine eklendi!');
} else {
  alert('Lütfen bu kodu www.robotistan.com açıkken çalıştırın.');
}
`.trim();

  // Modal veya prompt ile kullanıcıya seçenek sun
  const bookmarkletCode = `javascript:(function(){const pids=${JSON.stringify(pids)};const qtys=${JSON.stringify(qtys)};if(typeof addToCart==='function'){addToCart({productId:pids,variantId:pids.map(()=>0),quantity:qtys,redirect:'/sepet'});}else{window.location.href='https://www.robotistan.com';}})();`;

  navigator.clipboard.writeText(scriptCode).then(() => {
    alert(
      "⚡ Robotistan Çoklu Sepet Kodu Panoya Kopyalandı!\n\n" +
      "1. Robotistan.com sekmesini açın.\n" +
      "2. F12 (Geliştirici Konsolu) açıp yapıştırın (veya doğrudan sepet linklerini açın).\n" +
      "3. Tüm " + pids.length + " çeşit ürün anında sepetinize yüklenecektir!\n\n" +
      "Şimdi Robotistan açılıyor..."
    );
    window.open("https://www.robotistan.com/sepet", "_blank");
  }).catch(() => {
    window.open("https://www.robotistan.com/sepet", "_blank");
  });
}

// ==========================================
// 📋 DRAFT (TASLAK) SİPARİŞ YÖNETİMİ
// ==========================================

async function loadDraftsBadge() {
  try {
    const res = await fetch("/api/draft-orders");
    const data = await res.json();
    const badge = document.getElementById("badge-drafts-count");
    if (badge) badge.innerText = (data && data.length) ? data.length : 0;
  } catch (err) {
    console.error("Draft rozet hatası:", err);
  }
}

async function loadDraftOrders() {
  const container = document.getElementById("draft-orders-container");
  container.innerHTML = '<div class="py-12 text-center text-slate-500"><i class="fa-solid fa-spinner fa-spin text-2xl text-purple-500 mb-2"></i><p>Taslak siparişler yükleniyor...</p></div>';

  try {
    const res = await fetch("/api/draft-orders");
    const orders = await res.json();

    loadDraftsBadge();

    if (!orders || orders.length === 0) {
      container.innerHTML = `
        <div class="bg-slate-900 border border-slate-800 rounded-xl py-12 px-4 text-center text-slate-500 space-y-2">
          <i class="fa-solid fa-clipboard-question text-4xl mb-2 text-slate-600"></i>
          <p class="font-medium text-slate-300">Henüz kayıtlı bir taslak sipariş listeniz bulunmuyor.</p>
          <p class="text-xs text-slate-400 max-w-md mx-auto">
            AI Asistanına (Cursor, Claude vb.) <i>"Şu proje için eksikleri çıkar ve Robotistan taslak siparişi oluştur"</i> diyebilir veya Proje Asistanı sekmesinden analiz yapıp taslak olarak kaydedebilirsiniz.
          </p>
        </div>
      `;
      return;
    }

    // Her taslağın detayını çekerek kart oluştur
    const orderCards = await Promise.all(orders.map(async (o) => {
      const detailRes = await fetch(`/api/draft-orders/${o.id}`);
      const detail = await detailRes.json();
      const items = detail.items || [];

      const statusMap = {
        draft: { text: "Taslak (Draft)", class: "bg-purple-500/20 text-purple-300 border-purple-500/30" },
        ready: { text: "Sepete Aktarıldı", class: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" },
        ordered: { text: "Sipariş Verildi", class: "bg-cyan-500/20 text-cyan-300 border-cyan-500/30" },
        archived: { text: "Arşiv", class: "bg-slate-700/40 text-slate-400 border-slate-600/30" }
      };
      const st = statusMap[o.status] || statusMap.draft;

      return `
        <div class="bg-slate-900 border border-slate-800 hover:border-purple-500/40 rounded-xl p-5 space-y-4 transition shadow-sm">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
            <div>
              <div class="flex items-center gap-2">
                <h3 class="font-bold text-white text-base">#${o.id} - ${escapeHtml(o.title)}</h3>
                <span class="text-xs px-2 py-0.5 rounded border font-medium ${st.class}">${st.text}</span>
              </div>
              <p class="text-xs text-slate-400 mt-1">${escapeHtml(o.description || 'Açıklama yok')} • <i class="fa-regular fa-clock text-[10px]"></i> ${o.updated_at.slice(0, 16).replace('T', ' ')}</p>
            </div>
            <div class="text-right">
              <span class="text-xl font-bold text-emerald-400">~${o.total_estimated_price || 0} TL</span>
              <span class="text-xs text-slate-500 block">${o.item_count} Kalem (${o.total_quantity} Adet)</span>
            </div>
          </div>

          <!-- Ürün Kalemleri Listesi -->
          <div class="space-y-2">
            <h4 class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Sipariş Edilecek Kalemler:</h4>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
              ${items.map(it => `
                <div class="bg-slate-950 p-2.5 rounded-lg border border-slate-800 flex items-center justify-between gap-2">
                  <div class="min-w-0 flex-1">
                    <p class="font-medium text-slate-200 truncate" title="${escapeHtml(it.title)}">${escapeHtml(it.title)}</p>
                    <div class="flex items-center gap-2 text-[11px] text-slate-400 mt-0.5">
                      <span class="text-emerald-400 font-mono">${it.price || 'Fiyat Yok'}</span>
                      <span>• Adet: <b>${it.quantity}</b></span>
                      ${it.notes ? `<span class="text-slate-500 italic truncate">• ${escapeHtml(it.notes)}</span>` : ''}
                    </div>
                  </div>
                  ${it.url ? `
                    <a href="${it.url}" target="_blank" class="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300" title="Robotistan'da Gör">
                      <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
                    </a>
                  ` : ''}
                </div>
              `).join("")}
            </div>
          </div>

          <!-- Aksiyonlar -->
          <div class="pt-3 border-t border-slate-800 flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <button onclick="applyDraftOrderToCart(${o.id})" class="px-3.5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs flex items-center gap-1.5 shadow transition">
                <i class="fa-solid fa-cart-plus"></i> Bu Listeyi Sepete Aktar
              </button>
            </div>
            <button onclick="deleteDraftOrderPrompt(${o.id})" class="p-2 rounded hover:bg-rose-950/30 text-slate-400 hover:text-rose-400 transition" title="Taslağı Sil">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </div>
      `;
    }));

    container.innerHTML = orderCards.join("");

  } catch (err) {
    console.error("Draft yükleme hatası:", err);
    container.innerHTML = `<div class="py-8 text-center text-rose-400">Taslak siparişler yüklenirken hata oluştu: ${err.message}</div>`;
  }
}

async function applyDraftOrderToCart(draftId) {
  try {
    const res = await fetch(`/api/draft-orders/${draftId}/apply-to-cart`, { method: "POST" });
    const data = await res.json();
    if (data.success) {
      loadCartBadge();
      loadDraftsBadge();
      showToast(data.message || "Taslak sipariş sepete aktarıldı!");
      switchTab("cart");
    } else {
      alert("Hata: " + (data.error || "Aktarım başarısız"));
    }
  } catch (err) {
    console.error("Sepete aktarma hatası:", err);
  }
}

async function deleteDraftOrderPrompt(draftId) {
  if (!confirm(`Draft #${draftId} numaralı taslak sipariş listesini silmek istediğinize emin misiniz?`)) return;
  try {
    const res = await fetch(`/api/draft-orders/${draftId}`, { method: "DELETE" });
    if (res.ok) {
      loadDraftOrders();
      loadDraftsBadge();
      showToast("Taslak sipariş listesi silindi");
    }
  } catch (err) {
    console.error("Taslak silme hatası:", err);
  }
}

async function saveDraftFromAnalysis() {
  if (!window.lastProjectAnalysis || !window.lastProjectAnalysis.missing_items) {
    alert("Kayıt edilecek analiz bulunamadı.");
    return;
  }

  const analysis = window.lastProjectAnalysis;
  const draftItems = [];
  (analysis.robotistan_recommendations || []).forEach(rec => {
    const prods = rec.found_products || [];
    if (prods.length > 0) {
      const best = prods[0];
      draftItems.append ? null : draftItems.push({
        title: best.title,
        product_id: best.product_id,
        url: best.url,
        price: best.price,
        price_value: best.price_value || 0.0,
        quantity: 1,
        in_stock: best.in_stock,
        source: "robotistan",
        notes: `Gereksinim: ${rec.missing_part_role}`
      });
    } else {
      draftItems.push({
        title: rec.missing_part_role,
        source: "other",
        notes: `Robotistan'da stok yok (${rec.searched_query})`
      });
    }
  });

  const title = prompt("Taslak sipariş listesi için bir başlık girin:", `${analysis.project_description.slice(0, 35)}... (BOM)`);
  if (!title) return;

  try {
    const res = await fetch("/api/draft-orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: title.trim(),
        description: analysis.project_description,
        items: draftItems,
        notes: "Proje Asistanı üzerinden kaydedildi."
      })
    });
    const data = await res.json();
    if (data.success) {
      loadDraftsBadge();
      showToast("Taslak sipariş listesi oluşturuldu!");
      switchTab("drafts");
    }
  } catch (err) {
    console.error("Taslak kaydetme hatası:", err);
  }
}


// ==========================================
// KOD & METİN KOPYALAMA YARDIMCILARI (DEVELOPER TAB)
// ==========================================

function copyCode(elementId) {
  const el = document.getElementById(elementId);
  if (!el) return;
  copyText(el.innerText);
}

function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      showToast("Panoya kopyalandı! 📋");
    }).catch(() => fallbackCopy(text));
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  try {
    document.execCommand("copy");
    showToast("Panoya kopyalandı! 📋");
  } catch (err) {
    prompt("Kopyalamak için Ctrl+C tuşlayın:", text);
  }
  document.body.removeChild(textarea);
}



