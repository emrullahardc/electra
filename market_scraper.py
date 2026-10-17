"""
ElectroStock - Türkiye Elektronik Pazarı Çoklu Tedarikçi & Fiyat Karşılaştırma Modülü
Desteklenen Mağazalar:
1. Robotistan (robotistan.com) - T-Soft
2. Robotronik (robotronik.com.tr) - SoftTr (Kullanıcı Talebi)
3. Direnç.net (direnc.net) - T-Soft v5 (Türkiye'nin en geniş komponent arşivi)
4. Motorobit (motorobit.com) - T-Soft v5 (Robotik, motor ve uygun fiyatlı kartlar)

Tüm mağazaları paralel (ThreadPoolExecutor) tarar, fiyatları KDV dahil olarak normalize eder,
anlamsal uyumluluk filtresinden geçirir, en ucuz stoğu tespit eder ve BOM karşılaştırması sunar.
"""

import urllib.request
import urllib.parse
import urllib.error
import re
import html as html_lib
import time
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from robotistan_scraper import scraper as robotistan_scraper, normalize_search_query, relax_query
from component_matcher import (
    evaluate_component_relevance,
    get_component_search_aliases,
    discover_cooccurring_aliases,
    parse_component_spec,
)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
COMMON_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

CACHE_TTL = 900  # 15 dakika önbellek
_MARKET_CACHE: Dict[str, Dict[str, Any]] = {}


def parse_turkish_price(raw: str) -> float:
    """
    Hem Türkçe ('14,83 TL', '1.483,50 TL') hem de SoftTr/US ('1,023.54') formatındaki
    fiyatları doğru biçimde floata çevirir.
    """
    if not raw:
        return 0.0
    cleaned = re.sub(r'<[^>]+>', '', str(raw)).replace("TL", "").replace("₺", "").replace("&nbsp;", "").strip()
    if not cleaned:
        return 0.0
    if "." in cleaned and "," in cleaned:
        # Hangisi daha sağdaysa o ondalık ayırıcıdır
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            cleaned = parts[0] + "." + parts[1]
        else:
            cleaned = cleaned.replace(",", "")
    nums = re.findall(r'\d+(?:\.\d+)?', cleaned)
    if nums:
        try:
            return round(float(nums[0]), 2)
        except Exception:
            return 0.0
    return 0.0


def fetch_url(url: str, timeout: int = 8) -> str:
    """Belirtilen URL'den HTML içeriğini çeker."""
    req = urllib.request.Request(url, headers=COMMON_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _split_tsoft_v5_cards(html: str) -> List[str]:
    """
    Direnç.net ve Motorobit (T-Soft v5) arama sayfalarında alt kısımdaki
    data-toggle='product-loader' ve footer'ı keserek yalnızca gerçek ürün kartlarını böler.
    """
    loader_idx = html.find('data-toggle="product-loader"')
    if loader_idx == -1:
        loader_idx = html.find("data-toggle='product-loader'")
    if loader_idx != -1:
        html = html[:loader_idx]
    else:
        main_end = html.find("</main>")
        if main_end != -1:
            html = html[:main_end]

    return re.split(r'data-toggle=[\"\']product[\"\']\s+data-id=', html)


# ==========================================
# 1. ROBOTRONIK SCRAPER (robotronik.com.tr)
# ==========================================
def search_robotronik(query: str, only_in_stock: bool = False, limit: int = 10) -> List[Dict[str, Any]]:
    """Robotronik.com.tr üzerinde ürün araması yapar."""
    norm_q = normalize_search_query(query)
    search_target = norm_q if norm_q else query
    url = f"https://www.robotronik.com.tr/index.php?pagename=search&q={urllib.parse.quote(search_target)}"

    try:
        html = fetch_url(url, timeout=8)
    except Exception:
        return []

    parts = re.split(r'<div[^>]*class=[\"\'][^\"\']*urun urun-mobile[^\"\']*[\"\'][^>]*>', html)
    if len(parts) <= 1:
        relaxed = relax_query(search_target)
        if relaxed and relaxed != search_target:
            try:
                rel_url = f"https://www.robotronik.com.tr/index.php?pagename=search&q={urllib.parse.quote(relaxed)}"
                html = fetch_url(rel_url, timeout=8)
                parts = re.split(r'<div[^>]*class=[\"\'][^\"\']*urun urun-mobile[^\"\']*[\"\'][^>]*>', html)
            except Exception:
                pass

    items: List[Dict[str, Any]] = []
    for block in parts[1:]:
        title_m = re.search(
            r'<a[^>]+href=[\"\'](?:\.\./\.\./)?([^\"\']+)[\"\'][^>]*class=[\"\'][^\"\']*urun-title[^\"\']*[\"\'][^>]*>([^<]+)</a>',
            block
        )
        # Robotronik .urun-title metnini ~45 karakterde '...' ile keser; tam başlık <img> title/alt içindedir
        img_title_m = re.search(
            r'<img[^>]+(?:title|alt)=[\"\']([^\"\']+)[\"\'][^>]*class=[\"\'][^\"\']*urun-img[^\"\']*[\"\']|<img[^>]+class=[\"\'][^\"\']*urun-img[^\"\']*[\"\'][^>]+(?:title|alt)=[\"\']([^\"\']+)[\"\']',
            block
        )
        price_m = re.search(r'<div[^>]*class=[\"\'][^\"\']*urun-fiyat[^\"\']*[\"\'][^>]*>(.*?)</div>', block, re.DOTALL)
        in_stock = ("urun-tukendi" not in block)

        if only_in_stock and not in_stock:
            continue

        if title_m:
            short_title = html_lib.unescape(title_m.group(2).strip())
            full_title = ""
            if img_title_m:
                full_title = html_lib.unescape((img_title_m.group(1) or img_title_m.group(2) or "").strip())
            title = full_title if (full_title and len(full_title) >= len(short_title.rstrip('.'))) else short_title

            href = title_m.group(1).lstrip("/")
            pval = parse_turkish_price(price_m.group(1)) if price_m else 0.0

            items.append({
                "vendor": "Robotronik",
                "vendor_key": "robotronik",
                "vendor_domain": "robotronik.com.tr",
                "title": title,
                "price": f"{pval:.2f} TL" if pval > 0 else "Fiyat Belirtilmedi",
                "price_value": pval,
                "in_stock": in_stock,
                "url": f"https://www.robotronik.com.tr/{href}"
            })
            if len(items) >= limit:
                break

    return items


# ==========================================
# 2. DİRENÇ.NET SCRAPER (direnc.net)
# ==========================================
def search_direnc(query: str, only_in_stock: bool = False, limit: int = 10) -> List[Dict[str, Any]]:
    """Direnc.net üzerinde ürün araması yapar."""
    norm_q = normalize_search_query(query)
    search_target = norm_q if norm_q else query
    url = f"https://www.direnc.net/arama?q={urllib.parse.quote(search_target)}"

    try:
        html = fetch_url(url, timeout=8)
    except Exception:
        return []

    cards = _split_tsoft_v5_cards(html)
    if len(cards) <= 1:
        relaxed = relax_query(search_target)
        if relaxed and relaxed != search_target:
            try:
                rel_url = f"https://www.direnc.net/arama?q={urllib.parse.quote(relaxed)}"
                html = fetch_url(rel_url, timeout=8)
                cards = _split_tsoft_v5_cards(html)
            except Exception:
                pass

    items: List[Dict[str, Any]] = []
    for block in cards[1:]:
        u_m = re.search(
            r'data-toggle=[\"\']product-url[\"\'][^>]*href=[\"\']([^\"\']+)[\"\']|href=[\"\']([^\"\']+)[\"\'][^>]*data-toggle=[\"\']product-url[\"\']',
            block
        )
        t_m = re.search(
            r'data-toggle=[\"\']product-title[\"\'][^>]*>([^<]+)</span>|title=[\"\']([^\"\']+)[\"\']',
            block
        )
        # Önce KDV dahil fiyatı (price-sell-vat) veya data-qa=product-price yakala
        p_vat_m = re.search(r'data-toggle=[\"\']price-sell-vat[\"\'][^>]*>([^<]+)</span>', block)
        p_m = re.search(r'data-qa=[\"\']product-price[\"\'][^>]*>(.*?)</div>', block, re.DOTALL)
        in_stock = ("Tükendi" not in block and "tükendi" not in block)

        if only_in_stock and not in_stock:
            continue

        href = (u_m.group(1) or u_m.group(2)) if u_m else ""
        title = (t_m.group(1) or t_m.group(2)) if t_m else ""

        if href and title:
            title = html_lib.unescape(title.strip())
            if p_vat_m:
                pval = parse_turkish_price(p_vat_m.group(1))
            elif p_m:
                pval = parse_turkish_price(p_m.group(1))
            else:
                pval = 0.0

            items.append({
                "vendor": "Direnç.net",
                "vendor_key": "direnc",
                "vendor_domain": "direnc.net",
                "title": title,
                "price": f"{pval:.2f} TL" if pval > 0 else "Fiyat Belirtilmedi",
                "price_value": pval,
                "in_stock": in_stock,
                "url": f"https://www.direnc.net{href}"
            })
            if len(items) >= limit:
                break

    return items


# ==========================================
# 3. MOTOROBİT SCRAPER (motorobit.com)
# ==========================================
def search_motorobit(query: str, only_in_stock: bool = False, limit: int = 10) -> List[Dict[str, Any]]:
    """Motorobit.com üzerinde ürün araması yapar (Fiyatları KDV dahil olarak normalize eder)."""
    norm_q = normalize_search_query(query)
    search_target = norm_q if norm_q else query
    url = f"https://www.motorobit.com/arama?q={urllib.parse.quote(search_target)}"

    try:
        html = fetch_url(url, timeout=8)
    except Exception:
        return []

    cards = _split_tsoft_v5_cards(html)
    if len(cards) <= 1:
        relaxed = relax_query(search_target)
        if relaxed and relaxed != search_target:
            try:
                rel_url = f"https://www.motorobit.com/arama?q={urllib.parse.quote(relaxed)}"
                html = fetch_url(rel_url, timeout=8)
                cards = _split_tsoft_v5_cards(html)
            except Exception:
                pass

    items: List[Dict[str, Any]] = []
    for block in cards[1:]:
        u_m = re.search(
            r'data-toggle=[\"\']product-url[\"\'][^>]*href=[\"\']([^\"\']+)[\"\']|href=[\"\']([^\"\']+)[\"\'][^>]*data-toggle=[\"\']product-url[\"\']',
            block
        )
        t_m = re.search(
            r'data-toggle=[\"\']product-title[\"\'][^>]*>([^<]+)</span>|title=[\"\']([^\"\']+)[\"\']',
            block
        )
        p_vat_m = re.search(r'data-toggle=[\"\']price-sell-vat[\"\'][^>]*>([^<]+)</span>', block)
        p_m = re.search(r'data-toggle=[\"\']price-sell[\"\'][^>]*>([^<]+)</span>', block)
        in_stock = ("Tükendi" not in block and "tükendi" not in block)

        if only_in_stock and not in_stock:
            continue

        href = (u_m.group(1) or u_m.group(2)) if u_m else ""
        title = (t_m.group(1) or t_m.group(2)) if t_m else ""

        if href and title:
            title = html_lib.unescape(title.strip())
            if p_vat_m:
                pval = parse_turkish_price(p_vat_m.group(1))
            elif p_m:
                pval = parse_turkish_price(p_m.group(1))
                # Motorobit arama kartlarında '505,00 TL + KDV' şeklinde KDV hariç fiyat yazar;
                # diğer tüm mağazalarla ve ürün detay sayfasıyla eşit karşılaştırma için %20 KDV ekle.
                if pval > 0 and re.search(r'\+\s*kdv', block, re.I):
                    pval = round(pval * 1.20, 2)
            else:
                pval = 0.0

            items.append({
                "vendor": "Motorobit",
                "vendor_key": "motorobit",
                "vendor_domain": "motorobit.com",
                "title": title,
                "price": f"{pval:.2f} TL" if pval > 0 else "Fiyat Belirtilmedi",
                "price_value": pval,
                "in_stock": in_stock,
                "url": f"https://www.motorobit.com{href}"
            })
            if len(items) >= limit:
                break

    return items


# ==========================================
# 4. ROBOTİSTAN SCRAPER WRAPPER
# ==========================================
def search_robotistan(query: str, only_in_stock: bool = False, limit: int = 10) -> List[Dict[str, Any]]:
    """Robotistan sonuçlarını ortak veri şemasına uydurur."""
    res = robotistan_scraper.search(query=query, only_in_stock=only_in_stock, limit=limit)
    items: List[Dict[str, Any]] = []
    for r in res.get("results", []):
        items.append({
            "vendor": "Robotistan",
            "vendor_key": "robotistan",
            "vendor_domain": "robotistan.com",
            "title": r.get("title", ""),
            "price": r.get("price", "Fiyat Belirtilmedi"),
            "price_value": r.get("price_value") or 0.0,
            "in_stock": r.get("in_stock", False),
            "url": r.get("url", "")
        })
    return items


# ==========================================
# 5. ÇOKLU TEDARİKÇİ PARALEL ARAMA & KARŞILAŞTIRMA
# ==========================================
VENDORS = {
    "robotistan": {"name": "Robotistan", "search_func": search_robotistan, "domain": "robotistan.com"},
    "robotronik": {"name": "Robotronik", "search_func": search_robotronik, "domain": "robotronik.com.tr"},
    "direnc": {"name": "Direnç.net", "search_func": search_direnc, "domain": "direnc.net"},
    "motorobit": {"name": "Motorobit", "search_func": search_motorobit, "domain": "motorobit.com"}
}


def search_market(
    query: str,
    vendors: Optional[List[str]] = None,
    only_in_stock: bool = True,
    limit_per_vendor: int = 5,
    sort_by_price: bool = True
) -> Dict[str, Any]:
    """
    Seçilen veya tüm tedarikçilerde eşzamanlı (paralel) arama yapar.
    Yalnızca anlamsal ve teknik uyumluluk filtresinden geçen (is_compatible=True) ürünleri döndürür.
    """
    q = query.strip()
    if not q:
        return {"query": "", "results": [], "vendor_counts": {}, "cheapest": None}

    cache_key = f"{q.lower()}::{only_in_stock}::{','.join(sorted(vendors or list(VENDORS.keys())))}"
    now = time.time()
    if cache_key in _MARKET_CACHE:
        entry = _MARKET_CACHE[cache_key]
        if now - entry["timestamp"] < CACHE_TTL:
            return entry["data"]

    target_vendors = vendors if vendors else list(VENDORS.keys())
    active_funcs = {v: VENDORS[v]["search_func"] for v in target_vendors if v in VENDORS}

    raw_results: List[Dict[str, Any]] = []

    # 1. Birincil sorgu ile paralel arama (Katalog başlıklarından çapraz alias öğrenebilmek için tüm sonuçları çek)
    with ThreadPoolExecutor(max_workers=max(1, len(active_funcs))) as executor:
        future_to_vendor = {
            executor.submit(func, q, False, max(limit_per_vendor, 5)): v
            for v, func in active_funcs.items()
        }
        for future in as_completed(future_to_vendor):
            try:
                v_results = future.result()
                raw_results.extend(v_results)
            except Exception:
                pass

    # 2. Anlamsal Uyumluluk Filtresi & Çapraz Model/Breakout Kodu Öğrenme
    valid_results: List[Dict[str, Any]] = []
    compatible_titles: List[str] = []
    seen_urls: set = set()

    for item in raw_results:
        u = item.get("url") or f"{item.get('vendor_key')}:{item.get('title')}"
        if u in seen_urls:
            continue
        is_valid, rel_score, reason = evaluate_component_relevance(q, item.get("title", ""))
        if is_valid:
            compatible_titles.append(item.get("title", ""))
            if only_in_stock and not item.get("in_stock"):
                continue
            seen_urls.add(u)
            item["is_compatible"] = True
            item["relevance_score"] = rel_score
            item["compatibility_note"] = reason
            valid_results.append(item)

    # Doğrulanan katalog başlıklarında birlikte geçen alternatif modül/breakout kodlarını (örn: NEO-6M <-> GY-NEO6MV2, MPU6050 <-> GY-521) otomatik öğren!
    discovered_aliases = discover_cooccurring_aliases(q, compatible_titles)

    # 3. Henüz geçerli stok bulamayan mağazalar için öğrenilen ve ortografik alias'ları dene
    aliases = discovered_aliases + [a for a in get_component_search_aliases(q) if a not in discovered_aliases]
    tried_aliases = {q.lower(), normalize_search_query(q).lower()}

    for alias in aliases[:6]:
        a_low = alias.strip().lower()
        if not a_low or a_low in tried_aliases:
            continue
        tried_aliases.add(a_low)

        missing_vendors = {
            v: func for v, func in active_funcs.items()
            if not any(r.get("vendor_key") == v and r.get("in_stock") for r in valid_results)
        }
        if not missing_vendors:
            break

        with ThreadPoolExecutor(max_workers=max(1, len(missing_vendors))) as executor:
            alias_futures = {
                executor.submit(func, alias, only_in_stock, limit_per_vendor): v
                for v, func in missing_vendors.items()
            }
            for fut in as_completed(alias_futures):
                try:
                    a_res = fut.result()
                    for it in a_res:
                        if only_in_stock and not it.get("in_stock"):
                            continue
                        u = it.get("url") or f"{it.get('vendor_key')}:{it.get('title')}"
                        if u in seen_urls:
                            continue
                        is_v, sc, rsn = evaluate_component_relevance(q, it.get("title", ""))
                        if is_v:
                            seen_urls.add(u)
                            it["is_compatible"] = True
                            it["relevance_score"] = sc
                            it["compatibility_note"] = rsn
                            it["matched_via_alias"] = alias
                            valid_results.append(it)
                except Exception:
                    pass

        vendors_with_stock = {r.get("vendor_key") for r in valid_results if r.get("in_stock")}
        if len(vendors_with_stock) >= len(active_funcs):
            break

    # Mağaza başına geçerli ürün sayıları
    vendor_counts: Dict[str, int] = {
        v: sum(1 for r in valid_results if r.get("vendor_key") == v)
        for v in active_funcs.keys()
    }

    candidate_items = list(valid_results)
    for it in candidate_items:
        it_sp = parse_component_spec(it.get("title", ""))
        it["pack_quantity"] = it_sp.pack_quantity
        if it_sp.pack_quantity > 1 and it.get("price_value"):
            it["unit_price"] = round(it["price_value"] / it_sp.pack_quantity, 2)
            it["price_display"] = f"{it['price']} ({it_sp.pack_quantity}'li Paket • Adet: {it['unit_price']:.2f} TL)"
        else:
            it["unit_price"] = it.get("price_value", 0.0)
            it["price_display"] = it.get("price", "")

    # Önce yüksek uyumluluk kademesi (relevance_score >= 0.65), sonra fiyat küçükten büyüğe sırala
    if sort_by_price:
        candidate_items.sort(
            key=lambda x: (
                0 if (x.get("price_value", 0) > 0 and x.get("in_stock")) else 1,
                0 if x.get("relevance_score", 0.0) >= 0.65 else 1,
                x.get("price_value", 999999) if x.get("price_value", 0) > 0 else 999999
            )
        )

    # En ucuz olanı belirle (SADECE uyumlu adaylar arasından)
    cheapest = None
    for item in candidate_items:
        if item.get("in_stock") and item.get("price_value", 0) > 0:
            item["is_cheapest"] = True
            cheapest = item
            break

    # Robotistan seçeneğini tespit et (SADECE uyumlu adaylar arasından)
    robotistan_item = next(
        (x for x in candidate_items if x.get("vendor_key") == "robotistan" and x.get("in_stock") and x.get("price_value", 0) > 0),
        None
    )

    # Akıllı Karar & Tedarikçi Tavsiyesi (Robotistan Önceliği ve Kargo Maliyeti Hesabı)
    decision_advice: Dict[str, Any] = {}
    if cheapest:
        c_price = cheapest.get("price_value", 0.0)
        c_vendor = cheapest.get("vendor", "")
        c_vkey = cheapest.get("vendor_key", "")

        if robotistan_item:
            rob_price = robotistan_item.get("price_value", 0.0)
            diff = round(rob_price - c_price, 2)

            if c_vkey == "robotistan" or diff <= 0:
                decision_advice = {
                    "action": "prefer_robotistan",
                    "recommended_vendor": "robotistan",
                    "recommended_vendor_name": "Robotistan",
                    "should_ask_user": False,
                    "price_diff": 0.0,
                    "robotistan_price": rob_price,
                    "cheapest_price": c_price,
                    "cheapest_vendor": "Robotistan",
                    "summary": "Robotistan en uygun fiyata sahip ve aynı gün teslimat avantajı var.",
                    "prompt_question": None
                }
            elif diff <= 100.0:
                decision_advice = {
                    "action": "prefer_robotistan",
                    "recommended_vendor": "robotistan",
                    "recommended_vendor_name": "Robotistan",
                    "should_ask_user": False,
                    "price_diff": diff,
                    "robotistan_price": rob_price,
                    "cheapest_price": c_price,
                    "cheapest_vendor": c_vendor,
                    "summary": (
                        f"Robotistan ({rob_price:.2f} TL) ile en ucuz mağaza ({c_vendor} {c_price:.2f} TL) "
                        f"arasındaki fark sadece {diff:.2f} TL (≤100 TL eşiği). Diğer sitelerdeki minimum 40-75 TL kargo ücreti "
                        f"ve teslimat gecikmesi düşünüldüğünde aynı gün teslimat için Robotistan tavsiye edilir."
                    ),
                    "prompt_question": (
                        f"Bu parça Robotistan'da {rob_price:.2f} TL (aynı gün teslimat), {c_vendor}'de {c_price:.2f} TL "
                        f"(Fark: {diff:.2f} TL). Ek kargo ücreti ödememek ve aynı gün teslim almak için Robotistan'ı mı tercih edelim?"
                    )
                }
            else:
                decision_advice = {
                    "action": "ask_user",
                    "recommended_vendor": c_vkey,
                    "recommended_vendor_name": c_vendor,
                    "should_ask_user": True,
                    "price_diff": diff,
                    "robotistan_price": rob_price,
                    "cheapest_price": c_price,
                    "cheapest_vendor": c_vendor,
                    "summary": (
                        f"{c_vendor} {diff:.2f} TL daha ucuz (>100 TL tasarruf). "
                        f"Kargo bekleme süresi ve ek kargo ücreti (~40-75 TL) göze alınıyorsa harici mağaza tercih edilebilir."
                    ),
                    "prompt_question": (
                        f"Bu parça Robotistan'da {rob_price:.2f} TL (Aynı gün kargo), fakat {c_vendor}'de {c_price:.2f} TL "
                        f"(Net {diff:.2f} TL daha ucuz!). Kargo süresini bekleyip {c_vendor} üzerinden mi alalım, "
                        f"yoksa aynı gün gelmesi için Robotistan'ı mı seçelim?"
                    )
                }
        else:
            decision_advice = {
                "action": "external_vendor",
                "recommended_vendor": c_vkey,
                "recommended_vendor_name": c_vendor,
                "should_ask_user": False,
                "price_diff": None,
                "robotistan_price": None,
                "cheapest_price": c_price,
                "cheapest_vendor": c_vendor,
                "summary": f"Robotistan stoklarında bu parça bulunamadı. En uygun seçenek {c_vendor} ({c_price:.2f} TL).",
                "prompt_question": f"Bu parça Robotistan'da stokta yok. En uygun {c_vendor}'de ({c_price:.2f} TL) bulundu, taslağa bunu ekliyorum."
            }

    data = {
        "query": q,
        "total_results": len(candidate_items),
        "in_stock_results": sum(1 for r in candidate_items if r.get("in_stock")),
        "vendor_counts": vendor_counts,
        "cheapest": cheapest,
        "robotistan_option": robotistan_item,
        "decision_advice": decision_advice,
        "results": candidate_items
    }

    _MARKET_CACHE[cache_key] = {"timestamp": now, "data": data}
    return data


def get_suggested_sourcing_channel(part_name: str) -> str:
    """Türkiye yerel perakende mağazalarında bulunamayan komponentler için tedarik kanalı önerir."""
    p_lower = part_name.lower()
    if any(k in p_lower for k in ["max-m10", "atgm336", "gnss", "gps"]):
        return "AliExpress / SparkFun / Mouser / JLCPCB"
    elif any(k in p_lower for k in ["ao3401", "ht7833", "lis3dh", "sot-23", "sot-89", "qfn", "mosfet", "ldo", "ivmeölçer"]):
        return "AliExpress / JLCPCB SMT Montaj / Özdisan / Digikey"
    elif any(k in p_lower for k in ["bms", "pcm", "koruma"]):
        return "Robotronik / AliExpress / Direnç.net"
    else:
        return "AliExpress / Özdisan / Uluslararası Distribütörler (Mouser/Digikey)"


def compare_bom_prices(
    parts: List[str],
    only_in_stock: bool = True,
    shipping_cost_per_vendor: float = 50.0,
    price_threshold: float = 100.0,
    prefer_robotistan: bool = True
) -> Dict[str, Any]:
    """
    Verilen parça listesi (BOM) için hem yerel envanterde (electro_db) hem de tüm mağazalarda araştırma yapar.

    Robotistan Birincil Tedarikçi Mantığı:
    1. Kullanıcı Robotistan'dan aynı gün teslimat alır.
    2. Harici mağazalar minimum ~40-75 TL kargo ücreti ekler.
    3. Fiyat farkı 100 TL'nin altındaysa veya ek kargo tasarrufu siliyorsa parça Robotistan sepetinde tutulur.
    4. Fiyat farkı 100 TL'nin üzerindeyse veya Robotistan'da stok yoksa kullanıcıya soru yöneltilir.
    5. Mağazalarda bulunamayan parçalar sessizce düşürülmez; 'unfound_items' listesinde alternatif tedarik kanallarıyla raporlanır.
    6. Kullanıcının kendi envanterinde bulunan parçalar ('local_inventory') ayrıca işaretlenir.
    """
    clean_parts = [p.strip() for p in parts if p.strip()]
    if not clean_parts:
        return {
            "total_items_requested": 0,
            "found_items_count": 0,
            "unfound_items_count": 0,
            "unfound_items": [],
            "local_inventory_hits": [],
            "items": [],
            "smart_plan": {},
            "naive_plan": {},
            "total_smart_parts_cost": 0.0,
            "total_shipping_estimated": 0.0,
            "total_landed_cost": 0.0,
            "prompt_questions": []
        }

    try:
        import electro_db as db_mod
    except ImportError:
        db_mod = None

    item_comparisons = []
    smart_basket: Dict[str, List[Dict[str, Any]]] = {v: [] for v in VENDORS.keys()}
    naive_basket: Dict[str, List[Dict[str, Any]]] = {v: [] for v in VENDORS.keys()}
    prompt_questions: List[Dict[str, Any]] = []
    unfound_items: List[Dict[str, Any]] = []
    local_inventory_hits: List[Dict[str, Any]] = []
    assigned_urls: set = set()

    total_smart_parts_cost = 0.0
    total_naive_parts_cost = 0.0

    for part_name in clean_parts:
        # 0. Yerel envanter kontrolü
        local_matches = []
        if db_mod:
            try:
                raw_local = db_mod.search_components(query=part_name)
                for lc in raw_local:
                    if lc.get("status") == "working" and lc.get("quantity", 0) > 0:
                        is_lv, _, _ = evaluate_component_relevance(part_name, lc.get("name", ""))
                        if is_lv:
                            local_matches.append(lc)
            except Exception:
                pass

        if local_matches:
            local_inventory_hits.append({
                "part_query": part_name,
                "matches": local_matches
            })

        search_res = search_market(part_name, only_in_stock=only_in_stock, limit_per_vendor=3, sort_by_price=True)
        results = search_res.get("results", [])
        cheapest = search_res.get("cheapest")
        rob_item = search_res.get("robotistan_option")
        decision = search_res.get("decision_advice", {})

        comp = {
            "part_query": part_name,
            "found": len(results) > 0,
            "in_local_inventory": len(local_matches) > 0,
            "local_inventory": local_matches,
            "cheapest_option": cheapest,
            "robotistan_option": rob_item,
            "decision_advice": decision,
            "options": results[:6]
        }
        item_comparisons.append(comp)

        # 1. Naive Sepet (Kargo hesaba katılmayan salt en ucuz)
        if cheapest:
            v_key = cheapest.get("vendor_key", "other")
            naive_basket.setdefault(v_key, []).append(cheapest)
            total_naive_parts_cost += cheapest.get("price_value", 0.0)

        # 2. Akıllı Sepet (Robotistan Önceliği + Kargo Maliyeti Bilinci)
        if prefer_robotistan and rob_item:
            rob_price = rob_item.get("price_value", 0.0)
            c_price = cheapest.get("price_value", 0.0) if cheapest else rob_price
            diff = rob_price - c_price
            target_url = rob_item.get("url")

            is_dup = target_url in assigned_urls
            assigned_urls.add(target_url)

            if not cheapest or cheapest.get("vendor_key") == "robotistan" or diff <= price_threshold:
                reason_note = "Robotistan (Aynı gün kargo & fark ≤100 TL)"
                if is_dup:
                    reason_note += " [UYARI: Mükerrer Ürün Eşleşmesi]"
                if local_matches:
                    reason_note += f" [🏠 Envanterde Mevcut: {local_matches[0]['name']} ({local_matches[0]['quantity']} adet)]"
                smart_basket.setdefault("robotistan", []).append({
                    **rob_item,
                    "part_query": part_name,
                    "assigned_reason": reason_note
                })
                total_smart_parts_cost += rob_price
            else:
                v_key = cheapest.get("vendor_key", "other")
                reason_note = f"{cheapest['vendor']} ({diff:.2f} TL tasarruf > 100 TL)"
                if local_matches:
                    reason_note += f" [🏠 Envanterde Mevcut: {local_matches[0]['name']} ({local_matches[0]['quantity']} adet)]"
                smart_basket.setdefault(v_key, []).append({
                    **cheapest,
                    "part_query": part_name,
                    "assigned_reason": reason_note
                })
                total_smart_parts_cost += c_price
                if decision.get("prompt_question"):
                    prompt_questions.append({
                        "part": part_name,
                        "question": decision["prompt_question"],
                        "diff": diff,
                        "robotistan_price": rob_price,
                        "cheapest_vendor": cheapest.get("vendor"),
                        "cheapest_price": c_price
                    })
        elif cheapest:
            v_key = cheapest.get("vendor_key", "other")
            target_url = cheapest.get("url")
            assigned_urls.add(target_url)

            reason_note = "Robotistan stokta yok"
            if local_matches:
                reason_note += f" [🏠 Envanterde Mevcut: {local_matches[0]['name']} ({local_matches[0]['quantity']} adet)]"
            smart_basket.setdefault(v_key, []).append({
                **cheapest,
                "part_query": part_name,
                "assigned_reason": reason_note
            })
            total_smart_parts_cost += cheapest.get("price_value", 0.0)
            if decision.get("prompt_question"):
                prompt_questions.append({
                    "part": part_name,
                    "question": decision["prompt_question"],
                    "diff": 0.0,
                    "robotistan_price": None,
                    "cheapest_vendor": cheapest.get("vendor"),
                    "cheapest_price": cheapest.get("price_value")
                })
        else:
            unfound_items.append({
                "part_query": part_name,
                "status": "in_local_inventory" if local_matches else "not_in_stock",
                "local_inventory": local_matches,
                "reason": (
                    f"Mağazalarda stok yok ancak yerel envanterinizde mevcut: {local_matches[0]['name']} ({local_matches[0]['quantity']} adet)"
                    if local_matches else
                    "Robotistan, Robotronik, Direnç.net ve Motorobit mağazalarında geçerli stok bulunamadı."
                ),
                "suggested_channel": get_suggested_sourcing_channel(part_name)
            })

    active_smart = {k: v for k, v in smart_basket.items() if len(v) > 0}
    active_naive = {k: v for k, v in naive_basket.items() if len(v) > 0}

    external_vendor_count = sum(1 for v in active_smart.keys() if v != "robotistan")
    estimated_shipping_total = external_vendor_count * shipping_cost_per_vendor
    total_landed_cost = total_smart_parts_cost + estimated_shipping_total

    return {
        "total_items_requested": len(clean_parts),
        "found_items_count": len(clean_parts) - len(unfound_items),
        "unfound_items_count": len(unfound_items),
        "unfound_items": unfound_items,
        "local_inventory_hits": local_inventory_hits,
        "items": item_comparisons,
        "smart_plan": active_smart,
        "naive_plan": active_naive,
        "total_smart_parts_cost": round(total_smart_parts_cost, 2),
        "estimated_shipping_total": round(estimated_shipping_total, 2),
        "total_landed_cost": round(total_landed_cost, 2),
        "external_vendor_count": external_vendor_count,
        "prompt_questions": prompt_questions
    }


def get_universal_product_details(url: str) -> Dict[str, Any]:
    """
    Belirtilen ürün linkinin (Robotistan, Robotronik, Direnç.net, Motorobit) detaylı
    teknik özelliklerini, KDV dahil gerçek fiyatını ve stok durumunu ayrıştırır.
    """
    if not url or not url.startswith("http"):
        return {"error": "Geçersiz ürün URL'si", "url": url}

    try:
        html = fetch_url(url, timeout=10)
    except Exception as e:
        return {"error": f"Ürün sayfasına ulaşılamadı: {e}", "url": url}

    url_lower = url.lower()
    title = ""
    price_val = 0.0
    in_stock = True
    stock_status = "Stokta Var"
    specs: List[str] = []
    category_name = ""
    category_url = ""

    # 1. ROBOTRONİK (robotronik.com.tr - SoftTr)
    if "robotronik.com.tr" in url_lower:
        t_m = re.search(r"<div[^>]*class=[\"'][^\"']*urun-detay-baslik[^\"']*[\"'][^>]*>(.*?)</div>", html, re.DOTALL)
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", t_m.group(1)).strip()) if t_m else ""
        if not title:
            m_t = re.search(r"<title>([^<]+)</title>", html)
            title = html_lib.unescape(m_t.group(1).split("-")[0].strip()) if m_t else ""

        p_m = re.search(r"class=[\"'][^\"']*urun-detay-fiyat2[^\"']*[\"'][^>]*>\s*([^\s<]+)", html)
        if not p_m:
            p_m = re.search(r"id=[\"']normalprice[\"'][^>]*>.*?([0-9.,]+)", html, re.DOTALL)
        if p_m:
            price_val = parse_turkish_price(p_m.group(1))

        stk_m = re.search(r"class=[\"'][^\"']*kalan-stok-sayi[^\"']*[\"'][^>]*>\s*(\d+)", html)
        has_buy_btn = bool(re.search(r"id=[\"']sepete-ekle[\"']|class=[\"'][^\"']*sepete-ekle[^\"']*[\"']", html))
        stock_count = int(stk_m.group(1)) if stk_m else None
        if stock_count is not None and stock_count > 0:
            in_stock = True
            stock_status = f"Stokta Var ({stock_count} Adet)"
        elif stock_count == 0:
            in_stock = False
            stock_status = "Tükendi"
        else:
            in_stock = has_buy_btn
            stock_status = "Stokta Var" if in_stock else "Tükendi"

        bc_links = re.findall(r'<li[^>]*class=[\"\'][^\"\']*breadcrumb-item[^\"\']*[\"\'][^>]*>\s*<a[^>]+href=[\"\'](?:\.\./)*([^\"\']+)[\"\'][^>]*>([^<]+)</a>', html)
        if len(bc_links) >= 2:
            cat_href, cat_label = bc_links[-1]
            if cat_href.strip("/"):
                category_name = html_lib.unescape(cat_label.strip())
                category_url = f"https://www.robotronik.com.tr/{cat_href.lstrip('/')}"

        aciklama_m = re.search(r"id=[\"']aciklama[\"'][^>]*>(.*?)</div>\s*</div>", html, re.DOTALL)
        if aciklama_m:
            clean_text = re.sub(r"<[^>]+>", "\n", aciklama_m.group(1))
            for line in clean_text.split("\n"):
                line = html_lib.unescape(line).strip()
                if 5 < len(line) < 120 and any(c in line for c in [":", "-", "V", "A", "Ω", "mm"]):
                    specs.append(line)

    # 2. DİRENÇ.NET & MOTOROBİT (T-Soft v5)
    elif "direnc.net" in url_lower or "motorobit.com" in url_lower:
        name_inp = re.search(r'<input[^>]+id=[\"\']product-name[\"\'][^>]+value=[\"\']([^\"\']+)[\"\']', html)
        h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
        if name_inp:
            title = html_lib.unescape(name_inp.group(1).strip())
        elif h1_m:
            title = html_lib.unescape(re.sub(r"<[^>]+>", "", h1_m.group(1)).strip())
        if not title:
            m_t = re.search(r"<title>([^<]+)</title>", html)
            title = html_lib.unescape(m_t.group(1).split("|")[0].split("-")[0].strip()) if m_t else ""

        vat_inp = re.search(r'<input[^>]+id=[\"\']product-price-vat-include[\"\'][^>]+value=[\"\']([^\"\']+)[\"\']', html)
        if vat_inp:
            price_val = parse_turkish_price(vat_inp.group(1))
        else:
            h1_pos = html.find("<h1")
            sub_html = html[h1_pos:] if h1_pos != -1 else html
            p_m = re.search(
                r'data-toggle=[\"\']price-sell-vat[\"\'][^>]*>([^<]+)</span>|data-toggle=[\"\']price-sell[\"\'][^>]*>([^<]+)</span>',
                sub_html
            )
            if p_m:
                price_val = parse_turkish_price(p_m.group(1) or p_m.group(2))

        stk_inp = re.search(r'<input[^>]+id=[\"\']product-stock-status[\"\'][^>]+value=[\"\'](\d+)[\"\']', html)
        if stk_inp:
            in_stock = (stk_inp.group(1) == "1")
        else:
            h1_pos = html.find("<h1")
            sub_html = html[h1_pos:h1_pos + 12000] if h1_pos != -1 else html
            in_stock = bool(re.search(r'data-toggle=[\"\']add-to-cart[\"\']|SEPETE EKLE', sub_html, re.I))
        stock_status = "Stokta Var" if in_stock else "Tükendi"

        bc_items = re.findall(r'data-qa=[\"\']breadcrumb-item[\"\'][^>]*>.*?<a[^>]+href=[\"\']([^\"\']+)[\"\'][^>]*>([^<]+)</a>', html, re.DOTALL)
        if len(bc_items) >= 2:
            category_url, category_name = bc_items[-2][0].strip(), html_lib.unescape(bc_items[-2][1].strip())
        elif len(bc_items) == 1:
            category_url, category_name = bc_items[0][0].strip(), html_lib.unescape(bc_items[0][1].strip())

        h1_pos = html.find("<h1")
        detail_zone = html[h1_pos:h1_pos + 45000] if h1_pos != -1 else html
        for row in re.findall(r'<tr[^>]*>(.*?)</tr>', detail_zone, re.DOTALL):
            cols = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            if len(cols) >= 2:
                k = html_lib.unescape(re.sub(r'<[^>]+>', '', cols[0]).strip())
                v = html_lib.unescape(re.sub(r'<[^>]+>', '', cols[1]).strip())
                if k and v and len(k) < 80 and len(v) < 150:
                    kv = f"{k}: {v}"
                    if kv not in specs:
                        specs.append(kv)

        if not specs:
            for li in re.findall(r'<li[^>]*>(.*?)</li>', detail_zone, re.DOTALL):
                clean_li = html_lib.unescape(re.sub(r'<[^>]+>', '', li).strip())
                if 5 < len(clean_li) < 140 and any(c in clean_li for c in [":", "V", "A", "mm", "MHz", "Pin", "GPIO"]):
                    if clean_li not in specs:
                        specs.append(clean_li)

    # 3. ROBOTİSTAN (robotistan.com)
    else:
        m_title = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", m_title.group(1)).strip()) if m_title else ""
        if not title:
            m_t = re.search(r"<title>([^<]+)</title>", html)
            title = html_lib.unescape(m_t.group(1).replace("Satın Al", "").strip()) if m_t else ""

        m_price = re.search(r'class=[\"\'][^\"\']*\bproduct-price\b(?!\-not\-vat)[^\"\']*[\"\'][^>]*>\s*([0-9.,]+)', html)
        if not m_price:
            m_price = re.search(r'class=[\"\'][^\"\']*(?:price-current|current-price|price-sell)[^\"\']*[\"\'][^>]*>\s*([0-9.,]+)', html)
        if not m_price:
            m_price = re.search(r"(\d+[\.,]\d+)\s*(?:TL|₺)", html)
        if m_price:
            price_val = parse_turkish_price(m_price.group(1))

        has_cart_btn = bool(re.search(r"id=[\"']addToCartBtn[\"']|class=[\"'][^\"']*btn-add-to-cart[^\"']*[\"']", html))
        is_out = ("urun-tukendi" in html or "btn-out-of-stock" in html)
        in_stock = (not is_out) and has_cart_btn
        stock_status = "Stokta Var" if in_stock else "Tükendi"

        bc_rob = re.findall(r'<a[^>]+href=[\"\'](https://www\.robotistan\.com/[^\"\']+)[\"\'][^>]*class=[\"\'][^\"\']*breadcrumb-item[^\"\']*[\"\'][^>]*>([^<]+)</a>', html)
        if len(bc_rob) >= 2:
            category_url, category_name = bc_rob[-2][0].strip(), html_lib.unescape(bc_rob[-2][1].strip())

        for row in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL):
            cols = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            if len(cols) >= 2:
                k = html_lib.unescape(re.sub(r'<[^>]+>', '', cols[0]).strip())
                v = html_lib.unescape(re.sub(r'<[^>]+>', '', cols[1]).strip())
                if k and v and k.lower() != 'parametre' and len(k) < 80 and len(v) < 150:
                    clean_kv = f"{k}: {v}"
                    if clean_kv not in specs:
                        specs.append(clean_kv)

        body_m = re.search(r'id=[\"\']product-fullbody[\"\'][^>]*>(.*?)</div>\s*</div>', html, re.DOTALL)
        if not body_m:
            body_m = re.search(r'id=[\"\']product-features[\"\'][^>]*>(.*?)</div>\s*</div>', html, re.DOTALL)
        li_zone = body_m.group(1) if body_m else html
        for raw_li in re.findall(r"<li[^>]*>(.*?)</li>", li_zone, re.DOTALL):
            clean_s = html_lib.unescape(re.sub(r"<[^>]+>", "", raw_li).strip())
            clean_s = re.sub(r"\s+", " ", clean_s)
            if 5 < len(clean_s) < 150 and clean_s not in specs:
                if ":" in clean_s or any(u in clean_s for u in ["V", "A", "mm", "mAh", "MHz", "GHz", "Ohm", "Ω", "Pin", "GPIO", "I2C", "SPI", "UART", "°C"]):
                    specs.append(clean_s)

    return {
        "title": title or "Bilinmeyen Ürün",
        "price": f"{price_val:.2f} TL" if price_val > 0 else "Fiyat Belirtilmedi",
        "price_value": price_val,
        "in_stock": in_stock,
        "stock_status": stock_status,
        "category_name": category_name,
        "category_url": category_url,
        "specs": specs[:12],
        "url": url
    }


def discover_category_alternatives(product_url: str, exclude_title: str = "", limit: int = 8) -> Dict[str, Any]:
    """
    Bir ürünün mağaza sayfasındaki kategori ağacını (breadcrumb) takip ederek,
    aynı mağaza kategorisinde yer alan stoktaki diğer alternatif/muadil ürünleri canlı çeker.
    """
    details = get_universal_product_details(product_url)
    cat_url = details.get("category_url", "")
    cat_name = details.get("category_name", "")
    if not cat_url or not cat_url.startswith("http"):
        return {"category_name": cat_name, "category_url": cat_url, "peers": [], "source_details": details}

    try:
        cat_html = fetch_url(cat_url, timeout=8)
    except Exception:
        return {"category_name": cat_name, "category_url": cat_url, "peers": [], "source_details": details}

    peers: List[Dict[str, Any]] = []
    u_low = cat_url.lower()
    excl_low = (exclude_title or details.get("title", "")).lower().strip()

    if "robotistan.com" in u_low:
        for r in robotistan_scraper._parse_html(cat_html):
            if r.get("in_stock") and r.get("title", "").lower() != excl_low and r.get("url") != product_url:
                peers.append({
                    "vendor": "Robotistan",
                    "title": r["title"],
                    "price": r["price"],
                    "price_value": r.get("price_value") or 0.0,
                    "url": r["url"]
                })
    elif "direnc.net" in u_low or "motorobit.com" in u_low:
        v_name = "Direnç.net" if "direnc.net" in u_low else "Motorobit"
        domain = "https://www.direnc.net" if "direnc.net" in u_low else "https://www.motorobit.com"
        for block in _split_tsoft_v5_cards(cat_html)[1:]:
            if "Tükendi" in block or "tükendi" in block:
                continue
            u_m = re.search(r'data-toggle=[\"\']product-url[\"\'][^>]*href=[\"\']([^\"\']+)[\"\']|href=[\"\']([^\"\']+)[\"\'][^>]*data-toggle=[\"\']product-url[\"\']', block)
            t_m = re.search(r'data-toggle=[\"\']product-title[\"\'][^>]*>([^<]+)</span>|title=[\"\']([^\"\']+)[\"\']', block)
            p_vat_m = re.search(r'data-toggle=[\"\']price-sell-vat[\"\'][^>]*>([^<]+)</span>', block)
            p_m = re.search(r'data-qa=[\"\']product-price[\"\'][^>]*>(.*?)</div>|data-toggle=[\"\']price-sell[\"\'][^>]*>([^<]+)</span>', block, re.DOTALL)
            href = (u_m.group(1) or u_m.group(2)) if u_m else ""
            t_str = html_lib.unescape(((t_m.group(1) or t_m.group(2)) if t_m else "").strip())
            if not href or not t_str or t_str.lower() == excl_low or f"{domain}{href}" == product_url:
                continue
            pval = parse_turkish_price(p_vat_m.group(1)) if p_vat_m else (parse_turkish_price(p_m.group(1) or p_m.group(2)) if p_m else 0.0)
            if v_name == "Motorobit" and not p_vat_m and pval > 0 and re.search(r'\+\s*kdv', block, re.I):
                pval = round(pval * 1.20, 2)
            peers.append({
                "vendor": v_name,
                "title": t_str,
                "price": f"{pval:.2f} TL" if pval > 0 else "Fiyat Belirtilmedi",
                "price_value": pval,
                "url": f"{domain}{href}"
            })
    elif "robotronik.com.tr" in u_low:
        parts = re.split(r'<div[^>]*class=[\"\'][^\"\']*urun urun-mobile[^\"\']*[\"\'][^>]*>', cat_html)
        for block in parts[1:]:
            if "urun-tukendi" in block:
                continue
            title_m = re.search(r'<a[^>]+href=[\"\'](?:\.\./\.\./)?([^\"\']+)[\"\'][^>]*class=[\"\'][^\"\']*urun-title[^\"\']*[\"\'][^>]*>([^<]+)</a>', block)
            img_m = re.search(r'<img[^>]+(?:title|alt)=[\"\']([^\"\']+)[\"\'][^>]*class=[\"\'][^\"\']*urun-img[^\"\']*[\"\']|<img[^>]+class=[\"\'][^\"\']*urun-img[^\"\']*[\"\'][^>]+(?:title|alt)=[\"\']([^\"\']+)[\"\']', block)
            price_m = re.search(r'<div[^>]*class=[\"\'][^\"\']*urun-fiyat[^\"\']*[\"\'][^>]*>(.*?)</div>', block, re.DOTALL)
            if title_m:
                t_str = html_lib.unescape(((img_m.group(1) or img_m.group(2)) if img_m else title_m.group(2)).strip())
                href = title_m.group(1).lstrip("/")
                full_u = f"https://www.robotronik.com.tr/{href}"
                if t_str.lower() == excl_low or full_u == product_url:
                    continue
                pval = parse_turkish_price(price_m.group(1)) if price_m else 0.0
                peers.append({
                    "vendor": "Robotronik",
                    "title": t_str,
                    "price": f"{pval:.2f} TL" if pval > 0 else "Fiyat Belirtilmedi",
                    "price_value": pval,
                    "url": full_u
                })

    return {
        "category_name": cat_name,
        "category_url": cat_url,
        "peers": peers[:limit],
        "source_details": details
    }

