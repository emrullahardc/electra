"""
ElectroStock - Elektronik Parça ve Stok Takip Veritabanı Modülü
SQLite tabanlı, elektronik bileşenlere özel alanlar (değer, kılıf/paket, durum, saklama lokasyonu, arıza notu).
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = "electro_stock.db"

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
                FOREIGN KEY (draft_order_id) REFERENCES draft_orders(id) ON DELETE CASCADE
            )
        """)

        # Arama ve hız için indeksler
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comp_name ON components(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comp_category ON components(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comp_status ON components(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comp_location ON components(location)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comp_value ON components(value)")

        conn.commit()


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
    """Gelişmiş filtreleme ve arama."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        conditions = []
        params = []

        if query:
            q = f"%{query.strip()}%"
            conditions.append("(name LIKE ? OR value LIKE ? OR package LIKE ? OR notes LIKE ? OR tags LIKE ?)")
            params.extend([q, q, q, q, q])

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
        sql += " ORDER BY status ASC, name ASC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


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

        # Saklama lokasyonları listesi
        cursor.execute("SELECT DISTINCT location FROM components WHERE location != '' ORDER BY location")
        locations = [r["location"] for r in cursor.fetchall()]

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
            "locations": locations
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
            """, (product_id, title, price, price_value or 0.0, url, quantity))
            conn.commit()
            return cursor.lastrowid


def get_cart_items(db_path: str = DB_PATH) -> Dict[str, Any]:
    """Sepetteki tüm ürünleri ve toplam tutarı döndürür."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cart_items ORDER BY created_at DESC")
        items = [dict(r) for r in cursor.fetchall()]
        
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
                pv = it.get("price_value") or 0.0
                qty = it.get("quantity", 1)
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
                    it.get("price_value") or 0.0,
                    int(it.get("quantity", 1)),
                    1 if it.get("in_stock", True) else 0,
                    it.get("source", "robotistan"),
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
        
        # Her siparişin kalem sayısını ekle
        for o in orders:
            cursor.execute("SELECT COUNT(*) as item_count, SUM(quantity) as total_qty FROM draft_order_items WHERE draft_order_id = ?", (o["id"],))
            agg = cursor.fetchone()
            o["item_count"] = agg["item_count"] or 0
            o["total_quantity"] = agg["total_qty"] or 0

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
        cursor.execute("SELECT * FROM draft_order_items WHERE draft_order_id = ? ORDER BY id ASC", (draft_id,))
        items = [dict(r) for r in cursor.fetchall()]
        order["items"] = items
        order["item_count"] = len(items)
        order["total_quantity"] = sum(it["quantity"] for it in items)
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
            item.get("price_value") or 0.0,
            int(item.get("quantity", 1)),
            1 if item.get("in_stock", True) else 0,
            item.get("source", "robotistan"),
            item.get("matched_inventory_id"),
            item.get("notes", "").strip()
        ))
        item_id = cursor.lastrowid

        # Taslak siparişin toplam tutarını ve updated_at tarihini güncelle
        cursor.execute("""
            UPDATE draft_orders 
            SET total_estimated_price = (
                SELECT SUM(price_value * quantity) FROM draft_order_items WHERE draft_order_id = ?
            ), updated_at = ?
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


