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

    # Robotistan seçeneğini tespit et
    robotistan_item = next((x for x in all_results if x.get("vendor_key") == "robotistan" and x.get("in_stock") and x.get("price_value", 0) > 0), None)

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
                # Fark 100 TL'den fazla -> Kullanıcıya sorulmalı
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
        "total_results": len(all_results),
        "in_stock_results": sum(1 for r in all_results if r.get("in_stock")),
        "vendor_counts": vendor_counts,
        "cheapest": cheapest,
        "robotistan_option": robotistan_item,
        "decision_advice": decision_advice,
        "results": all_results
    }

    _MARKET_CACHE[cache_key] = {"timestamp": now, "data": data}
    return data


def compare_bom_prices(
    parts: List[str],
    only_in_stock: bool = True,
    shipping_cost_per_vendor: float = 50.0,
    price_threshold: float = 100.0,
    prefer_robotistan: bool = True
) -> Dict[str, Any]:
    """
    Verilen parça listesi (BOM) için tüm mağazalarda fiyat araştırması yapar.
    
    Robotistan Birincil Tedarikçi Mantığı:
    1. Kullanıcı Robotistan'dan aynı gün teslimat alır.
    2. Harici mağazalar minimum ~40-75 TL kargo ücreti ekler.
    3. Fiyat farkı 100 TL'nin altındaysa veya ek kargo tasarrufu siliyorsa parça Robotistan sepetinde tutulur.
    4. Fiyat farkı 100 TL'nin üzerindeyse veya Robotistan'da stok yoksa kullanıcıya soru yöneltilir.
    """
    clean_parts = [p.strip() for p in parts if p.strip()]
    if not clean_parts:
        return {
            "items": [],
            "smart_plan": {},
            "naive_plan": {},
            "total_smart_price": 0.0,
            "total_shipping_estimated": 0.0,
            "total_landed_cost": 0.0,
            "prompt_questions": []
        }

    item_comparisons = []
    smart_basket: Dict[str, List[Dict[str, Any]]] = {v: [] for v in VENDORS.keys()}
    naive_basket: Dict[str, List[Dict[str, Any]]] = {v: [] for v in VENDORS.keys()}
    prompt_questions: List[Dict[str, Any]] = []

    total_smart_parts_cost = 0.0
    total_naive_parts_cost = 0.0

    for part_name in clean_parts:
        search_res = search_market(part_name, only_in_stock=only_in_stock, limit_per_vendor=3, sort_by_price=True)
        results = search_res.get("results", [])
        cheapest = search_res.get("cheapest")
        rob_item = search_res.get("robotistan_option")
        decision = search_res.get("decision_advice", {})

        comp = {
            "part_query": part_name,
            "found": len(results) > 0,
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

            if not cheapest or cheapest.get("vendor_key") == "robotistan" or diff <= price_threshold:
                # Robotistan'da tut
                smart_basket.setdefault("robotistan", []).append({**rob_item, "part_query": part_name, "assigned_reason": "Robotistan (Aynı gün kargo & fark ≤100 TL)"})
                total_smart_parts_cost += rob_price
            else:
                # Harici mağaza >100 TL daha ucuz -> Hariciye ver ama kullanıcıya sor
                v_key = cheapest.get("vendor_key", "other")
                smart_basket.setdefault(v_key, []).append({**cheapest, "part_query": part_name, "assigned_reason": f"{cheapest['vendor']} ({diff:.2f} TL tasarruf > 100 TL)"})
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
            # Robotistan'da stok yok, mecbur harici mağaza
            v_key = cheapest.get("vendor_key", "other")
            smart_basket.setdefault(v_key, []).append({**cheapest, "part_query": part_name, "assigned_reason": "Robotistan stokta yok"})
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

    active_smart = {k: v for k, v in smart_basket.items() if len(v) > 0}
    active_naive = {k: v for k, v in naive_basket.items() if len(v) > 0}

    # Tahmini Harici Kargo Maliyeti Hesabı
    # Robotistan ana sipariş kabul edilir (0 TL ek kargo). Her harici aktif mağaza için shipping_cost_per_vendor eklenir.
    external_vendor_count = sum(1 for v in active_smart.keys() if v != "robotistan")
    estimated_shipping_total = external_vendor_count * shipping_cost_per_vendor
    total_landed_cost = total_smart_parts_cost + estimated_shipping_total

    return {
        "total_items_requested": len(clean_parts),
        "items": item_comparisons,
        "smart_plan": active_smart,
        "naive_plan": active_naive,
        "total_smart_parts_cost": round(total_smart_parts_cost, 2),
        "estimated_shipping_total": round(estimated_shipping_total, 2),
        "total_landed_cost": round(total_landed_cost, 2),
        "external_vendor_count": external_vendor_count,
        "prompt_questions": prompt_questions
    }

