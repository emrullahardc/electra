"""
ElectroStock - Elektronik Komponent Eşleştirme, Donanım Alias ve Anlamsal Uyumluluk Motoru (Component Matcher)

Özellikler:
1. Donanım Alias Genişletme: Mağazalar arasındaki farklı isimlendirmeleri (örn. NEO-6M <-> GY-NEO6MV2, ESP32-C3 Super Mini <-> ESP32-C3 Mini) çözer.
2. Anlamsal Negatif Filtreleme (Entity Guard):
   - Pil/Batarya aramalarında Koruma Kartı (BMS/PCM), şarj aleti veya gösterge gibi aksesuarları eler.
   - Konnektörlerde pin sayısı uyuşmazlığını (2 pin yerine 6 pin) eler.
   - Kondansatörlerde dielektrik ve kılıf uyuşmazlığını (Seramik/SMD yerine Elektrolitik) eler.
   - Dirençlerde montaj tipi uyuşmazlığını (DIP/THT yerine SMD 0805) eler.
"""

import re
from typing import List, Dict, Any, Tuple, Optional


# Donanım Alias ve Eşdeğer Arama Haritası
KNOWN_COMPONENT_ALIASES: Dict[str, List[str]] = {
    # GPS / GNSS
    "neo-6m": ["GY-NEO6MV2", "NEO-6M", "NEO 6M", "GY-NEO-6M"],
    "gy-neo6mv2": ["GY-NEO6MV2", "NEO-6M", "NEO 6M"],
    "atgm336h": ["ATGM336H", "ATGM336"],
    "neo-m8n": ["NEO-M8N", "NEO-8M", "GY-NEO8MV2"],
    "max-m10s": ["MAX-M10S", "MAX-M10", "u-blox M10"],

    # ESP32 ve Geliştirme Kartları
    "esp32-c3 super mini": ["ESP32-C3 SuperMini", "ESP32-C3 Mini", "ESP32-C3 Super Mini", "ESP32-C3"],
    "esp32-c3 supermini": ["ESP32-C3 SuperMini", "ESP32-C3 Mini", "ESP32-C3"],
    "esp32-c3 mini": ["ESP32-C3 SuperMini", "ESP32-C3 Mini", "ESP32-C3"],
    "esp32-wroom": ["ESP-WROOM-32", "ESP32 NodeMCU", "ESP32 DevKit"],
    "pico w": ["Raspberry Pi Pico W", "RP2040 Pico W", "Pico"],

    # Güç, Şarj ve LiPo
    "tp4056": ["TP4056 Type-C", "TP4056 Micro-USB", "TP4056 Lipo Şarj"],
    "1s lipo": ["1S Lipo Batarya", "1S Lipo Pil", "3.7V Lipo Pil", "1S Lityum Polimer"],
    "1s lipo pil": ["1S Lipo Batarya", "1S Lipo Pil", "3.7V Lipo Pil", "1S Lityum Polimer"],
    "1s lipo 1000mah": ["1S 1000mAh Lipo Pil", "1S 3.7V 1000mAh Batarya", "Tinylab 1S 1000mAh", "1000mAh Lityum Polimer"],

    # Sensörler
    "bme280": ["BME280 I2C", "BME280 Sensör", "BMP280"],
    "bmp280": ["BMP280 I2C", "BME280"],
    "mpu6050": ["GY-521", "MPU-6050", "MPU6050 İvme"],
    "ds18b20": ["DS18B20 Su Geçirmez", "DS18B20 Sıcaklık Sensörü"]
}


def get_component_search_aliases(query: str) -> List[str]:
    """
    Verilen parça sorgusu için kataloglarda aranabilecek alternatif anahtar kelimeleri döndürür.
    """
    q_norm = query.strip().lower()
    q_clean = re.sub(r'[\s\-_]+', ' ', q_norm).strip()
    aliases = [query.strip()]

    # Doğrudan sözlük eşleşmesi
    for key, val_list in KNOWN_COMPONENT_ALIASES.items():
        k_clean = re.sub(r'[\s\-_]+', ' ', key).strip()
        if k_clean in q_clean or q_clean in k_clean:
            for term in val_list:
                if term.lower() not in [a.lower() for a in aliases]:
                    aliases.append(term)

    # 1. GPS Kalıpları
    if re.search(r'\b(?:neo[- ]?6m|neo6m|gy[- ]?neo6mv2)\b', q_norm):
        for term in ["GY-NEO6MV2", "NEO-6M", "NEO 6M"]:
            if term.lower() not in [a.lower() for a in aliases]:
                aliases.append(term)

    # 2. LiPo Pil Kalıpları (Kapasite ile)
    m_mah = re.search(r'(\d+)\s*mah', q_norm)
    if ("lipo" in q_norm or "li-po" in q_norm) and not any(k in q_norm for k in ["bms", "koruma", "şarj devresi"]):
        mah_val = m_mah.group(1) if m_mah else ""
        term1 = f"1S {mah_val}mAh Lipo Pil".strip() if mah_val else "1S Lipo Pil"
        term2 = f"3.7V {mah_val}mAh Lityum Polimer".strip() if mah_val else "1S Lityum Polimer"
        for t in [term1, term2]:
            if t.lower() not in [a.lower() for a in aliases]:
                aliases.append(t)

    # 3. JST Konnektör Kalıpları
    if "jst-ph" in q_norm or "jst ph" in q_norm:
        m_pin = re.search(r'(\d+)\s*(?:pin|p\b)', q_norm)
        if m_pin:
            p_cnt = m_pin.group(1)
            for t in [f"JST-PH {p_cnt} Pin", f"JST-PH 2.0 {p_cnt}P", f"JST-PH {p_cnt} Pin Kablolu"]:
                if t.lower() not in [a.lower() for a in aliases]:
                    aliases.append(t)

    # 4. Kondansatörler
    m_cap = re.search(r'(\d+(?:\.\d+)?)\s*(?:uf|µf|nf|pf)', q_norm)
    if m_cap:
        cap_val = m_cap.group(0).upper()
        if any(k in q_norm for k in ["smd", "seramik", "ceramic", "mlcc"]):
            for t in [f"{cap_val} SMD Kondansatör", f"{cap_val} 0805 Kondansatör", f"{cap_val} Seramik"]:
                if t.lower() not in [a.lower() for a in aliases]:
                    aliases.append(t)

    return aliases


def evaluate_component_relevance(query: str, product_title: str) -> Tuple[bool, float, str]:
    """
    Sorgu ile mağazada bulunan ürünün başlığını teknik uyumluluk açısından denetler.
    
    Döndürür:
    (is_valid: bool, score: float, reason: str)
    """
    q = query.lower().strip()
    t = product_title.lower().strip()

    # -------------------------------------------------------------
    # 1. PİL vs BMS / KORUMA KARTI / GÖSTERGE / AKSESUAR KONTROLÜ
    # -------------------------------------------------------------
    is_battery_search = any(k in q for k in ["pil", "batarya", "battery", "hücre", "cell", "akü"]) or (
        ("lipo" in q or "li-po" in q or "18650" in q or "lityum" in q) and not any(k in q for k in ["bms", "koruma", "pcm", "şarj devresi", "şarj modülü", "yuva"])
    )

    if is_battery_search:
        battery_disqualifiers = [
            "koruma kartı", "koruma karti", "koruma devresi", "bms", "pcm",
            "şarj devresi", "sarj devresi", "şarj modülü", "sarj modulu", "şarj kartı",
            "pil yuvası", "pil yuvasi", "pil tutucu", "battery holder", "pil kutusu",
            "kapasite göstergesi", "gostergesi", "test cihazı", "voltmetre",
            "nikel şerit", "lehim şeridi", "punta"
        ]
        for dq in battery_disqualifiers:
            if dq in t:
                return False, 0.0, f"Ürün bir pil değil, aksesuar/koruma devresi: '{dq}'"

    # BMS / Koruma kartı aranıyorsa çıplak pil gelmesini engelle
    is_bms_search = any(k in q for k in ["bms", "koruma kartı", "koruma devresi", "pcm"])
    if is_bms_search:
        if not any(k in t for k in ["bms", "koruma", "pcm", "devre", "kart"]):
            return False, 0.0, "BMS / Koruma kartı istendi ancak ürün devre/kart içermiyor."

    # -------------------------------------------------------------
    # 2. KONNEKTÖR VE PIN SAYISI KONTROLÜ
    # -------------------------------------------------------------
    q_pin_m = re.search(r'\b(\d+)\s*(?:pin|p\b|kutuplu|yollu)', q)
    if q_pin_m:
        req_pins = int(q_pin_m.group(1))
        t_pins = re.findall(r'\b(\d+)\s*(?:pin|p\b|kutuplu|yollu)', t)
        if t_pins:
            found_pins = [int(p) for p in t_pins]
            if req_pins not in found_pins:
                return False, 0.0, f"Pin sayısı uyuşmuyor: İstenen {req_pins} pin, üründeki pin {found_pins[0]}."

    # -------------------------------------------------------------
    # 3. KONDANSATÖR DİELEKTRİK VE KILIF KONTROLÜ
    # -------------------------------------------------------------
    if any(k in q for k in ["kondansatör", "kapasitör", "uf", "µf", "nf", "pf"]):
        if any(k in q for k in ["smd", "seramik", "ceramic", "mlcc"]):
            if any(k in t for k in ["elektrolitik", "electrolytic", "alüminyum", "radial", "bacaklı"]):
                return False, 0.0, "Kondansatör tipi uyuşmuyor: Seramik/SMD istendi, ürün Elektrolitik."
        elif "elektrolitik" in q:
            if any(k in t for k in ["seramik", "ceramic", "mlcc"]):
                return False, 0.0, "Kondansatör tipi uyuşmuyor: Elektrolitik istendi, ürün Seramik."

    # -------------------------------------------------------------
    # 4. MONTAJ / KILIF TİPİ KONTROLÜ (DIP / THT vs SMD)
    # -------------------------------------------------------------
    if any(k in q for k in ["dip", "tht", "bacaklı", "1/4w", "çeyrek watt", "el lehim"]):
        if any(k in t for k in ["smd", "0805", "0603", "0402", "1206"]):
            return False, 0.0, "Montaj tipi uyuşmuyor: DIP/THT el lehimine uygun istendi, ürün SMD."
    elif any(k in q for k in ["smd", "0805", "0603", "1206"]):
        if any(k in t for k in ["dip", "tht", "bacaklı", "1/4w", "çeyrek watt"]):
            return False, 0.0, "Montaj tipi uyuşmuyor: SMD istendi, ürün DIP/THT."

    # -------------------------------------------------------------
    # 5. GPS MODÜL & ÇİP AİLESİ KONTROLÜ (Çapraz Yanlış İkame Engelleme)
    # -------------------------------------------------------------
    # MAX-M10S aranıyorsa NEO serisi veya ATGM eşleşemez
    if any(k in q for k in ["max-m10", "max-m10s", "m10s", "u-blox m10"]):
        if not any(k in t for k in ["max-m10", "m10s", "m10"]):
            return False, 0.0, "MAX-M10S istendi ancak ürün M10 serisi değil."

    # ATGM336H aranıyorsa NEO serisi eşleşemez
    if any(k in q for k in ["atgm336", "atgm336h", "atgm"]):
        if not any(k in t for k in ["atgm336", "atgm"]):
            return False, 0.0, "ATGM336H istendi ancak ürün ATGM serisi değil."

    # NEO-M8N / NEO-8M aranıyorsa NEO-6M veya MAX-M10 eşleşemez
    if any(k in q for k in ["neo-m8n", "neo-8m", "m8n", "neo8m"]):
        if not any(k in t for k in ["m8n", "neo-8", "neo-m8", "m8"]):
            return False, 0.0, "NEO-M8N istendi ancak ürün M8N serisi değil."

    # NEO-6M aranıyorsa NEO-8M veya ATGM eşleşemez
    if any(k in q for k in ["neo-6m", "neo6m", "gy-neo6mv2"]):
        if any(k in t for k in ["m8n", "neo-8", "neo-m8", "atgm"]):
            return False, 0.0, "NEO-6M yerine farklı nesil/üretici çip (M8N / ATGM) eşleşemez."
        if not any(k in t for k in ["neo-6", "neo6", "gy-neo6", "gyneo6", "gps"]):
            return False, 0.0, "NEO-6M anahtar kelimesiyle uyuşmuyor."

    # -------------------------------------------------------------
    # 6. KELİME ÖRTÜŞME SKORU
    # -------------------------------------------------------------
    stop_words = {"ve", "ile", "için", "icin", "adet", "set", "uyumlu", "li", "modülü", "modulu", "kartı", "karti"}
    q_words = [w for w in re.split(r'[\s\-_/,.]+', q) if len(w) > 1 and w not in stop_words]
    if not q_words:
        return True, 1.0, "Uyumlu"

    matched_words = sum(1 for w in q_words if w in t)
    score = matched_words / len(q_words)

    # Temel kelimelerin en az %30'u veya ana donanım kodu eşleşmeli
    if score < 0.25 and not any(k in t for k in ["neo-6m", "gy-neo6mv2", "esp32-c3", "supermini"]):
        return False, score, "Arama terimleri ürün başlığıyla yeterince örtüşmüyor."

    return True, score, "Teknik olarak uyumlu"

