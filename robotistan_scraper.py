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


def normalize_search_query(q: str) -> str:
    """Elektronik parça aramalarında sıkça geçen eşanlamlı ve bağlaçları normalize eder."""
    text = q.strip().lower()
    text = re.sub(r'\bli-po\b|\blityum[- ]polimer\b', 'lipo', text)
    text = re.sub(r'\bli-ion\b|\blityum[- ]iyon\b', 'li-ion', text)
    text = re.sub(r'\bivmeölçer\b|\bivme sensörü\b', 'ivmeolcer', text)
    return text.strip()


def relax_query(q: str) -> Optional[str]:
    """Arama 0 sonuç verdiğinde arama gürültüsü oluşturan kelimeleri çıkarıp anahtar kelimeleri bırakır."""
    noise_words = {
        'korumalı', 'korumasiz', 'koruma', 'kartı', 'karti', 'devreli', 'dahili', 'harici',
        'orijinal', 'adet', 'set', 'seti', 'parça', 'parca', 'modülü', 'modulu', 'uyumlu',
        'mah', 'v', 'volt', 'amper'
    }
    words = [w for w in re.split(r'[\s\-_/]+', q.lower()) if w]
    filtered = [w for w in words if w not in noise_words and not re.match(r'^\d+(?:mah|v|a|cm|mm)$', w)]
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

        # Sorguyu normalize et (örn: 'Lityum Polimer Pil korumalı' -> 'lipo pil korumalı')
        norm_q = normalize_search_query(q)
        search_target = norm_q if norm_q else q
        search_url = f"{self.base_url}/arama?q={urllib.parse.quote(search_target)}"

        try:
            html_content = self._fetch_html(search_url)
        except urllib.error.URLError as e:
            # Network erişimi yoksa
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

        # Eğer sonuç çıkmadıysa akıllı arama gevşetme (Relaxed Query) dene:
        if not parsed_items:
            relaxed = relax_query(search_target)
            if relaxed and relaxed != search_target:
                try:
                    rel_url = f"{self.base_url}/arama?q={urllib.parse.quote(relaxed)}"
                    rel_html = self._fetch_html(rel_url)
                    rel_items = self._parse_html(rel_html)
                    if rel_items:
                        parsed_items = rel_items
                except Exception:
                    pass

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

    def get_product_details(self, url: str) -> Dict[str, Any]:
        """Belirtilen Robotistan ürün sayfasının detaylı teknik özelliklerini ve açıklamasını çeker."""
        if not url or not url.startswith("http"):
            return {"error": "Geçersiz URL"}

        try:
            html = self._fetch_html(url)
        except Exception as e:
            return {"error": f"Ürün sayfasına ulaşılamadı: {e}", "url": url}

        # 1. Başlık
        m_title = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
        title = re.sub(r'<[^>]+>', '', m_title.group(1)).strip() if m_title else ""
        if not title:
            m_t = re.search(r'<title>([^<]+)</title>', html)
            title = m_t.group(1).replace("Satın Al", "").strip() if m_t else ""

        # 2. Fiyat
        m_price = re.search(r'class=[\"\'][^\"\']*(?:product-price|price-current|current-price|price)[^\"\']*[\"\']>\s*([0-9.,]+)', html)
        if not m_price:
            m_price = re.search(r'(\d+[\.,]\d+)\s*(?:TL|₺)', html)
        price_val = None
        price_str = "Fiyat Belirtilmedi"
        if m_price:
            raw_p = m_price.group(1).strip()
            price_str = f"{raw_p} TL"
            price_val = clean_price(raw_p)

        # 3. Stok
        is_out = ("out-of-stock" in html.lower()) or ("tükendi" in html.lower()) or ("gelince haber ver" in html.lower())

        # 4. Teknik Özellikler ve Parametre Tablosu
        specs = []
        m_feat = re.search(r'<div[^>]+id=[\"\']product-features[\"\'][^>]*>(.*?)</div>\s*</div>', html, re.DOTALL)
        if m_feat:
            content = m_feat.group(1)
            # Tablo satırları
            for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', content, re.DOTALL):
                tds = re.findall(r'<td[^>]*>(.*?)</td>', tr)
                if len(tds) >= 2:
                    k = re.sub(r'<[^>]+>', '', tds[0]).strip()
                    v = re.sub(r'<[^>]+>', '', tds[1]).strip()
                    if k and v and k.lower() != "parametre":
                        specs.append(f"{k}: {v}")
            # Liste maddeleri
            for li in re.findall(r'<li[^>]*>(.*?)</li>', content):
                clean_li = re.sub(r'<[^>]+>', '', li).strip()
                if clean_li and clean_li not in specs and len(clean_li) > 2:
                    specs.append(clean_li)

        # 5. Açıklama metni
        desc_text = ""
        m_desc = re.search(r'<div[^>]+id=[\"\']product-detail[\"\'][^>]*>(.*?)</div>\s*</div>', html, re.DOTALL)
        if not m_desc:
            m_desc = m_feat
        if m_desc:
            clean_desc = re.sub(r'<style[^>]*>.*?</style>', '', m_desc.group(1), flags=re.DOTALL)
            clean_desc = re.sub(r'<script[^>]*>.*?</script>', '', clean_desc, flags=re.DOTALL)
            clean_desc = re.sub(r'<[^>]+>', ' ', clean_desc)
            desc_text = re.sub(r'\s+', ' ', clean_desc).strip()
            if len(desc_text) > 600:
                desc_text = desc_text[:600] + "..."

        return {
            "title": title,
            "price": price_str,
            "price_value": price_val,
            "in_stock": not is_out,
            "stock_status": "Stokta Var" if not is_out else "Tükendi",
            "specs": specs,
            "description": desc_text,
            "url": url
        }

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
