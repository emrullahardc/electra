"""
Robotistan Canlı Arama ve Stok / Fiyat Scraper Modülü
Robotistan.com üzerinden ürünlerin canlı stok durumunu, fiyatını ve linkini çeker.
Önbellekleme (Cache) ve hata toleransı ile çalışır.
"""

import urllib.request
import urllib.parse
import urllib.error
import re
import time
from typing import List, Dict, Any, Optional

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
CACHE_TTL = 900  # 15 dakika önbellek süresi

# URL Cache: {query_lower: {"timestamp": float, "results": list}}
_CACHE: Dict[str, Dict[str, Any]] = {}


def clean_price(price_str: str) -> Optional[float]:
    """Türk Lirası formatındaki fiyatı (örn. '1.298,21 TL') floata çevirir."""
    try:
        cleaned = price_str.replace("TL", "").replace("₺", "").strip()
        cleaned = cleaned.replace(".", "").replace(",", ".")
        return round(float(cleaned), 2)
    except Exception:
        return None


class RobotistanScraper:
    def __init__(self, cache_ttl: int = CACHE_TTL):
        self.cache_ttl = cache_ttl
        self.base_url = "https://www.robotistan.com"

    def search(
        self,
        query: str,
        only_in_stock: bool = False,
        limit: int = 15,
        bypass_cache: bool = False
    ) -> Dict[str, Any]:
        """
        Robotistan'da ürün arar.
        Döndürdüğü alanlar:
        - query: Arama terimi
        - total_found: Bulunan ürün sayısı
        - in_stock_count: Stokta olan ürün sayısı
        - results: [ {title, price, price_value, in_stock, url, image}, ... ]
        """
        q = query.strip()
        if not q:
            return {"query": "", "total_found": 0, "in_stock_count": 0, "results": []}

        cache_key = q.lower()
        now = time.time()

        if not bypass_cache and cache_key in _CACHE:
            entry = _CACHE[cache_key]
            if now - entry["timestamp"] < self.cache_ttl:
                results = entry["results"]
                if only_in_stock:
                    results = [r for r in results if r["in_stock"]]
                return {
                    "query": q,
                    "from_cache": True,
                    "total_found": len(results),
                    "in_stock_count": sum(1 for r in results if r["in_stock"]),
                    "results": results[:limit]
                }

        search_url = f"{self.base_url}/arama?q={urllib.parse.quote(q)}"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.robotistan.com/"
        }

        req = urllib.request.Request(search_url, headers=headers)
        html_content = ""

        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                html_content = response.read().decode("utf-8", errors="ignore")
        except urllib.error.URLError as e:
            # Network erişimi yoksa (örn. sandbox kısıtlaması)
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

        parsed_items = self._parse_html(html_content)

        # Önbelleğe kaydet
        _CACHE[cache_key] = {
            "timestamp": now,
            "results": parsed_items
        }

        final_results = parsed_items
        if only_in_stock:
            final_results = [r for r in final_results if r["in_stock"]]

        return {
            "query": q,
            "from_cache": False,
            "total_found": len(final_results),
            "in_stock_count": sum(1 for r in parsed_items if r["in_stock"]),
            "results": final_results[:limit]
        }

    def _parse_html(self, html: str) -> List[Dict[str, Any]]:
        """Robotistan T-Soft HTML sayfasından ürün kartlarını ayrıştırır."""
        items: List[Dict[str, Any]] = []

        # Ürün kartları container'ı
        product_cards = re.findall(
            r'<div[^>]*class=[\"\'][^\"\']*product-item[^\"\']*[\"\'][^>]*>(.*?)</div>\s*</div>\s*</div>',
            html,
            re.DOTALL
        )

        for card in product_cards:
            # Başlık ve Ürün Linki
            title_match = re.search(
                r'<a[^>]+class=[\"\'][^\"\']*product-title[^\"\']*[\"\'][^>]*>([^<]+)</a>',
                card
            )
            if not title_match:
                title_match = re.search(
                    r'<a[^>]+href=[\"\']([^\"\']+)[\"\'][^>]*class=[\"\'][^\"\']*product-title[^\"\']*[\"\'][^>]*>([^<]+)</a>',
                    card
                )

            # Link
            link_match = re.search(r'href=[\"\'](/[^\"\']+)[\"\']', card)

            # Fiyat
            price_match = re.search(r'class=[\"\']product-price[\"\']>([^<]+)</strong>', card)

            # Stok durumu kontrolü
            is_out_of_stock = ("out-of-stock" in card.lower()) or ("tükendi" in card.lower())

            # Görsel
            img_match = re.search(r'<img[^>]+(?:data-src|src)=[\"\']([^\"\']+)[\"\']', card)

            if title_match:
                # Başlık
                if len(title_match.groups()) == 2:
                    link = title_match.group(1).strip()
                    title = title_match.group(2).strip()
                else:
                    title = title_match.group(1).strip()
                    link = link_match.group(1).strip() if link_match else ""

                if link and not link.startswith("http"):
                    link = self.base_url + link

                # Fiyat formatlama
                if price_match:
                    raw_price = price_match.group(1).strip()
                    formatted_price = f"{raw_price} TL"
                    price_val = clean_price(raw_price)
                else:
                    formatted_price = "Tükendi / Fiyat Yok" if is_out_of_stock else "Fiyat Belirtilmemiş"
                    price_val = None

                # Görsel formatlama
                image_url = ""
                if img_match:
                    img_src = img_match.group(1).strip()
                    if img_src.startswith("//"):
                        image_url = "https:" + img_src
                    elif img_src.startswith("/"):
                        image_url = self.base_url + img_src
                    else:
                        image_url = img_src

                # Ürün ID (T-Soft Product ID)
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
                "note": "Canlı fiyat ve stok için linke tıklayabilirsiniz (veya MCP/Web servis ağ izniyle çalıştırıldığında anlık çeker)."
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
