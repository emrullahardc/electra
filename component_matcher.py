"""
ElectroStock - Genel Parametrik ve Gramatikal Komponent Analiz Motoru (ComponentSpec Engine)

Mimari İlkeler (Sıfır Hardcoded Parça Sözlüğü):
1. Kod içinde sabit parça/model listesi (KNOWN_COMPONENT_ALIASES vb.) TUTULMAZ.
2. Her sorgu ve ürün başlığı evrensel bir `ComponentSpec` nesnesine ayrıştırılır:
   - Gramatikal Baş-Rol (Head-Role): Ürünün fiziksel olarak ne olduğu (Ana Komponent, Pil Hücresi,
     BMS/Koruma Devresi, Şarj Modülü, Genişletme Kartı/Shield, Kutu/Muhafaza, Tutucu/Aparat, Gösterge, Yuva).
   - Fiziksel ve Elektriksel Parametreler: Kapasitans (pF/nF/uF), Direnç (Ohm/k/M), Endüktans (uH/mH),
     Kapasite (mAh/Ah), Hücre Sayısı (1S..8S), Pin Sayısı, Pin Adımı (mm), Kılıf/Montaj (SMD/THT, 0402..1206, SOT-23 vb.),
     Kanal Kutupluluğu (N-Kanal/P-Kanal), Dielektrik (Seramik/Elektrolit/Tantal) ve Pil Kimyası (LiPo/Li-ion vs LiFePO4).
   - Sentaktik Model Tanımlayıcıları: Alfanümerik çip/model kodlarını (örn: <AİLE>-<VARYANT>) otomatik tanır ve
     ortografik varyasyonlarını (bitişik, tireli, boşluklu, revizyon kökü) dinamik üretir.
3. Mağazalar Arası Çapraz Öğrenme (Cross-Vendor Co-Occurrence Discovery):
   Bir mağazanın başlığında bir arada geçen çip ve modül kodlarını (örn: aynı başlıkta geçen MPU6050 ve GY-521,
   veya NEO-6M ve GY-NEO6MV2) çalışma anında keşfeder ve SQLite (`component_aliases`) tablosuna kaydeder.
"""

import re
from dataclasses import dataclass, field
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
    """Tire, boşluk ve noktalama işaretlerini kaldırarak alfanümerik karşılaştırma dizgesi üretir."""
    return re.sub(r'[^a-z0-9.]+', '', normalize_tr(text))


# Model kodu SAYILMAYACAK genel fiziksel birim, kılıf, protokol ve kategori belirteçleri
_UNIT_AND_GENERIC_TOKENS: Set[str] = {
    "smd", "smt", "dip", "tht", "dip8", "dip14", "dip16", "dip20", "dip28", "dip40",
    "soic", "soic8", "sop8", "ssop", "tssop", "msop", "qfn", "qfp", "tqfp", "bga",
    "sot23", "sot223", "sot89", "to92", "to220", "to252", "to263", "dpak", "d2pak",
    "0402", "0603", "0805", "1206", "1210", "2512",
    "18650", "21700", "14500", "16340", "26650", "cr2032", "cr2025", "cr2016", "cr1220",
    "1s", "2s", "3s", "4s", "5s", "6s", "7s", "8s",
    "1p", "2p", "3p", "4p", "5p", "6p", "7p", "8p", "9p", "10p", "12p", "16p", "20p", "40p",
    "i2c", "spi", "uart", "usart", "usb", "typec", "microusb", "miniusb",
    "pwm", "adc", "dac", "gpio", "ttl", "rs232", "rs485", "can",
    "rgb", "argb", "led", "lcd", "oled", "tft", "ips",
    "gps", "gnss", "gsm", "gprs", "lte", "4g", "3g", "2g", "wifi", "ble", "bt", "rf", "lora", "rfid", "nfc",
    "pcb", "bms", "pcm", "ldo", "dc", "ac", "esr", "mlcc", "ntc", "ptc", "ldr", "pir", "ssr",
    "sma", "rpsma", "ipex", "ufl", "jst", "dupont",
    "x7r", "x5r", "y5v", "c0g", "np0",
    "3v3", "5v", "12v", "24v", "36v", "48v",
    # Mağaza stok / SKU önekleri (model kodu değildir)
    "dstk", "khb", "af", "st", "xr", "yd",
}


def _is_parametric_or_sku_token(tok: str) -> bool:
    """Alfanümerik bir kelimenin fiziksel parametre (1000mAh, 10uF, 100k, 2.0mm) veya mağaza SKU kodu olup olmadığını denetler."""
    t = tok.lower().strip('.-_+')
    if not t or t in _UNIT_AND_GENERIC_TOKENS:
        return True
    # Mağaza iç stok kodları (DSTK22511, A0626, KHB.WFI...)
    if re.match(r'^(?:dstk\d+|a\d{4}|khb\w*|\d+mos)$', t):
        return True
    # Sayı + fiziksel birim (1000mah, 3.7v, 10uf, 100k, 4.7k, 2pin, 100ohm, 16mhz, 2.0mm, 40c, 10adet)
    if re.match(r'^\d+(?:[.,]\d+)?(?:v|volt|mv|kv|a|ma|ua|mah|ah|wh|w|mw|uf|nf|pf|mf|uh|mh|ohm|r|k|m|kohm|mohm|hz|khz|mhz|ghz|pin|pinli|p|s|mm|cm|m|bit|ch|kanal|db|dbi|c|awg|adet|li|lu|deg|derece|inc|inch)$', t):
        return True
    # Ara harfli birim gösterimi (4k7, 2r2, 3v3, 1n5)
    if re.match(r'^\d+[vrukmn]\d+$', t):
        return True
    # Boyut / matris gösterimi (1x40, 2x20, 32x4x2mm)
    if re.match(r'^\d+x\d+(?:x\d+)?(?:mm|cm)?$', t):
        return True
    return False


@dataclass
class ModelIdentifier:
    """Sentaktik olarak ayrıştırılmış donanım model kodu."""
    raw: str
    compact: str
    family: str = ""      # örn: 'esp32', 'neo', 'jst', 'mpu', 'ao'
    subvariant: str = ""  # örn: 'c3', '6m', 'ph', '6050', '3401'
    base_root: str = ""   # revizyon harfi kırpılmış kök (örn: ao3401a -> ao3401, mp1584en -> mp1584)


@dataclass
class ComponentSpec:
    """Bir sorgunun veya ürün başlığının yapılandırılmış teknik özeti."""
    raw: str
    norm: str
    compact: str
    role: str = "PRIMARY"  # PRIMARY, BATTERY_CELL, PROTECTION_BMS, CHARGER_MODULE, EXPANSION_SHIELD, ENCLOSURE_CASE, MOUNTING_BRACKET, HOLDER_SOCKET, METER_INDICATOR
    models: List[ModelIdentifier] = field(default_factory=list)
    capacitance_pf: List[float] = field(default_factory=list)
    resistance_ohm: List[float] = field(default_factory=list)
    inductance_uh: List[float] = field(default_factory=list)
    capacity_mah: List[float] = field(default_factory=list)
    pins: List[int] = field(default_factory=list)
    cells_s: List[int] = field(default_factory=list)
    is_multi_cell_range: bool = False
    pitch_mm: List[float] = field(default_factory=list)
    mounting: Optional[str] = None          # 'SMD' veya 'THT'
    mounting_preferred: Optional[str] = None # 'SMD' veya 'THT' (belirtilmediğinde varsayılan tercih)
    smd_footprints: List[str] = field(default_factory=list)
    polarity: Optional[str] = None          # 'P-CH', 'N-CH'
    chemistry: Optional[str] = None         # 'LIFEPO4', 'LIPO_LIION'
    dielectric: Optional[str] = None        # 'CERAMIC', 'ELECTROLYTIC', 'TANTALUM'
    connector_family: Optional[str] = None  # 'jst-ph', 'jst-xh', 'xt60', 'xt30' vb.
    form_factor: Optional[str] = None       # 'MODULE' (modül/kart/devre/breakout) veya 'IC' (entegre/çip/sop8/dip8)
    pack_quantity: int = 1                  # Paket içindeki adet (örn: 10 adet -> 10)
    is_passive: bool = False
    tokens: List[str] = field(default_factory=list)


def extract_model_identifiers(text: str) -> List[ModelIdentifier]:
    """
    Metin içerisindeki alfanümerik donanım/model kodlarını sentaktik kurallarla çıkarır.
    Hiçbir sabit parça listesine ihtiyaç duymaz; <AİLE>-<VARYANT> ve <HARF><RAKAM> yapılarını tanır.
    """
    t_tr = normalize_tr(text)
    identifiers: List[ModelIdentifier] = []
    seen_compacts: Set[str] = set()

    # 1. Tireli <PREFIX>-<SUFFIX> yapıları (örn: esp32-c3, neo-6m, max-m10s, gy-521, gy-neo6mv2, hc-sr04, jst-ph)
    for m in re.finditer(r'\b([a-z]{2,8}\d{0,4})-([a-z0-9]{1,10})\b', t_tr):
        p1, p2 = m.group(1), m.group(2)
        full_raw = f"{p1}-{p2}"
        comp = f"{p1}{p2}"
        # JST alt serisi konnektör ailesi olarak ayrıca işlenir, genel model kodu olarak alma
        if p1 == "jst" and p2 in ("ph", "xh", "sh", "gh", "sm"):
            continue
        # Li-Po, Li-ion, P-Kanal, N-Kanal, Step-Down, Type-C gibi genel kelimeleri atla
        if p1 in ("li", "step", "type", "micro", "mini", "dc", "ac", "wi", "hi", "lo", "pull", "push", "op", "t"):
            continue
        if not (re.search(r'\d', p1) or re.search(r'\d', p2)):
            continue
        if _is_parametric_or_sku_token(comp) or comp in seen_compacts:
            continue
        seen_compacts.add(comp)
        base_m = re.match(r'^([a-z]{2,6}\d{3,5})[a-z]{1,2}$', comp)
        base_root = base_m.group(1) if base_m else comp
        identifiers.append(ModelIdentifier(raw=full_raw, compact=comp, family=p1, subvariant=p2, base_root=base_root))

    # 2. Boşluklu <FAMILY> <SUBVARIANT> yapıları (örn: 'esp32 c3', 'esp32 s3', 'neo 6m', 'neo m8n', 'hc sr04')
    for m in re.finditer(r'\b(esp32|stm32|neo|max|hc|gy)\s+([csxh]\d|\d{1,3}[a-z]{1,3}|m\d{1,2}[a-z]?|sr\d{2})\b', t_tr):
        p1, p2 = m.group(1), m.group(2)
        comp = f"{p1}{p2}"
        if comp not in seen_compacts:
            seen_compacts.add(comp)
            identifiers.append(ModelIdentifier(raw=f"{p1}-{p2}", compact=comp, family=p1, subvariant=p2, base_root=comp))

    # 3. Tekil alfanümerik çip/model kodları (örn: mpu6050, atgm336h, ao3401, ht7833, bme280, lis3dh, irlz44n, sim800l)
    for tok in re.split(r'[\s,;/()\[\]]+', t_tr):
        tok_clean = tok.strip('.-_+')
        if not tok_clean or '-' in tok_clean:
            continue
        if len(tok_clean) >= 4 and re.search(r'[a-z]', tok_clean) and re.search(r'\d', tok_clean):
            if _is_parametric_or_sku_token(tok_clean):
                continue
            # Zaten tireli/boşluklu bir kodun parçasıysa tekrar ekleme
            if any(tok_clean in existing or existing in tok_clean for existing in seen_compacts):
                continue
            seen_compacts.add(tok_clean)
            m_sp = re.match(r'^([a-z]{2,6})(\d{2,5}[a-z0-9]*)$', tok_clean)
            fam = m_sp.group(1) if m_sp else ""
            sub = m_sp.group(2) if m_sp else ""
            base_m = re.match(r'^([a-z]{2,6}\d{3,5})[a-z]{1,2}$', tok_clean)
            base_root = base_m.group(1) if base_m else tok_clean
            identifiers.append(ModelIdentifier(raw=tok_clean, compact=tok_clean, family=fam, subvariant=sub, base_root=base_root))

    return identifiers


def extract_model_codes(query: str) -> List[str]:
    """Geriye dönük uyumluluk için model kodu dizgelerinin listesini döndürür."""
    return [m.raw for m in extract_model_identifiers(query)]


def _detect_functional_role(t_tr: str) -> str:
    """
    Türkçe ve İngilizce tamlama yapısına göre ürünün/sorgunun gramatikal baş-rolünü (Head-Role) belirler.
    Örn: 'ESP32-C3 Super Mini Genişletme Kartı' -> EXPANSION_SHIELD
         '1S 3A 3.7V Li-ion Lipo Batarya Koruma Kartı' -> PROTECTION_BMS
         '3.7V 1000mAh LiPo Pil' -> BATTERY_CELL
    """
    # 1. Genişletme Kartı / Shield / Taban Kartı / Boş PCB
    if any(k in t_tr for k in [
        "expansion board", "expansion shield", "genisletme kart", "sensor shield",
        "io shield", "base board", "taban kart", "adaptor kart", "bos pcb"
    ]):
        return "EXPANSION_SHIELD"

    # 2. Kutu / Muhafaza / Kılıf / Çanta
    if any(k in t_tr for k in [
        "pleksi", "koruma kutu", "muhafaza kutu", "plastik kutu", "aluminyum kutu",
        "akrilik kutu", "tasima cantasi", "silikon kilif", "lipo cantasi", "lipo guard", "yanmaz torba"
    ]):
        return "ENCLOSURE_CASE"

    # 3. Tutucu / Montaj Aparatı / Braket
    if any(k in t_tr for k in [
        "tutucu aparat", "montaj aparat", "tutucu ayag", "montaj braket", "motor tutucu", "sensor tutucu"
    ]):
        return "MOUNTING_BRACKET"

    # 4. Pil Yuvası / Soketi
    if any(k in t_tr for k in ["pil yuva", "pil tutucu", "battery holder", "pil kutu", "18650 yuva", "cr2032 yuva"]):
        return "HOLDER_SOCKET"

    # 5. Kapasite / Seviye Göstergesi / Test Cihazı
    if any(k in t_tr for k in ["kapasite gosterge", "pil gosterge", "seviye gosterge", "pil test", "voltmetre", "lipo alarm", "lipo buzzer"]):
        return "METER_INDICATOR"

    # 6. BMS / Pil Koruma Devresi
    if any(k in t_tr for k in ["bms", "koruma kart", "koruma devre", "koruma modul", "batarya koruyucu", "balans devre", "pcm"]):
        return "PROTECTION_BMS"

    # 7. Şarj Devresi / Şarj Aleti
    if any(k in t_tr for k in ["sarj devre", "sarj modul", "sarj kart", "sarj cihaz", "sarj alet", "lipo sarj", "charger"]):
        return "CHARGER_MODULE"

    # 7.5 Konnektör / Soket / Fiş / Terminal (JST, Dupont, Klemens, Header vb.)
    # "batarya konektörü" veya "lipo soket" pil hücresi DEĞİL, konnektördür!
    if any(k in t_tr for k in [
        "konektor", "konnektor", "connector", "header", "klemens", "terminal"
    ]) or (any(k in t_tr for k in ["soket", "socket", "kablo"]) and any(c in t_tr for c in ["jst", "dupont", "pin", "batarya", "pil", "lipo"])):
        return "CONNECTOR"

    # 8. Pil / Batarya Hücresi
    has_mah = bool(re.search(r'\b\d+\s*mah\b', t_tr))
    if any(k in t_tr for k in ["pil", "batarya", "battery", "lipo", "li-po", "lityum polimer", "li-polymer", "18650"]) or has_mah:
        # Nikel şerit, punta, makaron gibi sarf malzemeleri pil değildir
        if any(k in t_tr for k in ["nikel serit", "lehim serid", "punta", "pil band", "makaron"]):
            return "ACCESSORY_CONSUMABLE"
        return "BATTERY_CELL"

    return "PRIMARY"


def parse_component_spec(text: str) -> ComponentSpec:
    """Herhangi bir sorgu veya ürün başlığını evrensel fiziksel/elektriksel parametrelere ayrıştırır."""
    t_tr = normalize_tr(text)
    t_comp = normalize_compact(text)
    role = _detect_functional_role(t_tr)
    models = extract_model_identifiers(text)

    spec = ComponentSpec(raw=text, norm=t_tr, compact=t_comp, role=role, models=models)

    # 1. Kapasitans (pF, nF, uF)
    for m in re.finditer(r'(?<![a-z0-9])(\d+(?:[.,]\d+)?)\s*(uf|nf|pf)(?![a-z0-9])', t_tr):
        num = float(m.group(1).replace(',', '.'))
        u = m.group(2)
        pf = num * (1e6 if u == 'uf' else (1e3 if u == 'nf' else 1.0))
        spec.capacitance_pf.append(pf)

    # 2. Direnç (Ohm, k, M, 4k7, 2r2)
    is_res_ctx = any(k in t_tr for k in ["direnc", "resistor", "ohm", "kohm", "mohm", "1/4w", "1/2w", "ceyrek watt"])
    for m in re.finditer(r'\b(\d+)(r|k|m)(\d+)\b', t_tr):
        base = float(f"{m.group(1)}.{m.group(3)}")
        mult = 1.0 if m.group(2) == 'r' else (1e3 if m.group(2) == 'k' else 1e6)
        spec.resistance_ohm.append(base * mult)
    for m in re.finditer(r'(?<![a-z0-9])(\d+(?:[.,]\d+)?)\s*(kohm|mohm|ohm|k|r)(?![a-z0-9])', t_tr):
        num = float(m.group(1).replace(',', '.'))
        u = m.group(2)
        if u in ('kohm', 'mohm', 'ohm') or is_res_ctx:
            mult = 1e3 if u in ('k', 'kohm') else (1e6 if u == 'mohm' else 1.0)
            spec.resistance_ohm.append(num * mult)

    # 3. Endüktans (uH, mH)
    for m in re.finditer(r'(?<![a-z0-9])(\d+(?:[.,]\d+)?)\s*(uh|mh)(?![a-z0-9])', t_tr):
        num = float(m.group(1).replace(',', '.'))
        spec.inductance_uh.append(num * (1e3 if m.group(2) == 'mh' else 1.0))

    # 4. Pil Kapasitesi (mAh)
    for m in re.finditer(r'(?<![a-z0-9])(\d+(?:[.,]\d+)?)\s*mah(?![a-z0-9])', t_tr):
        spec.capacity_mah.append(float(m.group(1).replace(',', '.')))

    # 5. Hücre Sayısı (1S..8S)
    if re.search(r'\b1s[-/]?[468]s\b', t_tr):
        spec.is_multi_cell_range = True
    spec.cells_s = [int(x) for x in re.findall(r'(?<![0-9-])([1-8])s(?![a-z0-9-])', t_tr)]

    # 6. Pin Sayısı
    spec.pins = [int(p) for p in re.findall(r'\b(\d+)\s*(?:pin|pinli|p\b|kutuplu|yollu)', t_tr)]

    # 7. Konnektör Ailesi ve Pin Adımı (Pitch mm)
    m_jst = re.search(r'\bjst[- ]?(ph|xh|sh|gh|sm)\b', t_tr)
    if m_jst:
        spec.connector_family = f"jst-{m_jst.group(1)}"
    elif "2.0mm" in t_tr or "2.0 mm" in t_tr:
        if "jst" in t_tr or "ph" in t_tr:
            spec.connector_family = "jst-ph"
    elif "2.54mm" in t_tr or "2.54 mm" in t_tr:
        if "jst" in t_tr or "xh" in t_tr:
            spec.connector_family = "jst-xh"
    elif "jst" in t_tr:
        if any(k in t_tr for k in ["batarya", "pil", "lipo"]):
            spec.connector_family = "jst-ph"
        else:
            spec.connector_family = "jst"

    # 8. Montaj Tipi (SMD vs THT) ve Kılıf Boyutu
    smd_pkgs = [("0805" if p == "805" else p) for p in re.findall(r'\b(0402|0603|0805|805|1206|1210|2512|sot-?23|sot-?89|sot-?223|soic|qfn)\b', t_tr)]
    spec.smd_footprints = [p.replace('-', '') for p in smd_pkgs]
    if any(k in t_tr for k in ["smd", "smt", "mlcc"]) or spec.smd_footprints:
        spec.mounting = "SMD"
    elif any(k in t_tr for k in ["dip", "tht", "bacakli", "delik ici", "1/4w", "1/2w", "ceyrek watt", "el lehim", "to-220", "to-92", "radial"]):
        spec.mounting = "THT"

    # 9. Dielektrik Tipi (Kondansatörler için)
    if any(k in t_tr for k in ["seramik", "ceramic", "mlcc", "x7r", "x5r", "np0", "c0g"]):
        spec.dielectric = "CERAMIC"
    elif any(k in t_tr for k in ["elektrolit", "electrolytic", "aluminyum"]):
        spec.dielectric = "ELECTROLYTIC"
    elif any(k in t_tr for k in ["tantal", "tantalum"]):
        spec.dielectric = "TANTALUM"

    # 10. MOSFET / Transistör Kanal Kutupluluğu
    if any(k in t_tr for k in ["p-kanal", "p kanal", "p-channel", "p channel", "pmos"]):
        spec.polarity = "P-CH"
    elif any(k in t_tr for k in ["n-kanal", "n kanal", "n-channel", "n channel", "nmos"]):
        spec.polarity = "N-CH"

    # 11. Pil Kimyası
    if any(k in t_tr for k in ["lifepo4", "li-fe", "demir fosfat", "3.2v"]):
        spec.chemistry = "LIFEPO4"
    elif any(k in t_tr for k in ["ni-cd", "nicd", "ni-mh", "nimh", "nikel", "1.2v"]):
        spec.chemistry = "NIMH_NICD"
    elif any(k in t_tr for k in ["lipo", "li-po", "li-ion", "lityum", "polimer", "polymer", "18650", "3.7v"]):
        spec.chemistry = "LIPO_LIION"

    # 12. Form Faktörü (Modül / Devre Kartı vs Yalın Entegre / IC Çip)
    has_mod_kw = any(k in t_tr for k in ["modul", "modulu", "karti", "kart", "devresi", "devre", "breakout", "shield", "board"])
    has_ic_kw = any(k in t_tr for k in ["entegre", "entegresi", "kontrol entegresi", "smd sop8", "smd dip", "sop-8", "sop8", "dip-8", "dip8", "soic-8", "soic8", "qfn", "ic chip", "yalın entegre"])
    if has_mod_kw and not has_ic_kw:
        spec.form_factor = "MODULE"
    elif has_ic_kw and not has_mod_kw:
        spec.form_factor = "IC"
    elif has_mod_kw and has_ic_kw:
        if any(k in t_tr for k in ["sarj modul", "sarj devre", "gps modul", "sensor modul", "breakout"]):
            spec.form_factor = "MODULE"
        else:
            spec.form_factor = "IC"

    # 13. Paket / Adet Miktarı (Pack Quantity)
    m_pack = re.search(r'\b(\d+)\s*(?:adet|li paket|lu paket|pack|pcs)\b', t_tr)
    if m_pack:
        q_val = int(m_pack.group(1))
        if q_val in (2, 5, 10, 20, 25, 50, 100):
            spec.pack_quantity = q_val

    spec.is_passive = bool(spec.capacitance_pf or spec.resistance_ohm or spec.inductance_uh) or any(
        k in t_tr for k in ["kondansator", "kapasitor", "capacitor", "direnc", "resistor", "bobin", "induktor"]
    )
    if spec.mounting:
        spec.mounting_preferred = spec.mounting
    elif spec.is_passive:
        spec.mounting_preferred = "THT"

    stop_words = {
        "ve", "ile", "icin", "adet", "set", "uyumlu", "li", "lu",
        "modulu", "modul", "karti", "kart", "devresi", "devre", "sensoru", "sensor"
    }
    spec.tokens = [
        w.strip('.,') for w in re.split(r'[\s\-_/(),;\[\]]+', t_tr)
        if len(w.strip('.,')) > 1 and w.strip('.,') not in stop_words
    ]
    return spec


def discover_cooccurring_aliases(query: str, matched_titles: List[str]) -> List[str]:
    """
    Mağazalar arası çapraz aramada, sorguyla eşleştiği doğrulanmış bir ürün başlığında
    birlikte geçen alternatif modül/çip kodlarını (örn: 'MPU6050 ... GY-521' veya 'GY-NEO6MV2 ... NEO-6M')
    otomatik keşfeder, SQLite'a kaydeder ve eksik mağazalarda aranmak üzere döndürür.
    """
    q_spec = parse_component_spec(query)
    if not q_spec.models:
        return []

    q_compacts = {m.compact for m in q_spec.models}
    discovered: List[str] = []

    try:
        import electro_db
    except ImportError:
        electro_db = None

    for title in matched_titles:
        t_models = extract_model_identifiers(title)
        t_compacts = {tm.compact for tm in t_models}
        for qm in q_spec.models:
            if qm.compact not in t_compacts and qm.base_root not in t_compacts:
                continue
            for tm in t_models:
                if tm.compact not in q_compacts and len(tm.compact) >= 4:
                    term_upper = tm.raw.upper()
                    if term_upper not in discovered:
                        discovered.append(term_upper)
                    if electro_db:
                        electro_db.save_learned_alias(qm.compact, term_upper, tm.compact, source="cross_vendor")

    return discovered


def get_component_search_aliases(query: str) -> List[str]:
    """
    Sorgu için hiçbir sabit sözlüğe bağlı olmadan:
    1. Çoklu alternatif sözdizimini ('NEO-6M | GY-NEO6MV2') ayırır,
    2. SQLite `component_aliases` tablosunda daha önce öğrenilmiş karşılıkları çeker,
    3. `ComponentSpec` üzerinden ortografik varyantları (bitişik/tireli/boşluklu) ve
       parametrik çekirdek sorguları (<Değer><Birim> <Başİsim>) otomatik üretir.
    """
    aliases: List[str] = []

    def _add(term: str):
        t_str = term.strip()
        if t_str and t_str.lower() not in [a.lower() for a in aliases]:
            aliases.append(t_str)

    # Çoklu alternatif ayracı ('|' veya ' / ') desteği
    parts = [p.strip() for p in re.split(r'\s*\|\s*|\s+/\s+', query) if p.strip()]
    for p in parts:
        _add(p)

    spec = parse_component_spec(parts[0] if parts else query)
    q_raw = parts[0] if parts else query.strip()

    # 1. SQLite veritabanında öğrenilmiş alias'ları ve bilgi bankası anahtar kelimelerini çek
    try:
        import electro_db
        # A) component_aliases tablosu
        for m in spec.models:
            for row in electro_db.get_learned_aliases(m.compact):
                _add(row["alias_term"])

    except Exception:
        pass

    # 2. Bileşik kelime ortografisi (Super Mini <-> SuperMini, Pro Mini <-> ProMini)
    for w1, w2 in [("super", "mini"), ("pro", "mini"), ("node", "mcu"), ("dev", "kit")]:
        if re.search(rf'(?i)\b{w1}\s+{w2}\b', q_raw):
            _add(re.sub(rf'(?i)\b{w1}\s+{w2}\b', f"{w1.capitalize()}{w2.capitalize()}", q_raw))
        elif re.search(rf'(?i)\b{w1}{w2}\b', q_raw):
            _add(re.sub(rf'(?i)\b{w1}{w2}\b', f"{w1.capitalize()} {w2.capitalize()}", q_raw))

    # 3. Sentaktik Model Kodu Ortografik Varyasyonları (ABC-123 <-> ABC123 <-> ABC 123)
    for m in spec.models:
        if m.family and m.subvariant:
            fam_u, sub_u = m.family.upper(), m.subvariant.upper()
            _add(f"{fam_u}-{sub_u}")
            _add(f"{fam_u}{sub_u}")
            _add(f"{fam_u} {sub_u}")
            # Evrensel Çin / Maker Breakout kuralı (GY- prefiksli modüller: GY-NEO6MV2, GY-521, GY-271, GY-BMP280)
            if m.family == "neo":
                _add(f"GY-{fam_u}{sub_u}V2")
                _add(f"GY-{fam_u}{sub_u}")
            elif m.family in ("mpu", "hmc", "bmp", "bme", "mlx", "vl"):
                _add(f"GY-{sub_u}")
                _add(f"GY-{fam_u}{sub_u}")
        if m.base_root and m.base_root != m.compact:
            _add(m.base_root.upper())

    # 4. Parametrik Çekirdek Sorgu Üretimi (Mağaza arama motorlarının çok kelimeli sorgularda 0 dönmesini önler)
    if spec.role == "BATTERY_CELL":
        cell_str = f"{spec.cells_s[0]}S" if spec.cells_s else "1S"
        mah_val = int(spec.capacity_mah[0]) if spec.capacity_mah else None
        if mah_val:
            _add(f"{mah_val}mAh Pil")
            _add(f"{mah_val}mAh Li-Po")
            _add(f"{mah_val}mAh")
            _add(f"{cell_str} {mah_val}mAh Lipo")
            _add(f"{cell_str} Lipo Pil")
            _add(f"{cell_str} Lipo")
            _add(f"{cell_str} Batarya")
        else:
            _add(f"{cell_str} Lipo Pil")
            _add(f"{cell_str} Lipo")
            _add("Lipo Pil")

    elif spec.role == "PROTECTION_BMS":
        cell_str = f"{spec.cells_s[0]}S" if spec.cells_s else "1S"
        _add(f"{cell_str} BMS")
        _add(f"{cell_str} Koruma Kartı")
        _add(f"{cell_str} Pil Koruma Kartı")
        _add(f"{cell_str} LiPo Koruma Kartı")
        _add(f"{cell_str} Li-ion Koruma")
        _add("1S Koruma Kartı")
        _add("Pil Koruma Kartı")

    elif spec.role == "CHARGER_MODULE":
        if any(m.family == "tp" for m in spec.models):
            _add("TP4056 Modül")
            _add("TP4056 Şarj Modülü")
            _add("TP4056 Şarj Devresi")
            _add("TP4056 Type-C")

    elif spec.connector_family or spec.role == "CONNECTOR":
        p = spec.pins[0] if spec.pins else None
        cf = spec.connector_family or "jst"
        cf_u = cf.upper()
        cf_sp = cf_u.replace('-', ' ')

        if "jst" in cf:
            if p:
                _add(f"JST-PH {p}-Pin")
                _add(f"JST-PH {p} Pin")
                _add(f"JST {p}-Pin")
                _add(f"JST {p} Pin")
                _add(f"JST-PH {p}P")
                _add(f"JST {p}P")
                _add(f"JST-PH {p}")
                _add(f"JST {p}")
                _add("JST-PH 2.0mm")
                _add("JST-PH")
            else:
                _add("JST-PH")
                _add("JST Konnektör")
                _add("JST Konektör")
            _add("JST Konnektör")
            _add("JST Konektör")
        else:
            if p:
                _add(f"{cf_u} {p}-Pin")
                _add(f"{cf_u} {p} Pin")
                _add(f"{cf_sp} {p} Pin")
                _add(f"{cf_u} {p}P")
            else:
                _add(cf_u)
                _add(cf_sp)

    elif spec.capacitance_pf:
        pf = spec.capacitance_pf[0]
        if pf >= 1e6:
            cap_str = f"{pf / 1e6:g}uF"
        elif pf >= 1e3:
            cap_str = f"{pf / 1e3:g}nF"
        else:
            cap_str = f"{pf:g}pF"
        if spec.dielectric == "CERAMIC":
            if spec.mounting == "SMD":
                _add(f"{cap_str} SMD Seramik Kondansatör")
                _add(f"{cap_str} SMD Kondansatör")
            else:
                _add(f"{cap_str} Seramik Kondansatör")
                _add(f"{cap_str} Kondansatör")
        elif spec.mounting == "SMD":
            _add(f"{cap_str} SMD Kondansatör")
            _add(f"{cap_str} 0805")
        else:
            _add(f"{cap_str} Kondansatör")
            _add(f"{cap_str} Elektrolitik Kondansatör")

    elif spec.resistance_ohm:
        ohm = spec.resistance_ohm[0]
        if ohm >= 1e6:
            r_str = f"{ohm / 1e6:g}M"
        elif ohm >= 1e3:
            r_str = f"{ohm / 1e3:g}K"
        else:
            r_str = f"{ohm:g}R"
        if spec.mounting == "SMD":
            _add(f"{r_str} SMD Direnç")
        elif spec.mounting == "THT":
            _add(f"{r_str} 1/4W Direnç")
            _add(f"{r_str} Direnç")
        else:
            _add(f"{r_str} 1/4W Direnç")
            _add(f"{r_str} Direnç")
            _add(f"{r_str} 1/4 W Direnç")
            _add(f"1/4W {r_str} Direnç")

    return aliases


def _evaluate_single_spec_relevance(q_spec: ComponentSpec, t_spec: ComponentSpec) -> Tuple[bool, float, str]:
    """İki `ComponentSpec` nesnesini gramatikal rol, fiziksel parametreler ve model kodu açısından karşılaştırır."""

    # 1. GRAMATİKAL BAŞ-ROL (HEAD-ROLE) UYUMLULUĞU
    # Ana komponent veya pil ararken kutu, tutucu, genişletme kartı (expansion board), BMS, gösterge gelmesini engelle
    auxiliary_roles = {
        "EXPANSION_SHIELD", "ENCLOSURE_CASE", "MOUNTING_BRACKET",
        "HOLDER_SOCKET", "METER_INDICATOR", "ACCESSORY_CONSUMABLE"
    }
    if q_spec.role not in auxiliary_roles and t_spec.role in auxiliary_roles:
        return False, 0.0, f"Fonksiyonel rol uyuşmazlığı: İstenen '{q_spec.role}', ürün '{t_spec.role}'."

    if q_spec.role == "BATTERY_CELL" and t_spec.role != "BATTERY_CELL":
        return False, 0.0, f"Pil/Batarya hücresi istendi ancak ürün '{t_spec.role}'."

    if q_spec.role == "PROTECTION_BMS" and t_spec.role != "PROTECTION_BMS":
        return False, 0.0, f"BMS/Koruma devresi istendi ancak ürün '{t_spec.role}'."

    if q_spec.role == "CONNECTOR" and t_spec.role != "CONNECTOR":
        return False, 0.0, f"Konnektör istendi ancak ürün '{t_spec.role}'."

    if q_spec.role != "CONNECTOR" and t_spec.role == "CONNECTOR":
        return False, 0.0, f"Ürün konnektör/soket ancak istenen '{q_spec.role}'."

    # 2. FİZİKSEL VE ELEKTRİKSEL PARAMETRE DOĞRULAMASI
    # 2a. Pil Kimyası ve Hücre Sayısı
    if q_spec.role in ("BATTERY_CELL", "PROTECTION_BMS", "CHARGER_MODULE"):
        if q_spec.chemistry == "LIPO_LIION" and t_spec.chemistry in ("LIFEPO4", "NIMH_NICD"):
            return False, 0.0, f"Pil kimyası uyuşmuyor: Standart 3.7V LiPo/Li-ion yerine {t_spec.chemistry}."
        if q_spec.chemistry == "LIFEPO4" and t_spec.chemistry != "LIFEPO4":
            return False, 0.0, "Pil kimyası uyuşmuyor: LiFePO4 istendi."

        if q_spec.cells_s:
            if t_spec.is_multi_cell_range and q_spec.role != "METER_INDICATOR":
                return False, 0.0, "Çok hücreli aralık (1S-8S), tekil hücre ürünü değil."
            if t_spec.cells_s and q_spec.cells_s[0] not in t_spec.cells_s:
                return False, 0.0, f"Hücre sayısı uyuşmuyor: İstenen {q_spec.cells_s[0]}S, üründeki {t_spec.cells_s[0]}S."

        if q_spec.capacity_mah and q_spec.role == "BATTERY_CELL" and t_spec.capacity_mah:
            req_mah = q_spec.capacity_mah[0]
            closest_diff = min(abs(tm - req_mah) / max(req_mah, 1.0) for tm in t_spec.capacity_mah)
            if closest_diff > 0.35:
                return False, 0.0, f"Pil kapasitesi uyuşmuyor: İstenen {int(req_mah)}mAh, üründeki {int(t_spec.capacity_mah[0])}mAh."

    # 2b. Konnektör Ailesi ve Pin Sayısı
    if q_spec.connector_family:
        if q_spec.connector_family != "jst" and t_spec.connector_family and t_spec.connector_family != "jst":
            if t_spec.connector_family != q_spec.connector_family:
                return False, 0.0, f"Konnektör serisi uyuşmuyor: İstenen {q_spec.connector_family.upper()}."

    if q_spec.pins and t_spec.pins:
        if q_spec.pins[0] not in t_spec.pins:
            return False, 0.0, f"Pin sayısı uyuşmuyor: İstenen {q_spec.pins[0]} pin, üründeki {t_spec.pins[0]} pin."

    # 2c. Kapasitans ve Dielektrik
    if q_spec.capacitance_pf and t_spec.capacitance_pf:
        req_pf = q_spec.capacitance_pf[0]
        if not any(abs(tc - req_pf) / max(req_pf, 1e-6) <= 0.05 for tc in t_spec.capacitance_pf):
            return False, 0.0, "Kondansatör kapasitans değeri uyuşmuyor."

    if q_spec.dielectric and t_spec.dielectric and q_spec.dielectric != t_spec.dielectric:
        return False, 0.0, f"Dielektrik tipi uyuşmuyor: İstenen {q_spec.dielectric}, üründeki {t_spec.dielectric}."

    # 2d. Direnç Değeri
    if q_spec.resistance_ohm and t_spec.resistance_ohm:
        req_ohm = q_spec.resistance_ohm[0]
        if not any(abs(tr - req_ohm) / max(req_ohm, 1e-6) <= 0.02 for tr in t_spec.resistance_ohm):
            return False, 0.0, f"Direnç değeri uyuşmuyor: İstenen {req_ohm:g} Ohm, üründeki {t_spec.resistance_ohm[0]:g} Ohm."

    # 2e. Montaj Tipi (SMD vs THT) ve SMD Kılıf Boyutu
    if q_spec.mounting == "THT" and t_spec.mounting == "SMD":
        return False, 0.0, "Montaj tipi uyuşmuyor: DIP/THT bacaklı istendi, ürün SMD."
    elif q_spec.mounting == "SMD":
        if t_spec.mounting == "THT":
            return False, 0.0, "Montaj tipi uyuşmuyor: SMD istendi, ürün DIP/THT bacaklı."
        if q_spec.is_passive and t_spec.mounting != "SMD":
            return False, 0.0, "SMD pasif komponent istendi ancak ürün başlığında SMD/kılıf ibaresi yok."

    if q_spec.smd_footprints and t_spec.smd_footprints:
        if not any(fp in t_spec.smd_footprints for fp in q_spec.smd_footprints):
            return False, 0.0, f"SMD kılıf boyutu uyuşmuyor: İstenen {q_spec.smd_footprints[0]}."

    # 2f. MOSFET / Transistör Kanal Kutupluluğu
    if q_spec.polarity and t_spec.polarity and q_spec.polarity != t_spec.polarity:
        return False, 0.0, f"Kanal tipi uyuşmuyor: İstenen {q_spec.polarity}, üründeki {t_spec.polarity}."

    # 2g. Form Faktörü (Modül / Devre Kartı vs Yalın Entegre / IC Çip)
    if q_spec.form_factor == "MODULE" and t_spec.form_factor == "IC":
        return False, 0.0, "Modül / devre kartı istendi; ürün yalın entegre (IC çip)."
    if q_spec.form_factor == "IC" and t_spec.form_factor == "MODULE":
        return False, 0.0, "Yalın entegre (IC çip) istendi; ürün hazır modül / devre kartı."

    # 3. SENTAKTİK MODEL KODU VE ALT-VARYANT DOĞRULAMASI
    for qm in q_spec.models:
        accepted = {qm.compact, qm.base_root}
        if qm.family == "neo":
            accepted.add(f"gy{qm.family}{qm.subvariant}v2")
            accepted.add(f"gy{qm.family}{qm.subvariant}")
        elif qm.family in ("mpu", "hmc", "bmp", "bme", "mlx", "vl"):
            accepted.add(f"gy{qm.subvariant}")
            accepted.add(f"gy{qm.family}{qm.subvariant}")

        # SQLite'da öğrenilmiş çapraz alias varsa kabul listesine ekle
        try:
            import electro_db
            for row in electro_db.get_learned_aliases(qm.compact):
                accepted.add(row["alias_compact"])
                accepted.add(row["canonical_compact"])
        except Exception:
            pass

        # Eğer <FAMILY>-<SUBVARIANT> (örn: esp32-c3, neo-6m) ise ve ürün başlığında aynı <FAMILY>'nin
        # FARKLI bir alt varyantı (örn: esp32-s3, neo-m8n, neo-8m) varsa kesin olarak reddet!
        if qm.family and qm.subvariant:
            for tm in t_spec.models:
                if tm.family == qm.family and tm.subvariant and tm.subvariant != qm.subvariant:
                    # Örn: neo6mv2 içinde '6m' geçer, bu uyumludur; ancak 'm8n' veya 's3' geçmez
                    if not tm.subvariant.startswith(qm.subvariant) and tm.compact not in accepted:
                        return False, 0.0, f"Model alt serisi uyuşmuyor: '{qm.raw.upper()}' yerine '{tm.raw.upper()}'."

            # Alt varyantın (örn: 'c3', '6m') veya öğrenilmiş alias'ın başlıkta bulunması şarttır
            has_family_and_sub = (qm.family in t_spec.compact and qm.subvariant in t_spec.compact)
            has_accepted = any(acc in t_spec.compact for acc in accepted if acc)
            if not (has_family_and_sub or has_accepted):
                return False, 0.0, f"Model kodu ('{qm.raw.upper()}') ürün başlığında doğrulanamadı."
        else:
            if not any(acc in t_spec.compact for acc in accepted if acc):
                return False, 0.0, f"Model kodu ('{qm.raw.upper()}') ürün başlığında bulunamadı."

    # 4. AĞIRLIKLI UYUMLULUK SKORU HESABI
    if not q_spec.tokens:
        return True, 1.0, "Uyumlu"

    matched = 0.0
    for w in q_spec.tokens:
        w_comp = re.sub(r'[^a-z0-9.]', '', w)
        if w in t_spec.norm or (w_comp and w_comp in t_spec.compact):
            matched += 1.0
        elif w in ("lipo", "li-po", "polimer") and t_spec.chemistry == "LIPO_LIION":
            matched += 1.0
        elif w in ("pil", "batarya", "battery") and t_spec.role == "BATTERY_CELL":
            matched += 1.0
        elif w in ("koruma", "bms", "pcm") and t_spec.role == "PROTECTION_BMS":
            matched += 1.0
        elif w in ("kondansator", "kapasitor") and bool(t_spec.capacitance_pf):
            matched += 1.0

    score = min(1.0, matched / len(q_spec.tokens))

    if q_spec.models:
        score = max(score, 0.70)
    if q_spec.capacity_mah and t_spec.capacity_mah and q_spec.capacity_mah[0] in t_spec.capacity_mah:
        score = min(1.0, score + 0.25)

    if score < 0.35:
        return False, round(score, 2), "Arama terimleri ürün başlığıyla yeterince örtüşmüyor."

    return True, round(score, 2), "Teknik olarak uyumlu"


def evaluate_component_relevance(query: str, product_title: str) -> Tuple[bool, float, str]:
    """
    Sorgu (veya '|' ile ayrılmış alternatif sorgular) ile mağaza ürün başlığını
    yapılandırılmış `ComponentSpec` motoru üzerinden karşılaştırır.
    """
    if not product_title or not product_title.strip():
        return False, 0.0, "Boş ürün başlığı."

    t_spec = parse_component_spec(product_title)
    sub_queries = [q.strip() for q in re.split(r'\s*\|\s*|\s+/\s+', query) if q.strip()]
    if not sub_queries:
        return False, 0.0, "Boş sorgu."

    best_res: Tuple[bool, float, str] = (False, 0.0, "Uyumsuz")
    for sq in sub_queries:
        q_spec = parse_component_spec(sq)
        is_v, sc, rsn = _evaluate_single_spec_relevance(q_spec, t_spec)
        if is_v and sc > best_res[1]:
            best_res = (is_v, sc, rsn)
        elif not best_res[0]:
            best_res = (is_v, sc, rsn)

    return best_res
