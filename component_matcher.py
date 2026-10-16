"""
ElectroStock - Elektronik Komponent Eşleştirme, Donanım Alias ve Anlamsal Uyumluluk Motoru (Component Matcher)

Özellikler:
1. Türkçe & Ortografik Normalizasyon: Tire/boşluk/bitişik yazım farklarını (MPU-6050 <-> MPU6050 <-> MPU 6050,
   Super Mini <-> SuperMini, JST-PH <-> JST PH) ve Türkçe karakter dönüşümlerini genel kurallarla çözer.
2. Donanım & Breakout Alias Genişletme: Çip kodu ile modül/breakout kodu arasındaki bilinen eşleşmeleri
   (NEO-6M <-> GY-NEO6MV2, MPU6050 <-> GY-521, ADXL345 <-> GY-291 vb.) genişletir.
3. Çok Katmanlı Anlamsal Filtreleme (Entity & Parametric Guard):
   - Aksesuar / Kutu / Tutucu / Genişletme Kartı (Expansion Board / Shield) ayrımı.
   - Pil vs BMS / Koruma Kartı / Şarj Modülü / Gösterge / Pil Yuvası ayrımı.
   - Pil kimyası (LiFePO4 vs Li-ion/LiPo), hücre sayısı (1S vs 2S/3S/4S) ve kapasite (mAh ±%35) kontrolü.
   - Konnektör ailesi (JST-PH vs JST-XH, XT60 vs XT30) ve pin sayısı kontrolü.
   - Pasif eleman (Direnç Ohm/k/M, Kondansatör pF/nF/uF) sayısal değer, dielektrik (Seramik vs Elektrolit) ve kılıf (DIP/THT vs SMD) kontrolü.
   - Genel Alfanümerik Model / Çip Kodu Doğrulaması (MAX-M10S, ATGM336H, ESP32-C3, AO3401, HT7833, LIS3DH vb.).
"""

import re
from typing import List, Dict, Any, Tuple, Optional, Set


# Türkçe karakter -> ASCII dönüşüm tablosu
_TR_MAP = str.maketrans({
    "ç": "c", "Ç": "c",
    "ğ": "g", "Ğ": "g",
    "ı": "i", "I": "i", "İ": "i",
    "ö": "o", "Ö": "o",
    "ş": "s", "Ş": "s",
    "ü": "u", "Ü": "u",
    "µ": "u", "μ": "u",
    "Ω": "ohm", "ω": "ohm",
})


def normalize_tr(text: str) -> str:
    """Türkçe karakterleri ASCII karşılıklarına dönüştürür ve küçük harfe çevirir."""
    if not text:
        return ""
    return text.translate(_TR_MAP).lower().strip()


def normalize_compact(text: str) -> str:
    """Tire, boşluk ve alt çizgileri kaldırarak alfanümerik karşılaştırma dizgesi üretir."""
    return re.sub(r'[^a-z0-9.]+', '', normalize_tr(text))


# Çip kodu <-> Breakout / Modül kodu karşılık haritası (Çift yönlü doğrulama ve arama için)
BREAKOUT_IC_MAP: Dict[str, List[str]] = {
    "neo6m": ["gyneo6mv2", "gygps6mv2", "neo6mv2", "neo6m"],
    "gyneo6mv2": ["neo6m", "gyneo6mv2", "gygps6mv2"],
    "neom8n": ["gyneo8mv2", "gygpsv3neo", "neo8m", "neom8n"],
    "mpu6050": ["gy521", "mpu6050"],
    "gy521": ["mpu6050", "gy521"],
    "mpu9250": ["gy9250", "gy91", "mpu9250"],
    "adxl345": ["gy291", "adxl345"],
    "gy291": ["adxl345", "gy291"],
    "hmc5883": ["gy271", "hmc5883", "qmc5883"],
    "qmc5883": ["gy271", "qmc5883", "hmc5883"],
    "gy271": ["hmc5883", "qmc5883", "gy271"],
    "bmp180": ["gy68", "bmp180"],
    "bmp280": ["gybmp280", "bmp280"],
    "bme280": ["gybme280", "bme280"],
    "bh1750": ["gy302", "gy30", "bh1750"],
    "vl53l0x": ["gy530", "gyvl53l0x", "vl53l0x"],
    "ina219": ["gy219", "ina219"],
    "htu21d": ["gy21", "htu21", "sht21"],
    "max30100": ["gymax30100", "max30100"],
    "max30102": ["gymax30102", "max30102"],
}


# Donanım Alias ve Eşdeğer Arama Haritası
KNOWN_COMPONENT_ALIASES: Dict[str, List[str]] = {
    # GPS / GNSS
    "neo-6m": ["GY-NEO6MV2", "NEO-6M", "NEO 6M", "NEO6MV2"],
    "gy-neo6mv2": ["GY-NEO6MV2", "NEO-6M", "NEO 6M"],
    "atgm336h": ["ATGM336H", "ATGM336", "ATGM336H GPS"],
    "neo-m8n": ["NEO-M8N", "NEO-8M", "GY-NEO8MV2", "NEO M8N"],
    "max-m10s": ["MAX-M10S", "MAX-M10", "u-blox M10"],

    # ESP32 ve Geliştirme Kartları
    "esp32-c3 super mini": ["ESP32-C3 SuperMini", "ESP32-C3 Super Mini", "ESP32 C3 Super Mini", "ESP32-C3 Mini", "ESP32-C3", "ESP32 C3"],
    "esp32-c3 supermini": ["ESP32-C3 SuperMini", "ESP32-C3 Super Mini", "ESP32 C3 Super Mini", "ESP32-C3 Mini", "ESP32-C3", "ESP32 C3"],
    "esp32-c3 mini": ["ESP32-C3 SuperMini", "ESP32-C3 Mini", "ESP32-C3", "ESP32 C3"],
    "esp32-c3": ["ESP32-C3", "ESP32 C3", "ESP32-C3 SuperMini", "ESP32-C3 Mini"],
    "esp32-s3": ["ESP32-S3", "ESP32 S3"],
    "esp32-wroom": ["ESP-WROOM-32", "ESP32 NodeMCU", "ESP32 DevKit", "ESP32"],
    "pico w": ["Raspberry Pi Pico W", "RP2040 Pico W", "Pico W"],

    # Güç, Şarj, BMS ve LiPo
    "tp4056": ["TP4056", "TP4056 Type-C", "TP4056 Lipo Şarj"],
    "1s koruma kartı": ["1S BMS", "1S Koruma Kartı", "1S 3.7V BMS", "1S Li-ion Koruma"],
    "1s pil koruma kartı": ["1S BMS", "1S Koruma Kartı", "1S 3.7V BMS", "1S Li-ion Koruma"],
    "1s bms": ["1S BMS", "1S Koruma Kartı", "1S 3.7V BMS"],
    "1s lipo": ["3.7V Lipo Pil", "1S Lipo Pil", "1S Lipo Batarya", "Lityum Polimer Pil"],
    "1s lipo pil": ["3.7V Lipo Pil", "1S Lipo Pil", "1S Lipo Batarya", "Lityum Polimer Pil"],
    "1s lipo 1000mah": ["3.7V 1000mAh Lipo Pil", "1000mAh Lipo Pil", "1S 1000mAh Lipo", "3.7V 1000mAh Li-Polymer"],

    # Sensörler
    "bme280": ["BME280", "GY-BME280", "BME280 Sensör"],
    "bmp280": ["BMP280", "GY-BMP280", "BMP280 Sensör"],
    "mpu6050": ["MPU6050", "GY-521", "MPU-6050", "MPU 6050"],
    "mpu-6050": ["MPU6050", "GY-521", "MPU-6050", "MPU 6050"],
    "adxl345": ["ADXL345", "GY-291", "ADXL-345"],
    "adxl-345": ["ADXL345", "GY-291", "ADXL-345"],
    "lis3dh": ["LIS3DH", "GY-LIS3DH"],
    "ds18b20": ["DS18B20", "DS18B20 Sıcaklık Sensörü"],
    "hc-sr04": ["HC-SR04", "HC SR04", "HCSR04"],

    # MOSFET & Regülatörler
    "ao3401": ["AO3401", "AO3401A", "SOT-23 P-Kanal MOSFET"],
    "ao3400": ["AO3400", "AO3400A", "SOT-23 N-Kanal MOSFET"],
    "ht7833": ["HT7833", "HT7333", "XC6206P332MR"],
    "ams1117-3.3": ["AMS1117 3.3V", "AMS1117-3.3", "AMS1117 3V3"],
}


# Model kodu SAYILMAYACAK genel parametre/birim/kategori/kılıf kelimeleri
_NON_MODEL_TOKENS: Set[str] = {
    # Kılıf / Montaj
    "smd", "smt", "dip", "tht", "dip8", "dip14", "dip16", "dip28", "dip40",
    "soic", "soic8", "sop8", "ssop", "tssop", "msop", "qfn", "qfp", "tqfp", "bga",
    "sot23", "sot223", "sot89", "to92", "to220", "to252", "to263", "dpak", "d2pak",
    "0402", "0603", "0805", "1206", "1210", "2512",
    # Pil hücre kodları ve boyutlar
    "18650", "21700", "14500", "16340", "26650", "cr2032", "cr2025", "cr2016", "cr1220",
    "1s", "2s", "3s", "4s", "5s", "6s", "7s", "8s",
    "1p", "2p", "3p", "4p", "5p", "6p", "7p", "8p", "9p", "10p", "12p", "16p", "20p", "40p",
    # Arayüz / Protokol / Genel kısaltmalar
    "i2c", "spi", "uart", "usart", "usb", "typec", "microusb", "miniusb",
    "pwm", "adc", "dac", "gpio", "ttl", "rs232", "rs485", "can",
    "rgb", "argb", "led", "lcd", "oled", "tft", "ips",
    "gps", "gnss", "gsm", "gprs", "lte", "4g", "3g", "2g", "wifi", "ble", "bt", "rf", "lora", "rfid", "nfc",
    "pcb", "bms", "pcm", "ldo", "dc", "ac", "esr", "mlcc", "ntc", "ptc", "ldr", "pir", "ssr",
    "sma", "rpsma", "ipex", "ufl", "jst", "xh", "ph", "sh", "gh", "dupont",
    "x7r", "x5r", "y5v", "c0g", "np0", "1w", "2w", "3w", "5w", "10w",
    "3v3", "5v", "12v", "24v", "36v", "48v",
}


def _is_parametric_token(tok: str) -> bool:
    """Bir alfanümerik token'ın voltaj/akım/kapasite/direnç/pin gibi parametrik değer olup olmadığını kontrol eder."""
    if tok in _NON_MODEL_TOKENS:
        return True
    # Sayı + birim (örn: 1000mah, 3.7v, 10uf, 100k, 4k7, 2pin, 100ohm, 16mhz, 2.0mm, 1/4w, 2x40)
    if re.match(r'^\d+(?:\.\d+)?(?:v|volt|mv|kv|a|ma|ua|mah|ah|wh|w|mw|uf|nf|pf|mf|ohm|r|k|m|kohm|mohm|hz|khz|mhz|ghz|pin|pinli|p|s|mm|cm|m|bit|ch|kanal|db|dbi|c|awg|adet|li|lu)$', tok):
        return True
    # 4k7, 2r2, 3v3, 1n5 gibi ara harfli değer gösterimleri
    if re.match(r'^\d+[vrukmn]\d+$', tok):
        return True
    # Boyut/matris gösterimleri (1x40, 2x20, 3x4, 5x7, 6x6)
    if re.match(r'^\d+x\d+(?:mm)?$', tok):
        return True
    return False


def extract_model_codes(query: str) -> List[str]:
    """
    Sorgu içerisindeki spesifik donanım/çip/model kodlarını (örn: neo-6m, max-m10s, atgm336h,
    esp32-c3, ao3401, ht7833, lis3dh, mpu6050, bme280, irlz44n) ayıklar.
    Genel birim ve parametreleri (1000mAh, 3.7V, 10uF, 100k, 0805, 1S, 2P) hariç tutar.
    """
    q_tr = normalize_tr(query)
    codes: List[str] = []

    # 1. Tireli özel model kodlarını yakala (örn: neo-6m, max-m10s, esp32-c3, hc-sr04, gy-neo6mv2, gy-521)
    for m in re.finditer(r'\b([a-z]{2,8}-\d{1,5}[a-z0-9]*|[a-z]{2,5}\d{1,4}-[a-z0-9]{1,6}|gy-[a-z0-9]{2,10}|hc-sr\d{2})\b', q_tr):
        raw_code = m.group(1)
        compact = re.sub(r'[^a-z0-9]', '', raw_code)
        if not _is_parametric_token(compact) and raw_code not in codes:
            codes.append(raw_code)

    # 2. Tekil alfanümerik model kelimelerini yakala (örn: atgm336h, ao3401, ht7833, mpu6050, lis3dh, bme280)
    tokens = re.split(r'[\s,;/()\[\]]+', q_tr)
    for tok in tokens:
        tok_clean = tok.strip('.-_+')
        if not tok_clean or '-' in tok_clean:
            continue
        # Hem harf hem rakam içermeli ve en az 4 karakter olmalı
        if len(tok_clean) >= 4 and re.search(r'[a-z]', tok_clean) and re.search(r'\d', tok_clean):
            if not _is_parametric_token(tok_clean):
                # Zaten tireli bir kodun parçası değilse ekle
                if not any(tok_clean in c.replace('-', '') for c in codes):
                    codes.append(tok_clean)

    return codes


def get_component_search_aliases(query: str) -> List[str]:
    """
    Verilen parça sorgusu için kataloglarda aranabilecek alternatif anahtar kelimeleri döndürür.
    T-Soft ve IdeaSoft arama motorlarının tire/boşluk hassasiyetini (MPU-6050 vs MPU6050,
    ESP32-C3 vs ESP32 C3, JST-PH vs JST PH) otomatik ortografik varyasyonlarla çözer.
    """
    q_raw = query.strip()
    q_norm = q_raw.lower()
    q_tr = normalize_tr(q_raw)
    q_clean = re.sub(r'[\s\-_]+', ' ', q_tr).strip()

    aliases: List[str] = []

    def _add(term: str):
        t_str = term.strip()
        if t_str and t_str.lower() not in [a.lower() for a in aliases]:
            aliases.append(t_str)

    _add(q_raw)

    # 1. Doğrudan sözlük eşleşmesi
    for key, val_list in KNOWN_COMPONENT_ALIASES.items():
        k_clean = re.sub(r'[\s\-_]+', ' ', normalize_tr(key)).strip()
        if k_clean == q_clean or k_clean in q_clean or (len(q_clean) >= 5 and q_clean in k_clean):
            for term in val_list:
                _add(term)

    # 2. Bileşik kelime varyasyonları (Super Mini <-> SuperMini, Li-Po <-> Lipo)
    if re.search(r'\bsuper\s+mini\b', q_tr):
        _add(re.sub(r'(?i)\bsuper\s+mini\b', 'SuperMini', q_raw))
    elif re.search(r'\bsupermini\b', q_tr):
        _add(re.sub(r'(?i)\bsupermini\b', 'Super Mini', q_raw))

    # 3. Genel Ortografik Model Kodu Varyasyonları (ABC-123 <-> ABC123 <-> ABC 123)
    model_codes = extract_model_codes(q_raw)
    for code in model_codes:
        c_compact = re.sub(r'[^a-z0-9]', '', code)
        # Harf ve rakam sınırından tireli / bitişik / boşluklu varyantlar üret
        m_split = re.match(r'^([a-z]+)[- ]?(\d+[a-z0-9]*)$', code)
        if m_split:
            prefix, suffix = m_split.group(1).upper(), m_split.group(2).upper()
            _add(f"{prefix}{suffix}")
            _add(f"{prefix}-{suffix}")
            _add(f"{prefix} {suffix}")
            # Sonunda tek revizyon harfi varsa (örn: AO3401A -> AO3401, MP1584EN -> MP1584)
            m_rev = re.match(r'^(\d{3,5})[A-Z]{1,2}$', suffix)
            if m_rev:
                _add(f"{prefix}{m_rev.group(1)}")
        elif '-' in code:
            _add(code.upper())
            _add(code.replace('-', ' ').upper())
            _add(code.replace('-', '').upper())

        # Breakout karşılığı varsa ekle (örn: mpu6050 -> GY-521, neo6m -> GY-NEO6MV2)
        if c_compact in BREAKOUT_IC_MAP:
            for brk in BREAKOUT_IC_MAP[c_compact]:
                if brk.startswith("gy") and len(brk) > 2 and brk[2:].isdigit():
                    _add(f"GY-{brk[2:]}")
                elif brk == "gyneo6mv2":
                    _add("GY-NEO6MV2")

    # 4. LiPo / Pil Kalıpları
    m_mah = re.search(r'(\d+)\s*mah', q_tr)
    is_bms_q = any(k in q_tr for k in ["bms", "koruma", "pcm", "sarj devresi", "sarj modulu"])
    if ("lipo" in q_tr or "li-po" in q_tr or "lityum polimer" in q_tr) and not is_bms_q:
        mah_val = m_mah.group(1) if m_mah else ""
        if mah_val:
            _add(f"3.7V {mah_val}mAh Lipo Pil")
            _add(f"{mah_val}mAh Lipo Pil")
            _add(f"1S {mah_val}mAh Lipo")
            _add(f"3.7V {mah_val}mAh Li-Polymer")
        else:
            _add("3.7V Lipo Pil")
            _add("1S Lipo Pil")
            _add("1S Lipo Batarya")

    # 5. BMS / Pil Koruma Kartı Kalıpları
    if is_bms_q:
        m_cell = re.search(r'\b([1-8]s)\b', q_tr)
        cell_str = m_cell.group(1).upper() if m_cell else "1S"
        _add(f"{cell_str} BMS")
        _add(f"{cell_str} Koruma Kartı")
        _add(f"{cell_str} Li-ion Koruma")
        if cell_str == "1S":
            _add("1S 3.7V BMS")

    # 6. JST Konnektör Kalıpları
    m_jst = re.search(r'\bjst[- ]?(ph|xh|sh|gh|sm)\b', q_tr)
    if m_jst:
        series = m_jst.group(1).upper()
        m_pin = re.search(r'\b(\d+)\s*(?:pin|pinli|p\b|kutuplu)', q_tr)
        if m_pin:
            p_cnt = m_pin.group(1)
            _add(f"JST-{series} {p_cnt} Pin")
            _add(f"JST {series} {p_cnt} Pin")
            _add(f"JST-{series} {p_cnt}P")
        else:
            _add(f"JST-{series}")
            _add(f"JST {series}")

    # 7. Kondansatör Kalıpları
    m_cap = re.search(r'(\d+(?:[.,]\d+)?)\s*(uf|nf|pf)\b', q_tr)
    if m_cap:
        val_num = m_cap.group(1).replace(',', '.')
        unit_raw = m_cap.group(2).lower()
        unit_fmt = "uF" if unit_raw == "uf" else ("nF" if unit_raw == "nf" else "pF")
        cap_str = f"{val_num}{unit_fmt}"
        if any(k in q_tr for k in ["seramik", "ceramic", "mlcc"]):
            _add(f"{cap_str} Seramik Kondansatör")
            _add(f"{cap_str} SMD Kondansatör")
            _add(f"{cap_str} 0805 Kondansatör")
        elif any(k in q_tr for k in ["smd", "0805", "0603", "1206"]):
            _add(f"{cap_str} SMD Kondansatör")
            _add(f"{cap_str} 0805")
        else:
            _add(f"{cap_str} Kondansatör")

    # 8. Direnç Kalıpları
    if any(k in q_tr for k in ["direnc", "resistor", "ohm", "kohm"]):
        m_res = re.search(r'\b(\d+(?:[.,]\d+)?)\s*(k|m|r|ohm|kohm|mohm)?\b', q_tr)
        if m_res:
            r_num = m_res.group(1)
            r_unit = (m_res.group(2) or "").upper()
            if r_unit in ("K", "KOHM"):
                if any(k in q_tr for k in ["smd", "0805", "0603"]):
                    _add(f"{r_num}K SMD Direnç")
                    _add(f"{r_num}K 0805 Direnç")
                else:
                    _add(f"{r_num}K Direnç")
                    _add(f"{r_num}K 1/4W Direnç")

    return aliases


def _parse_resistance_ohms(text: str) -> List[float]:
    """Metindeki direnç değerlerini (örn: 100k, 4.7k, 4k7, 220R, 100 Ohm) Ohm cinsinden ayıklar."""
    t = normalize_tr(text)
    vals: List[float] = []

    # 4k7, 2r2, 1m5 formatı
    for m in re.finditer(r'\b(\d+)(r|k|m)(\d+)\b', t):
        whole, mult_ch, frac = m.group(1), m.group(2), m.group(3)
        base = float(f"{whole}.{frac}")
        mult = 1.0 if mult_ch == 'r' else (1e3 if mult_ch == 'k' else 1e6)
        vals.append(base * mult)

    # 100k, 4.7k, 10kohm, 220 ohm, 220r formatı
    for m in re.finditer(r'(?<![a-z0-9])(\d+(?:[.,]\d+)?)\s*(kohm|mohm|ohm|k|r)(?![a-z0-9])', t):
        num = float(m.group(1).replace(',', '.'))
        u = m.group(2)
        if u in ('k', 'kohm'):
            vals.append(num * 1e3)
        elif u == 'mohm':
            vals.append(num * 1e6)
        elif u in ('r', 'ohm'):
            vals.append(num)

    return vals


def _parse_capacitance_pf(text: str) -> List[float]:
    """Metindeki kapasitans değerlerini (pF, nF, uF/µF) pF cinsinden ayıklar."""
    t = normalize_tr(text)
    vals: List[float] = []
    for m in re.finditer(r'(?<![a-z0-9])(\d+(?:[.,]\d+)?)\s*(uf|nf|pf)(?![a-z0-9])', t):
        num = float(m.group(1).replace(',', '.'))
        u = m.group(2)
        if u == 'uf':
            vals.append(num * 1e6)
        elif u == 'nf':
            vals.append(num * 1e3)
        elif u == 'pf':
            vals.append(num)
    return vals


def evaluate_component_relevance(query: str, product_title: str) -> Tuple[bool, float, str]:
    """
    Sorgu ile mağazada bulunan ürünün başlığını teknik ve anlamsal uyumluluk açısından denetler.

    Döndürür:
    (is_valid: bool, score: float, reason: str)
    """
    if not product_title or not product_title.strip():
        return False, 0.0, "Boş ürün başlığı."

    q = query.lower().strip()
    t = product_title.lower().strip()
    q_tr = normalize_tr(query)
    t_tr = normalize_tr(product_title)
    t_compact = normalize_compact(product_title)

    # -------------------------------------------------------------
    # 1. EVRENSEL AKSESUAR / GENİŞLETME KARTI / KUTU / TUTUCU KORUMASI
    # -------------------------------------------------------------
    # Sorgu doğrudan aksesuar/genişletme kartı/kutu/tutucu istemiyorsa, bu yan ürünleri ele!
    accessory_markers = [
        ("expansion board", "Genişletme kartı (Expansion Board)"),
        ("expansion shield", "Genişletme shield"),
        ("genisletme kart", "Genişletme kartı"),
        ("sensor shield", "Sensör shield"),
        ("io shield", "I/O shield"),
        ("base board", "Taban kartı (Base Board)"),
        ("taban kart", "Taban kartı"),
        ("adaptor kart", "Adaptör kartı"),
        ("pleksi", "Pleksi kutu/aksesuar"),
        ("koruma kutu", "Koruma kutusu"),
        ("muhafaza kutu", "Muhafaza kutusu"),
        ("plastik kutu", "Plastik kutu"),
        ("aluminyum kutu", "Alüminyum kutu"),
        ("akrilik kutu", "Akrilik kutu"),
        ("tutucu aparat", "Tutucu aparat"),
        ("montaj aparat", "Montaj aparatı"),
        ("tutucu ayag", "Tutucu ayak"),
        ("montaj braket", "Montaj braketi"),
        ("bos pcb", "Boş PCB"),
        ("tasima cantasi", "Taşıma çantası"),
        ("silikon kilif", "Silikon kılıf"),
    ]
    q_asks_accessory = any(
        k in q_tr for k in [
            "expansion", "genisletme", "shield", "base board", "taban kart",
            "adaptor", "adapter", "kutu", "case", "pleksi", "muhafaza",
            "tutucu", "aparat", "braket", "bracket", "holder", "yuva", "bos pcb", "kilif"
        ]
    )
    if not q_asks_accessory:
        for marker, label in accessory_markers:
            if marker in t_tr:
                return False, 0.0, f"Ana komponent yerine aksesuar/yan ürün: '{label}'"

    # -------------------------------------------------------------
    # 2. PİL vs BMS / KORUMA KARTI / GÖSTERGE / YUVA + KİMYA & HÜCRE & KAPASİTE
    # -------------------------------------------------------------
    is_bms_search = any(k in q_tr for k in ["bms", "koruma kart", "koruma devre", "koruma modul", "pcm", "korumali"]) and not any(
        k in q_tr for k in ["mah", "lityum polimer pil"]
    )
    is_battery_search = not is_bms_search and (
        any(k in q_tr for k in ["pil", "batarya", "battery", "hucre", "cell", "aku"]) or (
            any(k in q_tr for k in ["lipo", "li-po", "18650", "lityum", "li-polymer", "mah"])
            and not any(k in q_tr for k in ["bms", "koruma", "pcm", "sarj", "yuva", "tutucu", "gosterge"])
        )
    )

    if is_battery_search:
        battery_disqualifiers = [
            "koruma kart", "koruma devre", "koruma modul", "bms", "pcm",
            "sarj devre", "sarj modul", "sarj kart", "sarj cihaz", "sarj alet", "charger", "tp4056",
            "pil yuva", "pil tutucu", "battery holder", "pil kutu", "18650 yuva",
            "kapasite gosterge", "pil gosterge", "seviye gosterge", "test cihaz", "voltmetre", "buzzer", "alarm",
            "nikel serit", "lehim serid", "punta", "pil band", "makaron", "yanmaz torba", "lipo cantasi", "lipo guard"
        ]
        for dq in battery_disqualifiers:
            if dq.strip() in t_tr:
                return False, 0.0, f"Ürün bir pil değil, aksesuar/koruma/şarj devresi: '{dq.strip()}'"

        # Başlıkta gerçekten pil/batarya/hücre/mAh olduğuna dair emare olmalı
        if not any(k in t_tr for k in ["pil", "batarya", "battery", "lipo", "li-po", "polimer", "polymer", "18650", "mah"]):
            return False, 0.0, "Ürün başlığı pil/batarya niteliği taşımıyor."

    if is_bms_search:
        if not any(k in t_tr for k in ["bms", "koruma", "pcm", "balans"]):
            return False, 0.0, "BMS / Koruma kartı istendi ancak ürün koruma devresi içermiyor."

    # Pil Kimyası Kontrolü (LiFePO4 vs Standart 3.7V Li-ion/LiPo)
    if is_battery_search or is_bms_search:
        q_wants_lifepo4 = any(k in q_tr for k in ["lifepo4", "li-fe", "demir fosfat", "3.2v"])
        t_is_lifepo4 = any(k in t_tr for k in ["lifepo4", "li-fepo4", "demir fosfat", "3.2v", "3.6v lifepo"])
        if not q_wants_lifepo4 and t_is_lifepo4:
            return False, 0.0, "Pil kimyası uyuşmuyor: Standart 3.7V Li-ion/LiPo yerine 3.2V LiFePO4."
        if q_wants_lifepo4 and not t_is_lifepo4:
            return False, 0.0, "Pil kimyası uyuşmuyor: LiFePO4 istendi."

        # Seri Hücre Sayısı Kontrolü (1S vs 2S/3S/4S...)
        q_cell_m = re.search(r'(?<![0-9-])([1-8])s(?![a-z0-9-])', q_tr)
        if q_cell_m:
            req_s = int(q_cell_m.group(1))
            # 1s-8s gibi gösterge aralıklarını yakala
            if re.search(r'\b1s[-/]?[68]s\b', t_tr) and "gosterge" not in q_tr:
                return False, 0.0, "Çok hücreli gösterge (1S-8S), tekil hücre ürünü değil."
            t_cells = [int(x) for x in re.findall(r'(?<![0-9-])([1-8])s(?![a-z0-9-])', t_tr)]
            if t_cells and req_s not in t_cells:
                return False, 0.0, f"Hücre sayısı uyuşmuyor: İstenen {req_s}S, üründeki {t_cells[0]}S."

        # Pil Kapasitesi (mAh) Yakınlık Kontrolü (±%35 tolerans)
        q_mah_m = re.search(r'(\d+)\s*mah', q_tr)
        if q_mah_m and is_battery_search:
            req_mah = float(q_mah_m.group(1))
            t_mahs = [float(x) for x in re.findall(r'(\d+)\s*mah', t_tr)]
            if t_mahs:
                closest_diff = min(abs(tm - req_mah) / max(req_mah, 1.0) for tm in t_mahs)
                if closest_diff > 0.35:
                    return False, 0.0, f"Pil kapasitesi uyuşmuyor: İstenen {int(req_mah)}mAh, üründeki {int(t_mahs[0])}mAh."

    # -------------------------------------------------------------
    # 3. KONNEKTÖR AİLESİ VE PIN SAYISI KONTROLÜ
    # -------------------------------------------------------------
    # JST alt serisi kontrolü (JST-PH vs JST-XH vs JST-SH vs JST-SM)
    q_jst_m = re.search(r'\bjst[- ]?(ph|xh|sh|gh|sm)\b', q_tr)
    if q_jst_m:
        req_jst = q_jst_m.group(1)
        t_jst_m = re.findall(r'\bjst[- ]?(ph|xh|sh|gh|sm)\b', t_tr)
        if t_jst_m and req_jst not in t_jst_m:
            return False, 0.0, f"JST serisi uyuşmuyor: İstenen JST-{req_jst.upper()}, üründeki JST-{t_jst_m[0].upper()}."
        if req_jst == "ph":
            if "2.54" in t_tr and "2.0" not in t_tr:
                return False, 0.0, "JST-PH (2.0mm) istendi ancak ürün 2.54mm (XH) konnektör."
            if not re.search(r'\bph\b|jst[- ]?ph|2\.0\s*mm|2\.0mm', t_tr):
                return False, 0.0, "JST-PH (2.0mm) serisi ürün başlığında doğrulanamadı."
        elif req_jst == "xh":
            if not re.search(r'\bxh\b|jst[- ]?xh|2\.54\s*mm|2\.54mm', t_tr):
                return False, 0.0, "JST-XH (2.54mm) serisi ürün başlığında doğrulanamadı."
        else:
            if not re.search(rf'\b{req_jst}\b|jst[- ]?{req_jst}', t_tr):
                return False, 0.0, f"JST-{req_jst.upper()} serisi ürün başlığında doğrulanamadı."

    # Pin sayısı kontrolü
    q_pin_m = re.search(r'\b(\d+)\s*(?:pin|pinli|p\b|kutuplu|yollu)', q_tr)
    if q_pin_m:
        req_pins = int(q_pin_m.group(1))
        t_pins = [int(p) for p in re.findall(r'\b(\d+)\s*(?:pin|pinli|p\b|kutuplu|yollu)', t_tr)]
        if t_pins and req_pins not in t_pins:
            return False, 0.0, f"Pin sayısı uyuşmuyor: İstenen {req_pins} pin, üründeki {t_pins[0]} pin."

    # -------------------------------------------------------------
    # 4. PASİF KOMPONENT (DİRENÇ / KONDANSATÖR) DEĞER, DİELEKTRİK VE KILIF KONTROLÜ
    # -------------------------------------------------------------
    # 4a. Kondansatör Kontrolleri
    is_cap_search = any(k in q_tr for k in ["kondansator", "kapasitor", "capacitor", "seramik", "mlcc", "elektrolit"]) or bool(_parse_capacitance_pf(q_tr))
    if is_cap_search:
        q_caps = _parse_capacitance_pf(q_tr)
        t_caps = _parse_capacitance_pf(t_tr)
        if q_caps and t_caps:
            req_pf = q_caps[0]
            if not any(abs(tc - req_pf) / max(req_pf, 1e-6) <= 0.05 for tc in t_caps):
                return False, 0.0, "Kondansatör kapasitans değeri uyuşmuyor."

        # Dielektrik kontrolü (Robotistan 'Elektrolit' yazar, 'Elektrolitik' değil!)
        if any(k in q_tr for k in ["seramik", "ceramic", "mlcc"]):
            if any(k in t_tr for k in ["elektrolit", "electrolytic", "aluminyum", "tantal", "radial", "bacakli"]):
                return False, 0.0, "Kondansatör tipi uyuşmuyor: Seramik istendi, ürün Elektrolitik/Tantal."
        elif any(k in q_tr for k in ["elektrolit", "electrolytic"]):
            if any(k in t_tr for k in ["seramik", "ceramic", "mlcc", "mercimek"]):
                return False, 0.0, "Kondansatör tipi uyuşmuyor: Elektrolitik istendi, ürün Seramik."

    # 4b. Direnç Kontrolleri
    is_res_search = any(k in q_tr for k in ["direnc", "resistor", "ohm", "kohm", "1/4w", "ceyrek watt"])
    if is_res_search:
        q_res = _parse_resistance_ohms(q_tr)
        t_res = _parse_resistance_ohms(t_tr)
        if q_res and t_res:
            req_ohm = q_res[0]
            if not any(abs(tr - req_ohm) / max(req_ohm, 1e-6) <= 0.02 for tr in t_res):
                return False, 0.0, f"Direnç değeri uyuşmuyor: İstenen {req_ohm:g} Ohm, üründeki {t_res[0]:g} Ohm."

    # 4c. Montaj / Kılıf Tipi Kontrolü (DIP/THT vs SMD)
    if any(k in q_tr for k in ["dip", "tht", "bacakli", "delik ici", "1/4w", "1/2w", "ceyrek watt", "el lehim"]):
        if any(k in t_tr for k in ["smd", "smt", "0402", "0603", "0805", "805", "1206"]):
            return False, 0.0, "Montaj tipi uyuşmuyor: DIP/THT bacaklı istendi, ürün SMD."
    elif any(k in q_tr for k in ["smd", "smt", "0402", "0603", "0805", "1206", "sot-23", "sot23"]):
        if any(k in t_tr for k in ["dip", "tht", "bacakli", "1/4w", "ceyrek watt", "to-220", "to-92"]):
            return False, 0.0, "Montaj tipi uyuşmuyor: SMD istendi, ürün DIP/THT bacaklı."
        # Pasif elemanlarda (kondansatör/direnç) SMD istendiyse, başlıkta mutlaka SMD veya kılıf kodu geçmeli
        if is_cap_search or is_res_search:
            if not any(k in t_tr for k in ["smd", "smt", "0402", "0603", "0805", "805", "1206", "1210", "2512", "mlcc"]):
                return False, 0.0, "SMD pasif komponent istendi ancak ürün başlığında SMD/kılıf ibaresi yok (muhtemelen bacaklı THT)."

    # Spesifik SMD kılıf boyutu (0402 / 0603 / 0805 / 1206) kontrolü
    q_smd_m = re.search(r'\b(0402|0603|0805|1206)\b', q_tr)
    if q_smd_m:
        req_pkg = q_smd_m.group(1)
        t_pkgs = [("0805" if p == "805" else p) for p in re.findall(r'\b(0402|0603|0805|805|1206)\b', t_tr)]
        if t_pkgs and req_pkg not in t_pkgs:
            return False, 0.0, f"SMD kılıf boyutu uyuşmuyor: İstenen {req_pkg}, üründeki {t_pkgs[0]}."

    # -------------------------------------------------------------
    # 5. MOSFET KANAL KUTupluluğu (N-Kanal vs P-Kanal)
    # -------------------------------------------------------------
    if any(k in q_tr for k in ["p-kanal", "p kanal", "p-channel", "p channel", "pmos"]):
        if any(k in t_tr for k in ["n-kanal", "n kanal", "n-channel", "n channel", "nmos"]):
            return False, 0.0, "MOSFET kanal tipi uyuşmuyor: P-Kanal istendi, ürün N-Kanal."
    elif any(k in q_tr for k in ["n-kanal", "n kanal", "n-channel", "n channel", "nmos"]):
        if any(k in t_tr for k in ["p-kanal", "p kanal", "p-channel", "p channel", "pmos"]):
            return False, 0.0, "MOSFET kanal tipi uyuşmuyor: N-Kanal istendi, ürün P-Kanal."

    # -------------------------------------------------------------
    # 6. EVRENSEL ALFANÜMERİK MODEL / ÇİP KODU DOĞRULAMASI
    # -------------------------------------------------------------
    model_codes = extract_model_codes(query)
    for code in model_codes:
        c_compact = re.sub(r'[^a-z0-9]', '', code)
        # Kabul edilebilir eşdeğer/breakout kod listesi
        accepted_compacts = {c_compact}
        if c_compact in BREAKOUT_IC_MAP:
            accepted_compacts.update(BREAKOUT_IC_MAP[c_compact])

        # Sonunda tek revizyon harfi olan IC kodlarında (örn: ao3401a -> ao3401, atgm336h -> atgm336, mp1584en -> mp1584)
        m_rev = re.match(r'^([a-z]{2,6}\d{3,5})[a-z]{1,2}$', c_compact)
        if m_rev:
            accepted_compacts.add(m_rev.group(1))

        # Özel durum: NEO-6M için gyneo6 / neo6 kabul edilir ama neo8 / m8n / m10 / atgm kesinlikle reddedilir
        if c_compact in ("neo6m", "gyneo6mv2"):
            if any(bad in t_compact for bad in ["neom8", "neo8", "m8n", "maxm10", "m10s", "atgm"]):
                return False, 0.0, "NEO-6M yerine farklı nesil/üretici GPS çipi eşleşemez."
            accepted_compacts.update({"neo6", "gyneo6"})

        # Özel durum: BME280 istendiğinde yalnızca BMP280 olan ürünü reddet (BMP280 nem ölçmez)
        if c_compact == "bme280" and "bmp280" in t_compact and "bme280" not in t_compact:
            return False, 0.0, "BME280 (Sıcaklık+Basınç+Nem) istendi ancak ürün yalnızca BMP280 (Nem sensörü yok)."

        # Özel durum: ESP32 alt ailesi (ESP32-C3, ESP32-S3, ESP32-S2, ESP32-C6, ESP32-H2)
        m_esp = re.match(r'^esp32([csxh]\d)$', c_compact)
        if m_esp:
            sub_family = m_esp.group(1)  # örn: c3, s3
            if "esp32" not in t_compact or sub_family not in t_tr:
                return False, 0.0, f"ESP32 alt serisi uyuşmuyor: ESP32-{sub_family.upper()} istendi."
            continue

        # Genel kontrol: Ürün başlığında model kodu veya bilinen breakout karşılığı geçiyor mu?
        if not any(acc in t_compact for acc in accepted_compacts):
            return False, 0.0, f"Spesifik model/çip kodu ('{code.upper()}') ürün başlığında bulunamadı."

    # ESP32 genel sorgusunda alt seri (C3, S3, S2) ayrı kelime olarak yazılmışsa (örn: "esp32 c3 super mini")
    if "esp32" in q_tr:
        for sub in ("c3", "s3", "s2", "c6", "h2"):
            if re.search(rf'\b{sub}\b', q_tr) and not re.search(rf'(?:esp32[- ]?{sub}|\b{sub}\b)', t_tr):
                return False, 0.0, f"ESP32-{sub.upper()} alt serisi ürün başlığında bulunamadı."

    # -------------------------------------------------------------
    # 7. KELİME VE ANLAMSAL ÖRTÜŞME SKORU
    # -------------------------------------------------------------
    stop_words = {
        "ve", "ile", "icin", "adet", "set", "uyumlu", "li", "lu",
        "modulu", "modul", "karti", "kart", "devresi", "devre", "sensoru", "sensor"
    }
    # Ondalık noktaları (3.3v, 4.7k, 0.96) BÖLMEDEN kelime ayırma!
    q_words = [
        w.strip('.,') for w in re.split(r'[\s\-_/(),;\[\]]+', q_tr)
        if len(w.strip('.,')) > 1 and w.strip('.,') not in stop_words
    ]
    if not q_words:
        return True, 1.0, "Uyumlu"

    matched_words = 0.0
    for w in q_words:
        w_comp = re.sub(r'[^a-z0-9.]', '', w)
        if w in t_tr or (w_comp and w_comp in t_compact):
            matched_words += 1.0
        elif w in ("lipo", "li-po", "polimer") and any(k in t_tr for k in ["lipo", "li-po", "polimer", "polymer"]):
            matched_words += 1.0
        elif w in ("pil", "batarya", "battery") and any(k in t_tr for k in ["pil", "batarya", "battery"]):
            matched_words += 1.0
        elif w in ("koruma", "bms", "pcm") and any(k in t_tr for k in ["koruma", "bms", "pcm"]):
            matched_words += 1.0
        elif w in ("kondansator", "kapasitor") and any(k in t_tr for k in ["kondansator", "kapasitor"]):
            matched_words += 1.0
        elif w_comp in BREAKOUT_IC_MAP and any(brk in t_compact for brk in BREAKOUT_IC_MAP[w_comp]):
            matched_words += 1.0

    score = min(1.0, matched_words / len(q_words))

    # Kapasite veya direnç tam eşleşmesinde skoru ödüllendir
    if is_battery_search:
        q_mah_m = re.search(r'(\d+)\s*mah', q_tr)
        if q_mah_m and f"{q_mah_m.group(1)}mah" in t_compact:
            score = min(1.0, score + 0.25)

    # Eğer spesifik model kodu doğrulamasından geçtiyse, en az 0.65 taban skor ver
    if model_codes:
        score = max(score, 0.65)

    if score < 0.35:
        return False, round(score, 2), "Arama terimleri ürün başlığıyla yeterince örtüşmüyor."

    return True, round(score, 2), "Teknik olarak uyumlu"
