"""
Robotistan Canlı Arama ve Stok / Fiyat Scraper Modülü
Robotistan.com üzerinden ürünlerin canlı stok durumunu, fiyatını ve linkini çeker.
Önbellekleme (Cache) ve hata toleransı ile çalışır.
"""

import urllib.request
import urllib.parse
import urllib.error
import html as html_lib
import re
import time
from typing import List, Dict, Any, Optional

from component_matcher import (
    get_component_search_aliases,
    evaluate_component_relevance,
)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
CACHE_TTL = 900  # 15 dakika önbellek süresi

# URL Cache: {query_lower: {"timestamp": float, "results": list}}
_CACHE: Dict[str, Dict[str, Any]] = {}


def clean_price(price_str: str) -> Optional[float]:
    """Türk Lirası formatındaki fiyatı (örn. '1.298,21 TL' veya '1,023.54') floata çevirir."""
    if not price_str:
        return None
    try:
        cleaned = re.sub(r'<[^>]+>', '', str(price_str)).replace("TL", "").replace("₺", "").replace("&nbsp;", "").strip()
        if "." in cleaned and "," in cleaned:
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
        return round(float(nums[0]), 2) if nums else None
    except Exception:
        return None


def normalize_search_query(q: str) -> str:
    """Elektronik parça aramalarında sıkça geçen eşanlamlı ve bağlaçları normalize eder."""
    text = q.strip().lower()
    text = re.sub(r'\bli-po\b|\blityum[- ]polimer\b', 'lipo', text)
    text = re.sub(r'\bli-ion\b|\blityum[- ]iyon\b', 'li-ion', text)
    text = re.sub(r'\bivmeölçer\b|\bivme sensörü\b', 'ivmeolcer', text)
    return text.strip()


def relax_query(q: str) -> Optional[str]:
    """
    Arama 0 sonuç verdiğinde yalnızca gerçek dolgu kelimelerini çıkarır;
    asla 'koruma', 'kartı', 'bms', kapasite (mAh) veya voltaj (V) değerlerini silmez.
    """
    noise_words = {
        'orijinal', 'adet', 'set', 'seti', 'parça', 'parca', 'modülü', 'modulu',
        'uyumlu', 'dahili', 'harici', 'paket', 'paketi', 'sensörü', 'sensoru'
    }
    words = [w for w in re.split(r'\s+', q.lower().strip()) if w]
    filtered = [w for w in words if w not in noise_words]
    if filtered and len(filtered) < len(words):
        return " ".join(filtered)
    return None


class RobotistanScraper:
    def __init__(self, cache_ttl: int = CACHE_TTL):
        self.cache_ttl = cache_ttl
        self.base_url = "https://www.robotistan.com"

    def _fetch_html(self, url: str) -> str:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.robotistan.com/"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as response:
            return response.read().decode("utf-8", errors="ignore")

    def _filter_compatible(self, query: str, items: List[Dict[str, Any]], seen_urls: set) -> List[Dict[str, Any]]:
        """Ayrıştırılan ürünleri anlamsal uyumluluk filtresinden geçirir ve mükerrer URL'leri eler."""
        valid: List[Dict[str, Any]] = []
        for it in items:
            url = it.get("url") or it.get("title", "")
            if url in seen_urls:
                continue
            is_valid, rel_score, reason = evaluate_component_relevance(query, it.get("title", ""))
            if is_valid:
                seen_urls.add(url)
                it["relevance_score"] = rel_score
                it["compatibility_note"] = reason
                valid.append(it)
        return valid

    def search(
        self,
        query: str,
        only_in_stock: bool = False,
        limit: int = 15,
        bypass_cache: bool = False
    ) -> Dict[str, Any]:
        """
        Robotistan'da ürün arar.
        Önce birincil sorguyu dener ve anlamsal uyumluluk filtresinden geçirir.
        Eğer uyumlu ve stokta olan bir ürün bulunamazsa donanım alias'larını (örn. NEO-6M -> GY-NEO6MV2,
        MPU-6050 -> MPU6050 / GY-521) sırasıyla dener.
        """
        q = query.strip()
        if not q:
            return {"query": "", "total_found": 0, "in_stock_count": 0, "results": []}

        cache_key = q.lower()
        now = time.time()

        if not bypass_cache and cache_key in _CACHE:
            entry = _CACHE[cache_key]
            if now - entry["timestamp"] < self.cache_ttl:
                results = list(entry["results"])
                if only_in_stock:
                    results = [r for r in results if r["in_stock"]]
                return {
                    "query": q,
                    "from_cache": True,
                    "total_found": len(results),
                    "in_stock_count": sum(1 for r in results if r["in_stock"]),
                    "results": results[:limit]
                }

        norm_q = normalize_search_query(q)
        search_target = norm_q if norm_q else q
        search_url = f"{self.base_url}/arama?q={urllib.parse.quote(search_target)}"

        try:
            html_content = self._fetch_html(search_url)
        except urllib.error.URLError as e:
            return {
                "query": q,
                "error": f"Robotistan sunucusuna ulaşılamadı: {e}",
                "network_error": True,
                "total_found": 0,
                "in_stock_count": 0,
                "results": self._generate_fallback_results(q)
            }
        except Exception as e:
            return {
                "query": q,
                "error": str(e),
                "total_found": 0,
                "in_stock_count": 0,
                "results": []
            }

        seen_urls: set = set()
        raw_items = self._parse_html(html_content)
        valid_items = self._filter_compatible(q, raw_items, seen_urls)

        # 1. Eğer uyumlu ve stokta olan ürün bulunamadıysa donanım ve ortografik alias'ları dene
        if not any(it.get("in_stock") for it in valid_items):
            aliases = get_component_search_aliases(q)
            tried_queries = {q.lower(), search_target.lower()}
            for alias in aliases:
                a_low = alias.strip().lower()
                if not a_low or a_low in tried_queries:
                    continue
                tried_queries.add(a_low)
                try:
                    alias_url = f"{self.base_url}/arama?q={urllib.parse.quote(alias)}"
                    alias_html = self._fetch_html(alias_url)
                    alias_raw = self._parse_html(alias_html)
                    alias_valid = self._filter_compatible(q, alias_raw, seen_urls)
                    if alias_valid:
                        valid_items.extend(alias_valid)
                        if any(it.get("in_stock") for it in valid_items):
                            break
                except Exception:
                    pass

        # 2. Hâlâ uyumlu ürün bulunamadıysa gevşetilmiş sorguyu (relaxed query) dene
        if not valid_items:
            relaxed = relax_query(search_target)
            if relaxed and relaxed.lower() not in {q.lower(), search_target.lower()}:
                try:
                    rel_url = f"{self.base_url}/arama?q={urllib.parse.quote(relaxed)}"
                    rel_html = self._fetch_html(rel_url)
                    rel_raw = self._parse_html(rel_html)
                    valid_items.extend(self._filter_compatible(q, rel_raw, seen_urls))
                except Exception:
                    pass

        # Stokta olanları ve yüksek uyumluluk skoruna sahip olanları öne sırala
        valid_items.sort(
            key=lambda x: (
                0 if x.get("in_stock") else 1,
                -(x.get("relevance_score", 0.5)),
                x.get("price_value") if (x.get("price_value") and x.get("price_value") > 0) else 999999
            )
        )

        _CACHE[cache_key] = {
            "timestamp": now,
            "results": valid_items
        }

        final_results = [r for r in valid_items if r["in_stock"]] if only_in_stock else valid_items

        return {
            "query": q,
            "from_cache": False,
            "total_found": len(final_results),
            "in_stock_count": sum(1 for r in valid_items if r["in_stock"]),
            "results": final_results[:limit]
        }

    def _parse_html(self, html: str) -> List[Dict[str, Any]]:
        """Robotistan T-Soft HTML sayfasından ürün kartlarını ayrıştırır."""
        items: List[Dict[str, Any]] = []

        product_cards = re.findall(
            r'<div[^>]*class=[\"\'][^\"\']*product-item[^\"\']*[\"\'][^>]*>(.*?)</div>\s*</div>\s*</div>',
            html,
            re.DOTALL
        )

        for card in product_cards:
            title_match = re.search(
                r'<a[^>]+class=[\"\'][^\"\']*product-title[^\"\']*[\"\'][^>]*>([^<]+)</a>',
                card
            )
            if not title_match:
                title_match = re.search(
                    r'<a[^>]+href=[\"\']([^\"\']+)[\"\'][^>]*class=[\"\'][^\"\']*product-title[^\"\']*[\"\'][^>]*>([^<]+)</a>',
                    card
                )

            link_match = re.search(r'href=[\"\'](/[^\"\']+)[\"\']', card)
            price_match = re.search(r'class=[\"\']product-price[\"\']>([^<]+)</strong>', card)
            is_out_of_stock = ("out-of-stock" in card.lower()) or ("tükendi" in card.lower())
            img_match = re.search(r'<img[^>]+(?:data-src|src)=[\"\']([^\"\']+)[\"\']', card)

            if title_match:
                if len(title_match.groups()) == 2:
                    link = title_match.group(1).strip()
                    title = html_lib.unescape(title_match.group(2).strip())
                else:
                    title = html_lib.unescape(title_match.group(1).strip())
                    link = link_match.group(1).strip() if link_match else ""

                if link and not link.startswith("http"):
                    link = self.base_url + link

                if price_match:
                    raw_price = price_match.group(1).strip()
                    price_val = clean_price(raw_price)
                    formatted_price = f"{price_val:.2f} TL" if price_val else f"{raw_price} TL"
                else:
                    formatted_price = "Tükendi / Fiyat Yok" if is_out_of_stock else "Fiyat Belirtilmemiş"
                    price_val = None

                image_url = ""
                if img_match:
                    img_src = img_match.group(1).strip()
                    if img_src.startswith("//"):
                        image_url = "https:" + img_src
                    elif img_src.startswith("/"):
                        image_url = self.base_url + img_src
                    else:
                        image_url = img_src

                pid_match = re.search(r'addToCart\((\d+)', card)
                if not pid_match:
                    pid_match = re.search(r'data-id=[\"\'](\d+)[\"\']', card)
                product_id = int(pid_match.group(1)) if pid_match else None

                items.append({
                    "product_id": product_id,
                    "title": title,
                    "price": formatted_price,
                    "price_value": price_val,
                    "in_stock": not is_out_of_stock,
                    "stock_status": "Stokta Var" if not is_out_of_stock else "Tükendi",
                    "url": link,
                    "image": image_url
                })

        return items

    def get_product_details(self, url: str) -> Dict[str, Any]:
        """Belirtilen ürün sayfasının detaylı teknik özelliklerini, KDV dahil fiyatını ve stok durumunu çeker."""
        from market_scraper import get_universal_product_details
        return get_universal_product_details(url)

    def _generate_fallback_results(self, query: str) -> List[Dict[str, Any]]:
        """Ağ erişimi olmadığında doğrudan arama URL'sini ve örnek bilgiyi sunar."""
        safe_q = urllib.parse.quote(query)
        return [
            {
                "title": f"Robotistan Arama: '{query}'",
                "price": "Robotistan'da İncele",
                "price_value": None,
                "in_stock": True,
                "stock_status": "Robotistan Sayfasına Git",
                "url": f"https://www.robotistan.com/arama?q={safe_q}",
                "image": "https://robotistan.witcdn.net/Data/EditorFiles/logo/logo-1.png",
                "note": "Canlı fiyat ve stok için linke tıklayabilirsiniz."
            }
        ]


# Singleton instance
scraper = RobotistanScraper()


if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "esp32"
    print(f"Robotistan'da '{query}' aranıyor...")
    res = scraper.search(query)
    print(f"Toplam {res['total_found']} ürün bulundu (Stokta olan: {res['in_stock_count']}):")
    for item in res["results"][:5]:
        print(f" - [{item['stock_status']}] {item['title']} -> {item['price']} ({item['url']})")
