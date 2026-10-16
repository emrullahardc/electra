"""
ElectroStock - Türkiye Elektronik Pazarı Çoklu Tedarikçi & Fiyat Karşılaştırma Modülü
Desteklenen Mağazalar:
1. Robotistan (robotistan.com) - T-Soft
2. Robotronik (robotronik.com.tr) - SoftTr (Kullanıcı Talebi)
3. Direnç.net (direnc.net) - T-Soft (Türkiye'nin en geniş komponent arşivi)
4. Motorobit (motorobit.com) - T-Soft (Robotik, motor ve uygun fiyatlı kartlar)

Tüm mağazaları paralel (ThreadPoolExecutor) tarar, fiyatları normalize eder,
en ucuz mağazayı tespit eder ve BOM karşılaştırması sunar.
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

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
COMMON_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

CACHE_TTL = 900  # 15 dakika önbellek
_MARKET_CACHE: Dict[str, Dict[str, Any]] = {}


def fetch_url(url: str, timeout: int = 8) -> str:
    """Belirtilen URL'den HTML içeriğini çeker."""
    req = urllib.request.Request(url, headers=COMMON_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


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
    except Exception as e:
        # Hata durumunda boş liste dön
        return []

    parts = re.split(r'<div[^>]*class=[\"\'][^\"\']*urun urun-mobile[^\"\']*[\"\'][^>]*>', html)
    if len(parts) <= 1:
        # Eğer relaxed query varsa dene
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
        title_m = re.search(r'<a[^>]+href=[\"\'](?:\.\./\.\./)?([^\"\']+)[\"\'][^>]*class=[\"\'][^\"\']*urun-title[^\"\']*[\"\'][^>]*>([^<]+)</a>', block)
        price_m = re.search(r'<div[^>]*class=[\"\'][^\"\']*urun-fiyat[^\"\']*[\"\'][^>]*>(.*?)</div>', block, re.DOTALL)
        in_stock = ("urun-tukendi" not in block)

        if only_in_stock and not in_stock:
            continue

        if title_m:
            title = html_lib.unescape(title_m.group(2).strip())
            href = title_m.group(1).lstrip("/")
            raw_p = re.sub(r'<[^>]+>', '', price_m.group(1)).replace("₺", "").replace("&nbsp;", "").strip() if price_m else "0"
            clean_p = raw_p.replace(",", "")
            try:
                pval = round(float(clean_p), 2)
            except Exception:
                pval = 0.0

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

    cards = re.split(r'data-toggle=[\"\']product[\"\']', html)
    if len(cards) <= 1:
        relaxed = relax_query(search_target)
        if relaxed and relaxed != search_target:
            try:
                rel_url = f"https://www.direnc.net/arama?q={urllib.parse.quote(relaxed)}"
                html = fetch_url(rel_url, timeout=8)
                cards = re.split(r'data-toggle=[\"\']product[\"\']', html)
            except Exception:
                pass

    items: List[Dict[str, Any]] = []
    for block in cards[1:]:
        u_m = re.search(r'data-toggle=[\"\']product-url[\"\'][^>]*href=[\"\']([^\"\']+)[\"\']|href=[\"\']([^\"\']+)[\"\'][^>]*data-toggle=[\"\']product-url[\"\']', block)
        t_m = re.search(r'data-toggle=[\"\']product-title[\"\'][^>]*>([^<]+)</span>|title=[\"\']([^\"\']+)[\"\']', block)
        p_m = re.search(r'data-qa=[\"\']product-price[\"\'][^>]*>(.*?)</div>', block, re.DOTALL)
        in_stock = ("Tükendi" not in block)

        if only_in_stock and not in_stock:
            continue

        href = (u_m.group(1) or u_m.group(2)) if u_m else ""
        title = (t_m.group(1) or t_m.group(2)) if t_m else ""

        if href and title:
            title = html_lib.unescape(title.strip())
            raw_p = re.sub(r'<[^>]+>', '', p_m.group(1)).strip() if p_m else "0"
            clean_p = raw_p.replace("TL", "").replace("KDV dahil", "").replace(".", "").replace(",", ".").strip()
            nums = re.findall(r'\d+(?:\.\d+)?', clean_p)
            pval = round(float(nums[0]), 2) if nums else 0.0

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
    """Motorobit.com üzerinde ürün araması yapar."""
    norm_q = normalize_search_query(query)
    search_target = norm_q if norm_q else query
    url = f"https://www.motorobit.com/arama?q={urllib.parse.quote(search_target)}"

    try:
        html = fetch_url(url, timeout=8)
    except Exception:
        return []

    cards = re.split(r'data-toggle=[\"\']product[\"\']', html)
    if len(cards) <= 1:
        relaxed = relax_query(search_target)
        if relaxed and relaxed != search_target:
            try:
                rel_url = f"https://www.motorobit.com/arama?q={urllib.parse.quote(relaxed)}"
                html = fetch_url(rel_url, timeout=8)
                cards = re.split(r'data-toggle=[\"\']product[\"\']', html)
            except Exception:
                pass

    items: List[Dict[str, Any]] = []
    for block in cards[1:]:
        u_m = re.search(r'data-toggle=[\"\']product-url[\"\'][^>]*href=[\"\']([^\"\']+)[\"\']|href=[\"\']([^\"\']+)[\"\'][^>]*data-toggle=[\"\']product-url[\"\']', block)
        t_m = re.search(r'data-toggle=[\"\']product-title[\"\'][^>]*>([^<]+)</span>|title=[\"\']([^\"\']+)[\"\']', block)
        p_m = re.search(r'data-toggle=[\"\']price-sell[\"\'][^>]*>([^<]+)</span>', block)
        in_stock = ("Tükendi" not in block)

        if only_in_stock and not in_stock:
            continue

        href = (u_m.group(1) or u_m.group(2)) if u_m else ""
        title = (t_m.group(1) or t_m.group(2)) if t_m else ""

        if href and title:
            title = html_lib.unescape(title.strip())
            raw_p = p_m.group(1).strip() if p_m else "0"
            clean_p = raw_p.replace(".", "").replace(",", ".").strip()
            try:
                pval = round(float(clean_p), 2)
            except Exception:
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
            "price_value": r.get("price_value", 0.0),
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
    Fiyatları karşılaştırır ve en ucuz stoğu öne çıkarır.
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

    all_results: List[Dict[str, Any]] = []
    vendor_counts: Dict[str, int] = {}

    # ThreadPoolExecutor ile paralel sorgulama (maksimum 4 thread)
    with ThreadPoolExecutor(max_workers=len(active_funcs)) as executor:
        future_to_vendor = {
            executor.submit(func, q, only_in_stock, limit_per_vendor): v
            for v, func in active_funcs.items()
        }
        for future in as_completed(future_to_vendor):
            v_key = future_to_vendor[future]
            try:
                v_results = future.result()
                vendor_counts[v_key] = len(v_results)
                all_results.extend(v_results)
            except Exception as e:
                vendor_counts[v_key] = 0

    # Fiyata göre sırala (0 TL olanları en sona at, geçerli fiyatları küçükten büyüğe)
    if sort_by_price:
        all_results.sort(key=lambda x: (0 if (x.get("price_value", 0) > 0 and x.get("in_stock")) else 1, x.get("price_value", 999999)))

    # En ucuz olanı belirle
    cheapest = None
    for item in all_results:
        if item.get("in_stock") and item.get("price_value", 0) > 0:
            item["is_cheapest"] = True
            cheapest = item
            break

    data = {
        "query": q,
        "total_results": len(all_results),
        "in_stock_results": sum(1 for r in all_results if r.get("in_stock")),
        "vendor_counts": vendor_counts,
        "cheapest": cheapest,
        "results": all_results
    }

    _MARKET_CACHE[cache_key] = {"timestamp": now, "data": data}
    return data


def compare_bom_prices(parts: List[str], only_in_stock: bool = True) -> Dict[str, Any]:
    """
    Verilen parça listesi (BOM) için tüm mağazalarda fiyat araştırması yapar.
    En avantajlı mağaza dağılımını (Split Order) ve tasarruf miktarını hesaplar.
    """
    clean_parts = [p.strip() for p in parts if p.strip()]
    if not clean_parts:
        return {"items": [], "optimal_plan": {}, "total_optimal_price": 0.0}

    item_comparisons = []
    vendor_totals: Dict[str, float] = {v: 0.0 for v in VENDORS.keys()}
    vendor_item_counts: Dict[str, int] = {v: 0 for v in VENDORS.keys()}
    optimal_basket: Dict[str, List[Dict[str, Any]]] = {v: [] for v in VENDORS.keys()}
    total_optimal_price = 0.0

    for part_name in clean_parts:
        search_res = search_market(part_name, only_in_stock=only_in_stock, limit_per_vendor=3, sort_by_price=True)
        results = search_res.get("results", [])
        cheapest = search_res.get("cheapest")

        comp = {
            "part_query": part_name,
            "found": len(results) > 0,
            "cheapest_option": cheapest,
            "options": results[:6]
        }
        item_comparisons.append(comp)

        if cheapest:
            v_key = cheapest.get("vendor_key", "other")
            optimal_basket.setdefault(v_key, []).append(cheapest)
            total_optimal_price += cheapest.get("price_value", 0.0)

    # Boş kalan mağazaları sepetten temizle
    active_optimal = {k: v for k, v in optimal_basket.items() if len(v) > 0}

    return {
        "total_items_requested": len(clean_parts),
        "items": item_comparisons,
        "optimal_plan": active_optimal,
        "total_optimal_price": round(total_optimal_price, 2)
    }
