# ⚡ ElectroStock - Elektronik Atölye Stok Takip & AI MCP Sunucusu

Elektronik projelerinde **"elimde hangi dirençten kaç tane var?", "bu parça sağlam mıydı yoksa arızalı mıydı?", "aynı parçayı unutup tekrar mı aldım?"** sorunlarını kökten çözen; **Model Context Protocol (MCP)** desteğiyle yapay zeka asistanlarınıza (Cursor, Claude Desktop, Antigravity vb.) atölyenizi tanıtan ve eksik parçaları **Robotistan** üzerinden anlık stok ve fiyatla bulan akıllı elektronik envanter sistemi.

---

## 🌟 Öne Çıkan Özellikler

1. **Elektronik Odaklı Stok Takibi:**
   - Direnç (Ω, kΩ, tolerans), Kondansatör (pF, nF, uF, voltaj), Entegre/MCU, Sensör, Modül ve Konnektör gibi elektroniğe özel alanlar.
   - **Kutu / Çekmece Lokasyonu Takibi** (Örn: *Çekmece A-1, Direnç Organizeri 2, Arızalı Sepeti*).
   - Tek tıkla `+` / `-` hızlı stok miktarı değiştirme.

2. **⚠️ Arızalı & Çıkma Parça Yönetimi (Unutup Tekrar Almayı Önler!):**
   - Atölyenizdeki arızalı, şüpheli veya sökülüp parça alınacak kartları (`defective`, `untested`, `salvage`) ayrı olarak takip eder.
   - Her parça için **arıza sebebi** ve **sağlam kalan komponent notu** tutulur (Örn: *"Regülatörü yanık ama MCU sağlam, harici 3.3V ile çalışır"*).

3. **🤖 MCP Server (Model Context Protocol) Desteği:**
   - Herhangi bir AI asistanına (Cursor, Claude Desktop, Antigravity vb.):
     > *"Elimdeki parçalarla Bluetooth kontrollü 2 kanallı röle devresi yapmak istiyorum, nelerim var?"*
   - Dediğinizde, MCP sunucusu yerel envanterinizi tarar:
     - **Sağlam olan parçalarınızı** ve hangi kutuda olduklarını listeler.
     - **Elinizdeki arızalı parçalar için sizi uyarır** (boşuna bir daha almamanız veya devreyi yakmamanız için).
     - **Eksik parçaları** saptar ve Robotistan'dan stokta olan ürünleri fiyatlarıyla önerir.

4. **🌐 Robotistan Canlı Stok & Fiyat Scraper'ı:**
   - Robotistan.com web sitesini doğrudan tarar.
   - Ürünün **aktif stokta olup olmadığını** (Stokta Var / Tükendi) ve **canlı TL fiyatını** getirir.
   - Eksik parça listesi için tahmini sepet tutarını hesaplar.

5. **🛒 Robotistan Atölye Sepeti & Tek Tıkla Aktarım:**
   - Eksik parçaları tek tıkla sepete ekleyebilir, adetlerini güncelleyebilir ve canlı toplam tutarı görebilirsiniz.
   - **"⚡ Robotistan Sepetime Aktar"** özelliği sayesinde, Robotistan'ın yerleşik çoklu ürün ekleme motoru (T-Soft multiCart API) kullanılarak tüm parçalar doğrudan Robotistan sepetinize aktarılır.

6. **💻 Modern & Sıfır Bağımlılık Web Dashboard:**
   - Harici hiçbir `npm` veya ağır kütüphane kurulumu gerektirmez. Standart Python ile çalışır.
   - Karanlık elektronik çalışma masası teması (Tailwind CSS).
   - Anlık arama, kategori/durum filtreleme, kritik stok alarmları ve JSON veri yedekleme.

---

## 🚀 Hızlı Başlangıç

### 1. Web Arayüzünü Başlatma
Terminalde proje dizinindeyken:
```bash
./start.sh
# veya
python3 web_app.py
```
Tarayıcınızda açın: **[http://localhost:8080](http://localhost:8080)**

---

## 🔌 MCP Sunucusu (Model Context Protocol) Kurulumu

ElectroStock MCP sunucusu `stdio` üzerinden standart JSON-RPC 2.0 protokolü ile çalışır.

### Claude Desktop Kurulumu
`~/Library/Application Support/Claude/claude_desktop_config.json` dosyanızı açın ve aşağıdaki bloğu ekleyin:

```json
{
  "mcpServers": {
    "electro-stock": {
      "command": "python3",
      "args": [
        "/Users/emrullahardic/Documents/antigravity/nifty-tesla/mcp_server.py"
      ]
    }
  }
}
```

### Cursor Kurulumu
1. Cursor'da **Settings -> Features -> MCP** sekmesine gidin.
2. **Add New MCP Server** butonuna tıklayın:
   - **Name:** `electro-stock`
   - **Type:** `command`
   - **Command:** `python3 /Users/emrullahardic/Documents/antigravity/nifty-tesla/mcp_server.py`

### Antigravity / Claude Code / Diğer AI Araçları
Proje kökündeki `mcp_server.py` dosyasını `python3 mcp_server.py` komutuyla doğrudan stdio sunucusu olarak bağlayabilirsiniz.

---

## 🛠️ MCP Tool'ları (AI Botunun Kullanabileceği Fonksiyonlar)

| Tool Adı | Açıklama |
|---|---|
| `electro_suggest_project_components` | Proje açıklamasını analiz eder, stoktaki sağlam parçaları listeler, arızalılar için uyarır ve eksik parçaları Robotistan'dan çeker. |
| `electro_search_inventory` | Parça adı, değer (10k, 100nF), kılıf, durum veya saklama yerine göre envanterde arama yapar. |
| `electro_search_robotistan` | Robotistan.com'da canlı arama yaparak aktif stok ve güncel TL fiyatı çeker. |
| `electro_add_component` | Sohbet sırasında atölyeye yeni parça ekler. |
| `electro_update_stock` | Stok miktarını artırır/azaltır veya durumunu günceller (örn: sağlamdan arızalıya taşır). |
| `electro_get_defective_parts` | Arızalı, çıkma ve tamir bekleyen parçaları ve arıza notlarını listeler. |
| `electro_get_inventory_summary` | Genel stok sayılarını, kategori dağılımını ve saklama kutularını özetler. |
| `electro_add_to_cart` | Robotistan'dan temin edilecek eksik veya yeni parçaları atölye alışveriş sepetine ekler. |
| `electro_get_cart` | Atölye sepetindeki tüm parçaları, adetleri, toplam tutarı ve Robotistan linklerini listeler. |
| `electro_clear_cart` | Atölye sepetini tamamen temizler. |

---

## 📂 Proje Yapısı

```
nifty-tesla/
├── electro_db.py            # SQLite veritabanı, parçalar, stok logları ve istatistikler
├── robotistan_scraper.py    # Robotistan canlı HTML scraper & stok/fiyat çözümleyici
├── project_matcher.py       # Proje analizi, sağlam/arızalı ayrımı ve Robotistan eşleştirme motoru
├── mcp_server.py            # Model Context Protocol (MCP) JSON-RPC 2.0 stdio sunucusu
├── web_app.py               # Sıfır harici paket gerektiren REST API & Web sunucusu
├── seed_data.py             # Başlangıç örnek elektronik parçaları ve arızalı parça demoları
├── mcp_config_example.json  # Claude Desktop ve Cursor için örnek konfigürasyon
├── start.sh                 # Tek tıkla başlatma betiği
└── static/
    ├── index.html           # Modern SPA Web arayüzü
    ├── app.js               # Reaktif arayüz mantığı ve Robotistan canlı aramaları
    └── style.css            # Elektronik çalışma masası teması ve stiller
```

---

## 💡 Örnek Kullanım Senaryosu (AI ile Sohbet)

> **Siz:** *"Elimdeki parçalarla ESP32 ve sıcaklık sensörlü bir akıllı sera yapmak istiyorum, elimde neler var?"*
> 
> **AI Bot (MCP üzerinden):**
> 
> **✅ Stokta Mevcut ve Kullanıma Hazır:**
> - **ESP32 NodeMCU** (2 Adet) — 📍 MCU Kutusu D-1
> - **DHT11 Sıcaklık Sensörü** (2 Adet) — 📍 Sensör Kutusu E-1
> - **5V Tekli Röle Modülü** (3 Adet) — 📍 Modül Kutusu F-1
> 
> **⚠️ Arızalı Parça Uyarısı:**
> - Elinizde 1 adet **ESP32 WROOM DevKit** bulunuyor ancak **"Arızalı"** olarak kayıtlı! *(Not: 3.3V AMS1117 regülatörü yanık, harici besleme verilirse çalışabilir).*
> 
> **🛒 Eksik Parçalar ve Robotistan Canlı Fiyatları:**
> - **Toprak Nem Sensörü:** Robotistan'da stokta mevcut (Kapasitif Toprak Nem Sensörü - 65,40 TL).
> - **Mini Su Pompası (5V):** Robotistan'da stokta mevcut (Dalgıç Su Pompası - 110,25 TL).
> - **Tahmini Sepet Tutarı:** ~175,65 TL
