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
        try:
            cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('components', 'stock_logs', 'projects', 'project_components', 'cart_items')")
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

