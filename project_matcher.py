"""
Proje & Devre Bileşeni Eşleştirme Motoru (Project Matcher)
Bir proje fikrini analiz eder, stoktaki SAĞLAM ve ARIZALI parçaları ayırt eder,
eksik parçaları saptar ve Robotistan'dan temin edilebilecek ürünleri canlı eşleştirir.
"""

import re
from typing import List, Dict, Any, Optional
import electro_db
from robotistan_scraper import scraper

# Elektronik proje şablonları ve tipik gereksinimler sözlüğü
COMPONENT_KNOWLEDGE_BASE = [
    {
        "keywords": ["esp32", "wifi", "iot", "bluetooth", "akıllı ev", "web server"],
        "name": "ESP32 Geliştirme Kartı",
        "category": "ic_mcu",
        "search_terms": ["esp32", "esp-32s", "nodemcu"],
        "critical": True,
        "role": "Ana Mikrodenetleyici / IoT Beyni"
    },
    {
        "keywords": ["arduino", "uno", "nano", "atmega", "çizgi izleyen", "robot"],
        "name": "Arduino / ATmega Mikrodenetleyici Kartı",
        "category": "ic_mcu",
        "search_terms": ["arduino", "nano", "uno"],
        "critical": True,
        "role": "Mikrodenetleyici"
    },
    {
        "keywords": ["sıcaklık", "nem", "hava", "termostat", "dht11", "dht22", "sera"],
        "name": "Sıcaklık ve Nem Sensörü (DHT11 / DHT22)",
        "category": "sensor",
        "search_terms": ["dht11", "dht22", "sıcaklık sensörü", "bme280"],
        "critical": True,
        "role": "Ortam Sıcaklık / Nem Ölçümü"
    },
    {
        "keywords": ["ekran", "lcd", "oled", "gösterge", "display", "yazı"],
        "name": "Ekran / Gösterge Modülü (OLED 0.96 / I2C LCD 16x2)",
        "category": "module",
        "search_terms": ["oled", "lcd", "ssd1306", "1602"],
        "critical": False,
        "role": "Bilgi / Durum Göstergesi"
    },
    {
        "keywords": ["röle", "lamba", "220v", "anahtarlama", "klima", "priz", "motor kontrol"],
        "name": "5V Röle Modülü",
        "category": "module",
        "search_terms": ["röle", "relay", "5v röle"],
        "critical": True,
        "role": "Yüksek Gerilim / Yük Anahtarlama"
    },
    {
        "keywords": ["mesafe", "engel", "park", "ultrasonik", "hc-sr04"],
        "name": "Mesafe Sensörü (HC-SR04 / ToF)",
        "category": "sensor",
        "search_terms": ["hc-sr04", "mesafe", "ultrasonik"],
        "critical": True,
        "role": "Mesafe ve Engel Algılama"
    },
    {
        "keywords": ["hareket", "insan", "güvenlik", "alarm", "pir"],
        "name": "PIR Hareket Sensörü (HC-SR501)",
        "category": "sensor",
        "search_terms": ["pir", "hc-sr501", "hareket sensörü"],
        "critical": True,
        "role": "Ortam Hareket Algılama"
    },
    {
        "keywords": ["servo", "motor", "açı", "kol", "kapı"],
        "name": "SG90 / MG996R Servo Motor",
        "category": "module",
        "search_terms": ["sg90", "servo", "mg996r"],
        "critical": True,
        "role": "Mekanik Hareket / Açısal Konumlandırma"
    },
    {
        "keywords": ["besleme", "pil", "18650", "adaptör", "şarj", "tp4056", "güç"],
        "name": "Güç / Şarj Modülü (TP4056 / Buck Converter)",
        "category": "power",
        "search_terms": ["tp4056", "lm2596", "regülatör", "18650"],
        "critical": True,
        "role": "Güç Dağıtımı ve Şarj"
    },
    {
        "keywords": ["direnç", "pull-up", "led direnci", "akım sınırlama"],
        "name": "Direnç Seti (220Ω, 1kΩ, 4.7kΩ, 10kΩ)",
        "category": "resistor",
        "search_terms": ["10k", "220", "direnç", "1k"],
        "critical": False,
        "role": "Pull-up, Pull-down veya LED Akım Sınırlama"
    },
    {
        "keywords": ["led", "ışık", "bildirim", "gösterge"],
        "name": "LED (5mm Kırmızı / Yeşil / Mavi)",
        "category": "diode_led",
        "search_terms": ["led", "5mm", "diyot"],
        "critical": False,
        "role": "Görsel Durum Bildirimi"
    },
    {
        "keywords": ["kablo", "bağlantı", "jumper", "breadboard", "devre tahtası"],
        "name": "Jumper Kablolar & Breadboard",
        "category": "connector",
        "search_terms": ["jumper", "breadboard", "kablo"],
        "critical": False,
        "role": "Devre Kurulumu ve Prototipleme"
    }
]


def extract_required_components_from_text(description: str) -> List[Dict[str, Any]]:
    """Proje açıklamasından olası bileşen ihtiyaçlarını çıkarır."""
    desc_lower = description.lower()
    matched_requirements = []

    for item in COMPONENT_KNOWLEDGE_BASE:
        # Anahtar kelime eşleşmesi
        match_score = sum(1 for kw in item["keywords"] if kw in desc_lower)
        if match_score > 0:
            matched_requirements.append({
                "name": item["name"],
                "category": item["category"],
                "search_terms": item["search_terms"],
                "critical": item["critical"],
                "role": item["role"],
                "score": match_score
            })

    # Eğer özel bir tespit yapılamadıysa açıklamadaki sözcükleri temel al
    if not matched_requirements:
        # Genel prototipleme bileşenleri öner
        matched_requirements = [
            {
                "name": "Mikrodenetleyici Kartı",
                "category": "ic_mcu",
                "search_terms": ["arduino", "esp32"],
                "critical": True,
                "role": "Ana İşlemci",
                "score": 1
            },
            {
                "name": "Jumper Kablo & Breadboard",
                "category": "connector",
                "search_terms": ["jumper", "breadboard"],
                "critical": False,
                "role": "Prototipleme",
                "score": 1
            }
        ]

    matched_requirements.sort(key=lambda x: x["score"], reverse=True)
    return matched_requirements


def match_project_components(
    project_description: str,
    custom_requirements: Optional[List[str]] = None,
    check_robotistan: bool = True,
    auto_create_draft_order: bool = False,
    db_path: str = electro_db.DB_PATH
) -> Dict[str, Any]:
    """
    Kullanıcının projesi için stok analizi yapar:
    1. Stokta SAĞLAM olan uygun parçaları listeler (Lokasyon ve adet bilgisiyle).
    2. Stokta olan ancak ARIZALI veya TEST BEKLEYEN parçaları kullanıcıya UYARI olarak sunar (boşu boşuna tekrar almasını veya bozuk parçayı devreye takmasını engeller!).
    3. Stokta OLMAYAN parçaları belirler ve Robotistan'dan stokta olan ürünleri fiyatlarıyla çeker.
    """
    needed_items = []

    if custom_requirements:
        for cr in custom_requirements:
            needed_items.append({
                "name": cr,
                "category": "",
                "search_terms": [cr.lower()],
                "critical": True,
                "role": "Kullanıcı Tarafından İstenen Parça",
                "score": 1
            })
    else:
        needed_items = extract_required_components_from_text(project_description)

    available_working: List[Dict[str, Any]] = []
    defective_warnings: List[Dict[str, Any]] = []
    missing_items: List[Dict[str, Any]] = []

    for item in needed_items:
        found_in_stock = False
        terms = item["search_terms"]

        # Stokta arama yap
        candidate_matches = []
        for t in terms:
            matches = electro_db.search_components(query=t, db_path=db_path)
            for m in matches:
                if m not in candidate_matches:
                    candidate_matches.append(m)

        working_parts = [p for p in candidate_matches if p["status"] == "working" and p["quantity"] > 0]
        broken_parts = [p for p in candidate_matches if p["status"] in ("defective", "untested", "salvage")]

        if working_parts:
            found_in_stock = True
            available_working.append({
                "required_role": item["name"],
                "matched_parts": [
                    {
                        "id": p["id"],
                        "name": p["name"],
                        "value": p["value"],
                        "package": p["package"],
                        "quantity": p["quantity"],
                        "location": p["location"] or "Belirtilmemiş",
                        "status": p["status"],
                        "notes": p["notes"]
                    } for p in working_parts
                ]
            })

        # Eğer kullanıcının elinde arızalı / test bekleyen versiyonu varsa MUTLAKA uyar
        if broken_parts:
            defective_warnings.append({
                "required_role": item["name"],
                "warning_message": f"Elinizde bu parçaya ait {len(broken_parts)} adet arızalı/şüpheli kayıt bulundu!",
                "parts": [
                    {
                        "id": p["id"],
                        "name": p["name"],
                        "status": electro_db.STATUSES.get(p["status"], p["status"]),
                        "location": p["location"] or "Arızalı Kutusu",
                        "notes": p["notes"] or "Arıza notu girilmemiş"
                    } for p in broken_parts
                ]
            })

        # Eğer sağlam hiç yoksa eksik listesine ekle
        if not working_parts:
            missing_items.append(item)

    # Eksik parçalar için Robotistan araması
    robotistan_recommendations: List[Dict[str, Any]] = []
    total_estimated_cost = 0.0

    if check_robotistan and missing_items:
        for m_item in missing_items:
            search_query = m_item["search_terms"][0] if m_item["search_terms"] else m_item["name"]
            rob_res = scraper.search(query=search_query, only_in_stock=True, limit=3)
            
            # Robotistan'dan stokta olan ürün önerisi
            recommended_products = rob_res.get("results", [])

            # Robotistan'da bulunamadıysa piyasa aramasını (Robotronik, Direnç.net, Motorobit) dene
            if not recommended_products:
                try:
                    import market_scraper
                    mkt_res = market_scraper.search_market(query=search_query, only_in_stock=True, limit_per_vendor=3)
                    if mkt_res.get("results"):
                        recommended_products = mkt_res["results"][:3]
                except Exception:
                    pass
            
            # En uygun ilk ürünün fiyatını tahmini maliyete ekle
            if recommended_products and recommended_products[0].get("price_value"):
                total_estimated_cost += recommended_products[0]["price_value"]

            robotistan_recommendations.append({
                "missing_part_role": m_item["name"],
                "searched_query": search_query,
                "found_products": recommended_products,
                "in_stock_found": len(recommended_products) > 0
            })

    draft_order_id = None
    if auto_create_draft_order and missing_items:
        draft_items = []
        for rec in robotistan_recommendations:
            prods = rec.get("found_products", [])
            if prods:
                best = prods[0]
                v_src = best.get("vendor_key") or best.get("vendor") or "robotistan"
                draft_items.append({
                    "title": best.get("title", rec["missing_part_role"]),
                    "product_id": best.get("product_id"),
                    "url": best.get("url", ""),
                    "price": best.get("price", ""),
                    "price_value": best.get("price_value", 0.0),
                    "quantity": 1,
                    "in_stock": best.get("in_stock", True),
                    "source": str(v_src).lower(),
                    "notes": f"Gereksinim: {rec['missing_part_role']}"
                })
            else:
                draft_items.append({
                    "title": rec["missing_part_role"],
                    "source": "market",
                    "in_stock": False,
                    "url": "",
                    "price": "",
                    "price_value": 0.0,
                    "notes": f"Robotistan'da doğrudan stok bulunamadı ({rec['searched_query']})"
                })

        short_title = project_description[:45] + ("..." if len(project_description) > 45 else "")
        draft_order_id = electro_db.create_draft_order(
            title=f"{short_title} (BOM Taslağı)",
            description=project_description,
            items=draft_items,
            notes="AI proje analizi tarafından otomatik oluşturulan eksik parça taslak siparişi.",
            db_path=db_path
        )

    return {
        "project_description": project_description,
        "available_working_count": len(available_working),
        "defective_warning_count": len(defective_warnings),
        "missing_items_count": len(missing_items),
        "available_working": available_working,
        "defective_warnings": defective_warnings,
        "missing_items": [
            {
                "name": mi["name"],
                "category": mi["category"],
                "role": mi["role"]
            } for mi in missing_items
        ],
        "robotistan_recommendations": robotistan_recommendations,
        "estimated_robotistan_cost_tl": round(total_estimated_cost, 2),
        "draft_order_id": draft_order_id
    }



def format_project_analysis_markdown(analysis: Dict[str, Any]) -> str:
    """Analiz sonucunu AI Bot veya kullanıcı için zengin bir Markdown metnine dönüştürür."""
    md = []
    md.append(f"# 🛠️ Proje Malzeme Analizi: {analysis['project_description']}\n")

    # 1. Stoktaki Sağlam Parçalar
    md.append("## ✅ Stokta Mevcut ve Kullanıma Hazır Parçalar")
    if analysis["available_working"]:
        for aw in analysis["available_working"]:
            md.append(f"\n### 🔹 {aw['required_role']}")
            for p in aw["matched_parts"]:
                loc = f"📍 **Konum:** {p['location']}" if p['location'] else "📍 Konum belirtilmemiş"
                val = f"({p['value']})" if p['value'] else ""
                md.append(f"- **{p['name']}** {val} — **Adet:** {p['quantity']} | {loc}")
                if p["notes"]:
                    md.append(f"  *Not:* {p['notes']}")
    else:
        md.append("Stokta bu proje için doğrudan eşleşen sağlam parça bulunamadı.\n")

    # 2. Arızalı / Şüpheli Parça Uyarıları (Çok Önemli!)
    if analysis["defective_warnings"]:
        md.append("\n## ⚠️ Arızalı / Test Bekleyen Parça Uyarıları (Yenisini Almadan Önce İnceleyin!)")
        for dw in analysis["defective_warnings"]:
            md.append(f"\n> [!WARNING] **{dw['required_role']}** için arızalı kayıtlarınız var:")
            for p in dw["parts"]:
                md.append(f"> - **{p['name']}** [{p['status']}] — 📍 {p['location']}")
                md.append(f">   *Arıza Sebebi / Notu:* {p['notes']}")

    # 3. Eksik Parçalar ve Robotistan Canlı Fiyatları
    if analysis["missing_items"]:
        md.append("\n## 🛒 Eksik Parçalar ve Satın Alma İhtiyaçları")
        for mi in analysis["missing_items"]:
            md.append(f"- 🔴 **{mi['name']}** ({mi.get('role', 'Gerekli Bileşen')})")

        if analysis.get("robotistan_recommendations"):
            md.append("\n### 🌐 Robotistan Canlı Stok ve Fiyat Seçenekleri:")
            for rec in analysis["robotistan_recommendations"]:
                md.append(f"\n#### 📦 **{rec['missing_part_role']}**")
                if rec["found_products"]:
                    for prod in rec["found_products"]:
                        stok_badge = "🟢 Stokta Var" if prod["in_stock"] else "🔴 Tükendi"
                        md.append(f"- [{prod['title']}]({prod['url']}) — **{prod['price']}** ({stok_badge})")
                else:
                    md.append(f"- Robotistan'da '{rec['searched_query']}' araması için doğrudan stok bulunamadı.")
            
            if analysis.get("estimated_robotistan_cost_tl", 0) > 0:
                cost_val = float(analysis['estimated_robotistan_cost_tl'])
                md.append(f"\n💰 **Robotistan Tahmini Eksik Parça Sepet Tutarı:** ~{cost_val:.2f} TL")

        if analysis.get("draft_order_id"):
            md.append(f"\n📋 **Taslak Sipariş Listesi Kaydedildi:** `Draft #{analysis['draft_order_id']}`\n*Bu listeyi web arayüzündeki 'Draft Siparişler' sekmesinden görebilir veya tek tıkla doğrudan Robotistan sepetinize aktarabilirsiniz.*")
    else:
        md.append("\n## 🛒 Eksik Parçalar")
        md.append("Tebrikler! Proje için gereken tüm parçalar elinizdeki sağlam stokta mevcut! 🎉\n")

    return "\n".join(md)

