#!/usr/bin/env python3
"""
ElectroStock Web Sunucusu ve REST API Modülü
Harici hiçbir pip veya npm bağımlılığı gerektirmez (Standart Python http.server ile çalışır).
Tarayıcı arayüzü ve yerel REST API sağlar.
"""

import http.server
import socketserver
import json
import urllib.parse
import os
import sys
import base64
from typing import Dict, Any, Optional
import electro_db
import project_matcher
from robotistan_scraper import scraper

PORT = 8080
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


class ElectroRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def log_message(self, format, *args):
        # Temiz terminal çıktısı
        sys.stderr.write(f"[Web] {args[0]} {args[1]} -> {args[2]}\n")

    def send_json(self, data: Any, status: int = 200, cookie: Optional[str] = None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        if status == 401:
            self.send_header("WWW-Authenticate", 'Basic realm="Electra Atolye Envanteri"')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def get_authenticated_user(self) -> Optional[str]:
        """
        Gelen istekteki Bearer token, Basic Auth veya Cookie'yi kontrol ederek
        doğrulanmış kullanıcı adını döndürür. Yetkisiz ise None döner.
        """
        # 1. Authorization Başlığı (Bearer Token veya Basic Auth)
        auth_header = self.headers.get("Authorization", "").strip()
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            user = electro_db.verify_session(token)
            if user:
                return user
        elif auth_header.startswith("Basic "):
            try:
                raw_b64 = auth_header[6:].strip()
                decoded = base64.b64decode(raw_b64).decode("utf-8")
                if ":" in decoded:
                    u, p = decoded.split(":", 1)
                    if electro_db.verify_user_credentials(u, p):
                        return u
            except Exception:
                pass

        # 2. Cookie Başlığı (electra_session=<token>)
        cookie_header = self.headers.get("Cookie", "")
        if "electra_session=" in cookie_header:
            for item in cookie_header.split(";"):
                item = item.strip()
                if item.startswith("electra_session="):
                    parts = item.split("=", 1)
                    if len(parts) == 2:
                        token = parts[1].strip()
                        user = electro_db.verify_session(token)
                        if user:
                            return user

        return None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        # 0. API: Kimlik Doğrulama Durumu (Herkese açık kontrol)
        if path == "/api/auth/check":
            user = self.get_authenticated_user()
            if user:
                self.send_json({"authenticated": True, "username": user})
            else:
                self.send_json({"authenticated": False, "username": None})
            return

        # Tüm diğer /api/ istekleri kimlik doğrulama gerektirir
        if path.startswith("/api/"):
            user = self.get_authenticated_user()
            if not user:
                self.send_json({"error": "Kimlik doğrulaması gerekli.", "authenticated": False}, status=401)
                return

        # 1. API: İstatistikler
        if path == "/api/stats":
            stats = electro_db.get_summary_stats()
            self.send_json(stats)
            return

        # 2. API: Parçalar Listesi & Arama
        elif path == "/api/components":
            q = params.get("q", [""])[0]
            cat = params.get("category", [""])[0]
            st = params.get("status", [""])[0]
            loc = params.get("location", [""])[0]
            low_stock = params.get("low_stock", ["0"])[0] in ("1", "true")
            results = electro_db.search_components(
                query=q,
                category=cat,
                status=st,
                location=loc,
                low_stock_only=low_stock
            )
            self.send_json(results)
            return

        # 3. API: Arızalı ve Çıkma Parçalar
        elif path == "/api/defective":
            items = electro_db.get_defective_components()
            self.send_json(items)
            return

        # 4. API: Kritik Stok Listesi
        elif path == "/api/low-stock":
            items = electro_db.get_low_stock_components()
            self.send_json(items)
            return

        # 5. API: Robotistan Canlı Arama
        elif path == "/api/robotistan/search":
            q = params.get("q", [""])[0]
            only_stock = params.get("only_in_stock", ["1"])[0] in ("1", "true")
            limit = int(params.get("limit", ["10"])[0])
            res = scraper.search(query=q, only_in_stock=only_stock, limit=limit)
            self.send_json(res)
            return

        # 6. API: Veritabanı Yedeği Dışa Aktarma (Export)
        elif path == "/api/export":
            all_data = {
                "components": electro_db.search_components(limit=1000),
                "stats": electro_db.get_summary_stats()
            }
            self.send_json(all_data)
            return

        # 7. API: Sepet Listesi
        elif path == "/api/cart":
            cart_data = electro_db.get_cart_items()
            self.send_json(cart_data)
            return

        # 8. API: Draft (Taslak) Sipariş Listesi & Detayı
        elif path == "/api/draft-orders":
            st = params.get("status", [""])[0]
            orders = electro_db.get_draft_orders(status=st)
            self.send_json(orders)
            return
        elif path.startswith("/api/draft-orders/"):
            parts = path.split("/")
            draft_id = int(parts[3])
            order = electro_db.get_draft_order_by_id(draft_id)
            if order:
                self.send_json(order)
            else:
                self.send_json({"error": "Taslak sipariş bulunamadı"}, status=404)
            return


        # Statik dosya sunumu (HTML, CSS, JS)
        if path == "/" or not os.path.exists(os.path.join(STATIC_DIR, path.lstrip("/"))):
            self.path = "/index.html"

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        # 0. API: Giriş Yap (Login)
        if path == "/api/auth/login":
            u = str(data.get("username", "")).strip()
            p = str(data.get("password", ""))
            if electro_db.verify_user_credentials(u, p):
                token = electro_db.create_session(u)
                cookie = f"electra_session={token}; Path=/; Max-Age=2592000; SameSite=Lax"
                self.send_json({
                    "success": True,
                    "token": token,
                    "username": u,
                    "message": "Giriş başarılı!"
                }, cookie=cookie)
            else:
                self.send_json({"error": "Kullanıcı adı veya şifre hatalı!"}, status=401)
            return

        # 0. API: Çıkış Yap (Logout)
        elif path == "/api/auth/logout":
            auth_header = self.headers.get("Authorization", "").strip()
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
                electro_db.delete_session(token)
            cookie_header = self.headers.get("Cookie", "")
            if "electra_session=" in cookie_header:
                for item in cookie_header.split(";"):
                    item = item.strip()
                    if item.startswith("electra_session="):
                        parts = item.split("=", 1)
                        if len(parts) == 2:
                            electro_db.delete_session(parts[1].strip())
            cookie = "electra_session=; Path=/; Max-Age=0; SameSite=Lax"
            self.send_json({"success": True, "message": "Çıkış yapıldı"}, cookie=cookie)
            return

        # Diğer tüm POST işlemleri kimlik doğrulama gerektirir
        user = self.get_authenticated_user()
        if not user:
            self.send_json({"error": "Kimlik doğrulaması gerekli.", "authenticated": False}, status=401)
            return

        # 0. API: Şifre Değiştir
        if path == "/api/auth/change-password":
            old_p = str(data.get("old_password", ""))
            new_p = str(data.get("new_password", ""))
            success, msg = electro_db.change_user_password(user, old_p, new_p)
            if success:
                self.send_json({"success": True, "message": msg})
            else:
                self.send_json({"error": msg}, status=400)
            return

        # 1. API: Yeni Parça Ekle
        elif path == "/api/components":
            if not data.get("name") or not data.get("category"):
                self.send_json({"error": "name ve category zorunludur"}, status=400)
                return

            comp_id = electro_db.add_component(
                name=data.get("name"),
                category=data.get("category"),
                value=data.get("value", ""),
                package=data.get("package", ""),
                quantity=int(data.get("quantity", 1)),
                min_quantity=int(data.get("min_quantity", 2)),
                status=data.get("status", "working"),
                location=data.get("location", ""),
                notes=data.get("notes", ""),
                tags=data.get("tags", ""),
                datasheet_url=data.get("datasheet_url", "")
            )
            self.send_json({"success": True, "id": comp_id, "message": "Parça eklendi"})
            return

        # 2. API: Stok Hızlı Güncelle (+ / -)
        elif path.startswith("/api/components/") and path.endswith("/adjust"):
            parts = path.split("/")
            comp_id = int(parts[3])
            delta = int(data.get("delta", 0))
            reason = data.get("reason", "")
            new_qty = electro_db.adjust_stock(comp_id, delta, reason)
            self.send_json({"success": True, "new_quantity": new_qty})
            return

        # 3. API: Proje Analizi & Robotistan Eşleştirme
        elif path == "/api/match-project":
            desc = data.get("project_description", "")
            check_rob = bool(data.get("check_robotistan", True))
            analysis = project_matcher.match_project_components(
                project_description=desc,
                check_robotistan=check_rob
            )
            analysis["markdown_report"] = project_matcher.format_project_analysis_markdown(analysis)
            self.send_json(analysis)
            return

        # 4. API: Tüm Verileri Temizle / Sıfırla
        elif path == "/api/clear":
            electro_db.clear_all_data()
            self.send_json({"success": True, "message": "Tüm veriler temizlendi"})
            return

        # 5. API: Robotistan Sepetine Ekle
        elif path == "/api/cart":
            title = data.get("title", "")
            url = data.get("url", "")
            price = data.get("price", "")
            price_val = data.get("price_value", 0.0)
            pid = data.get("product_id")
            qty = int(data.get("quantity", 1))
            item_id = electro_db.add_to_cart(
                title=title, url=url, price=price,
                price_value=price_val, product_id=pid, quantity=qty
            )
            self.send_json({"success": True, "id": item_id, "message": "Ürün sepete eklendi"})
            return

        # 6. API: Draft Sipariş Oluştur
        elif path == "/api/draft-orders":
            title = data.get("title", "Yeni Taslak Sipariş")
            desc = data.get("description", "")
            items = data.get("items", [])
            notes = data.get("notes", "")
            draft_id = electro_db.create_draft_order(
                title=title, description=desc, items=items, notes=notes
            )
            self.send_json({"success": True, "draft_id": draft_id, "message": "Taslak sipariş listesi oluşturuldu"})
            return

        # 7. API: Draft Siparişe Kalem Ekle
        elif path.startswith("/api/draft-orders/") and path.endswith("/items"):
            parts = path.split("/")
            draft_id = int(parts[3])
            item_id = electro_db.add_item_to_draft_order(draft_id, data)
            self.send_json({"success": True, "item_id": item_id, "message": "Kalem eklendi"})
            return

        # 8. API: Draft Siparişi Sepete Aktar
        elif path.startswith("/api/draft-orders/") and path.endswith("/apply-to-cart"):
            parts = path.split("/")
            draft_id = int(parts[3])
            result = electro_db.apply_draft_order_to_cart(draft_id)
            self.send_json(result)
            return

        self.send_json({"error": "Not found"}, status=404)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        user = self.get_authenticated_user()
        if not user:
            self.send_json({"error": "Kimlik doğrulaması gerekli.", "authenticated": False}, status=401)
            return

        if path.startswith("/api/components/"):
            comp_id = int(path.split("/")[3])
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                data = json.loads(body)
                success = electro_db.update_component(comp_id, **data)
                self.send_json({"success": success})
            except Exception as e:
                self.send_json({"error": str(e)}, status=400)
            return

        elif path.startswith("/api/cart/"):
            cart_id = int(path.split("/")[3])
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                data = json.loads(body)
                qty = int(data.get("quantity", 1))
                success = electro_db.update_cart_quantity(cart_id, qty)
                self.send_json({"success": success})
            except Exception as e:
                self.send_json({"error": str(e)}, status=400)
            return

        elif path.startswith("/api/draft-orders/") and path.endswith("/status"):
            parts = path.split("/")
            draft_id = int(parts[3])
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                data = json.loads(body)
                st = data.get("status", "draft")
                notes = data.get("notes", "")
                success = electro_db.update_draft_order_status(draft_id, st, notes)
                self.send_json({"success": success})
            except Exception as e:
                self.send_json({"error": str(e)}, status=400)
            return

        self.send_json({"error": "Not found"}, status=404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        user = self.get_authenticated_user()
        if not user:
            self.send_json({"error": "Kimlik doğrulaması gerekli.", "authenticated": False}, status=401)
            return

        if path.startswith("/api/components/"):
            comp_id = int(path.split("/")[3])
            success = electro_db.delete_component(comp_id)
            self.send_json({"success": success})
            return

        elif path == "/api/cart":
            electro_db.clear_cart()
            self.send_json({"success": True, "message": "Sepet boşaltıldı"})
            return

        elif path.startswith("/api/cart/"):
            cart_id = int(path.split("/")[3])
            success = electro_db.remove_from_cart(cart_id)
            self.send_json({"success": success})
            return

        elif path.startswith("/api/draft-orders/"):
            draft_id = int(path.split("/")[3])
            success = electro_db.delete_draft_order(draft_id)
            self.send_json({"success": success})
            return

        self.send_json({"error": "Not found"}, status=404)



class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def run_server(port: int = PORT):
    electro_db.init_db()
    os.makedirs(STATIC_DIR, exist_ok=True)

    # SO_REUSEADDR ile belirlenen porta bağlan (gerekirse kısa bekleme ile)
    for attempt in range(5):
        try:
            with ReusableTCPServer(("", port), ElectroRequestHandler) as httpd:
                print(f"🚀 ElectroStock Web Arayüzü Başlatıldı: http://localhost:{port}")
                print("Durdurmak için Ctrl+C tuşlayabilirsiniz.\n")
                httpd.serve_forever()
                break
        except OSError as e:
            if attempt < 4:
                import time
                time.sleep(0.5)
            else:
                print(f"Port hatası ({port}): {e}")
                sys.exit(1)


if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    run_server(port_arg)

