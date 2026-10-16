"""
ElectroStock - Dinamik Komponent Eşdeğerlik, Muadil ve Çapraz Referans Motoru
Kod içinde statik sözlük tutmaz; bilgileri SQLite (component_knowledge) ve
canlı mağaza kategori ağaçları (breadcrumb category discovery) üzerinden dinamik çözer.
"""

import re
import html as html_lib
from typing import Dict, Any, List, Optional
import electro_db
import component_matcher


_GENERIC_PART_WORDS = {
    "modülü", "modulu", "modül", "modul", "kartı", "karti", "kart", "devresi", "devre",
    "sensörü", "sensoru", "sensör", "sensor", "standart", "mini", "küçük", "kucuk",
    "sinyal", "genel", "beyaz", "mavi", "korumalı", "korumali", "entegre", "entegresi",
    "step", "down", "buck", "boost", "kanal", "logic", "level", "high", "side",
    "holtek", "torex", "microne", "microchip", "bosch", "aosong", "injoinic",
    "nordic", "ti", "st", "invensense", "analog", "devices", "espressif", "ublox",
    "sot", "dip", "smd", "tht", "pil", "batarya", "koruma", "şarj", "sarj"
}

_VENDOR_PREFIXES = (
    "Holtek ", "Torex ", "MicrOne ", "Microchip ", "Bosch ", "Aosong ",
    "Injoinic ", "Nordic ", "TI ", "ST ", "InvenSense ", "Analog Devices ",
    "Espressif ", "u-blox "
)


def _clean_part_search_name(part_name: str) -> str:
    """Piyasa araması için parça adındaki üretici öneklerini ve parantez açıklamalarını temizler."""
    base = part_name.split("(")[0].split("/")[0].strip()
    for pref in _VENDOR_PREFIXES:
        if base.lower().startswith(pref.lower()):
            base = base[len(pref):].strip()
    base = re.sub(r'\b(?:Mini Step-Down Buck Modülü|Step-Down Modül|Korumalı Modül|PowerBank Entegresi|Pil Koruma Kartı)\b', '', base, flags=re.I).strip()
    if "1S 3.7V BMS" in part_name:
        return "1S BMS Koruma Kartı"
    if "TP4056" in part_name:
        return "TP4056"
    if "XC6206" in base:
        return "XC6206"
    if "MP1584" in base:
        return "MP1584"
    return base or part_name.split("(")[0].strip()


def get_knowledge_database(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """SQLite veritabanından güncel komponent bilgi gruplarını çeker; boşsa başlangıç verilerini aktarır."""
    groups = electro_db.get_component_knowledge_groups(db_path or electro_db.DB_PATH)
    if not groups:
        try:
            import seed_knowledge
            seed_knowledge.seed_baseline_knowledge(db_path or electro_db.DB_PATH)
            groups = electro_db.get_component_knowledge_groups(db_path or electro_db.DB_PATH)
        except Exception:
            groups = []
    return groups


def find_component_equivalents(query: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    SQLite bilgi bankasındaki kayıtlar üzerinde semantik ve model kodu eşleştirmesi yaparak
    eşdeğer ve alternatif parça önerilerini döndürür.
    """
    q = query.strip()
    if not q:
        return None

    q_tr = component_matcher.normalize_tr(q.lower())
    q_comp = component_matcher.normalize_compact(q)
    q_models = [component_matcher.normalize_compact(m) for m in component_matcher.extract_model_codes(q)]

    knowledge_groups = get_knowledge_database(db_path)
    if not knowledge_groups:
        return None

    best_match = None
    matched_part = None
    best_score = 0.0

    for category_group in knowledge_groups:
        cat_score = 0.0
        cat_matched_part = None

        # 1. Parça isimleri ve model kodları eşleşmesi
        for p in category_group.get("parts", []):
            p_name = p["name"]
            p_tr = component_matcher.normalize_tr(p_name.lower())
            p_comp = component_matcher.normalize_compact(p_name)
            p_base = component_matcher.normalize_tr(p_name.split("(")[0].lower())
            p_models = [component_matcher.normalize_compact(m) for m in component_matcher.extract_model_codes(p_name)]

            part_score = 0.0

            # Model kodu tam veya önek eşleşmesi (örn: ao3401 <-> ao3401a, mp1584 <-> mp1584en)
            for qm in q_models:
                for pm in p_models:
                    if qm == pm:
                        part_score = max(part_score, 12.0)
                    elif len(qm) >= 5 and (pm.startswith(qm) or qm.startswith(pm)):
                        part_score = max(part_score, 10.0)

            # Özel belirteç kelimeleri
            if part_score == 0.0:
                tokens = [
                    t for t in re.split(r'[\s\-_/()]+', p_base)
                    if len(t) >= 3 and t not in _GENERIC_PART_WORDS
                ]
                for tok in tokens:
                    tok_comp = component_matcher.normalize_compact(tok)
                    if len(tok_comp) >= 4 and (re.search(rf'\b{re.escape(tok)}\b', q_tr) or tok_comp in q_comp):
                        part_score = max(part_score, 6.0)

            # Kanal kutupluluğu uyumu (P-Kanal vs N-Kanal MOSFET)
            if "p-kanal" in q_tr or "p kanal" in q_tr or "pmos" in q_tr:
                if "p-kanal" in p_tr:
                    part_score = max(part_score, 5.0)
                elif "n-kanal" in p_tr:
                    part_score = 0.0
            elif "n-kanal" in q_tr or "n kanal" in q_tr or "nmos" in q_tr:
                if "n-kanal" in p_tr:
                    part_score = max(part_score, 5.0)
                elif "p-kanal" in p_tr:
                    part_score = 0.0

            if part_score > cat_score:
                cat_score = part_score
                cat_matched_part = p

        # 2. Kategori anahtar kelimelerinde ara
        kw_hits = 0.0
        for kw in category_group.get("keywords", []):
            kw_tr = component_matcher.normalize_tr(kw.lower())
            if kw_tr == q_tr:
                kw_hits += 5.0
            elif len(kw_tr) >= 3 and kw_tr in q_tr:
                kw_hits += 2.0 + (len(kw_tr) * 0.1)

        total_cat_score = cat_score + kw_hits
        if total_cat_score > best_score:
            best_score = total_cat_score
            best_match = category_group
            matched_part = cat_matched_part

    if not best_match or best_score < 1.5:
        return None

    # Markdown formatında karşılaştırma raporu hazırla
    md = [f"# 🔄 Komponent Eşdeğerlik & Muadil Raporu: {best_match['category']}\n"]
    if best_match.get("summary"):
        md.append(f"💡 *Kategori İpucu:* {best_match['summary']}\n")

    if matched_part:
        md.append(f"**Aranan Parça:** `{matched_part['name']}`\n")
        if matched_part.get("features"):
            md.append(f"📌 **Özellikler:** {matched_part['features']}")
        if matched_part.get("pros"):
            md.append(f"✅ **Avantajları:** {matched_part['pros']}")
        if matched_part.get("cons"):
            md.append(f"⚠️ **Dezavantajları / Dikkat:** {matched_part['cons']}")
        md.append("\n### 🔁 Muadil ve Alternatif Parçalar:\n")

    for p in best_match.get("parts", []):
        if matched_part and p["name"] == matched_part["name"]:
            continue
        md.append(f"- **{p['name']}**")
        if p.get("features"):
            md.append(f"  • *Özellikler:* {p['features']}")
        if p.get("pros"):
            md.append(f"  • *Avantajları:* {p['pros']}")
        if p.get("cons"):
            md.append(f"  • *Dezavantajları:* {p['cons']}")
        md.append("")

    return {
        "query": query,
        "category": best_match["category"],
        "matched_part": matched_part["name"] if matched_part else None,
        "equivalents": best_match.get("parts", []),
        "markdown_report": "\n".join(md)
    }


def find_component_equivalents_with_market(
    query: str,
    check_market_prices: bool = True,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Muadil parça önerisi yapar.
    1. Önce SQLite'taki mühendislik bilgi bankasını tarar.
    2. Eğer bulunamazsa veya ek alternatif gerekiyorsa, mağazaların canlı kategori ağacından
       (breadcrumb category discovery) stoktaki gerçek alternatifleri canlı çeker ve parametrik kıyaslar.
    3. Tüm alternatiflerin Türkiye pazarındaki (Robotronik, Robotistan, Direnç.net, Motorobit) canlı fiyat ve stoklarını getirir.
    """
    import market_scraper

    eq_res = find_component_equivalents(query, db_path=db_path)

    # 1. SQLite Veritabanında Kayıtlı İse
    if eq_res:
        if check_market_prices:
            try:
                market_lines = ["\n### 💰 Alternatiflerin Canlı Piyasa Fiyatları (Robotistan / Robotronik / Direnç.net / Motorobit):"]
                queried_parts = eq_res["equivalents"][:4]
                for p in queried_parts:
                    search_term = _clean_part_search_name(p["name"])
                    m_res = market_scraper.search_market(search_term, only_in_stock=True, limit_per_vendor=1, sort_by_price=True)
                    cheapest = m_res.get("cheapest")
                    rob_opt = m_res.get("robotistan_option")
                    if cheapest:
                        line = f"- **{p['name']}**: En uygun **{cheapest['price']}** ([{cheapest['vendor']}]({cheapest['url']}))"
                        if rob_opt and rob_opt.get("vendor_key") != cheapest.get("vendor_key"):
                            line += f" | Robotistan: **{rob_opt['price']}** ([Link]({rob_opt['url']}))"
                        market_lines.append(line)
                    else:
                        market_lines.append(f"- **{p['name']}**: *Türkiye perakende mağazalarında aktif stok yok (AliExpress / Özdisan / Mouser önerilir)*")

                eq_res["markdown_report"] += "\n" + "\n".join(market_lines)
            except Exception:
                pass

        eq_res["found_in_database"] = True
        return eq_res

    # 2. SQLite Veritabanında Yoksa: Dinamik Canlı Kategori Keşfi (Live Category Discovery)
    market_search = market_scraper.search_market(query, only_in_stock=True, limit_per_vendor=2)
    top_results = market_search.get("results", [])
    query_spec = component_matcher.parse_component_spec(query)

    md = [f"# 🌐 Canlı Piyasa & Kategori Analizi: '{query}'\n"]

    if not top_results:
        md.append(f"❌ `{query}` için Türkiye mağazalarında (Robotistan, Robotronik, Direnç.net, Motorobit) doğrudan stok bulunamadı.\n")
        md.append("💡 *Öneri:* Parça kodunun kök modelini (örn. son ekleri olmadan) arayabilir veya Özdisan / AliExpress kataloglarına bakabilirsiniz.")
        return {
            "found_in_database": False,
            "query": query,
            "markdown_report": "\n".join(md),
            "market_results": [],
            "category_peers": []
        }

    top_item = top_results[0]
    md.append(f"Bu bileşen yerel bilgi bankasında kayıtlı değil, ancak Türkiye pazarında **[{top_item['vendor']}] [{top_item['title']}]({top_item['url']})** bulundu (**{top_item['price']}**).\n")

    # Ürünün mağazadaki kategori ağacını (breadcrumb) keşfet
    cat_disc = market_scraper.discover_category_alternatives(top_item["url"], exclude_title=top_item["title"], limit=6)
    category_name = cat_disc.get("category_name", "")
    peers = cat_disc.get("peers", [])

    if category_name:
        md.append(f"📁 **Mağaza Kategorisi:** {category_name}\n")

    md.append("### 🔍 Doğrudan Eşleşen Ürünler:")
    for it in top_results[:4]:
        md.append(f"- **[{it['vendor']}] [{it['title']}]({it['url']})** — **{it['price']}**")

    if peers:
        md.append(f"\n### 🏬 Aynı Mağaza Kategorisinde Bulunan Alternatif / Muadil Modeller:")
        md.append(f"*(Bu ürünler tedarikçinin `{category_name or 'İlgili'}` reyonundaki diğer aktif stoklarıdır)*\n")
        for p in peers:
            p_spec = component_matcher.parse_component_spec(p["title"])
            spec_notes = []
            if p_spec.smd_footprints:
                spec_notes.append(f"Paket: {', '.join(p_spec.smd_footprints)}")
            if p_spec.capacity_mah:
                spec_notes.append(f"Kapasite: {p_spec.capacity_mah[0]}mAh")
            if p_spec.pins:
                spec_notes.append(f"{p_spec.pins[0]}-Pin")
            if p_spec.mounting:
                spec_notes.append(p_spec.mounting)

            note_str = f" ({', '.join(spec_notes)})" if spec_notes else ""
            md.append(f"- **[{p['vendor']}] [{p['title']}]({p['url']})** — **{p['price']}**{note_str}")

    return {
        "found_in_database": False,
        "query": query,
        "category_name": category_name,
        "markdown_report": "\n".join(md),
        "market_results": top_results,
        "category_peers": peers
    }


def save_learned_equivalent(
    category: str,
    part_name: str,
    features: str = "",
    pros: str = "",
    cons: str = "",
    keywords: str = "",
    summary: str = "",
    db_path: Optional[str] = None
) -> int:
    """Yeni öğrenilen bir bileşeni veya kategoriyi doğrudan SQLite veritabanına kaydeder."""
    return electro_db.save_component_knowledge(
        category=category,
        part_name=part_name,
        features=features,
        pros=pros,
        cons=cons,
        keywords=keywords,
        summary=summary,
        db_path=db_path or electro_db.DB_PATH
    )


get_component_equivalents = find_component_equivalents
