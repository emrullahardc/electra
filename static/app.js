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
  working: { text: "Sağlam", class: "apple-badge apple-badge-green", icon: "fa-circle-check" },
  defective: { text: "Arızalı", class: "apple-badge apple-badge-red", icon: "fa-triangle-exclamation" },
  untested: { text: "Test Bekliyor", class: "apple-badge apple-badge-amber", icon: "fa-clock" },
  salvage: { text: "Çıkma/Hurda", class: "apple-badge apple-badge-default", icon: "fa-recycle" }
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
      loadCartBadge();
      loadDraftsBadge();

      // Kaldığı sekmeyi belirle ve aç
      const tabToOpen = determineInitialTab();
      switchTab(tabToOpen, false);
    } else {
      showLoginScreen();
    }
  } catch (err) {
    showLoginScreen();
  }
}

function determineInitialTab() {
  const VALID_TABS = ["inventory", "defective", "lowstock", "project", "robotistan", "cart", "drafts", "developer"];

  // 1. URL Hash (#drafts, #cart, #developer vb.)
  if (window.location.hash) {
    const hash = window.location.hash.replace("#", "").trim().toLowerCase();
    if (VALID_TABS.includes(hash)) return hash;
  }

  // 2. URL Path (/developer, /drafts vb.)
  const path = window.location.pathname.replace(/^\/+|\/+$/g, "").toLowerCase();
  if (VALID_TABS.includes(path)) return path;

  // 3. LocalStorage
  const savedTab = localStorage.getItem("electra_active_tab");
  if (savedTab && VALID_TABS.includes(savedTab)) {
    return savedTab;
  }

  // 4. Varsayılan Sekme
  return "inventory";
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
function switchTab(tabId, updateUrl = true) {
  const VALID_TABS = ["inventory", "defective", "lowstock", "project", "robotistan", "cart", "drafts", "developer"];
  if (!VALID_TABS.includes(tabId)) tabId = "inventory";

  currentTab = tabId;
  try {
    localStorage.setItem("electra_active_tab", tabId);
  } catch (_) {}

  if (updateUrl) {
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, "", `#${tabId}`);
    } else {
      window.location.hash = tabId;
    }
  }

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

window.addEventListener("hashchange", () => {
  const tab = determineInitialTab();
  if (tab !== currentTab) {
    switchTab(tab, false);
  }
});


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

    // Lokasyon Filtrelerini ve Cache'i Doldur
    cachedLocationStats = data.location_stats || (data.locations || []).map(l => ({ name: l, count: 0 }));
    renderQuickLocationChips();

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
        <td colspan="7" class="py-12 text-center text-[#86868b]">
          <i class="fa-solid fa-box-open text-3xl mb-2 text-[#48484a]"></i>
          <p class="font-medium text-[#f5f5f7]">Aramanıza uygun bileşen bulunamadı</p>
          <p class="text-xs text-[#86868b] mt-1">Filtreleri sıfırlayabilir veya yeni parça ekleyebilirsiniz.</p>
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
      <tr class="hover:bg-white/[0.03] transition">
        <td class="py-3 px-4">
          <div class="font-medium text-white flex items-center gap-2">
            ${c.name}
            ${isLowStock ? '<span class="apple-badge apple-badge-red text-[10px]">Kritik</span>' : ''}
          </div>
          <div class="text-[11px] text-[#8e8e93] mt-0.5 flex items-center gap-1.5">
            <span class="px-1.5 py-0.2 rounded bg-white/5 text-[#a1a1aa] font-mono">${catName}</span>
            ${c.notes ? `<span class="truncate max-w-[200px] text-[#71717a]" title="${escapeHtml(c.notes)}">• ${escapeHtml(c.notes)}</span>` : ''}
          </div>
        </td>
        <td class="py-3 px-3 font-mono text-white/90 font-medium">${c.value || '-'}</td>
        <td class="py-3 px-3 text-[#a1a1aa] text-xs font-mono">${c.package || '-'}</td>
        <td class="py-3 px-3">
          <span class="apple-badge ${stConfig.class}">
            ${stConfig.text}
          </span>
        </td>
        <td class="py-3 px-3 text-xs text-[#a1a1aa]">
          ${c.location ? `<span class="flex items-center gap-1 text-[#d1d1d6]"><i class="fa-solid fa-folder-closed text-[#636366]"></i> ${escapeHtml(c.location)}</span>` : '<span class="text-[#636366]">-</span>'}
        </td>
        <td class="py-3 px-3">
          <div class="flex items-center justify-center gap-1">
            <button onclick="adjustQty(${c.id}, -1)" class="w-6 h-6 rounded-md bg-white/5 hover:bg-white/10 text-white flex items-center justify-center text-xs transition select-none flex-shrink-0" title="1 Azalt">-</button>
            <input type="number" min="0" value="${c.quantity}" data-old-qty="${c.quantity}"
                   onfocus="this.select()"
                   onkeydown="if(event.key==='Enter'){this.blur();}"
                   onchange="setDirectQty(${c.id}, this)"
                   class="w-12 h-6 text-center text-xs font-semibold rounded bg-white/5 hover:bg-white/10 focus:bg-[#202024] focus:ring-1 focus:ring-blue-500 border border-transparent hover:border-white/15 focus:border-blue-500/50 ${isLowStock ? 'text-[#ff453a]' : 'text-white'} outline-none transition [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                   title="Doğrudan yeni stok adedini yazabilirsiniz">
            <button onclick="adjustQty(${c.id}, 1)" class="w-6 h-6 rounded-md bg-white/5 hover:bg-white/10 text-white flex items-center justify-center text-xs transition select-none flex-shrink-0" title="1 Artır">+</button>
          </div>
        </td>
        <td class="py-3 px-4 text-right space-x-1">
          <button onclick="openMoveToDefectiveModal(${c.id})" class="p-1.5 rounded-lg text-[#8e8e93] hover:text-amber-400 hover:bg-amber-400/10 transition" title="Bu parçadan arızalı olanı ayır / arızaya taşı">
            <i class="fa-solid fa-triangle-exclamation text-xs"></i>
          </button>
          <button onclick="editComponent(${c.id})" class="p-1.5 rounded-lg text-[#8e8e93] hover:text-white hover:bg-white/10 transition" title="Düzenle">
            <i class="fa-solid fa-pen-to-square text-xs"></i>
          </button>
          <button onclick="deleteComponent(${c.id}, '${escapeHtml(c.name)}')" class="p-1.5 rounded-lg text-[#8e8e93] hover:text-[#ff453a] hover:bg-white/10 transition" title="Sil">
            <i class="fa-solid fa-trash text-xs"></i>
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

// Hızlı Stok Miktarı Değiştirme (+ / -)
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

// Doğrudan Sayı Girerek Stok Güncelleme
async function setDirectQty(compId, inputEl) {
  const newQty = parseInt(inputEl.value, 10);
  const oldQty = parseInt(inputEl.getAttribute("data-old-qty"), 10);

  if (isNaN(newQty) || newQty < 0) {
    inputEl.value = isNaN(oldQty) ? 0 : oldQty;
    return;
  }
  if (newQty === oldQty) return;

  try {
    const res = await fetch(`/api/components/${compId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quantity: newQty })
    });
    if (res.ok) {
      inputEl.setAttribute("data-old-qty", newQty);
      loadStats();
      loadComponents();
      showToast(`Stok güncellendi: ${newQty} adet`);
    } else {
      inputEl.value = oldQty;
      showToast("Stok güncellenemedi", "error");
    }
  } catch (err) {
    console.error("Stok güncellenirken hata:", err);
    inputEl.value = oldQty;
    showToast("Bağlantı hatası", "error");
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
  container.innerHTML = '<div class="col-span-full py-8 text-center text-[#86868b]"><i class="fa-solid fa-spinner fa-spin text-lg mb-2"></i><p class="text-xs">Arızalı parçalar listeleniyor...</p></div>';

  try {
    const res = await fetch("/api/defective");
    const items = await res.json();

    if (!items || items.length === 0) {
      container.innerHTML = `
        <div class="col-span-full py-12 text-center text-[#86868b]">
          <i class="fa-solid fa-circle-check text-2xl mb-2 text-[#30d158]"></i>
          <p class="font-medium text-[#f5f5f7] text-xs">Harika! Kayıtlı hiçbir arızalı veya bozuk parçanız yok.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = items.map(item => {
      const stConfig = STATUS_CONFIG[item.status] || STATUS_CONFIG.defective;
      return `
        <div class="apple-card p-4 space-y-3">
          <div class="flex items-start justify-between gap-2">
            <div>
              <h4 class="font-medium text-white text-xs">${escapeHtml(item.name)}</h4>
              <p class="text-[11px] text-[#8e8e93] font-mono mt-0.5">${item.value || 'Değer belirtilmemiş'} • ${item.package || 'Kılıf yok'}</p>
            </div>
            <span class="apple-badge ${stConfig.class}">
              ${stConfig.text}
            </span>
          </div>

          <div class="bg-white/5 rounded-xl p-2.5 text-xs text-[#d1d1d6] border border-white/5 space-y-0.5">
            <span class="font-medium text-[#ffd60a] text-[11px] block">Arıza / Durum:</span>
            <p class="leading-relaxed text-[#d1d1d6]">${escapeHtml(item.notes || 'Arıza detayı belirtilmemiş')}</p>
          </div>

          <div class="flex items-center justify-between text-xs text-[#8e8e93] pt-2 border-t border-[#242426]">
            <span class="flex items-center gap-1.5 text-[11px]">
              <i class="fa-solid fa-folder text-[#8e8e93]"></i> 
              <span class="text-[#d1d1d6]">${escapeHtml(item.location || 'Arızalı Kutusu')}</span>
            </span>
            <div class="space-x-1">
              <button onclick="markAsWorking(${item.id})" class="apple-btn-secondary text-[11px] px-2.5 py-1" title="Tamir edildi olarak işaretle">
                Tamir Edildi
              </button>
              <button onclick="editComponent(${item.id})" class="apple-btn-secondary text-[11px] px-2 py-1">
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
  container.innerHTML = '<div class="col-span-full py-8 text-center text-[#8e8e93]"><i class="fa-solid fa-spinner fa-spin text-lg mb-2"></i><p class="text-xs">Kritik stok kontrol ediliyor...</p></div>';

  try {
    const res = await fetch("/api/low-stock");
    const items = await res.json();

    if (!items || items.length === 0) {
      container.innerHTML = `
        <div class="col-span-full py-12 text-center text-[#8e8e93]">
          <i class="fa-solid fa-circle-check text-2xl mb-2 text-[#34c759]"></i>
          <p class="font-medium text-white text-xs">Tüm parçalarınız yeterli seviyede.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = items.map(item => {
      return `
        <div class="apple-card p-4 space-y-3">
          <div class="flex items-start justify-between">
            <div>
              <h4 class="font-medium text-white text-xs">${escapeHtml(item.name)}</h4>
              <p class="text-[11px] text-[#8e8e93] font-mono mt-0.5">${item.value || ''} • ${CATEGORY_NAMES[item.category] || item.category}</p>
            </div>
            <div class="text-right">
              <span class="text-lg font-semibold text-[#ff453a] font-mono">${item.quantity}</span>
              <span class="text-[10px] text-[#8e8e93] block">Min: ${item.min_quantity}</span>
            </div>
          </div>

          <div class="flex items-center justify-between text-xs text-[#8e8e93] pt-2 border-t border-[#242426]">
            <span class="text-[11px]">Konum: <b class="text-[#d1d1d6]">${escapeHtml(item.location || 'Belirtilmemiş')}</b></span>
            <button onclick="searchRobotistanForPart('${escapeHtml(item.name)}')" class="apple-btn-primary text-xs px-2.5 py-1">
              <i class="fa-solid fa-cart-shopping text-[10px]"></i> Piyasa Bul
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
      workingList.innerHTML = '<p class="text-[#86868b] text-xs col-span-full py-4 text-center">Bu proje için stokta doğrudan eşleşen sağlam parça bulunamadı.</p>';
    } else {
      workingList.innerHTML = analysis.available_working.map(aw => `
        <div class="apple-card p-3 space-y-1">
          <p class="font-medium text-[#f5f5f7] text-xs">${escapeHtml(aw.required_role)}</p>
          ${aw.matched_parts.map(p => `
            <div class="text-xs text-[#86868b] flex items-center justify-between">
              <span>• <b class="text-[#f5f5f7] font-normal">${escapeHtml(p.name)}</b> (${p.quantity} Adet)</span>
              <span class="text-[#636366] text-[11px]"><i class="fa-solid fa-location-dot"></i> ${escapeHtml(p.location)}</span>
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
        <div class="p-3.5 rounded-xl bg-amber-500/[0.06] border border-amber-500/20 space-y-1.5">
          <p class="font-medium text-amber-300 text-xs">${escapeHtml(dw.required_role)} için arızalı kayıtlarınız var:</p>
          ${dw.parts.map(p => `
            <div class="text-xs text-amber-200/90 pl-2.5 border-l-2 border-amber-500/40">
              <b class="font-medium">${escapeHtml(p.name)}</b> [${p.status}] • Konum: ${escapeHtml(p.location)}<br>
              <i class="text-[#86868b]">Arıza Notu: ${escapeHtml(p.notes)}</i>
            </div>
          `).join("")}
        </div>
      `).join("");
    }

    // 3. Eksik Parçalar ve Robotistan Canlı Fiyatları
    const robList = document.getElementById("project-robotistan-list");
    document.getElementById("project-cost-badge").innerText = `Tahmini Robotistan Tutarı: ~${formatPrice(analysis.estimated_robotistan_cost_tl)}`;

    if (!analysis.missing_items || analysis.missing_items.length === 0) {
      robList.innerHTML = `
        <div class="py-8 text-center text-[#30d158]">
          <i class="fa-solid fa-circle-check text-2xl mb-2"></i>
          <p class="font-medium text-[#f5f5f7]">Elinizdeki stok proje için tamamen yeterli</p>
          <p class="text-xs text-[#86868b] mt-1">Hiçbir ek parça satın almanıza gerek yok.</p>
        </div>
      `;
    } else {
      robList.innerHTML = analysis.robotistan_recommendations.map(rec => `
        <div class="apple-card p-4 space-y-3">
          <div class="flex items-center justify-between">
            <h5 class="font-medium text-sm text-[#f5f5f7] flex items-center gap-2">
              <span class="w-1.5 h-1.5 rounded-full bg-red-400"></span>
              Eksik: ${escapeHtml(rec.missing_part_role)}
            </h5>
            <span class="text-[11px] text-[#86868b] font-mono">"${escapeHtml(rec.searched_query)}"</span>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 pt-1">
            ${rec.found_products && rec.found_products.length > 0 ? rec.found_products.map(p => `
              <div class="apple-card p-3 flex flex-col justify-between hover:border-[#38383a] transition-colors">
                <div>
                  <div class="flex items-start justify-between gap-2">
                    <p class="text-xs font-medium text-[#f5f5f7] line-clamp-2 leading-snug">${escapeHtml(p.title)}</p>
                    <span class="apple-badge ${p.in_stock ? 'apple-badge-green' : 'apple-badge-red'} whitespace-nowrap">
                      ${p.stock_status}
                    </span>
                  </div>
                  <p class="text-sm font-semibold text-[#f5f5f7] font-mono mt-2">${formatPrice(p.price_value || p.price)}</p>
                </div>
                <div class="mt-3 flex items-center gap-2">
                  <button onclick="addToCartFromProduct('${escapeHtml(p.title)}', '${p.url}', '${p.price}', ${p.price_value || 0}, ${p.product_id || 'null'})" class="apple-btn-secondary flex-1 py-1 px-2.5 text-xs font-medium justify-center">
                    <i class="fa-solid fa-cart-plus"></i> Sepete Ekle
                  </button>
                  <a href="${p.url}" target="_blank" class="apple-btn-secondary px-2.5 py-1 text-xs" title="Robotistan'da Gör">
                    <i class="fa-solid fa-arrow-up-right-from-square"></i>
                  </a>
                </div>
              </div>
            `).join("") : '<p class="text-xs text-[#86868b] col-span-full py-2">Robotistan stoklarında uygun ürün bulunamadı.</p>'}
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

// Türkiye Pazarı & Çoklu Tedarikçi Canlı Arama (Robotronik, Robotistan, Direnç.net, Motorobit)
async function searchRobotistanDirect() {
  const query = document.getElementById("rob-search-input").value.trim();
  const onlyStock = document.getElementById("rob-only-stock").checked;
  const vendorSelect = document.getElementById("market-vendor-select");
  const vendor = vendorSelect ? vendorSelect.value : "all";

  if (!query) return;

  const btn = document.getElementById("btn-rob-search");
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

  const container = document.getElementById("rob-results-container");
  container.innerHTML = `
    <div class="col-span-full py-12 text-center text-[#86868b]">
      <i class="fa-solid fa-spinner fa-spin text-xl text-[#f5f5f7] mb-2"></i>
      <p class="text-xs">Türkiye pazarı (Robotronik, Robotistan, Direnç.net, Motorobit) taranıyor...</p>
    </div>
  `;

  try {
    const url = new URL("/api/market/search", window.location.origin);
    url.searchParams.set("q", query);
    url.searchParams.set("vendor", vendor);
    url.searchParams.set("only_in_stock", onlyStock ? "1" : "0");
    url.searchParams.set("limit", "8");

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
    window.lastMarketSearch = data;
    const results = data.results || [];
    const decision = data.decision_advice || null;

    if (results.length === 0) {
      container.innerHTML = `
        <div class="col-span-full apple-card py-12 text-center text-[#86868b] space-y-1">
          <i class="fa-solid fa-box-open text-3xl mb-2 text-[#48484a]"></i>
          <p class="font-medium text-[#f5f5f7]">"${escapeHtml(query)}" için seçilen mağazalarda ürün bulunamadı.</p>
          <p class="text-xs text-[#86868b]">Arama filtresini gevşetmeyi veya "Tüm Siteler" seçeneğini deneyebilirsiniz.</p>
        </div>
      `;
      return;
    }

    const vendorStyles = {
      robotronik: { badge: "apple-badge apple-badge-default", name: "Robotronik" },
      robotistan: { badge: "apple-badge apple-badge-default", name: "Robotistan" },
      direnc: { badge: "apple-badge apple-badge-default", name: "Direnç.net" },
      motorobit: { badge: "apple-badge apple-badge-default", name: "Motorobit" }
    };

    // 🎯 Akıllı Satın Alma ve Kargo Karar Kartı (Robotistan Önceliği)
    let adviceHtml = "";
    if (decision && decision.action) {
      if (decision.action === "prefer_robotistan") {
        adviceHtml = `
          <div class="col-span-full apple-card p-4 mb-2 flex items-start gap-3">
            <div class="w-7 h-7 rounded-lg bg-white/10 text-white flex items-center justify-center text-xs flex-shrink-0">
              <i class="fa-solid fa-truck-fast"></i>
            </div>
            <div class="space-y-1 text-xs">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-semibold text-white">Robotistan Tavsiyesi (Aynı Gün Teslimat)</span>
                ${decision.price_diff > 0 ? `<span class="apple-badge apple-badge-default font-mono">Fark: ${decision.price_diff.toFixed(2)} TL (≤100 TL)</span>` : '<span class="apple-badge apple-badge-green font-mono">En Uygun & Aynı Gün</span>'}
              </div>
              <p class="text-[#8e8e93] leading-relaxed">${escapeHtml(decision.summary)}</p>
            </div>
          </div>
        `;
      } else if (decision.action === "ask_user") {
        adviceHtml = `
          <div class="col-span-full apple-card p-4 mb-2 flex items-start gap-3 border-amber-500/30">
            <div class="w-7 h-7 rounded-lg bg-amber-500/10 text-[#ffd60a] flex items-center justify-center text-xs flex-shrink-0">
              <i class="fa-solid fa-scale-balanced"></i>
            </div>
            <div class="space-y-1 text-xs">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-semibold text-white">Fiyat Farkı Uyarısı (>100 TL Tasarruf)</span>
                <span class="apple-badge apple-badge-green font-mono">${escapeHtml(decision.cheapest_vendor)} ${decision.price_diff.toFixed(2)} TL Daha Ucuz</span>
              </div>
              <p class="text-[#8e8e93] leading-relaxed">${escapeHtml(decision.summary)}</p>
              ${decision.prompt_question ? `<p class="text-[#ffd60a] font-medium text-[11px] mt-1">❓ "${escapeHtml(decision.prompt_question)}"` : ''}
            </div>
          </div>
        `;
      } else if (decision.action === "external_vendor") {
        adviceHtml = `
          <div class="col-span-full apple-card p-4 mb-2 flex items-start gap-3">
            <div class="w-7 h-7 rounded-lg bg-white/10 text-white flex items-center justify-center text-xs flex-shrink-0">
              <i class="fa-solid fa-store-slash"></i>
            </div>
            <div class="space-y-1 text-xs">
              <span class="font-semibold text-white">Robotistan Stoklarında Yok</span>
              <p class="text-[#8e8e93] leading-relaxed">${escapeHtml(decision.summary)}</p>
            </div>
          </div>
        `;
      }
    }

    const cardsHtml = results.map(item => {
      const vKey = item.vendor_key || "other";
      const vStyle = vendorStyles[vKey] || { badge: "apple-badge apple-badge-default", name: item.vendor || vKey };
      const isCheap = Boolean(item.is_cheapest);

      return `
        <div class="apple-card p-4 flex flex-col justify-between space-y-3">
          <div class="space-y-2">
            <div class="flex items-center justify-between gap-1.5 flex-wrap">
              <span class="${vStyle.badge}">
                ${vStyle.name}
              </span>
              ${isCheap ? `
                <span class="apple-badge apple-badge-green">
                  ⭐ En Uygun
                </span>
              ` : ''}
              <span class="text-[10px] text-[#8e8e93] font-medium ml-auto">
                ${item.in_stock ? '🟢 Stokta' : '🔴 Tükendi'}
              </span>
            </div>

            <h4 class="font-medium text-white text-xs line-clamp-2" title="${escapeHtml(item.title)}">
              ${escapeHtml(item.title)}
            </h4>

            <p class="text-sm font-semibold text-white font-mono">
              ${formatPrice(item.price_value || item.price)}
            </p>
          </div>

          <div class="pt-2 border-t border-[#242426] flex flex-wrap items-center justify-between gap-1.5">
            <div class="flex items-center gap-1.5 flex-wrap">
              ${vKey === 'robotistan' ? `
                <button onclick="addToCartFromProduct('${escapeHtml(item.title).replace(/'/g, "\\'")}', '${item.url}', '${item.price}', ${item.price_value || 0}, ${item.product_id || 'null'})" class="apple-btn-primary text-xs px-2.5 py-1" title="Robotistan Sepetine Ekle">
                  <i class="fa-solid fa-cart-plus text-[10px]"></i> Sepete
                </button>
              ` : ''}
              <button onclick="quickAddMarketItemToDraft('${escapeHtml(item.title).replace(/'/g, "\\'")}', '${item.url}', ${item.price_value || 0}, '${vKey}')" class="apple-btn-secondary text-xs px-2.5 py-1" title="Bu ürünü taslak sipariş listesine ekle">
                <i class="fa-solid fa-clipboard-list text-[10px]"></i> Taslağa Ekle
              </button>
              <button onclick="addRobotistanItemToInventory('${escapeHtml(item.title).replace(/'/g, "\\'")}')" class="p-1 rounded-lg text-[#8e8e93] hover:text-white hover:bg-white/5 text-xs transition" title="Atölye Envanterine Ekle">
                + Stoğa
              </button>
            </div>
            <a href="${item.url}" target="_blank" class="text-[#8e8e93] hover:text-white text-xs p-1 rounded-lg hover:bg-white/5 transition ml-auto" title="Mağaza Sayfasını Aç">
              <i class="fa-solid fa-arrow-up-right-from-square text-[11px]"></i>
            </a>
          </div>
        </div>
      `;
    }).join("");

    container.innerHTML = adviceHtml + cardsHtml;

  } catch (err) {
    console.error("Piyasa arama hatası:", err);
    container.innerHTML = `<div class="col-span-full py-8 text-center text-rose-400">Arama sırasında bir hata oluştu: ${err.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> Ara & Kıyasla';
  }
}

async function quickAddMarketItemToDraft(title, url, priceVal, vendorKey) {
  try {
    // ⚡ Robotistan Önceliği ve Kargo Maliyeti Kontrolü
    if (vendorKey !== 'robotistan' && window.lastMarketSearch && window.lastMarketSearch.decision_advice) {
      const adv = window.lastMarketSearch.decision_advice;
      if (adv.action === 'prefer_robotistan' && adv.robotistan_price) {
        const confirmChoice = confirm(
          `⚡ Kargo ve Hız Avantajı Hatırlatması:\n\n` +
          `Bu parça Robotistan'da aynı gün kargo avantajıyla ${formatPrice(adv.robotistan_price)} tutarındadır.\n` +
          `Seçilen ${vendorKey.toUpperCase()} ile aradaki fark sadece ${adv.price_diff.toFixed(2)} TL'dir (≤100 TL).\n\n` +
          `Diğer mağazalarda minimum 40-75 TL kargo ücreti ekleneceğinden toplamda Robotistan daha avantajlıdır.\n\n` +
          `Yine de ${vendorKey.toUpperCase()} mağazasını taslağa eklemek istiyor musunuz?\n` +
          `(İptal ederseniz Robotistan seçeneğini eklemeyi önereceğiz)`
        );
        if (!confirmChoice) {
          const robItem = window.lastMarketSearch.robotistan_option;
          if (robItem && confirm(`Bunun yerine Robotistan seçeneğini (${formatPrice(robItem.price_value)}) taslağa eklemek ister misiniz?`)) {
            title = robItem.title;
            url = robItem.url;
            priceVal = robItem.price_value;
            vendorKey = "robotistan";
          } else {
            return;
          }
        }
      }
    }

    const res = await fetch("/api/draft-orders");
    const drafts = await res.json();
    if (!drafts || drafts.length === 0) {
      alert("Önce 'Draft Siparişler' sekmesinden bir taslak oluşturmalısınız.");
      return;
    }

    // En son güncellenen aktif taslağa ekle (veya tek taslak varsa direkt ona)
    let targetDraft = drafts[0];
    if (drafts.length > 1) {
      const options = drafts.map(d => `#${d.id}: ${d.title}`).join("\n");
      const chosenId = prompt(`Bu ürünü hangi taslağa eklemek istersiniz?\n\nMevcut Taslaklar:\n${options}\n\nLütfen Taslak ID numarasını girin:`, targetDraft.id);
      if (!chosenId) return;
      const found = drafts.find(d => String(d.id) === String(chosenId).trim());
      if (found) targetDraft = found;
    }

    const payload = {
      title,
      url,
      quantity: 1,
      source: vendorKey || "market",
      price_value: priceVal,
      price: priceVal > 0 ? `${priceVal.toFixed(2)} TL` : "",
      in_stock: true,
      notes: `${vendorKey.toUpperCase()} üzerinden eklendi`
    };

    const addRes = await fetch(`/api/draft-orders/${targetDraft.id}/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const addData = await addRes.json();
    if (addRes.ok && addData.success) {
      showToast(`"${title}" [#${targetDraft.id} ${targetDraft.title}] taslağına eklendi ✨`);
      loadDraftsBadge();
    } else {
      alert("Hata: " + (addData.error || "Kalem eklenemedi"));
    }
  } catch (err) {
    console.error("Taslağa hızlı ekleme hatası:", err);
    alert("Hata: " + err.message);
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

// Modal Yönetimi & LiveSearch Otomatik Doldurma
let liveSearchDebounceTimer = null;
let liveSearchSelectedIndex = -1;
let currentSuggestions = [];
let lastLiveSearchTypedQuery = "";
let selectedQuickStockItem = null;

function closeFormNameSuggestions() {
  const container = document.getElementById("form-name-suggestions");
  if (container) {
    container.classList.add("hidden");
    container.innerHTML = "";
  }
  const spinner = document.getElementById("form-name-spinner");
  if (spinner) spinner.classList.add("hidden");
  liveSearchSelectedIndex = -1;
  currentSuggestions = [];
}

function dismissFormNameWarning() {
  const w = document.getElementById("form-name-warning");
  if (w) w.classList.add("hidden");
}

function showQuickStockView(item) {
  if (!item) return;
  selectedQuickStockItem = item;

  document.getElementById("quick-stock-id").innerText = item.id;
  document.getElementById("quick-stock-name").innerText = item.name;

  const catLabel = item.category_label || CATEGORY_NAMES[item.category] || item.category || "";
  const detailsParts = [];
  if (catLabel) detailsParts.push(catLabel);
  if (item.package) detailsParts.push(`Kılıf: ${item.package}`);
  if (item.value) detailsParts.push(`Değer: ${item.value}`);
  document.getElementById("quick-stock-details").innerText = detailsParts.join(" • ");

  const locEl = document.getElementById("quick-stock-location");
  if (item.location) {
    locEl.innerHTML = `<i class="fa-solid fa-folder-closed text-xs"></i> <span>Saklama Yeri: <b class="text-white">${escapeHtml(item.location)}</b></span>`;
    locEl.classList.remove("hidden");
  } else {
    locEl.innerHTML = `<span class="text-[#71717a]">Saklama yeri belirtilmemiş</span>`;
    locEl.classList.remove("hidden");
  }

  const currentQty = parseInt(item.quantity, 10) || 0;
  document.getElementById("quick-stock-current").innerText = currentQty;

  const addQtyInput = document.getElementById("quick-stock-add-qty");
  addQtyInput.value = 1;
  updateQuickStockPreview();

  // Modal başlığı ve form görünürlüğünü güncelle
  document.getElementById("modal-title").innerHTML = `<i class="fa-solid fa-boxes-stacked text-emerald-400 mr-2"></i> Envanterdeki Parçaya Stok Ekle`;
  document.getElementById("component-form").classList.add("hidden");
  document.getElementById("modal-quick-stock").classList.remove("hidden");

  closeFormNameSuggestions();

  setTimeout(() => {
    addQtyInput.focus();
    addQtyInput.select();
  }, 50);
}

function updateQuickStockPreview() {
  if (!selectedQuickStockItem) return;
  const current = parseInt(selectedQuickStockItem.quantity, 10) || 0;
  const addVal = parseInt(document.getElementById("quick-stock-add-qty").value, 10) || 0;
  const newTotal = Math.max(0, current + addVal);
  const previewEl = document.getElementById("quick-stock-preview");
  if (previewEl) {
    previewEl.innerHTML = `Yeni toplam stok: <b class="text-white">${newTotal} adet</b> olacak (${current} mevcut + ${addVal} yeni).`;
  }
}

async function submitQuickStockAdd() {
  if (!selectedQuickStockItem) return;
  const addVal = parseInt(document.getElementById("quick-stock-add-qty").value, 10);
  if (isNaN(addVal) || addVal <= 0) {
    alert("Lütfen eklenecek geçerli bir adet giriniz (en az 1).");
    return;
  }

  const btn = document.getElementById("quick-stock-submit-btn");
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`/api/components/${selectedQuickStockItem.id}/adjust`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        delta: addVal,
        reason: "Envanter Hızlı Stok Ekleme (+)"
      })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      const newTotal = data.new_quantity !== undefined ? data.new_quantity : ((selectedQuickStockItem.quantity || 0) + addVal);
      showToast(`✓ "${selectedQuickStockItem.name}" stoğuna +${addVal} adet eklendi! (Toplam: ${newTotal})`);
      closeModal();
      loadStats();
      loadComponents();
    } else {
      alert("Hata: " + (data.error || "Stok güncellenemedi"));
    }
  } catch (err) {
    console.error("Hızlı stok ekleme hatası:", err);
    alert("Bağlantı hatası oluştu.");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function cancelQuickStockSelection() {
  // Geri Dön / Yanlış Seçim butonuna basıldığında
  document.getElementById("modal-quick-stock").classList.add("hidden");
  document.getElementById("component-form").classList.remove("hidden");
  document.getElementById("modal-title").innerText = "Yeni Elektronik Parça Ekle";

  // Parça adı alanını kullanıcının son yazdığı metne geri al ve odaklan
  const nameInput = document.getElementById("form-name");
  if (nameInput) {
    nameInput.value = lastLiveSearchTypedQuery || "";
    nameInput.focus();
  }
  selectedQuickStockItem = null;
  showToast("Önceki girişe geri dönüldü");
}

function continueAsNewComponent() {
  // Kullanıcı bu parçayı ayrı bir kayıt olarak eklemek istiyor
  if (!selectedQuickStockItem) return;
  const item = selectedQuickStockItem;

  document.getElementById("modal-quick-stock").classList.add("hidden");
  document.getElementById("component-form").classList.remove("hidden");
  document.getElementById("modal-title").innerText = "Yeni Elektronik Parça Ekle";

  document.getElementById("form-name").value = item.name;
  if (item.category) document.getElementById("form-category").value = item.category;
  if (item.package) document.getElementById("form-package").value = item.package;
  if (item.value) document.getElementById("form-value").value = item.value;

  selectedQuickStockItem = null;
  const qtyInput = document.getElementById("form-quantity");
  if (qtyInput) {
    qtyInput.focus();
    qtyInput.select();
  }
}

function editExistingComponentFromQuickStock() {
  if (!selectedQuickStockItem) return;
  const compId = selectedQuickStockItem.id;
  document.getElementById("modal-quick-stock").classList.add("hidden");
  document.getElementById("component-form").classList.remove("hidden");
  selectedQuickStockItem = null;
  editComponent(compId);
}

function selectLiveSearchItem(item) {
  if (!item) return;

  const isEditMode = !!document.getElementById("form-comp-id").value;

  // Eğer bu parça yerel envanterdeki mevcut bir parçaysa ve yeni ekleme modundaysak:
  // Kafa karıştırıcı form yerine doğrudan adet isteme ekranını göster
  if (item.is_inventory && !isEditMode) {
    showQuickStockView(item);
    return;
  }

  // Standart şablon veya düzenleme modu: form alanlarını doldur
  document.getElementById("form-name").value = item.name;
  if (item.category) {
    const catSelect = document.getElementById("form-category");
    if (catSelect) catSelect.value = item.category;
  }
  if (item.package) {
    const pkgInput = document.getElementById("form-package");
    if (pkgInput) pkgInput.value = item.package;
  }
  if (item.value) {
    const valInput = document.getElementById("form-value");
    if (valInput) valInput.value = item.value;
  }

  dismissFormNameWarning();
  const qtyInput = document.getElementById("form-quantity");
  if (qtyInput) {
    qtyInput.focus();
    qtyInput.select();
  }

  closeFormNameSuggestions();
}

function handleFormNameKeydown(e) {
  const container = document.getElementById("form-name-suggestions");
  if (!container || container.classList.contains("hidden") || currentSuggestions.length === 0) {
    if (e.key === "Escape") closeFormNameSuggestions();
    return;
  }

  const items = container.querySelectorAll(".livesearch-item");
  if (!items.length) return;

  if (e.key === "ArrowDown") {
    e.preventDefault();
    liveSearchSelectedIndex = (liveSearchSelectedIndex + 1) % items.length;
    updateLiveSearchActiveItem(items);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    liveSearchSelectedIndex = (liveSearchSelectedIndex - 1 + items.length) % items.length;
    updateLiveSearchActiveItem(items);
  } else if (e.key === "Enter") {
    if (liveSearchSelectedIndex >= 0 && liveSearchSelectedIndex < currentSuggestions.length) {
      e.preventDefault();
      selectLiveSearchItem(currentSuggestions[liveSearchSelectedIndex]);
    }
  } else if (e.key === "Escape") {
    closeFormNameSuggestions();
  }
}

function updateLiveSearchActiveItem(domItems) {
  domItems.forEach((el, idx) => {
    if (idx === liveSearchSelectedIndex) {
      el.classList.add("bg-white/10", "border-l-2", "border-blue-400");
      el.scrollIntoView({ block: "nearest" });
    } else {
      el.classList.remove("bg-white/10", "border-l-2", "border-blue-400");
    }
  });
}

function renderLiveSearchDropdown(inventoryMatches, catalogSuggestions, query) {
  const container = document.getElementById("form-name-suggestions");
  if (!container) return;

  currentSuggestions = [];
  liveSearchSelectedIndex = -1;

  if (inventoryMatches.length === 0 && catalogSuggestions.length === 0) {
    container.innerHTML = `
      <div class="p-3 text-center text-[#8e8e93] text-[11px]">
        <i class="fa-solid fa-circle-info mr-1"></i> "${escapeHtml(query)}" için standart şablon bulunamadı. Kendi belirlediğiniz isimle ekleyebilirsiniz.
      </div>
    `;
    container.classList.remove("hidden");
    return;
  }

  let html = "";

  // 1. Envanterde Mevcut Parçalar (Mükerrer önleme & Hızlı Stok Ekleme)
  if (inventoryMatches.length > 0) {
    html += `
      <div class="px-3 py-1.5 bg-[#121214] text-[10px] font-semibold text-emerald-400 uppercase tracking-wider flex items-center justify-between">
        <span><i class="fa-solid fa-box mr-1"></i> Envanterinizde Zaten Kayıtlı (${inventoryMatches.length})</span>
        <span class="text-[#71717a] font-normal lowercase">tıklayarak doğrudan adet ekleyin</span>
      </div>
    `;
    inventoryMatches.forEach((inv) => {
      const idx = currentSuggestions.length;
      currentSuggestions.push(inv);
      const locStr = inv.location ? `• Yer: ${escapeHtml(inv.location)}` : "";
      html += `
        <div class="livesearch-item p-2.5 hover:bg-white/5 cursor-pointer flex items-center justify-between gap-2 transition"
             onclick="selectLiveSearchItem(currentSuggestions[${idx}])">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="px-1.5 py-0.2 rounded text-[9px] font-mono font-medium bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
                #${inv.id} • ${inv.quantity} Adet
              </span>
              <p class="font-medium text-white truncate text-xs">${escapeHtml(inv.name)}</p>
            </div>
            <div class="text-[11px] text-[#8e8e93] mt-0.5 flex items-center gap-1.5 flex-wrap">
              <span class="text-white/70">${escapeHtml(inv.category_label || inv.category)}</span>
              ${inv.package ? `<span class="text-[#8e8e93]">• ${escapeHtml(inv.package)}</span>` : ''}
              ${inv.value ? `<span class="text-[#8e8e93]">• ${escapeHtml(inv.value)}</span>` : ''}
              ${locStr ? `<span class="text-emerald-400/80">${locStr}</span>` : ''}
            </div>
          </div>
          <span class="text-[10px] text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 px-2.5 py-1 rounded border border-emerald-500/30 font-medium flex items-center gap-1 flex-shrink-0 transition">
            <i class="fa-solid fa-plus text-[9px]"></i> Stoğa Ekle ↵
          </span>
        </div>
      `;
    });
  }

  // 2. Standart Bileşen Kataloğu & Otomatik Doldurma
  if (catalogSuggestions.length > 0) {
    html += `
      <div class="px-3 py-1.5 bg-[#121214] text-[10px] font-semibold text-blue-400 uppercase tracking-wider flex items-center justify-between">
        <span><i class="fa-solid fa-microchip mr-1"></i> Standart Bileşen Şablonları (${catalogSuggestions.length})</span>
        <span class="text-[#71717a] font-normal lowercase">kategori, kılıf ve değer otomatik dolar</span>
      </div>
    `;
    catalogSuggestions.forEach((cat) => {
      const idx = currentSuggestions.length;
      currentSuggestions.push(cat);
      html += `
        <div class="livesearch-item p-2.5 hover:bg-white/5 cursor-pointer flex items-center justify-between gap-2 transition"
             onclick="selectLiveSearchItem(currentSuggestions[${idx}])">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="px-1.5 py-0.2 rounded text-[9px] font-mono font-medium bg-blue-500/15 text-blue-400 border border-blue-500/20">
                ${escapeHtml(cat.category_label || cat.category)}
              </span>
              <p class="font-medium text-white truncate text-xs">${escapeHtml(cat.name)}</p>
            </div>
            <div class="text-[11px] text-[#8e8e93] mt-0.5 flex items-center gap-1.5 flex-wrap">
              ${cat.package ? `<span class="text-white/80 font-mono">Kılıf: ${escapeHtml(cat.package)}</span>` : ''}
              ${cat.value ? `<span class="text-white/80">• ${escapeHtml(cat.value)}</span>` : ''}
              ${cat.description ? `<span class="text-[#71717a] italic truncate max-w-[220px]">• ${escapeHtml(cat.description)}</span>` : ''}
            </div>
          </div>
          <span class="text-[10px] text-blue-400 bg-white/5 px-2 py-1 rounded border border-white/5 font-medium flex-shrink-0">
            Seç & Doldur ↵
          </span>
        </div>
      `;
    });
  }

  container.innerHTML = html;
  container.classList.remove("hidden");
}

function handleFormNameInput(e) {
  const query = (e.target.value || "").trim();
  lastLiveSearchTypedQuery = e.target.value || "";
  const spinner = document.getElementById("form-name-spinner");

  if (liveSearchDebounceTimer) {
    clearTimeout(liveSearchDebounceTimer);
  }

  if (query.length < 2) {
    closeFormNameSuggestions();
    dismissFormNameWarning();
    return;
  }

  if (spinner) spinner.classList.remove("hidden");

  // 1. Hızlı Yerel Envanter Ön Taraması (0 ms)
  const normQ = query.toLowerCase().replace(/[\s\-_]/g, "");
  const localMatches = (allComponentsCache || []).filter(c => {
    const cNorm = (c.name || "").toLowerCase().replace(/[\s\-_]/g, "");
    const vNorm = (c.value || "").toLowerCase().replace(/[\s\-_]/g, "");
    return (normQ.length >= 2 && cNorm.includes(normQ)) || (vNorm && vNorm.includes(normQ));
  }).map(c => ({
    ...c,
    is_inventory: true,
    category_label: c.category
  }));

  if (localMatches.length > 0) {
    renderLiveSearchDropdown(localMatches.slice(0, 5), [], query);
  }

  // 2. Debounced Backend Katalog & Detaylı Eşleştirme Sorgusu (150ms)
  liveSearchDebounceTimer = setTimeout(async () => {
    try {
      const res = await fetch(`/api/components/suggest?q=${encodeURIComponent(query)}`);
      if (res.ok) {
        const data = await res.json();
        const inv = data.inventory_matches || [];
        const cat = data.catalog_suggestions || [];
        renderLiveSearchDropdown(inv, cat, query);
      }
    } catch (err) {
      console.error("LiveSearch hatası:", err);
    } finally {
      if (spinner) spinner.classList.add("hidden");
    }
  }, 150);
}

// ==========================================
// 📍 Saklama Yeri (Location) Autocomplete & Chips
// ==========================================
let cachedLocationStats = [];
let locationSelectedIndex = -1;
let currentLocationSuggestions = [];

function renderQuickLocationChips() {
  const container = document.getElementById("quick-location-chips");
  if (!container) return;
  if (!cachedLocationStats || cachedLocationStats.length === 0) {
    container.innerHTML = "";
    return;
  }
  // En çok parçaya sahip ilk 4 lokasyonu göster
  const topLocs = cachedLocationStats.slice(0, 4);
  container.innerHTML = topLocs.map(loc => `
    <button type="button" onclick="selectLocationItem('${escapeHtml(loc.name)}')" 
            class="px-2 py-0.5 rounded-lg bg-white/5 hover:bg-white/10 text-[#a1a1aa] hover:text-white border border-white/5 text-[10px] flex items-center gap-1 transition"
            title="Tıklayarak saklama yerini '${escapeHtml(loc.name)}' yap">
      <i class="fa-solid fa-folder-closed text-[9px] text-[#636366]"></i>
      <span class="truncate max-w-[120px]">${escapeHtml(loc.name)}</span>
      <span class="text-[9px] text-[#71717a] font-mono">(${loc.count})</span>
    </button>
  `).join("");
}

function closeLocationSuggestions() {
  const container = document.getElementById("form-location-suggestions");
  if (container) {
    container.classList.add("hidden");
    container.innerHTML = "";
  }
  locationSelectedIndex = -1;
  currentLocationSuggestions = [];
}

function renderLocationDropdown(matches, query) {
  const container = document.getElementById("form-location-suggestions");
  if (!container) return;

  currentLocationSuggestions = [];
  locationSelectedIndex = -1;

  let html = "";

  if (matches.length > 0) {
    html += `
      <div class="px-3 py-1.5 bg-[#121214] text-[10px] font-semibold text-blue-400 uppercase tracking-wider flex items-center justify-between">
        <span><i class="fa-solid fa-folder-tree mr-1"></i> Mevcut Saklama Yerleri (${matches.length})</span>
        <span class="text-[#71717a] font-normal lowercase">seçmek için tıklayın</span>
      </div>
    `;

    matches.forEach(item => {
      currentLocationSuggestions.push(item.name);
      html += `
        <div class="location-item p-2 hover:bg-white/5 cursor-pointer flex items-center justify-between gap-2 transition"
             onclick="selectLocationItem('${escapeHtml(item.name)}')">
          <div class="flex items-center gap-2 min-w-0">
            <i class="fa-solid fa-folder-closed text-xs text-blue-400/80"></i>
            <span class="text-xs text-white truncate font-medium">${escapeHtml(item.name)}</span>
          </div>
          <span class="text-[10px] text-[#8e8e93] font-mono bg-white/5 px-1.5 py-0.5 rounded border border-white/5 flex-shrink-0">
            ${item.count} parça
          </span>
        </div>
      `;
    });
  }

  // Eğer kullanıcı bir metin yazdıysa ve mevcut lokasyonlardan hiçbirine birebir uymuyorsa "Yeni Ekle" seçeneği sun
  const cleanQ = (query || "").trim();
  const exactMatch = matches.some(m => m.name.toLowerCase() === cleanQ.toLowerCase());
  if (cleanQ && !exactMatch) {
    currentLocationSuggestions.push(cleanQ);
    html += `
      <div class="location-item p-2 hover:bg-emerald-500/10 cursor-pointer flex items-center justify-between gap-2 transition border-t border-[#26262a]"
           onclick="selectLocationItem('${escapeHtml(cleanQ)}')">
        <div class="flex items-center gap-2 min-w-0">
          <i class="fa-solid fa-plus text-xs text-emerald-400"></i>
          <span class="text-xs text-emerald-300 truncate">Yeni Yer: <b>"${escapeHtml(cleanQ)}"</b></span>
        </div>
        <span class="text-[10px] text-emerald-400 bg-emerald-500/15 px-1.5 py-0.5 rounded font-medium flex-shrink-0">
          Seç ↵
        </span>
      </div>
    `;
  }

  if (matches.length === 0 && !cleanQ) {
    html = `
      <div class="p-3 text-center text-[#8e8e93] text-[11px]">
        <i class="fa-solid fa-circle-info mr-1"></i> Henüz kayıtlı bir saklama yeri bulunmuyor. Yeni bir yer adı yazabilirsiniz.
      </div>
    `;
  }

  container.innerHTML = html;
  container.classList.remove("hidden");
}

function handleLocationFocus(forceOpen = false) {
  const input = document.getElementById("form-location");
  if (!input) return;
  const q = (input.value || "").trim().toLowerCase();

  let matches = cachedLocationStats;
  if (q && !forceOpen) {
    matches = cachedLocationStats.filter(loc => loc.name.toLowerCase().includes(q));
  }
  renderLocationDropdown(matches, input.value);
}

function handleLocationInput(e) {
  const query = (e.target.value || "").trim();
  const qLower = query.toLowerCase();
  const matches = cachedLocationStats.filter(loc => loc.name.toLowerCase().includes(qLower));
  renderLocationDropdown(matches, query);
}

function selectLocationItem(name) {
  const input = document.getElementById("form-location");
  if (input) input.value = name;
  closeLocationSuggestions();
}

function handleLocationKeydown(e) {
  const container = document.getElementById("form-location-suggestions");
  if (!container || container.classList.contains("hidden") || currentLocationSuggestions.length === 0) {
    if (e.key === "Escape") closeLocationSuggestions();
    return;
  }

  const items = container.querySelectorAll(".location-item");
  if (!items.length) return;

  if (e.key === "ArrowDown") {
    e.preventDefault();
    locationSelectedIndex = (locationSelectedIndex + 1) % items.length;
    updateLocationActiveItem(items);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    locationSelectedIndex = (locationSelectedIndex - 1 + items.length) % items.length;
    updateLocationActiveItem(items);
  } else if (e.key === "Enter") {
    if (locationSelectedIndex >= 0 && locationSelectedIndex < currentLocationSuggestions.length) {
      e.preventDefault();
      selectLocationItem(currentLocationSuggestions[locationSelectedIndex]);
    }
  } else if (e.key === "Escape") {
    closeLocationSuggestions();
  }
}

function updateLocationActiveItem(domItems) {
  domItems.forEach((el, idx) => {
    if (idx === locationSelectedIndex) {
      el.classList.add("bg-white/10", "border-l-2", "border-blue-400");
      el.scrollIntoView({ block: "nearest" });
    } else {
      el.classList.remove("bg-white/10", "border-l-2", "border-blue-400");
    }
  });
}

function openAddModal() {
  document.getElementById("modal-title").innerText = "Yeni Elektronik Parça Ekle";
  document.getElementById("form-comp-id").value = "";
  document.getElementById("component-form").reset();
  document.getElementById("component-form").classList.remove("hidden");
  document.getElementById("modal-quick-stock").classList.add("hidden");
  selectedQuickStockItem = null;
  lastLiveSearchTypedQuery = "";
  document.getElementById("form-quantity").value = 1;
  document.getElementById("form-min-quantity").value = 2;
  closeFormNameSuggestions();
  closeLocationSuggestions();
  dismissFormNameWarning();
  document.getElementById("component-modal").classList.remove("hidden");
  setTimeout(() => {
    const nameInput = document.getElementById("form-name");
    if (nameInput) nameInput.focus();
  }, 50);
}

function editComponent(compId) {
  const comp = allComponentsCache.find(c => c.id === compId);
  if (!comp) return;

  document.getElementById("modal-title").innerText = "Elektronik Parçayı Düzenle";
  document.getElementById("component-form").classList.remove("hidden");
  document.getElementById("modal-quick-stock").classList.add("hidden");
  selectedQuickStockItem = null;

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

  closeFormNameSuggestions();
  closeLocationSuggestions();
  dismissFormNameWarning();
  document.getElementById("component-modal").classList.remove("hidden");
}

function closeModal() {
  closeFormNameSuggestions();
  closeLocationSuggestions();
  dismissFormNameWarning();
  document.getElementById("modal-quick-stock").classList.add("hidden");
  document.getElementById("component-form").classList.remove("hidden");
  selectedQuickStockItem = null;
  document.getElementById("component-modal").classList.add("hidden");
}

// Dropdown dışına tıklandığında önerileri kapat
document.addEventListener("click", (e) => {
  if (!e.target.closest("#form-name") && !e.target.closest("#form-name-suggestions")) {
    closeFormNameSuggestions();
  }
  if (!e.target.closest("#form-location") && !e.target.closest("#form-location-suggestions") && !e.target.closest("[onclick*='handleLocationFocus']")) {
    closeLocationSuggestions();
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeModal();
    closeMoveToDefectiveModal();
    closeChangePasswordModal();
  }
});

// ==========================================
// ⚠️ Parçayı Arızaya / Çıkmaya Taşıma Mantığı
// ==========================================
let currentMoveDefectiveComp = null;

function openMoveToDefectiveModal(compId) {
  const comp = allComponentsCache.find(c => c.id === compId);
  if (!comp) return;

  currentMoveDefectiveComp = comp;
  document.getElementById("move-def-comp-id").value = comp.id;
  document.getElementById("move-def-comp-id-label").innerText = comp.id;
  document.getElementById("move-def-name").innerText = comp.name;

  const catLabel = CATEGORY_NAMES[comp.category] || comp.category;
  const details = [catLabel];
  if (comp.package) details.push(`Kılıf: ${comp.package}`);
  if (comp.value) details.push(`Değer: ${comp.value}`);
  if (comp.location) details.push(`Yer: ${comp.location}`);
  document.getElementById("move-def-details").innerText = details.join(" • ");

  document.getElementById("move-def-current-qty").innerText = comp.quantity;

  const qtyInput = document.getElementById("move-def-qty");
  qtyInput.max = comp.quantity;
  qtyInput.value = 1;

  document.getElementById("move-def-status").value = "defective";
  document.getElementById("move-def-notes").value = "";
  document.getElementById("move-def-location").value = "Arızalı Kutusu";

  updateMoveDefectivePreview();

  document.getElementById("move-to-defective-modal").classList.remove("hidden");
  setTimeout(() => {
    const notesEl = document.getElementById("move-def-notes");
    if (notesEl) notesEl.focus();
  }, 50);
}

function updateMoveDefectivePreview() {
  if (!currentMoveDefectiveComp) return;
  const cur = parseInt(currentMoveDefectiveComp.quantity, 10) || 1;
  const input = document.getElementById("move-def-qty");
  let moveVal = parseInt(input.value, 10);
  if (isNaN(moveVal) || moveVal < 1) moveVal = 1;
  if (moveVal > cur) {
    moveVal = cur;
    input.value = cur;
  }

  const remaining = cur - moveVal;
  const prevEl = document.getElementById("move-def-preview");
  const btn = document.getElementById("move-def-submit-btn");

  if (remaining === 0) {
    prevEl.innerHTML = `<span class="text-amber-400 font-semibold"><i class="fa-solid fa-arrow-right"></i> Tüm stok (${moveVal} adet) arızalıya taşınacak.</span>`;
    if (btn) btn.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-xs"></i> <span>Tümünü Arızaya Taşı (${moveVal} Adet)</span>`;
  } else {
    prevEl.innerHTML = `Kalan sağlam: <b class="text-emerald-400 font-bold">${remaining} adet</b> • Arızaya ayrılacak: <b class="text-amber-400 font-bold">${moveVal} adet</b>`;
    if (btn) btn.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-xs"></i> <span>${moveVal} Adedi Arızaya Ayır</span>`;
  }
}

async function submitMoveToDefective(e) {
  e.preventDefault();
  if (!currentMoveDefectiveComp) return;

  const compId = currentMoveDefectiveComp.id;
  const qty = parseInt(document.getElementById("move-def-qty").value, 10);
  const statusVal = document.getElementById("move-def-status").value;
  const notes = document.getElementById("move-def-notes").value.trim();
  const location = document.getElementById("move-def-location").value.trim();

  if (!notes) {
    alert("Lütfen parçanın neden arızaya ayrıldığını (arıza / teşhis notunu) yazınız.");
    document.getElementById("move-def-notes").focus();
    return;
  }

  const btn = document.getElementById("move-def-submit-btn");
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`/api/components/${compId}/move-to-defective`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        quantity: qty,
        status: statusVal,
        notes: notes,
        location: location || "Arızalı Kutusu"
      })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      closeMoveToDefectiveModal();
      loadStats();
      loadComponents();
      loadDefectiveComponents();
      showToast(data.message || "Parça arızaya ayrıldı");
    } else {
      alert("Hata: " + (data.error || "İşlem gerçekleştirilemedi"));
    }
  } catch (err) {
    console.error("Arızaya taşıma hatası:", err);
    alert("Sunucuya bağlanırken bir hata oluştu.");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function closeMoveToDefectiveModal() {
  const modal = document.getElementById("move-to-defective-modal");
  if (modal) modal.classList.add("hidden");
  currentMoveDefectiveComp = null;
}

async function markAsWorking(compId) {
  if (!confirm("Bu parçayı tamir edildi / sağlam durumuna geçirmek istediğinize emin misiniz?")) return;
  try {
    const res = await fetch(`/api/components/${compId}/mark-repaired`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (res.ok && data.success) {
      loadStats();
      loadDefectiveComponents();
      loadComponents();
      showToast(data.message || "Parça durumu 'Sağlam' olarak güncellendi");
    } else {
      alert("Hata: " + (data.error || "İşlem başarısız"));
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

function formatPrice(val) {
  if (val === null || val === undefined || val === '') return "0.00 TL";
  if (typeof val === "number") {
    if (isNaN(val)) return "0.00 TL";
    return val.toFixed(2) + " TL";
  }
  let s = String(val).trim();
  if (/^-?\d+(\.\d+)?$/.test(s)) {
    return parseFloat(s).toFixed(2) + " TL";
  }
  const cleanTL = s.replace(/TL|₺/g, "").trim();
  if (/^-?\d+(\.\d+)?$/.test(cleanTL)) {
    return parseFloat(cleanTL).toFixed(2) + " TL";
  }
  if (cleanTL.includes(",")) {
    const trClean = cleanTL.replace(/\./g, "").replace(",", ".");
    const parsed = parseFloat(trClean);
    if (!isNaN(parsed)) return parsed.toFixed(2) + " TL";
  }
  const parsed = parseFloat(cleanTL);
  return isNaN(parsed) ? String(val) : parsed.toFixed(2) + " TL";
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
  tbody.innerHTML = '<tr><td colspan="5" class="py-8 text-center text-[#86868b]"><i class="fa-solid fa-spinner fa-spin text-lg mb-2"></i><p class="text-xs">Sepet yükleniyor...</p></td></tr>';

  try {
    const res = await fetch("/api/cart");
    const data = await res.json();
    currentCartData = data;

    document.getElementById("cart-summary-items").innerText = data.total_items_count || 0;
    document.getElementById("cart-summary-qty").innerText = data.total_quantity || 0;
    document.getElementById("cart-summary-total").innerText = formatPrice(data.total_price_tl);

    const badge = document.getElementById("badge-cart-count");
    if (badge) badge.innerText = data.total_quantity || 0;

    const items = data.items || [];
    if (items.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" class="py-12 text-center text-[#86868b]">
            <i class="fa-solid fa-cart-shopping text-3xl mb-2 text-[#48484a]"></i>
            <p class="font-medium text-[#f5f5f7]">Sepetiniz şu anda boş.</p>
            <p class="text-xs text-[#86868b] mt-1">Robotistan Canlı Arama veya Proje Asistanı üzerinden eksik parçaları ekleyebilirsiniz.</p>
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = items.map(item => {
      const itemTotal = ((item.price_value || 0) * item.quantity).toFixed(2);
      return `
        <tr class="hover:bg-white/[0.02] border-b border-[#1c1c1e] transition-colors">
          <td class="py-3 px-4">
            <a href="${item.url}" target="_blank" class="font-medium text-[#f5f5f7] hover:text-white flex items-center gap-1.5 transition">
              ${escapeHtml(item.title)}
              <i class="fa-solid fa-arrow-up-right-from-square text-[10px] text-[#86868b]"></i>
            </a>
            ${item.product_id ? `<span class="text-[10px] text-[#86868b] font-mono">T-Soft PID: ${item.product_id}</span>` : ''}
          </td>
          <td class="py-3 px-3 font-mono text-[#86868b] text-xs">${formatPrice(item.price_value || item.price)}</td>
          <td class="py-3 px-3">
            <div class="flex items-center justify-center gap-1.5">
              <button onclick="updateCartItemQty(${item.id}, ${item.quantity - 1})" class="w-6 h-6 rounded-md bg-[#2c2c2e] hover:bg-[#3a3a3c] text-[#f5f5f7] flex items-center justify-center text-xs transition select-none flex-shrink-0">-</button>
              <input type="number" min="1" value="${item.quantity}" data-old-qty="${item.quantity}"
                     onfocus="this.select()"
                     onkeydown="if(event.key==='Enter'){this.blur();}"
                     onchange="setCartItemDirectQty(${item.id}, this)"
                     class="w-12 h-6 text-center text-xs font-mono font-medium rounded bg-[#2c2c2e] hover:bg-[#3a3a3c] focus:bg-[#202024] focus:ring-1 focus:ring-blue-500 border border-transparent hover:border-white/15 text-[#f5f5f7] outline-none transition [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                     title="Doğrudan adet yazabilirsiniz">
              <button onclick="updateCartItemQty(${item.id}, ${item.quantity + 1})" class="w-6 h-6 rounded-md bg-[#2c2c2e] hover:bg-[#3a3a3c] text-[#f5f5f7] flex items-center justify-center text-xs transition select-none flex-shrink-0">+</button>
            </div>
          </td>
          <td class="py-3 px-3 font-mono text-[#f5f5f7] font-semibold">${formatPrice(itemTotal)}</td>
          <td class="py-3 px-4 text-right">
            <button onclick="deleteCartItem(${item.id})" class="p-1.5 rounded-md hover:bg-red-500/10 text-[#86868b] hover:text-red-400 transition" title="Sepetten Çıkar">
              <i class="fa-solid fa-trash text-xs"></i>
            </button>
          </td>
        </tr>
      `;
    }).join("");

  } catch (err) {
    console.error("Sepet yükleme hatası:", err);
  }
}

async function setCartItemDirectQty(cartId, inputEl) {
  const newQty = parseInt(inputEl.value, 10);
  const oldQty = parseInt(inputEl.getAttribute("data-old-qty"), 10);
  if (isNaN(newQty) || newQty < 1) {
    inputEl.value = isNaN(oldQty) ? 1 : oldQty;
    return;
  }
  if (newQty === oldQty) return;
  await updateCartItemQty(cartId, newQty);
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
    if (qty <= 0) {
      deleteCartItem(cartId);
      return;
    }
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
  container.innerHTML = '<div class="py-12 text-center text-[#86868b]"><i class="fa-solid fa-spinner fa-spin text-xl text-[#f5f5f7] mb-2"></i><p class="text-xs">Taslak siparişler yükleniyor...</p></div>';

  try {
    const res = await fetch("/api/draft-orders");
    const orders = await res.json();

    loadDraftsBadge();

    if (!orders || orders.length === 0) {
      container.innerHTML = `
        <div class="apple-card py-12 px-4 text-center text-[#86868b] space-y-1">
          <i class="fa-solid fa-clipboard-question text-3xl mb-2 text-[#48484a]"></i>
          <p class="font-medium text-[#f5f5f7]">Henüz kayıtlı bir taslak sipariş listeniz bulunmuyor.</p>
          <p class="text-xs text-[#86868b] max-w-md mx-auto">
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
      const pendingItems = items.filter(it => !it.is_purchased);
      const purchasedItems = items.filter(it => it.is_purchased);

      const statusMap = {
        draft: { text: "Taslak", class: "apple-badge apple-badge-default" },
        ready: { text: "Sepette", class: "apple-badge apple-badge-green" },
        ordered: { text: "Sipariş Verildi", class: "apple-badge apple-badge-blue" },
        archived: { text: "Arşiv", class: "apple-badge apple-badge-default" }
      };
      const st = statusMap[o.status] || statusMap.draft;

      const pendingCost = detail.pending_estimated_price != null ? detail.pending_estimated_price : o.total_estimated_price;
      const purchasedCost = detail.purchased_total_price || 0.0;

      return `
        <div class="apple-card p-5 space-y-4">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#242426] pb-3">
            <div>
              <div class="flex items-center gap-2">
                <h3 class="font-semibold text-white text-sm">#${o.id} — ${escapeHtml(o.title)}</h3>
                <span class="${st.class}">${st.text}</span>
              </div>
              <p class="text-xs text-[#8e8e93] mt-0.5">${escapeHtml(o.description || 'Açıklama yok')} • ${o.updated_at.slice(0, 16).replace('T', ' ')}</p>
            </div>
            <div class="text-right flex sm:flex-col items-center sm:items-end justify-between gap-1">
              <div>
                <span class="text-xs text-[#8e8e93] mr-1">Alınacak:</span>
                <span class="text-base font-semibold text-white font-mono">~${formatPrice(pendingCost)}</span>
              </div>
              ${purchasedItems.length > 0 ? `
                <div class="text-[11px] text-emerald-400 font-mono">
                  <span>✓ Satın Alınan: ${formatPrice(purchasedCost)}</span>
                </div>
              ` : ''}
              <span class="text-[11px] text-[#8e8e93] block">${pendingItems.length} Alınacak / ${purchasedItems.length} Alındı (${o.total_quantity} Adet)</span>
            </div>
          </div>

          <!-- 1. BÖLÜM: SATIN ALINACAK KALEMLER -->
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <h4 class="text-[11px] font-semibold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                <i class="fa-solid fa-cart-shopping"></i> Satın Alınacaklar (${pendingItems.length})
              </h4>
              <span class="text-[11px] text-[#8e8e93] font-mono">Tahmini: ~${formatPrice(pendingCost)}</span>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
              ${pendingItems.length === 0 ? `
                <div class="col-span-full py-3 px-4 bg-emerald-950/20 border border-emerald-900/30 rounded-xl text-center text-emerald-400 text-xs">
                  🎉 Bu taslaktaki tüm kalemler satın alındı! Aşağıdaki listeden stoğa aktarabilirsiniz.
                </div>
              ` : pendingItems.map(it => `
                <div class="bg-[#0e0e10] p-2.5 rounded-xl border border-[#222225] flex items-center justify-between gap-2 hover:border-[#333336] transition">
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-1.5 flex-wrap">
                      <span class="text-[10px] px-1.5 py-0.2 rounded bg-white/5 border border-white/5 text-[#8e8e93] font-mono font-medium" title="Kalem ID">#${it.id}</span>
                      <p class="font-medium text-white truncate flex-1 min-w-[120px]" title="${escapeHtml(it.title)}">${escapeHtml(it.title)}</p>
                      ${it.source && it.source !== 'robotistan' ? `<span class="apple-badge apple-badge-default text-[9px] uppercase font-mono">${escapeHtml(it.source)}</span>` : ''}
                    </div>
                    <div class="flex items-center gap-2 text-[11px] text-[#8e8e93] mt-1 flex-wrap">
                      <span class="text-white/90 font-mono font-medium">${it.price_value > 0 ? formatPrice(it.price_value) : (it.price ? formatPrice(it.price) : 'Fiyat Belirtilmedi')}</span>
                      ${it.url ? (it.in_stock ? '<span class="apple-badge apple-badge-green text-[10px]">Stokta</span>' : '<span class="apple-badge apple-badge-red text-[10px]">Tükendi</span>') : '<span class="apple-badge apple-badge-amber text-[10px]" title="Piyasada aranacak">⚪ Aranacak</span>'}
                      <span class="flex items-center gap-1 bg-white/5 px-1 py-0.5 rounded border border-white/5">
                        <button onclick="changeDraftItemQuantity(${it.id}, ${it.quantity - 1})" class="w-4 h-4 rounded hover:bg-white/10 text-[#8e8e93] hover:text-white flex items-center justify-center font-bold" title="1 Azalt">-</button>
                        <input type="number" min="1" value="${it.quantity}" data-old-qty="${it.quantity}"
                               onfocus="this.select()"
                               onkeydown="if(event.key==='Enter'){this.blur();}"
                               onchange="setDraftItemDirectQty(${it.id}, this)"
                               class="w-8 h-4 text-center text-[11px] font-mono font-medium text-white bg-transparent hover:bg-white/10 focus:bg-[#202024] rounded outline-none border border-transparent focus:border-blue-500 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                               title="Doğrudan adet yazabilirsiniz">
                        <button onclick="changeDraftItemQuantity(${it.id}, ${it.quantity + 1})" class="w-4 h-4 rounded hover:bg-white/10 text-[#8e8e93] hover:text-white flex items-center justify-center font-bold" title="1 Artır">+</button>
                      </span>
                      ${it.notes ? `<span class="text-[#71717a] italic truncate max-w-[160px]" title="${escapeHtml(it.notes)}">• ${escapeHtml(it.notes)}</span>` : ''}
                    </div>
                  </div>
                  <div class="flex items-center gap-1.5 flex-shrink-0">
                    <button onclick="markDraftItemPurchased(${it.id}, true)" class="px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20 text-[11px] font-medium flex items-center gap-1 transition" title="Bu ürünü satın aldım olarak işaretle">
                      <i class="fa-solid fa-check text-[10px]"></i> <span>Satın Aldım</span>
                    </button>
                    ${it.url ? `
                      <a href="${it.url}" target="_blank" class="p-1.5 rounded-lg text-[#8e8e93] hover:text-white hover:bg-white/5 transition" title="Ürün Sayfasına Git">
                        <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
                      </a>
                    ` : ''}
                    <button onclick="removeDraftOrderItem(${it.id}, '${escapeHtml(it.title)}')" class="p-1.5 rounded-lg text-[#8e8e93] hover:text-[#ff453a] hover:bg-white/5 transition" title="Kalemi Çıkar">
                      <i class="fa-solid fa-trash-can text-xs"></i>
                    </button>
                  </div>
                </div>
              `).join("")}
            </div>
          </div>

          <!-- 2. BÖLÜM: SATIN ALINAN KALEMLER (Ayrı Liste & Stoğa Aktarım) -->
          ${purchasedItems.length > 0 ? `
            <div class="space-y-2 pt-2 border-t border-emerald-950/40">
              <div class="flex items-center justify-between">
                <h4 class="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                  <i class="fa-solid fa-circle-check"></i> Satın Alınanlar (${purchasedItems.length})
                </h4>
                <span class="text-[11px] text-emerald-400/80 font-mono">Tutar: ${formatPrice(purchasedCost)}</span>
              </div>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                ${purchasedItems.map(it => `
                  <div class="bg-emerald-950/15 p-2.5 rounded-xl border border-emerald-900/30 flex items-center justify-between gap-2">
                    <div class="min-w-0 flex-1">
                      <div class="flex items-center gap-1.5 flex-wrap">
                        <span class="text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-mono font-medium">#${it.id}</span>
                        <p class="font-medium text-white/90 line-through truncate flex-1 min-w-[120px]" title="${escapeHtml(it.title)}">${escapeHtml(it.title)}</p>
                        ${it.source && it.source !== 'robotistan' ? `<span class="apple-badge apple-badge-default text-[9px] uppercase font-mono">${escapeHtml(it.source)}</span>` : ''}
                      </div>
                      <div class="flex items-center gap-2 text-[11px] text-[#8e8e93] mt-1 flex-wrap">
                        <span class="text-emerald-300 font-mono font-medium">${it.price_value > 0 ? formatPrice(it.price_value) : (it.price ? formatPrice(it.price) : '')}</span>
                        <span class="text-white/80 font-mono">${it.quantity} Adet</span>
                        ${it.transferred_to_inventory ? `
                          <span class="apple-badge apple-badge-green text-[10px] flex items-center gap-1">
                            <i class="fa-solid fa-boxes-stacked text-[9px]"></i> Stoğa Eklendi ${it.inventory_component_id ? `(#${it.inventory_component_id})` : ''}
                          </span>
                        ` : ''}
                        ${it.purchased_at ? `<span class="text-[10px] text-[#71717a] font-mono">${it.purchased_at.slice(0, 16).replace('T', ' ')}</span>` : ''}
                      </div>
                    </div>
                    <div class="flex items-center gap-1.5 flex-shrink-0">
                      ${!it.transferred_to_inventory ? `
                        <button onclick="transferDraftItemToInventory(${it.id}, '${escapeHtml(it.title).replace(/'/g, "\\'")}')" class="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-medium flex items-center gap-1 shadow-sm transition" title="Bu parçayı envanter stoğunuza aktarır">
                          <i class="fa-solid fa-box-archive text-[10px]"></i> <span>Stoğa Aktar</span>
                        </button>
                      ` : ''}
                      <button onclick="markDraftItemPurchased(${it.id}, false)" class="p-1.5 rounded-lg text-[#8e8e93] hover:text-amber-300 hover:bg-white/5 transition" title="Satın alınacaklara geri al">
                        <i class="fa-solid fa-arrow-rotate-left text-xs"></i>
                      </button>
                      ${it.url ? `
                        <a href="${it.url}" target="_blank" class="p-1.5 rounded-lg text-[#8e8e93] hover:text-white hover:bg-white/5 transition" title="Ürün Sayfasına Git">
                          <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
                        </a>
                      ` : ''}
                      <button onclick="removeDraftOrderItem(${it.id}, '${escapeHtml(it.title)}')" class="p-1.5 rounded-lg text-[#8e8e93] hover:text-[#ff453a] hover:bg-white/5 transition" title="Kalemi Çıkar">
                        <i class="fa-solid fa-trash-can text-xs"></i>
                      </button>
                    </div>
                  </div>
                `).join("")}
              </div>
            </div>
          ` : ''}

          <!-- Aksiyonlar -->
          <div class="pt-3 border-t border-[#242426] flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <button onclick="applyDraftOrderToCart(${o.id})" class="apple-btn-primary text-xs px-3 py-1.5">
                <i class="fa-solid fa-cart-plus text-[10px]"></i> <span>Sepete Aktar</span>
              </button>
              <button onclick="openAddDraftItemModal(${o.id}, '${escapeHtml(o.title).replace(/'/g, "\\'")}')" class="apple-btn-secondary text-xs px-3 py-1.5" title="Kalem Ekle">
                <i class="fa-solid fa-plus text-[10px]"></i> <span>Kalem Ekle</span>
              </button>
            </div>
            <button onclick="deleteDraftOrderPrompt(${o.id})" class="p-2 rounded-lg text-[#8e8e93] hover:text-[#ff453a] hover:bg-white/5 transition" title="Taslağı Sil">
              <i class="fa-solid fa-trash text-xs"></i>
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

async function removeDraftOrderItem(itemId, itemTitle) {
  if (!confirm(`"${itemTitle}" ürününü bu taslak sipariş listesinden çıkarmak istediğinize emin misiniz?`)) return;
  try {
    const res = await fetch(`/api/draft-orders/items/${itemId}`, { method: "DELETE" });
    if (res.ok) {
      showToast(`"${itemTitle}" taslak siparişten çıkarıldı 🗑️`);
      loadDraftOrders();
    } else {
      const err = await res.json();
      alert("Hata: " + (err.error || "Kalem çıkarılamadı"));
    }
  } catch (err) {
    console.error("Kalem silme hatası:", err);
  }
}

async function changeDraftItemQuantity(itemId, newQty) {
  try {
    if (newQty <= 0) {
      removeDraftOrderItem(itemId, "Bu ürün");
      return;
    }
    const res = await fetch(`/api/draft-orders/items/${itemId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quantity: newQty })
    });
    if (res.ok) {
      loadDraftOrders();
    }
  } catch (err) {
    console.error("Adet güncelleme hatası:", err);
  }
}

async function setDraftItemDirectQty(itemId, inputEl) {
  const newQty = parseInt(inputEl.value, 10);
  const oldQty = parseInt(inputEl.getAttribute("data-old-qty"), 10);
  if (isNaN(newQty) || newQty < 1) {
    inputEl.value = isNaN(oldQty) ? 1 : oldQty;
    return;
  }
  if (newQty === oldQty) return;
  await changeDraftItemQuantity(itemId, newQty);
}

async function markDraftItemPurchased(itemId, isPurchased) {
  try {
    const res = await fetch(`/api/draft-orders/items/${itemId}/purchase`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_purchased: isPurchased })
    });
    if (res.ok) {
      showToast(isPurchased ? "Kalem satın alındı olarak işaretlendi! ✅" : "Kalem satın alınacaklara geri alındı ↩");
      loadDraftOrders();
    } else {
      const err = await res.json();
      alert("Hata: " + (err.error || "İşlem başarısız"));
    }
  } catch (err) {
    console.error("Satın alma durumu güncelleme hatası:", err);
  }
}

async function transferDraftItemToInventory(itemId, itemTitle) {
  if (!confirm(`"${itemTitle}" bileşenini doğrudan çalışan envanter stoğunuza aktarmak istiyor musunuz?\n\n(Aynı isimde parça varsa adedi artırılır, yoksa yeni bileşen olarak eklenir)`)) return;
  try {
    const res = await fetch(`/api/draft-orders/items/${itemId}/transfer-to-inventory`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || "Stoğa başarıyla aktarıldı! 📦");
      loadDraftOrders();
      if (typeof loadInventory === "function") loadInventory();
    } else {
      alert("Hata: " + (data.error || "Stoğa aktarılamadı"));
    }
  } catch (err) {
    console.error("Stoğa aktarma hatası:", err);
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

function openAddDraftItemModal(draftId, draftTitle) {
  const modal = document.getElementById("add-draft-item-modal");
  if (!modal) return;
  document.getElementById("draft-item-draft-id").value = draftId;
  const titleEl = document.getElementById("add-draft-item-modal-title");
  if (titleEl) {
    titleEl.textContent = `Taslağa Kalem Ekle (#${draftId} - ${draftTitle || ''})`;
  }
  document.getElementById("draft-item-title").value = "";
  document.getElementById("draft-item-quantity").value = "1";
  document.getElementById("draft-item-source").value = "market";
  document.getElementById("draft-item-price").value = "";
  document.getElementById("draft-item-in-stock").value = "0";
  document.getElementById("draft-item-url").value = "";
  document.getElementById("draft-item-notes").value = "";
  modal.classList.remove("hidden");
  setTimeout(() => {
    const input = document.getElementById("draft-item-title");
    if (input) input.focus();
  }, 100);
}

function closeAddDraftItemModal() {
  const modal = document.getElementById("add-draft-item-modal");
  if (modal) modal.classList.add("hidden");
}

async function submitAddDraftItem(event) {
  if (event) event.preventDefault();
  const draftId = document.getElementById("draft-item-draft-id").value;
  if (!draftId) return;

  const title = (document.getElementById("draft-item-title").value || "").trim();
  const quantity = parseInt(document.getElementById("draft-item-quantity").value, 10) || 1;
  const source = document.getElementById("draft-item-source").value;
  const priceVal = parseFloat(document.getElementById("draft-item-price").value) || 0.0;
  const inStock = document.getElementById("draft-item-in-stock").value === "1";
  const url = (document.getElementById("draft-item-url").value || "").trim();
  const notes = (document.getElementById("draft-item-notes").value || "").trim();

  if (!title) {
    alert("Lütfen ürün / parça adını girin.");
    return;
  }

  try {
    const payload = {
      title,
      quantity,
      source,
      price_value: priceVal,
      price: priceVal > 0 ? `${priceVal.toFixed(2)} TL` : "",
      in_stock: inStock && Boolean(url),
      url: url || "",
      notes: notes || ""
    };

    const res = await fetch(`/api/draft-orders/${draftId}/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (res.ok && data.success) {
      closeAddDraftItemModal();
      showToast(`"${title}" taslak listeye eklendi ✨`);
      loadDraftOrders();
    } else {
      alert("Hata: " + (data.error || "Kalem eklenemedi"));
    }
  } catch (err) {
    console.error("Kalem ekleme hatası:", err);
    alert("Kalem eklenirken bir hata oluştu: " + err.message);
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

function copyCode(elementId, btn = null) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const text = (el.innerText || el.textContent || "").trim();
  const targetBtn = btn || (window.event ? (window.event.currentTarget || (window.event.target ? window.event.target.closest("button") : null)) : null);
  copyText(text, targetBtn);
}

function copyText(text, btn = null) {
  if (!text) return;
  const targetBtn = btn || (window.event ? (window.event.currentTarget || (window.event.target ? window.event.target.closest("button") : null)) : null);

  // 1. Önce modern clipboard API dene
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => {
      showCopySuccess(targetBtn);
    }).catch(() => {
      // Başarısız olursa senkron fallback'e geç
      fallbackCopy(text, targetBtn);
    });
    return;
  }

  // 2. Güvenli context yoksa veya API desteklenmiyorsa fallback çalıştır
  fallbackCopy(text, targetBtn);
}

function fallbackCopy(text, btn) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "0";
  textarea.style.left = "0";
  textarea.style.width = "2em";
  textarea.style.height = "2em";
  textarea.style.padding = "0";
  textarea.style.border = "none";
  textarea.style.outline = "none";
  textarea.style.boxShadow = "none";
  textarea.style.background = "transparent";
  textarea.style.opacity = "0.01";
  textarea.style.zIndex = "-1";
  document.body.appendChild(textarea);

  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, 99999);

  let success = false;
  try {
    success = document.execCommand("copy");
  } catch (err) {
    success = false;
  }
  document.body.removeChild(textarea);

  if (success) {
    showCopySuccess(btn);
  } else {
    window.prompt("Kopyalamak için Ctrl+C tuşlayın:", text);
  }
}

function showCopySuccess(btn) {
  showToast("Panoya kopyalandı! 📋");
  if (btn) {
    const origHtml = btn.dataset.origHtml || btn.innerHTML;
    btn.dataset.origHtml = origHtml;
    btn.innerHTML = '<i class="fa-solid fa-check text-emerald-400"></i> <span class="text-emerald-400 font-semibold">Kopyalandı!</span>';
    btn.classList.add("border-emerald-500", "bg-emerald-950/60");
    clearTimeout(btn._copyTimeout);
    btn._copyTimeout = setTimeout(() => {
      btn.innerHTML = origHtml;
      btn.classList.remove("border-emerald-500", "bg-emerald-950/60");
    }, 2200);
  }
}

// Explicit window bindings
window.copyCode = copyCode;
window.copyText = copyText;
window.fallbackCopy = fallbackCopy;
window.showCopySuccess = showCopySuccess;
window.openAddDraftItemModal = openAddDraftItemModal;
window.closeAddDraftItemModal = closeAddDraftItemModal;
window.submitAddDraftItem = submitAddDraftItem;
window.quickAddMarketItemToDraft = quickAddMarketItemToDraft;



