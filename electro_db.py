"""
ElectroStock - Elektronik Parça ve Stok Takip Veritabanı Modülü
SQLite tabanlı, elektronik bileşenlere özel alanlar (değer, kılıf/paket, durum, saklama lokasyonu, arıza notu).
"""

import sqlite3
import json
import hashlib
import secrets
import os
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "electro_stock.db")

CATEGORIES = {
    "resistor": "Direnç",
    "capacitor": "Kondansatör",
    "diode_led": "Diyot & LED",
    "transistor": "Transistör & MOSFET",
    "ic_mcu": "Entegre & Mikrodenetleyici",
    "sensor": "Sensör",
    "module": "Modül & Kart",
    "connector": "Konnektör & Kablo",
    "power": "Güç & Batarya",
    "passive_other": "Pasif & Diğer",
    "broken_scrap": "Arızalı / Çıkma Parça"
}

STATUSES = {
    "working": "Sağlam / Çalışır",
    "defective": "Arızalı / Bozuk",
    "untested": "Test Bekliyor / Şüpheli",
    "salvage": "Çıkma / Sökülecek"
}


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """PBKDF2 HMAC-SHA256 ile güvenli parola özetleme."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return hashed, salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Zamanlama saldırılarına karşı güvenli parola doğrulama."""
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return secrets.compare_digest(hashed, expected_hash)


def init_db(db_path: str = DB_PATH) -> None:
    """Veritabanı tablolarını ve indekslerini oluşturur."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Parçalar Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS components (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                value TEXT DEFAULT '',
                package TEXT DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 0,
                min_quantity INTEGER NOT NULL DEFAULT 2,
                status TEXT NOT NULL DEFAULT 'working',
                location TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                datasheet_url TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Stok Hareketleri Tablosu (Geçmiş takibi)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                component_id INTEGER NOT NULL,
                change_amount INTEGER NOT NULL,
                new_quantity INTEGER NOT NULL,
                reason TEXT DEFAULT '',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE
            )
        """)

        # Projeler Tablosu (Proje BOM & Malzeme Listesi)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'planning', -- planning, in_progress, completed
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Proje - Parça İlişki Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_components (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                component_id INTEGER,
                custom_name TEXT,
                required_quantity INTEGER NOT NULL DEFAULT 1,
                is_supplied BOOLEAN DEFAULT 0,
                source TEXT DEFAULT 'inventory', -- 'inventory' veya 'robotistan'
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE SET NULL
            )
        """)

        # Robotistan Atölye Sepeti Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cart_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                title TEXT NOT NULL,
                price TEXT NOT NULL,
                price_value REAL DEFAULT 0.0,
                url TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # AI Destekli Draft (Taslak) Sipariş ve Parça Listeleri
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS draft_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft', -- 'draft', 'ready', 'ordered', 'archived'
                total_estimated_price REAL DEFAULT 0.0,
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS draft_order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                draft_order_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                product_id INTEGER,
                url TEXT DEFAULT '',
                price TEXT DEFAULT '',
                price_value REAL DEFAULT 0.0,
                quantity INTEGER NOT NULL DEFAULT 1,
                in_stock BOOLEAN DEFAULT 1,
                source TEXT DEFAULT 'robotistan', -- 'robotistan', 'inventory', 'other'
                matched_inventory_id INTEGER,
                notes TEXT DEFAULT '',
                is_purchased INTEGER DEFAULT 0,
                purchased_at TIMESTAMP DEFAULT NULL,
                transferred_to_inventory INTEGER DEFAULT 0,
                inventory_component_id INTEGER DEFAULT NULL,
                FOREIGN KEY (draft_order_id) REFERENCES draft_orders(id) ON DELETE CASCADE
            )
        """)

        # Dinamik Kolon Migrasyonu (Mevcut draft_order_items tablosunda eksik alanlar varsa otomatik ekle)
        cursor.execute("PRAGMA table_info(draft_order_items)")
        doi_cols = {row["name"] for row in cursor.fetchall()}
        if "is_purchased" not in doi_cols:
            cursor.execute("ALTER TABLE draft_order_items ADD COLUMN is_purchased INTEGER DEFAULT 0")
        if "purchased_at" not in doi_cols:
            cursor.execute("ALTER TABLE draft_order_items ADD COLUMN purchased_at TIMESTAMP DEFAULT NULL")
        if "transferred_to_inventory" not in doi_cols:
            cursor.execute("ALTER TABLE draft_order_items ADD COLUMN transferred_to_inventory INTEGER DEFAULT 0")
        if "inventory_component_id" not in doi_cols:
            cursor.execute("ALTER TABLE draft_order_items ADD COLUMN inventory_component_id INTEGER DEFAULT NULL")

        # Kullanıcılar Tablosu (Güvenlik / Auth)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Oturumlar Tablosu (Session Tokens)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )
        """)

        # Dinamik Öğrenilen Donanım / Breakout Alias Tablosu (Kod içine gömmek yerine DB'de tutulur)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS component_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_compact TEXT NOT NULL,
                alias_term TEXT NOT NULL,
                alias_compact TEXT NOT NULL,
                source TEXT DEFAULT 'auto_discovered',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(canonical_compact, alias_compact)
            )
        """)

        # Muadil / Komponent Bilgi Bankası Tablosu (Dinamik genişletilebilir)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS component_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                keywords TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                part_name TEXT NOT NULL,
                features TEXT DEFAULT '',
                pros TEXT DEFAULT '',
                cons TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(category, part_name)
            )
        """)

        # Varsayılan kullanıcı kontrolü (Yoksa oluştur)
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            default_user = os.getenv("ELECTRA_AUTH_USER", "admin")
            default_pass = os.getenv("ELECTRA_AUTH_PASS", "electra2026")
            h, s = hash_password(default_pass)
            cursor.execute(
                "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                (default_user, h, s)
            )

        # Arama ve hız için indeksler
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comp_name ON components(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comp_category ON components(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comp_status ON components(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comp_location ON components(location)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comp_value ON components(value)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_token ON sessions(token)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alias_canon ON component_aliases(canonical_compact)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alias_comp ON component_aliases(alias_compact)")

        # Fiyat yuvarlama ve veri tutarlılığı temizliği
        cursor.execute("UPDATE draft_orders SET total_estimated_price = ROUND(total_estimated_price, 2)")
        cursor.execute("UPDATE draft_order_items SET price_value = ROUND(price_value, 2)")
        cursor.execute("UPDATE cart_items SET price_value = ROUND(price_value, 2)")
        # Linki olmayan veya sorgulanmamış parçaların hatalı 'Stokta Var' etiketini düzelt
        cursor.execute("UPDATE draft_order_items SET in_stock = 0 WHERE (url = '' OR url IS NULL)")
        cursor.execute("UPDATE draft_order_items SET source = 'market' WHERE (url = '' OR url IS NULL) AND (source = 'robotistan' OR source IS NULL)")

        conn.commit()

    # Muadil bilgi bankası boş ise başlangıç mühendislik verilerini aktar
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM component_knowledge")
            if cursor.fetchone()[0] == 0:
                import seed_knowledge
                seed_knowledge.seed_baseline_knowledge(db_path)
    except Exception:
        pass



def add_component(
    name: str,
    category: str,
    value: str = "",
    package: str = "",
    quantity: int = 1,
    min_quantity: int = 2,
    status: str = "working",
    location: str = "",
    notes: str = "",
    tags: str = "",
    datasheet_url: str = "",
    db_path: str = DB_PATH
) -> int:
    """Yeni bir elektronik parça ekler."""
    if category not in CATEGORIES:
        # Fallback or keep as-is
        pass

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO components (
                name, category, value, package, quantity, min_quantity,
                status, location, notes, tags, datasheet_url, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name.strip(), category, value.strip(), package.strip(),
            int(quantity), int(min_quantity), status, location.strip(),
            notes.strip(), tags.strip(), datasheet_url.strip(), now, now
        ))
        comp_id = cursor.lastrowid

        # İlk stok kaydı
        cursor.execute("""
            INSERT INTO stock_logs (component_id, change_amount, new_quantity, reason)
            VALUES (?, ?, ?, 'İlk Stok Girişi')
        """, (comp_id, int(quantity), int(quantity)))

        conn.commit()
        return comp_id


def update_component(
    component_id: int,
    db_path: str = DB_PATH,
    **kwargs
) -> bool:
    """Bileşen bilgilerini günceller."""
    allowed_fields = [
        "name", "category", "value", "package", "quantity",
        "min_quantity", "status", "location", "notes", "tags", "datasheet_url"
    ]
    updates = []
    values = []

    for k, v in kwargs.items():
        if k in allowed_fields:
            updates.append(f"{k} = ?")
            values.append(v)

    if not updates:
        return False

    updates.append("updated_at = ?")
    values.append(datetime.now().isoformat())
    values.append(component_id)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Eğer miktar güncelleniyorsa logla
        if "quantity" in kwargs:
            cursor.execute("SELECT quantity FROM components WHERE id = ?", (component_id,))
            row = cursor.fetchone()
            if row:
                old_qty = row["quantity"]
                new_qty = int(kwargs["quantity"])
                diff = new_qty - old_qty
                if diff != 0:
                    cursor.execute("""
                        INSERT INTO stock_logs (component_id, change_amount, new_quantity, reason)
                        VALUES (?, ?, ?, 'Miktar Güncellemesi')
                    """, (component_id, diff, new_qty))

        sql = f"UPDATE components SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(sql, tuple(values))
        conn.commit()
        return cursor.rowcount > 0


def adjust_stock(component_id: int, delta: int, reason: str = "", db_path: str = DB_PATH) -> Optional[int]:
    """Stok miktarını artırır veya azaltır."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT quantity FROM components WHERE id = ?", (component_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        current_qty = row["quantity"]
        new_qty = max(0, current_qty + delta)
        now = datetime.now().isoformat()

        cursor.execute("""
            UPDATE components SET quantity = ?, updated_at = ? WHERE id = ?
        """, (new_qty, now, component_id))

        cursor.execute("""
            INSERT INTO stock_logs (component_id, change_amount, new_quantity, reason)
            VALUES (?, ?, ?, ?)
        """, (component_id, delta, new_qty, reason or ('Stok Azaltma' if delta < 0 else 'Stok Ekleme')))

        conn.commit()
        return new_qty


def delete_component(component_id: int, db_path: str = DB_PATH) -> bool:
    """Bileşeni veritabanından siler."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM stock_logs WHERE component_id = ?", (component_id,))
        cursor.execute("DELETE FROM components WHERE id = ?", (component_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_component(component_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Tekil bileşen bilgilerini getirir."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM components WHERE id = ?", (component_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
    return None


def search_components(
    query: str = "",
    category: str = "",
    status: str = "",
    location: str = "",
    low_stock_only: bool = False,
    limit: int = 100,
    db_path: str = DB_PATH
) -> List[Dict[str, Any]]:
    """
    Gelişmiş filtreleme ve esnek donanım araması.
    Tire/boşluk/bitişik yazım farklarını (örn: 'ESP32-C3 SuperMini' <-> 'esp32 c3 super mini'),
    Türkçe karakterleri ve ek açıklama kelimelerini ('SIM800L Modül' <-> 'sim800l') tolere eder.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        conditions = []
        params = []

        if category and category != "all":
            conditions.append("category = ?")
            params.append(category)

        if status and status != "all":
            conditions.append("status = ?")
            params.append(status)

        if location and location != "all":
            conditions.append("location LIKE ?")
            params.append(f"%{location}%")

        if low_stock_only:
            conditions.append("quantity <= min_quantity")

        sql = "SELECT * FROM components"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY status ASC, name ASC"

        cursor.execute(sql, tuple(params))
        all_rows = [dict(r) for r in cursor.fetchall()]

        if not query or not query.strip():
            return all_rows[:limit]

        from component_matcher import normalize_tr, normalize_compact, evaluate_component_relevance

        clean_q = query.strip()
        q_tr = normalize_tr(clean_q)
        q_compact = normalize_compact(clean_q)

        filler_words = {
            "modul", "modulu", "kart", "karti", "devre", "devresi",
            "sensor", "sensoru", "uyumlu", "adet", "set", "ve", "ile"
        }
        q_tokens = [
            t for t in re.split(r'[\s\-_/(),;]+', q_tr)
            if t and t not in filler_words
        ]

        scored_matches = []
        for row in all_rows:
            full_blob = f"{row.get('name', '')} {row.get('value', '')} {row.get('package', '')} {row.get('notes', '')} {row.get('tags', '')} {row.get('category', '')}"
            blob_tr = normalize_tr(full_blob)
            blob_compact = normalize_compact(full_blob)

            # 1. Doğrudan veya bitişik (compact) alt dizge eşleşmesi
            if q_tr in blob_tr or (len(q_compact) >= 3 and q_compact in blob_compact):
                scored_matches.append((1.0, row))
                continue

            # 2. Tüm anlamlı arama kelimelerinin (veya bitişik karşılıklarının) geçmesi
            if q_tokens and all((tok in blob_tr or normalize_compact(tok) in blob_compact) for tok in q_tokens):
                scored_matches.append((0.95, row))
                continue

            # 3. Component Matcher anlamsal ve model kodu uyumluluğu
            title_candidate = f"{row.get('name', '')} {row.get('value', '')} {row.get('package', '')}".strip()
            is_valid, rel_score, _ = evaluate_component_relevance(clean_q, title_candidate)
            if is_valid and rel_score >= 0.5:
                scored_matches.append((rel_score, row))

        scored_matches.sort(key=lambda x: (-x[0], x[1].get("status", ""), x[1].get("name", "")))
        return [item for _, item in scored_matches[:limit]]



def get_summary_stats(db_path: str = DB_PATH) -> Dict[str, Any]:
    """Genel stok durum özeti ve analizleri."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Toplam parça çeşidi ve toplam adet
        cursor.execute("SELECT COUNT(*) as count, SUM(quantity) as total_qty FROM components")
        row = cursor.fetchone()
        total_items = row["count"] or 0
        total_qty = row["total_qty"] or 0

        # Durumlarına göre parça sayıları
        cursor.execute("SELECT status, COUNT(*) as count, SUM(quantity) as qty FROM components GROUP BY status")
        status_counts = {r["status"]: {"count": r["count"], "qty": r["qty"] or 0} for r in cursor.fetchall()}

        # Kritik stok sayısı
        cursor.execute("SELECT COUNT(*) as count FROM components WHERE quantity <= min_quantity")
        low_stock_count = cursor.fetchone()["count"]

        # Kategori dağılımı
        cursor.execute("SELECT category, COUNT(*) as count, SUM(quantity) as qty FROM components GROUP BY category")
        category_counts = {r["category"]: {"count": r["count"], "qty": r["qty"] or 0} for r in cursor.fetchall()}

        # Saklama lokasyonları listesi & parça sayıları
        cursor.execute("""
            SELECT location, COUNT(*) as count 
            FROM components 
            WHERE location IS NOT NULL AND TRIM(location) != '' 
            GROUP BY location 
            ORDER BY count DESC, location ASC
        """)
        loc_rows = cursor.fetchall()
        location_stats = [{"name": r["location"], "count": r["count"]} for r in loc_rows]
        locations = [item["name"] for item in location_stats]

        return {
            "total_items": total_items,
            "total_quantity": total_qty,
            "working_count": status_counts.get("working", {}).get("count", 0),
            "defective_count": status_counts.get("defective", {}).get("count", 0),
            "untested_count": status_counts.get("untested", {}).get("count", 0),
            "salvage_count": status_counts.get("salvage", {}).get("count", 0),
            "low_stock_count": low_stock_count,
            "status_breakdown": status_counts,
            "category_breakdown": category_counts,
            "locations": locations,
            "location_stats": location_stats
        }


def get_defective_components(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Arızalı veya şüpheli/çıkma parçaları getirir (Kullanıcının özellikle takip etmek istediği modül)."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM components 
            WHERE status IN ('defective', 'untested', 'salvage')
            ORDER BY status ASC, name ASC
        """)
        return [dict(r) for r in cursor.fetchall()]


def get_low_stock_components(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Kritik seviyeye düşmüş veya tükenmiş bileşenleri getirir."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM components 
            WHERE quantity <= min_quantity
            ORDER BY quantity ASC, name ASC
        """)
        return [dict(r) for r in cursor.fetchall()]


def clear_all_data(db_path: str = DB_PATH) -> None:
    """Tüm bileşenleri, logları ve projeleri temizler (Sıfırdan başlamak için)."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM project_components")
        cursor.execute("DELETE FROM projects")
        cursor.execute("DELETE FROM stock_logs")
        cursor.execute("DELETE FROM components")
        cursor.execute("DELETE FROM cart_items")
        cursor.execute("DELETE FROM draft_order_items")
        cursor.execute("DELETE FROM draft_orders")
        try:
            cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('components', 'stock_logs', 'projects', 'project_components', 'cart_items', 'draft_orders', 'draft_order_items')")
        except sqlite3.OperationalError:
            pass
        conn.commit()



# --- Robotistan Atölye Sepeti Fonksiyonları ---

def add_to_cart(
    title: str,
    url: str,
    price: str,
    price_value: Optional[float] = 0.0,
    product_id: Optional[int] = None,
    quantity: int = 1,
    db_path: str = DB_PATH
) -> int:
    """Robotistan sepetine yeni ürün ekler veya varsa adet artırır."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        # Eğer aynı ürün (url veya product_id) sepette varsa miktarı artır
        if product_id:
            cursor.execute("SELECT id, quantity FROM cart_items WHERE product_id = ?", (product_id,))
        else:
            cursor.execute("SELECT id, quantity FROM cart_items WHERE url = ?", (url,))
        
        existing = cursor.fetchone()
        if existing:
            new_qty = existing["quantity"] + quantity
            cursor.execute("UPDATE cart_items SET quantity = ? WHERE id = ?", (new_qty, existing["id"]))
            conn.commit()
            return existing["id"]
        else:
            cursor.execute("""
                INSERT INTO cart_items (product_id, title, price, price_value, url, quantity)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (product_id, title, price, round(float(price_value or 0.0), 2), url, quantity))
            conn.commit()
            return cursor.lastrowid


def get_cart_items(db_path: str = DB_PATH) -> Dict[str, Any]:
    """Sepetteki tüm ürünleri ve toplam tutarı döndürür."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cart_items ORDER BY created_at DESC")
        items = [dict(r) for r in cursor.fetchall()]
        
        for it in items:
            it["price_value"] = round(float(it.get("price_value") or 0.0), 2)

        total_qty = sum(item["quantity"] for item in items)
        total_price = sum((item["price_value"] or 0.0) * item["quantity"] for item in items)

        return {
            "items": items,
            "total_items_count": len(items),
            "total_quantity": total_qty,
            "total_price_tl": round(total_price, 2)
        }


def update_cart_quantity(cart_id: int, quantity: int, db_path: str = DB_PATH) -> bool:
    """Sepetteki ürünün miktarını günceller (0 ise siler)."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if quantity <= 0:
            cursor.execute("DELETE FROM cart_items WHERE id = ?", (cart_id,))
        else:
            cursor.execute("UPDATE cart_items SET quantity = ? WHERE id = ?", (quantity, cart_id))
        conn.commit()
        return cursor.rowcount > 0


def remove_from_cart(cart_id: int, db_path: str = DB_PATH) -> bool:
    """Sepetten ürünü çıkarır."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cart_items WHERE id = ?", (cart_id,))
        conn.commit()
        return cursor.rowcount > 0


def clear_cart(db_path: str = DB_PATH) -> None:
    """Sepeti tamamen boşaltır."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cart_items")
        conn.commit()


# --- AI Destekli Draft (Taslak) Sipariş ve Parça Listesi Fonksiyonları ---

def create_draft_order(
    title: str,
    description: str = "",
    items: Optional[List[Dict[str, Any]]] = None,
    notes: str = "",
    status: str = "draft",
    db_path: str = DB_PATH
) -> int:
    """Yeni bir taslak sipariş / parça listesi oluşturur."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        # Toplam tahmini tutarı hesapla
        total_price = 0.0
        if items:
            for it in items:
                pv = round(float(it.get("price_value") or 0.0), 2)
                qty = int(it.get("quantity", 1))
                total_price += pv * qty

        cursor.execute("""
            INSERT INTO draft_orders (title, description, status, total_estimated_price, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (title.strip(), description.strip(), status, round(total_price, 2), notes.strip(), now, now))
        draft_id = cursor.lastrowid

        # Kalemleri ekle
        if items:
            for it in items:
                cursor.execute("""
                    INSERT INTO draft_order_items (
                        draft_order_id, title, product_id, url, price, price_value,
                        quantity, in_stock, source, matched_inventory_id, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    draft_id,
                    it.get("title", "").strip(),
                    it.get("product_id"),
                    it.get("url", "").strip(),
                    it.get("price", "").strip(),
                    round(float(it.get("price_value") or 0.0), 2),
                    int(it.get("quantity", 1)),
                    1 if (it.get("in_stock", True) and it.get("url")) else 0,
                    it.get("source") or ("robotistan" if it.get("url") else "market"),
                    it.get("matched_inventory_id"),
                    it.get("notes", "").strip()
                ))

        conn.commit()
        return draft_id


def get_draft_orders(status: str = "", limit: int = 50, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Tüm taslak siparişleri getirir."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if status and status != "all":
            cursor.execute("""
                SELECT * FROM draft_orders 
                WHERE status = ? 
                ORDER BY updated_at DESC LIMIT ?
            """, (status, limit))
        else:
            cursor.execute("""
                SELECT * FROM draft_orders 
                ORDER BY updated_at DESC LIMIT ?
            """, (limit,))
        
        orders = [dict(r) for r in cursor.fetchall()]
        
        # Her siparişin kalem ve satın alma istatistiklerini ekle
        for o in orders:
            cursor.execute("""
                SELECT 
                    COUNT(*) as item_count, 
                    SUM(quantity) as total_qty,
                    SUM(CASE WHEN is_purchased = 1 THEN 1 ELSE 0 END) as purchased_count,
                    SUM(CASE WHEN is_purchased = 0 OR is_purchased IS NULL THEN 1 ELSE 0 END) as pending_count,
                    SUM(CASE WHEN is_purchased = 0 OR is_purchased IS NULL THEN price_value * quantity ELSE 0 END) as pending_price
                FROM draft_order_items WHERE draft_order_id = ?
            """, (o["id"],))
            agg = cursor.fetchone()
            o["item_count"] = agg["item_count"] or 0
            o["total_quantity"] = agg["total_qty"] or 0
            o["purchased_count"] = agg["purchased_count"] or 0
            o["pending_count"] = agg["pending_count"] or 0
            o["pending_price"] = round(float(agg["pending_price"] or 0.0), 2)
            o["total_estimated_price"] = round(float(o.get("total_estimated_price") or 0.0), 2)

        return orders


def get_draft_order_by_id(draft_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Belirli bir taslak siparişin detaylarını ve tüm ürün kalemlerini getirir."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM draft_orders WHERE id = ?", (draft_id,))
        order_row = cursor.fetchone()
        if not order_row:
            return None

        order = dict(order_row)
        order["total_estimated_price"] = round(float(order.get("total_estimated_price") or 0.0), 2)
        cursor.execute("SELECT * FROM draft_order_items WHERE draft_order_id = ? ORDER BY id ASC", (draft_id,))
        items = [dict(r) for r in cursor.fetchall()]
        for it in items:
            it["price_value"] = round(float(it.get("price_value") or 0.0), 2)
            it["is_purchased"] = bool(it.get("is_purchased", 0))
            it["transferred_to_inventory"] = bool(it.get("transferred_to_inventory", 0))

        pending_items = [it for it in items if not it["is_purchased"]]
        purchased_items = [it for it in items if it["is_purchased"]]

        order["items"] = items
        order["item_count"] = len(items)
        order["total_quantity"] = sum(it["quantity"] for it in items)
        order["pending_item_count"] = len(pending_items)
        order["pending_quantity"] = sum(it["quantity"] for it in pending_items)
        order["pending_estimated_price"] = round(sum(it["price_value"] * it["quantity"] for it in pending_items), 2)
        order["purchased_item_count"] = len(purchased_items)
        order["purchased_quantity"] = sum(it["quantity"] for it in purchased_items)
        order["purchased_total_price"] = round(sum(it["price_value"] * it["quantity"] for it in purchased_items), 2)
        return order


def add_item_to_draft_order(draft_id: int, item: Dict[str, Any], db_path: str = DB_PATH) -> int:
    """Mevcut bir taslak siparişe yeni ürün kalemi ekler."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO draft_order_items (
                draft_order_id, title, product_id, url, price, price_value,
                quantity, in_stock, source, matched_inventory_id, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            draft_id,
            item.get("title", "").strip(),
            item.get("product_id"),
            item.get("url", "").strip(),
            item.get("price", "").strip(),
            round(float(item.get("price_value") or 0.0), 2),
            int(item.get("quantity", 1)),
            1 if (item.get("in_stock", True) and item.get("url")) else 0,
            item.get("source") or ("robotistan" if item.get("url") else "market"),
            item.get("matched_inventory_id"),
            item.get("notes", "").strip()
        ))
        item_id = cursor.lastrowid

        # Taslak siparişin toplam tutarını ve updated_at tarihini güncelle
        cursor.execute("""
            UPDATE draft_orders 
            SET total_estimated_price = ROUND(COALESCE((
                SELECT SUM(price_value * quantity) FROM draft_order_items WHERE draft_order_id = ?
            ), 0.0), 2), updated_at = ?
            WHERE id = ?
        """, (draft_id, datetime.now().isoformat(), draft_id))

        conn.commit()
        return item_id


def delete_draft_order(draft_id: int, db_path: str = DB_PATH) -> bool:
    """Taslak siparişi siler."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM draft_order_items WHERE draft_order_id = ?", (draft_id,))
        cursor.execute("DELETE FROM draft_orders WHERE id = ?", (draft_id,))
        conn.commit()
        return cursor.rowcount > 0


def delete_draft_order_item(item_id: int, db_path: str = DB_PATH) -> bool:
    """Taslak siparişten tek bir kalemi siler ve taslağın toplam tutarını günceller."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT draft_order_id FROM draft_order_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        if not row:
            return False
        draft_id = row["draft_order_id"]

        cursor.execute("DELETE FROM draft_order_items WHERE id = ?", (item_id,))
        now = datetime.now().isoformat()
        cursor.execute("""
            UPDATE draft_orders 
            SET total_estimated_price = ROUND(COALESCE((
                SELECT SUM(price_value * quantity) FROM draft_order_items WHERE draft_order_id = ?
            ), 0.0), 2), updated_at = ?
            WHERE id = ?
        """, (draft_id, now, draft_id))
        conn.commit()
        return True


def delete_draft_order_item_by_query(draft_id: int, query: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Taslak sipariş içindeki kalemi başlık aramasıyla bulup siler."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title FROM draft_order_items WHERE draft_order_id = ? AND title LIKE ? LIMIT 1",
            (draft_id, f"%{query.strip()}%")
        )
        row = cursor.fetchone()
        if not row:
            return None
        item_id = row["id"]
        item_title = row["title"]
        success = delete_draft_order_item(item_id, db_path=db_path)
        if success:
            return {"id": item_id, "title": item_title}
        return None


def update_draft_order_item_quantity(item_id: int, quantity: int, db_path: str = DB_PATH) -> bool:
    """Taslak siparişteki bir kalemin adedini günceller (0 veya daha az olursa siler)."""
    if quantity <= 0:
        return delete_draft_order_item(item_id, db_path=db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT draft_order_id FROM draft_order_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        if not row:
            return False
        draft_id = row["draft_order_id"]

        cursor.execute("UPDATE draft_order_items SET quantity = ? WHERE id = ?", (quantity, item_id))
        now = datetime.now().isoformat()
        cursor.execute("""
            UPDATE draft_orders 
            SET total_estimated_price = ROUND(COALESCE((
                SELECT SUM(price_value * quantity) FROM draft_order_items WHERE draft_order_id = ?
            ), 0.0), 2), updated_at = ?
            WHERE id = ?
        """, (draft_id, now, draft_id))
        conn.commit()
        return True


def update_draft_order_status(draft_id: int, status: str, notes: str = "", db_path: str = DB_PATH) -> bool:
    """Taslak sipariş durumunu günceller (draft, ready, ordered, archived)."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        if notes:
            cursor.execute("UPDATE draft_orders SET status = ?, notes = ?, updated_at = ? WHERE id = ?", (status, notes, now, draft_id))
        else:
            cursor.execute("UPDATE draft_orders SET status = ?, updated_at = ? WHERE id = ?", (status, now, draft_id))
        conn.commit()
        return cursor.rowcount > 0


def apply_draft_order_to_cart(draft_id: int, db_path: str = DB_PATH) -> Dict[str, Any]:
    """Taslak siparişteki tüm Robotistan ürünlerini doğrudan sepete aktarır."""
    order = get_draft_order_by_id(draft_id, db_path=db_path)
    if not order:
        return {"success": False, "error": "Taslak sipariş bulunamadı"}

    added_count = 0
    for it in order.get("items", []):
        if it.get("source") == "robotistan" or it.get("url"):
            add_to_cart(
                title=it["title"],
                url=it.get("url", ""),
                price=it.get("price", "Fiyat Yok"),
                price_value=it.get("price_value", 0.0),
                product_id=it.get("product_id"),
                quantity=it.get("quantity", 1),
                db_path=db_path
            )
            added_count += 1

    # Durumu 'ready' veya güncel yap
    update_draft_order_status(draft_id, "ready", notes="Sepete aktarıldı", db_path=db_path)

    return {
        "success": True,
        "draft_id": draft_id,
        "title": order["title"],
        "added_items_count": added_count,
        "message": f"'{order['title']}' taslağındaki {added_count} ürün Robotistan sepetine aktarıldı!"
    }


def mark_draft_order_item_purchased(item_id: int, is_purchased: bool = True, db_path: str = DB_PATH) -> bool:
    """Taslak siparişteki bir kalemi satın alındı veya satın alınmadı (bekliyor) olarak işaretler."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        if is_purchased:
            cursor.execute("""
                UPDATE draft_order_items 
                SET is_purchased = 1, purchased_at = ? 
                WHERE id = ?
            """, (now, item_id))
        else:
            cursor.execute("""
                UPDATE draft_order_items 
                SET is_purchased = 0, purchased_at = NULL, transferred_to_inventory = 0 
                WHERE id = ?
            """, (item_id,))
        conn.commit()
        return cursor.rowcount > 0


def infer_component_category(name: str) -> str:
    """Parça adına göre uygun envanter kategorisini tahmin eder."""
    n_lower = name.lower()
    if any(k in n_lower for k in ["direnc", "resistor", "ohm", "kohm"]):
        return "resistor"
    elif any(k in n_lower for k in ["kondansator", "kapasitor", "capacitor", "uf", "nf", "pf"]):
        return "capacitor"
    elif any(k in n_lower for k in ["diyot", "diode", "led", "1n4001", "1n4148"]):
        return "diode_led"
    elif any(k in n_lower for k in ["transistor", "transistör", "mosfet", "bc547", "bc557", "2n2222", "irfz"]):
        return "transistor"
    elif any(k in n_lower for k in ["esp32", "esp8266", "stm32", "atmega", "arduino", "mcu", "mikrodenetleyici", "ch340", "cp2102"]):
        return "ic_mcu"
    elif any(k in n_lower for k in ["sensor", "sensör", "gps", "gyro", "ivme", "bmp280", "bme280", "dht", "hc-sr04"]):
        return "sensor"
    elif any(k in n_lower for k in ["modul", "modülü", "kart", "devre", "tp4056", "bms", "step-down", "step-up", "buck", "boost", "shield"]):
        return "module"
    elif any(k in n_lower for k in ["jst", "header", "klemens", "kablo", "soket", "konektor", "konnektor", "terminal", "dupont"]):
        return "connector"
    elif any(k in n_lower for k in ["pil", "batarya", "battery", "lipo", "li-po", "18650"]):
        return "power"
    elif any(k in n_lower for k in ["pertinaks", "plaket", "pcb", "breadboard"]):
        return "passive_other"
    return "module"


def transfer_draft_item_to_inventory(
    item_id: int,
    category: str = "",
    location: str = "",
    notes: str = "",
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    """
    Satın alınmış bir taslak kalemini doğrudan envanter stoğuna aktarır.
    Eğer envanterde eşleşen çalışan bir parça varsa adedini artırır;
    yoksa yeni bir bileşen kaydı açar.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM draft_order_items WHERE id = ?", (item_id,))
        item_row = cursor.fetchone()
        if not item_row:
            return {"success": False, "error": f"Kalem #{item_id} bulunamadı"}
        
        item = dict(item_row)
        draft_id = item["draft_order_id"]
        qty = max(1, int(item.get("quantity", 1)))
        title = item["title"].strip()
        url = item.get("url", "").strip()

        # Envanterde aynı isimli veya yakın çalışan parça var mı kontrol et
        cursor.execute("SELECT * FROM components WHERE status = 'working' AND LOWER(name) = ? LIMIT 1", (title.lower(),))
        existing = cursor.fetchone()

        now = datetime.now().isoformat()
        if existing:
            comp_id = existing["id"]
            new_qty = existing["quantity"] + qty
            cursor.execute("UPDATE components SET quantity = ?, updated_at = ? WHERE id = ?", (new_qty, now, comp_id))
            cursor.execute("""
                INSERT INTO stock_logs (component_id, change_amount, new_quantity, reason, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (comp_id, qty, new_qty, f"Taslak sipariş #{draft_id} satın alındı ve stoğa eklendi", now))
            action = "updated"
            comp_name = existing["name"]
        else:
            cat = category if (category and category in CATEGORIES) else infer_component_category(title)
            comp_notes = notes or f"Taslak sipariş #{draft_id} üzerinden satın alındı"
            cursor.execute("""
                INSERT INTO components (
                    name, category, value, package, quantity, min_quantity,
                    status, location, notes, tags, datasheet_url, created_at, updated_at
                ) VALUES (?, ?, '', '', ?, 2, 'working', ?, ?, '', ?, ?, ?)
            """, (title, cat, qty, location.strip(), comp_notes, url, now, now))
            comp_id = cursor.lastrowid
            cursor.execute("""
                INSERT INTO stock_logs (component_id, change_amount, new_quantity, reason, timestamp)
                VALUES (?, ?, ?, 'Taslak siparişten ilk stok girişi', ?)
            """, (comp_id, qty, qty, now))
            action = "created"
            comp_name = title

        # Taslak kalemini güncel tut: satın alındı ve stoğa aktarıldı
        cursor.execute("""
            UPDATE draft_order_items 
            SET is_purchased = 1, purchased_at = COALESCE(purchased_at, ?), 
                transferred_to_inventory = 1, inventory_component_id = ?
            WHERE id = ?
        """, (now, comp_id, item_id))
        conn.commit()

        return {
            "success": True,
            "action": action,
            "component_id": comp_id,
            "component_name": comp_name,
            "quantity_transferred": qty,
            "message": f"{qty} adet '{comp_name}' stoğa başarıyla eklendi (#{comp_id})"
        }


# ==========================================
# GÜVENLİK VE KİMLİK DOĞRULAMA (AUTH) FONKSİYONLARI
# ==========================================

def verify_user_credentials(username: str, password: str, db_path: str = DB_PATH) -> bool:
    """Kullanıcı adı ve şifresini doğrular."""
    if not username or not password:
        return False
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash, salt FROM users WHERE username = ?", (username.strip(),))
        row = cursor.fetchone()
        if not row:
            return False
        return verify_password(password, row["salt"], row["password_hash"])


def create_session(username: str, db_path: str = DB_PATH, days_valid: int = 30) -> str:
    """Belirtilen kullanıcı için yeni bir oturum belirteci (token) oluşturur."""
    token = secrets.token_hex(32)
    expires_at = datetime.utcnow() + timedelta(days=days_valid)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sessions (token, username, expires_at) VALUES (?, ?, ?)",
            (token, username.strip(), expires_at.isoformat())
        )
        conn.commit()
    return token


def verify_session(token: str, db_path: str = DB_PATH) -> Optional[str]:
    """Oturum token'ını kontrol eder; geçerliyse kullanıcı adını döndürür."""
    if not token or not isinstance(token, str):
        return None
    token = token.strip()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, expires_at FROM sessions WHERE token = ?", (token,))
        row = cursor.fetchone()
        if not row:
            return None
        try:
            expires_at = datetime.fromisoformat(row["expires_at"])
            if datetime.utcnow() > expires_at:
                cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
                return None
        except Exception:
            pass
        return row["username"]


def delete_session(token: str, db_path: str = DB_PATH) -> bool:
    """Oturumu sonlandırır (logout)."""
    if not token:
        return False
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE token = ?", (token.strip(),))
        conn.commit()
        return cursor.rowcount > 0


def change_user_password(username: str, old_password: str, new_password: str, db_path: str = DB_PATH) -> Tuple[bool, str]:
    """Kullanıcı şifresini değiştirir."""
    if not new_password or len(new_password) < 4:
        return False, "Yeni şifre en az 4 karakter uzunluğunda olmalıdır."

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash, salt FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            return False, "Kullanıcı bulunamadı."

        if not verify_password(old_password, row["salt"], row["password_hash"]):
            return False, "Mevcut şifreniz hatalı."

        new_hash, new_salt = hash_password(new_password)
        now = datetime.now().isoformat()
        cursor.execute(
            "UPDATE users SET password_hash = ?, salt = ?, updated_at = ? WHERE username = ?",
            (new_hash, new_salt, now, username)
        )
        conn.commit()
        return True, "Şifreniz başarıyla güncellendi."


def get_user_info(username: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Kullanıcı genel bilgilerini getirir."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, created_at, updated_at FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)


# ==========================================
# DİNAMİK DONANIM ALIAS VE BİLGİ BANKASI FONKSİYONLARI
# ==========================================

def save_learned_alias(canonical_compact: str, alias_term: str, alias_compact: str, source: str = "cross_vendor", db_path: str = DB_PATH) -> None:
    """Mağazalar arası aramada otomatik keşfedilen veya kullanıcı/AI tarafından eklenen donanım alias'ını DB'ye kaydeder."""
    if not canonical_compact or not alias_compact or canonical_compact == alias_compact:
        return
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO component_aliases (canonical_compact, alias_term, alias_compact, source) VALUES (?, ?, ?, ?)",
                (canonical_compact.lower(), alias_term.strip(), alias_compact.lower(), source)
            )
            conn.commit()
    except Exception:
        pass


def get_learned_aliases(code_compact: str, db_path: str = DB_PATH) -> List[Dict[str, str]]:
    """Verilen model kodu için veritabanında öğrenilmiş/kayıtlı alias'ları döndürür."""
    if not code_compact:
        return []
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            c = code_compact.lower()
            cursor.execute(
                "SELECT alias_term, alias_compact, canonical_compact FROM component_aliases WHERE canonical_compact = ? OR alias_compact = ?",
                (c, c)
            )
            results = []
            for r in cursor.fetchall():
                results.append(dict(r))
            return results
    except Exception:
        return []


def save_component_knowledge(
    category: str,
    part_name: str,
    features: str = "",
    pros: str = "",
    cons: str = "",
    keywords: str = "",
    summary: str = "",
    db_path: str = DB_PATH
) -> int:
    """Veritabanındaki dinamik muadil / komponent bilgi bankasına yeni bir parça veya güncelleme kaydeder."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO component_knowledge (category, keywords, summary, part_name, features, pros, cons, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(category, part_name) DO UPDATE SET
                keywords = CASE WHEN excluded.keywords != '' THEN excluded.keywords ELSE component_knowledge.keywords END,
                summary = CASE WHEN excluded.summary != '' THEN excluded.summary ELSE component_knowledge.summary END,
                features = excluded.features,
                pros = excluded.pros,
                cons = excluded.cons,
                updated_at = excluded.updated_at
        """, (category.strip(), keywords.strip(), summary.strip(), part_name.strip(), features.strip(), pros.strip(), cons.strip(), now))
        conn.commit()
        return cursor.lastrowid or 0


def get_component_knowledge_groups(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Veritabanında kayıtlı tüm komponent bilgi bankası gruplarını getirir."""
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM component_knowledge ORDER BY category ASC, id ASC")
            rows = cursor.fetchall()
            groups: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                cat = r["category"]
                if cat not in groups:
                    groups[cat] = {
                        "category": cat,
                        "keywords": [k.strip() for k in (r["keywords"] or "").split(",") if k.strip()],
                        "summary": r["summary"] or "",
                        "parts": []
                    }
                else:
                    if r["summary"] and not groups[cat]["summary"]:
                        groups[cat]["summary"] = r["summary"]
                    for k in (r["keywords"] or "").split(","):
                        if k.strip() and k.strip() not in groups[cat]["keywords"]:
                            groups[cat]["keywords"].append(k.strip())
                part_entry: Dict[str, Any] = {
                    "name": r["part_name"],
                    "features": r["features"] or ""
                }
                if r["pros"]:
                    part_entry["pros"] = r["pros"]
                if r["cons"]:
                    part_entry["cons"] = r["cons"]
                groups[cat]["parts"].append(part_entry)
            return list(groups.values())
    except Exception:
        return []


# ==========================================
# STANDART ELEKTRONİK KOMPONENT KATALOĞU (LIVESEARCH & AUTOCOMPLETE)
# ==========================================

CATEGORY_LABELS: Dict[str, str] = {
    "resistor": "Direnç",
    "capacitor": "Kondansatör",
    "diode_led": "Diyot & LED",
    "transistor": "Transistör & MOSFET",
    "ic_mcu": "Entegre & MCU",
    "sensor": "Sensör",
    "module": "Modül & Kart",
    "connector": "Konnektör & Kablo",
    "power": "Güç & Batarya",
    "passive_other": "Pasif & Diğer",
    "broken_scrap": "Arızalı / Çıkma Parça"
}

STANDARD_ELECTRONIC_CATALOG: List[Dict[str, Any]] = [
    # Transistörler & MOSFET'ler
    {"name": "2N2222A NPN Bipolar Transistör - TO-92", "category": "transistor", "package": "TO-92", "value": "NPN 40V 800mA", "aliases": ["2n2222a", "2n2222", "pn2222", "2n 2222"], "description": "Genel amaçlı NPN bipolar anahtarlama transistörü"},
    {"name": "2N3904 NPN Bipolar Transistör - TO-92", "category": "transistor", "package": "TO-92", "value": "NPN 40V 200mA", "aliases": ["2n3904", "2n 3904"], "description": "Düşük güçlü genel amaçlı NPN transistör"},
    {"name": "2N3906 PNP Bipolar Transistör - TO-92", "category": "transistor", "package": "TO-92", "value": "PNP 40V 200mA", "aliases": ["2n3906", "2n 3906"], "description": "Düşük güçlü genel amaçlı PNP transistör"},
    {"name": "2N7000 N-Kanal MOSFET - TO-92", "category": "transistor", "package": "TO-92", "value": "N-Ch 60V 200mA", "aliases": ["2n7000", "2n 7000"], "description": "Küçük sinyal N-kanal anahtarlama MOSFET'i"},
    {"name": "BC547 NPN Bipolar Transistör - TO-92", "category": "transistor", "package": "TO-92", "value": "NPN 45V 100mA", "aliases": ["bc547", "bc 547"], "description": "Genel amaçlı NPN ses ve anahtarlama transistörü"},
    {"name": "BC548 NPN Bipolar Transistör - TO-92", "category": "transistor", "package": "TO-92", "value": "NPN 30V 100mA", "aliases": ["bc548", "bc 548"], "description": "Genel amaçlı NPN transistör"},
    {"name": "BC557 PNP Bipolar Transistör - TO-92", "category": "transistor", "package": "TO-92", "value": "PNP 45V 100mA", "aliases": ["bc557", "bc 557"], "description": "Genel amaçlı PNP tamamlayıcı transistör"},
    {"name": "BD139 NPN Güç Transistörü - TO-126", "category": "transistor", "package": "TO-126", "value": "NPN 80V 1.5A", "aliases": ["bd139", "bd 139"], "description": "Orta güçte NPN ses ve sürücü transistörü"},
    {"name": "BD140 PNP Güç Transistörü - TO-126", "category": "transistor", "package": "TO-126", "value": "PNP 80V 1.5A", "aliases": ["bd140", "bd 140"], "description": "Orta güçte PNP ses ve sürücü transistörü"},
    {"name": "TIP120 NPN Darlington Güç Transistörü - TO-220", "category": "transistor", "package": "TO-220", "value": "NPN Darlington 60V 5A", "aliases": ["tip120", "tip 120"], "description": "Yüksek kazançlı Darlington motor/solenoid sürücü"},
    {"name": "IRFZ44N N-Kanal Güç MOSFET - TO-220", "category": "transistor", "package": "TO-220", "value": "N-Ch 55V 49A 17.5mΩ", "aliases": ["irfz44n", "irfz44", "irf z44n"], "description": "Yüksek akımlı düşük RDS(on) N-kanal güç MOSFET'i"},
    {"name": "IRF540N N-Kanal Güç MOSFET - TO-220", "category": "transistor", "package": "TO-220", "value": "N-Ch 100V 33A", "aliases": ["irf540n", "irf540"], "description": "100V N-kanal güç MOSFET'i"},
    {"name": "IRF9540N P-Kanal Güç MOSFET - TO-220", "category": "transistor", "package": "TO-220", "value": "P-Ch 100V 23A", "aliases": ["irf9540n", "irf9540"], "description": "Yüksek voltajlı P-kanal güç MOSFET'i"},
    {"name": "AO3400A N-Kanal SMD MOSFET - SOT-23", "category": "transistor", "package": "SOT-23", "value": "N-Ch 30V 5.7A", "aliases": ["ao3400", "ao3400a"], "description": "Kompakt SMD yüksek akımlı N-kanal MOSFET"},
    {"name": "AO3401A P-Kanal SMD MOSFET - SOT-23", "category": "transistor", "package": "SOT-23", "value": "P-Ch 30V 4A", "aliases": ["ao3401", "ao3401a"], "description": "Ters polarite koruması için ideal P-kanal SMD MOSFET"},
    {"name": "SI2302 N-Kanal SMD MOSFET - SOT-23", "category": "transistor", "package": "SOT-23", "value": "N-Ch 20V 2.8A", "aliases": ["si2302", "a2shb"], "description": "Mantık seviyesi SMD N-kanal MOSFET"},

    # Mikrodenetleyiciler & Geliştirme Kartları
    {"name": "ESP32-C3 Super Mini Geliştirme Kartı", "category": "ic_mcu", "package": "Modül", "value": "RISC-V 160MHz Wi-Fi+BLE 5.0", "aliases": ["esp32-c3", "esp32 c3", "c3 super mini", "super mini", "esp32c3"], "description": "Ultra kompakt Wi-Fi & Bluetooth 5 IoT mikrodenetleyici kartı"},
    {"name": "ESP32 DevKit V1 (ESP-WROOM-32)", "category": "ic_mcu", "package": "DIP-30 / Modül", "value": "Çift Çekirdek 240MHz Wi-Fi+BT", "aliases": ["esp32", "esp-wroom-32", "esp32 devkit", "devkit v1"], "description": "Çift çekirdekli standart IoT geliştirme kartı"},
    {"name": "NodeMCU V3 ESP8266 Wi-Fi Geliştirme Kartı", "category": "ic_mcu", "package": "DIP-30", "value": "80MHz Wi-Fi (ESP-12E)", "aliases": ["esp8266", "nodemcu", "esp12e"], "description": "Klasik Wi-Fi geliştirme kartı"},
    {"name": "Arduino Nano V3.0 (ATmega328P CH340)", "category": "ic_mcu", "package": "DIP-30", "value": "16MHz 5V AVR", "aliases": ["arduino nano", "nano v3", "nano"], "description": "Kompakt breadboard uyumlu mikrodenetleyici kartı"},
    {"name": "Arduino Pro Mini 3.3V 8MHz (ATmega328P)", "category": "ic_mcu", "package": "DIP-24", "value": "3.3V 8MHz Düşük Güç", "aliases": ["arduino pro mini", "pro mini"], "description": "Ultra düşük uyku akımı pilli projeler için Pro Mini"},
    {"name": "Arduino Uno R3 (ATmega328P DIP)", "category": "ic_mcu", "package": "Geliştirme Kartı", "value": "16MHz 5V AVR", "aliases": ["arduino uno", "uno r3", "uno"], "description": "Standart prototipleme ve eğitim kartı"},
    {"name": "STM32F103C8T6 ARM Cortex-M3 (Blue Pill)", "category": "ic_mcu", "package": "DIP-40", "value": "ARM M3 72MHz 64KB Flash", "aliases": ["stm32", "stm32f103c8t6", "bluepill", "blue pill"], "description": "32-bit ARM Cortex-M3 mikrodenetleyici kartı"},
    {"name": "Raspberry Pi Pico (RP2040 Dual ARM M0+)", "category": "ic_mcu", "package": "DIP-40", "value": "Dual M0+ 133MHz 2MB Flash", "aliases": ["pico", "rp2040", "raspberry pi pico"], "description": "Çift çekirdekli esnek I/O mikrodenetleyici kartı"},
    {"name": "ATmega328P-PU 8-Bit Mikrodenetleyici - DIP-28", "category": "ic_mcu", "package": "DIP-28", "value": "20MHz 32KB Flash", "aliases": ["atmega328p", "atmega328", "atmega 328p"], "description": "Arduino çekirdeği standalone entegresi"},
    {"name": "ATTiny85-20PU 8-Bit Mikrodenetleyici - DIP-8", "category": "ic_mcu", "package": "DIP-8", "value": "20MHz 8KB Flash", "aliases": ["attiny85", "attiny 85", "attiny"], "description": "Küçük 8 pinli AVR mikrodenetleyici"},

    # Entegre Devreler (IC)
    {"name": "NE555P Zamanlayıcı / Timer Entegresi - DIP-8", "category": "ic_mcu", "package": "DIP-8", "value": "Zamanlayıcı / PWM", "aliases": ["ne555", "555 timer", "ne555p", "555"], "description": "Hassas osilatör, PWM ve zamanlama entegresi"},
    {"name": "LM358P Çift Op-Amp Entegresi - DIP-8", "category": "ic_mcu", "package": "DIP-8", "value": "Dual Op-Amp 3V-32V", "aliases": ["lm358", "lm358p", "lm 358"], "description": "Tek kaynaklı düşük güçlü çift operasyonel yükselteç"},
    {"name": "LM324N Dörtlü Op-Amp Entegresi - DIP-14", "category": "ic_mcu", "package": "DIP-14", "value": "Quad Op-Amp", "aliases": ["lm324", "lm324n", "lm 324"], "description": "Dörtlü genel amaçlı op-amp"},
    {"name": "LM393P Çift Voltaj Komparatör - DIP-8", "category": "ic_mcu", "package": "DIP-8", "value": "Dual Comparator", "aliases": ["lm393", "lm393p", "lm 393"], "description": "Çift kanallı açık kolektör voltaj karşılaştırıcı"},
    {"name": "LM386N-1 Düşük Voltaj Ses Amplifikatörü - DIP-8", "category": "ic_mcu", "package": "DIP-8", "value": "0.3W - 1W Ses Amfisi", "aliases": ["lm386", "lm386n", "lm 386"], "description": "Pille çalışan düşük voltaj ses amplifikatörü"},
    {"name": "74HC595 8-Bit Seri Giriş Paralel Çıkış Kaydırma Yazmacı - DIP-16", "category": "ic_mcu", "package": "DIP-16", "value": "Shift Register", "aliases": ["74hc595", "595"], "description": "Pin çoğullama için 8-bit seri shift register"},
    {"name": "CD4017BE Ondalık Sayıcı / Johnson Counter - DIP-16", "category": "ic_mcu", "package": "DIP-16", "value": "Decade Counter", "aliases": ["cd4017", "4017"], "description": "10 çıkışlı Johnson yürüyen ışık / sayaç entegresi"},
    {"name": "PC817 Optokuplör / Optoizolatör - DIP-4", "category": "ic_mcu", "package": "DIP-4", "value": "Optocoupler 5kV", "aliases": ["pc817", "el817", "optokuplor"], "description": "Giriş-çıkış elektriksel izolasyonu için optokuplör"},
    {"name": "CH340G USB - TTL Seri Dönüştürücü Entegre - SOP-16", "category": "ic_mcu", "package": "SOP-16", "value": "USB-UART Köprüsü", "aliases": ["ch340g", "ch340"], "description": "USB seri iletişim köprü çipi"},
    {"name": "CP2102 USB - TTL Seri UART Modülü", "category": "module", "package": "Modül", "value": "USB 2.0 to UART", "aliases": ["cp2102"], "description": "Kararlı USB seri programlayıcı modülü"},
    {"name": "L298N Çift Motor Sürücü Modülü", "category": "module", "package": "Modül", "value": "Çift H-Köprüsü 2A", "aliases": ["l298n", "l298"], "description": "Çift DC motor veya step motor sürücü kartı"},
    {"name": "ULN2003A 7-Kanal Darlington Transistör Dizisi - DIP-16", "category": "ic_mcu", "package": "DIP-16", "value": "500mA 50V Darlington", "aliases": ["uln2003", "uln2003a"], "description": "Röle ve step motor sürücü entegresi"},

    # Sensörler & Konumlandırma
    {"name": "DHT11 Sıcaklık ve Nem Sensörü Modülü", "category": "sensor", "package": "4 Pin / Modül", "value": "0-50°C %20-90 RH", "aliases": ["dht11", "dht 11"], "description": "Temel ortam sıcaklık ve bağıl nem sensörü"},
    {"name": "DHT22 / AM2302 Hassas Sıcaklık ve Nem Sensörü", "category": "sensor", "package": "4 Pin", "value": "-40-80°C %0-100 RH", "aliases": ["dht22", "am2302", "dht 22"], "description": "Yüksek hassasiyetli dijital nem ve sıcaklık sensörü"},
    {"name": "DS18B20 1-Wire Dijital Sıcaklık Sensörü - TO-92", "category": "sensor", "package": "TO-92", "value": "-55°C ile +125°C", "aliases": ["ds18b20", "18b20", "ds 18b20"], "description": "Tek hatlı (1-Wire) hassas dijital sıcaklık sensörü"},
    {"name": "BME280 Sıcaklık, Nem ve Barometrik Basınç Sensörü (I2C)", "category": "sensor", "package": "Modül", "value": "I2C/SPI 3.3V", "aliases": ["bme280", "bme 280"], "description": "Bosch yüksek hassasiyetli çevre sensörü"},
    {"name": "BMP280 Barometrik Basınç ve Yükseklik Sensörü (I2C)", "category": "sensor", "package": "Modül", "value": "I2C 3.3V", "aliases": ["bmp280", "bmp 280"], "description": "Hassas atmosferik basınç ve altimetre sensörü"},
    {"name": "GY-521 MPU-6050 6 Eksen İvme ve Jiroskop Sensörü", "category": "sensor", "package": "Modül", "value": "6 DOF I2C", "aliases": ["mpu6050", "mpu-6050", "gy-521", "gy521"], "description": "3 eksen ivmeölçer + 3 eksen jiroskop hareket sensörü"},
    {"name": "ST LIS3DH 3 Eksen Düşük Güçlü İvmeölçer Modülü", "category": "sensor", "package": "Modül", "value": "Wake-on-motion 2µA", "aliases": ["lis3dh", "lis 3dh"], "description": "Pilli projeler için ultra düşük akımlı hareket uyandırma sensörü"},
    {"name": "HC-SR04 Ultrasonik Mesafe Sensörü", "category": "sensor", "package": "Modül", "value": "2cm - 400cm 5V", "aliases": ["hc-sr04", "hcsr04", "mesafe sensoru"], "description": "Ses dalgasıyla temassız mesafe ölçüm sensörü"},
    {"name": "HC-SR501 PIR Hareket Sensörü Modülü", "category": "sensor", "package": "Modül", "value": "PIR Kızılötesi 5V-20V", "aliases": ["hc-sr501", "hcsr501", "pir sensor"], "description": "Pasif kızılötesi vücut hareket sensörü"},
    {"name": "GY-NEO6MV2 GPS Modülü (u-blox NEO-6M Antenli)", "category": "sensor", "package": "Modül + Anten", "value": "UART 9600bps 3.3V-5V", "aliases": ["neo-6m", "neo6m", "gy-neo6mv2", "gyneo6mv2", "gps modulu"], "description": "u-blox NEO-6M tabanlı seramik antenli GPS modülü"},
    {"name": "ATGM336H GPS+BDS Çift Modlu Düşük Güçlü GNSS Modülü", "category": "sensor", "package": "Modül + Anten", "value": "25mA NEO-6M Muadili", "aliases": ["atgm336h", "atgm336"], "description": "Hızlı fix alan ve yarı yarıya az akım tüketen GPS modülü"},
    {"name": "MAX30102 Kalp Atış Hızı ve Nabız Oksimetresi Sensörü", "category": "sensor", "package": "Modül", "value": "I2C Nabız / SpO2", "aliases": ["max30102", "nabiz sensoru"], "description": "Optik kalp atışı ve kanda oksijen (SpO2) sensörü"},
    {"name": "BH1750FVI Dijital Işık Şiddeti (Lüks) Sensörü", "category": "sensor", "package": "Modül", "value": "I2C 1-65535 lx", "aliases": ["bh1750", "isik sensoru"], "description": "16-bit hassas ortam ışığı (lux) ölçüm sensörü"},
    {"name": "TowerPro SG90 9g Mini Servo Motor", "category": "module", "package": "Micro Servo", "value": "1.8 kg/cm 4.8V-6V", "aliases": ["sg90", "servo motor", "9g servo"], "description": "Robotik projeler için standart mini servo motor"},
    {"name": "MG996R Metal Dişli Yüksek Torklu Standart Servo Motor", "category": "module", "package": "Standart Servo", "value": "11 kg/cm Metal Dişli", "aliases": ["mg996r", "mg996"], "description": "Yüksek dayanımlı metal dişli güç servosu"},

    # Güç, Batarya & Şarj Modülleri
    {"name": "TP4056 1S 3.7V Type-C Lityum Batarya Şarj Modülü (Korumalı)", "category": "module", "package": "Modül", "value": "1A Type-C BMS Korumalı", "aliases": ["tp4056", "lipo sarj", "1s sarj"], "description": "DW01A + 8205A korumalı 1A Type-C Li-ion şarj devresi"},
    {"name": "LM2596 DC-DC Ayarlanabilir Step-Down Voltaj Düşürücü Modül", "category": "module", "package": "Modül", "value": "4V-40V Giriş, 3A Çıkış", "aliases": ["lm2596", "step down", "buck converter"], "description": "Yüksek verimli regüle voltaj düşürücü modül"},
    {"name": "MT3608 2A DC-DC Ayarlanabilir Step-Up Voltaj Yükseltici Modül", "category": "module", "package": "Modül", "value": "2V-24V Giriş, 2A Çıkış", "aliases": ["mt3608", "step up", "boost converter"], "description": "Küçük boyutlu voltaj yükseltici devre"},
    {"name": "AMS1117-3.3V SMD LDO Voltaj Regülatörü - SOT-223", "category": "power", "package": "SOT-223", "value": "3.3V 1A LDO", "aliases": ["ams1117-3.3", "ams1117 3.3v", "ams1117"], "description": "Yaygın 3.3V lineer voltaj regülatörü"},
    {"name": "AMS1117-5.0V SMD LDO Voltaj Regülatörü - SOT-223", "category": "power", "package": "SOT-223", "value": "5.0V 1A LDO", "aliases": ["ams1117-5.0", "ams1117 5v"], "description": "5.0V lineer voltaj regülatörü"},
    {"name": "L7805CV 5V 1.5A Pozitif Lineer Voltaj Regülatörü - TO-220", "category": "power", "package": "TO-220", "value": "5V 1.5A", "aliases": ["7805", "l7805", "7805 regülatör"], "description": "Klasik 5V lineer voltaj regülatörü"},
    {"name": "L7812CV 12V 1.5A Pozitif Lineer Voltaj Regülatörü - TO-220", "category": "power", "package": "TO-220", "value": "12V 1.5A", "aliases": ["7812", "l7812"], "description": "12V lineer voltaj regülatörü"},
    {"name": "LM317T Ayarlanabilir Lineer Voltaj Regülatörü - TO-220", "category": "power", "package": "TO-220", "value": "1.25V-37V 1.5A", "aliases": ["lm317", "lm317t"], "description": "Dirençle ayarlanabilir 1.5A voltaj regülatörü"},
    {"name": "18650 3.7V Li-ion Şarj Edilebilir Pil Hücresi", "category": "power", "package": "18650 Silindirik", "value": "3.7V 2600mAh", "aliases": ["18650", "18650 pil", "li-ion pil"], "description": "Standart yüksek kapasiteli lityum iyon silindirik pil"},
    {"name": "3.7V 1S 1000mAh Lityum Polimer (LiPo) Batarya", "category": "power", "package": "LiPo Paket", "value": "3.7V 1S 1000mAh", "aliases": ["1s lipo", "1000mah lipo", "lipo batarya", "1s batarya"], "description": "Kompakt boyutlu 3.7V 1S lityum polimer batarya"},

    # Diyotlar & LED'ler
    {"name": "1N4001 Doğrultucu Diyot 50V 1A - DO-41", "category": "diode_led", "package": "DO-41", "value": "50V 1A", "aliases": ["1n4001", "1n 4001"], "description": "Standart silisyum doğrultucu diyot"},
    {"name": "1N4007 Doğrultucu Diyot 1000V 1A - DO-41", "category": "diode_led", "package": "DO-41", "value": "1000V 1A", "aliases": ["1n4007", "1n 4007"], "description": "Yüksek voltaj doğrultucu diyot"},
    {"name": "1N4148 Hızlı Anahtarlama Diyotu - DO-35", "category": "diode_led", "package": "DO-35", "value": "100V 200mA 4ns", "aliases": ["1n4148", "1n 4148"], "description": "Küçük sinyal yüksek hızlı anahtarlama diyotu"},
    {"name": "1N5819 Schottky Doğrultucu Diyot 40V 1A - DO-41", "category": "diode_led", "package": "DO-41", "value": "Schottky 40V 1A", "aliases": ["1n5819", "1n 5819"], "description": "Düşük ileri voltaj düşümlü Schottky diyot"},
    {"name": "SS14 SMD Schottky Diyot 40V 1A - SMA", "category": "diode_led", "package": "SMA / DO-214AC", "value": "Schottky 40V 1A", "aliases": ["ss14", "1n5819 smd"], "description": "Yüzey montaj Schottky doğrultucu"},
    {"name": "SS34 SMD Schottky Diyot 40V 3A - SMC", "category": "diode_led", "package": "SMC / DO-214AB", "value": "Schottky 40V 3A", "aliases": ["ss34", "1n5822 smd"], "description": "3A yüksek akımlı SMD Schottky diyot"},
    {"name": "5mm Kırmızı Difüz LED", "category": "diode_led", "package": "5mm DIP", "value": "2.0V 20mA", "aliases": ["kirmizi led", "red led", "5mm led"], "description": "Standart gösterge ve sinyal ledi"},
    {"name": "5mm Yeşil Difüz LED", "category": "diode_led", "package": "5mm DIP", "value": "2.2V 20mA", "aliases": ["yesil led", "green led", "5mm led"], "description": "Standart yeşil durum ledi"},
    {"name": "WS2812B Adreslenebilir RGB LED (Neopixel)", "category": "diode_led", "package": "SMD 5050 / Modül", "value": "5V RGB Adresli", "aliases": ["ws2812b", "neopixel", "ws2812"], "description": "Dahili sürücülü dijital tek hattan kontrol edilen RGB LED"},

    # Konnektör & Prototipleme
    {"name": "1x8 Pin 2.54mm Tek Sıra Dişi Header Konnektör", "category": "connector", "package": "1x8 2.54mm", "value": "2.54mm Pitch", "aliases": ["1x8 disi header", "1x8 dişi header", "8 pin disi header", "disi header", "dişi header"], "description": "Arduino ve modül soketleri için dişi pin başlığı"},
    {"name": "1x40 Pin 2.54mm Tek Sıra Kırılabilir Erkek Header", "category": "connector", "package": "1x40 2.54mm", "value": "2.54mm Pitch", "aliases": ["1x40 erkek header", "erkek header", "header", "pin header"], "description": "Standart 40 pin kırılabilir erkek pin başlığı"},
    {"name": "JST-PH 2.0mm 2-Pin Erkek Konnektör & Kablolu Soket", "category": "connector", "package": "2-Pin 2.0mm", "value": "2.0mm Adım", "aliases": ["jst-ph 2 pin", "jst 2 pin", "jst-ph", "jst"], "description": "LiPo bataryalar için standart kutuplu 2 pin konnektör"},
    {"name": "5x7 cm Tek Taraflı Bakırlı Delikli Pertinaks Plaket", "category": "passive_other", "package": "5x7 cm Plaket", "value": "2.54mm Prototip PCB", "aliases": ["pertinaks", "delikli pertinaks", "delikli plaket", "plaket", "prototip pcb"], "description": "Devre lehimleme ve prototipleme plaketi"},

    # Temel Dirençler & Kondansatörler
    {"name": "10kΩ 1/4W %1 Metal Film Direnç", "category": "resistor", "package": "Axial / THT", "value": "10kΩ 0.25W", "aliases": ["10k", "10k direnc", "10k ohm", "10kohm"], "description": "Pull-up ve pull-down hatları için standart direnç"},
    {"name": "1kΩ 1/4W %1 Metal Film Direnç", "category": "resistor", "package": "Axial / THT", "value": "1kΩ 0.25W", "aliases": ["1k", "1k direnc", "1k ohm", "1kohm"], "description": "Transistör tetikleme ve sinyal direnci"},
    {"name": "220Ω 1/4W %1 Metal Film Direnç", "category": "resistor", "package": "Axial / THT", "value": "220Ω 0.25W", "aliases": ["220r", "220 ohm", "220 direnc"], "description": "LED akım sınırlama için 5V direnci"},
    {"name": "330Ω 1/4W %1 Metal Film Direnç", "category": "resistor", "package": "Axial / THT", "value": "330Ω 0.25W", "aliases": ["330r", "330 ohm", "330 direnc"], "description": "LED ve sinyal akım sınırlama direnci"},
    {"name": "4.7kΩ 1/4W %1 Metal Film Direnç", "category": "resistor", "package": "Axial / THT", "value": "4.7kΩ 0.25W", "aliases": ["4.7k", "4k7", "4.7k direnc"], "description": "I2C ve 1-Wire veri hattı pull-up direnci"},
    {"name": "100kΩ 1/4W %1 Metal Film Direnç", "category": "resistor", "package": "Axial / THT", "value": "100kΩ 0.25W", "aliases": ["100k", "100k direnc", "100k ohm"], "description": "Yüksek empedanslı pull-down ve gerilim bölücü direnç"},
    {"name": "100nF (0.1µF) 50V Çok Katmanlı Seramik Kondansatör", "category": "capacitor", "package": "Radial / DIP", "value": "100nF 50V (104)", "aliases": ["100nf", "0.1uf", "100nf kondansator", "104"], "description": "IC besleme gürültü filtreleme dekuplaj kondansatörü"},
    {"name": "10µF 50V Alüminyum Elektrolitik Kondansatör", "category": "capacitor", "package": "Radial DIP", "value": "10µF 50V", "aliases": ["10uf", "10uf kondansator"], "description": "Besleme regülatörü giriş/çıkış filtre kondansatörü"},
    {"name": "100µF 25V Alüminyum Elektrolitik Kondansatör", "category": "capacitor", "package": "Radial DIP", "value": "100µF 25V", "aliases": ["100uf", "100uf kondansator"], "description": "Güç hattı bulk filtre kondansatörü"},
    {"name": "22pF 50V Seramik Disk Kondansatör", "category": "capacitor", "package": "Radial DIP", "value": "22pF 50V (22)", "aliases": ["22pf", "22pf kondansator"], "description": "Kristal osilatör yük kondansatörü"}
]


def get_component_suggestions(query: str, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Parça adı giriş kutusuna yazılırken (LiveSearch) hem yerel envanterdeki
    eşleşmeleri (mükerrer kayıt önleme) hem de standart katalog önerilerini
    (otomatik form doldurma) döndürür.
    """
    clean_q = (query or "").strip()
    if len(clean_q) < 2:
        return {"query": clean_q, "inventory_matches": [], "catalog_suggestions": []}

    from component_matcher import normalize_tr, normalize_compact

    q_tr = normalize_tr(clean_q)
    q_compact = normalize_compact(clean_q)
    q_tokens = [t for t in re.split(r'[\s\-_/(),;]+', q_tr) if t]

    # 1. YEREL ENVANTERDEKİ MEVCUT PARÇALARI ARA
    inventory_matches = []
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, category, value, package, quantity, min_quantity, status, location, notes FROM components ORDER BY name ASC")
            all_comps = [dict(r) for r in cursor.fetchall()]

            for c in all_comps:
                c_name = c["name"] or ""
                c_tr = normalize_tr(c_name)
                c_compact = normalize_compact(c_name)
                c_val = normalize_tr(c.get("value") or "")
                c_pkg = normalize_tr(c.get("package") or "")

                is_match = False
                match_score = 0.0

                if q_compact and (q_compact in c_compact or c_compact in q_compact):
                    is_match = True
                    match_score = 1.0
                elif q_tokens and all(tok in c_tr or tok in c_val or tok in c_pkg for tok in q_tokens):
                    is_match = True
                    match_score = 0.9
                elif any(tok in c_tr for tok in q_tokens if len(tok) >= 3):
                    is_match = True
                    match_score = 0.6

                if is_match:
                    cat_key = c.get("category", "")
                    c["category_label"] = CATEGORY_LABELS.get(cat_key, cat_key.capitalize())
                    c["match_score"] = match_score
                    c["is_inventory"] = True
                    inventory_matches.append(c)

            inventory_matches.sort(key=lambda x: (-x["match_score"], x["name"]))
    except Exception:
        inventory_matches = []

    # 2. STANDART ELEKTRONİK KATALOĞUNDAN ÖNERİLER ÇEK
    catalog_suggestions = []
    for item in STANDARD_ELECTRONIC_CATALOG:
        item_name = item["name"]
        item_tr = normalize_tr(item_name)
        item_compact = normalize_compact(item_name)
        aliases = [normalize_compact(a) for a in item.get("aliases", [])]

        is_cat_match = False
        cat_score = 0.0

        if q_compact in item_compact or any(q_compact in a or a in q_compact for a in aliases if len(a) >= 2):
            is_cat_match = True
            cat_score = 1.0
        elif q_tokens and all(tok in item_tr or any(tok in a for a in aliases) for tok in q_tokens):
            is_cat_match = True
            cat_score = 0.95
        elif any(tok in item_tr or any(tok in a for a in aliases) for tok in q_tokens if len(tok) >= 3):
            is_cat_match = True
            cat_score = 0.7

        if is_cat_match:
            cat_key = item.get("category", "")
            catalog_suggestions.append({
                "name": item["name"],
                "category": cat_key,
                "category_label": CATEGORY_LABELS.get(cat_key, cat_key.capitalize()),
                "package": item.get("package", ""),
                "value": item.get("value", ""),
                "description": item.get("description", ""),
                "score": cat_score,
                "source": "catalog",
                "is_inventory": False
            })

    catalog_suggestions.sort(key=lambda x: (-x["score"], x["name"]))

    return {
        "query": clean_q,
        "inventory_matches": inventory_matches[:8],
        "catalog_suggestions": catalog_suggestions[:10]
    }





