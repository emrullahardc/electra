# ⚡ Electra (ElectroStock) — Project State & AI System Guide

> **Generated / Updated:** 2026-10-17  
> **Repository:** `https://github.com/emrullahardc/electra` (branch: `main`)  
> **Live Production:** `https://electra.matelab.dev` (Internal: `http://ms:8085`)  
> **Primary Purpose:** Smart electronic workshop component inventory, AI Model Context Protocol (MCP) server, multi-vendor Turkish market price scraper, BOM project planning, and purchase-to-stock lifecycle manager.

---

## 1. System Architecture & Tech Stack

```
                              ┌───────────────────────────────────────────────┐
                              │  AI Assistants (Cursor, Claude, Antigravity)  │
                              └──────────────────────┬────────────────────────┘
                                                     │ JSON-RPC 2.0 (stdio)
                                                     ▼
                                          ┌──────────────────────┐
                                          │    mcp_server.py     │
                                          └──────────┬───────────┘
                                                     │
┌───────────────────────────────┐                    │
│   Web Browser Client (SPA)    │                    │
│   Tailwind + FontAwesome JS   │                    │
└──────────────┬────────────────┘                    │
               │ HTTP / JSON REST API                │
               ▼                                     ▼
┌───────────────────────────────┐         ┌──────────────────────┐
│          web_app.py           │────────▶│    electro_db.py     │
│   (Python http.server, 8085)  │         │   (SQLite Engine)    │
└──────────────┬────────────────┘         └──────────┬───────────┘
               │                                     │
               ▼                                     ▼
┌───────────────────────────────┐         ┌──────────────────────┐
│       market_scraper.py       │         │   electro_stock.db   │
│  (Robotistan, Robotronik,     │         │   (10 Core Tables)   │
│   Direnc.net, Motorobit)      │         └──────────────────────┘
└──────────────┬────────────────┘
               ▼
┌───────────────────────────────┐
│     component_matcher.py      │
│  (Spec Parsing & Ranking)     │
└───────────────────────────────┘
```

### Core Technology Stack
- **Backend:** Pure Python 3 (3.10+) with zero heavy external frameworks (`http.server`, `sqlite3`, `urllib.request`, `json`, `hashlib`).
- **Scrapers:** Lightweight HTML/JSON parsers with regex and semantic tokenization (`market_scraper.py`, `robotistan_scraper.py`).
- **Protocol:** Model Context Protocol (MCP) v1 over `stdio` (`mcp_server.py`).
- **Database:** SQLite3 (`electro_stock.db`) with automatic schema migration, indexes, and WAL journal mode.
- **Frontend:** Apple Dark Theme Single Page App (`static/index.html`, `static/app.js`), Tailwind CSS (CDN), FontAwesome (CDN), zero Node.js/npm dependencies.
- **Production Server:** Ubuntu Linux (`ssh ms`), PM2 process manager, Nginx reverse proxy with SSL termination.

---

## 2. Directory & Module Blueprint

| File Path | Lines | Primary Responsibility |
|---|---|---|
| [`web_app.py`](file:///Users/emrullahardic/Documents/antigravity/nifty-tesla/web_app.py) | ~720 | Standalone HTTP REST server on port 8085, Basic Auth (`admin:alp236330`), session auth, endpoint routing. |
| [`electro_db.py`](file:///Users/emrullahardic/Documents/antigravity/nifty-tesla/electro_db.py) | ~1,520 | SQLite schema creation, CRUD operations, auto-migrations, 120+ standard catalog definitions (`STANDARD_ELECTRONIC_CATALOG`), suggest API. |
| [`mcp_server.py`](file:///Users/emrullahardic/Documents/antigravity/nifty-tesla/mcp_server.py) | ~1,600 | 10+ MCP tools for AI agents (BOM planning, market search, inventory checks, stock adjustments, cart/draft sync). |
| [`component_matcher.py`](file:///Users/emrullahardic/Documents/antigravity/nifty-tesla/component_matcher.py) | ~800 | Parametric spec parsing (`ComponentSpec`), packaging/footprint detection, bare IC vs module breakout distinction, normalization (`normalize_compact`). |
| [`market_scraper.py`](file:///Users/emrullahardic/Documents/antigravity/nifty-tesla/market_scraper.py) | ~1,100 | Multi-vendor price scraper (Robotistan, Robotronik, Direnc.net, Motorobit), KDV normalization, shipping-aware decision logic. |
| [`robotistan_scraper.py`](file:///Users/emrullahardic/Documents/antigravity/nifty-tesla/robotistan_scraper.py) | ~300 | Robotistan dedicated product search, pagination, technical detail scraper, T-Soft multiCart API integration. |
| [`component_equivalents.py`](file:///Users/emrullahardic/Documents/antigravity/nifty-tesla/component_equivalents.py) | ~300 | 11 core categories of pin-compatible and functional substitutes (LDOs, Op-Amps, MOSFETs, BJTs, MCUs, Battery Chargers, IMUs). |
| [`project_matcher.py`](file:///Users/emrullahardic/Documents/antigravity/nifty-tesla/project_matcher.py) | ~350 | Project BOM analysis: matches user requirements against local stock, warns on defective parts, queries market for missing items. |
| [`static/index.html`](file:///Users/emrullahardic/Documents/antigravity/nifty-tesla/static/index.html) | ~1,140 | Apple dark aesthetic UI layout with modals (component add/edit, quick-stock-add card, password change, login overlay). |
| [`static/app.js`](file:///Users/emrullahardic/Documents/antigravity/nifty-tesla/static/app.js) | ~2,390 | Vanilla JS SPA controller: tab switching, LiveSearch auto-suggest, inline table quantity editing, draft orders lifecycle, cart sync. |

---

## 3. Database Schema (`electro_stock.db`)

### Key Tables & Relationships

1. **`components`**: Local workshop physical stock.
   - `id` (INTEGER PRIMARY KEY)
   - `name` (TEXT): Full part name (e.g. `2N2222A NPN BJT Transistör`).
   - `category` (TEXT): `resistor`, `capacitor`, `diode_led`, `transistor`, `ic_mcu`, `sensor`, `module`, `connector`, `power`, `passive_other`, `broken_scrap`.
   - `value` (TEXT): Electrical value (e.g. `10kΩ`, `100nF`, `3.3V`, `800mA`).
   - `package` (TEXT): Footprint/package (e.g. `TO-92`, `DIP-8`, `0805`, `SOT-23`).
   - `quantity` (INTEGER): Current quantity in stock.
   - `min_quantity` (INTEGER): Threshold trigger for low stock alert.
   - `status` (TEXT): `working` (sağlam), `defective` (arızalı), `untested` (test bekliyor), `salvage` (çıkma/hurda).
   - `location` (TEXT): Drawer/organizer box (e.g. `Çekmece A-2`, `Direnç Kutusu 1`).
   - `notes` (TEXT): Diagnostic notes, defective subsystem status (e.g. `Regülatör yanık ama MCU sağlam`).
   - `tags`, `datasheet_url`, `created_at`, `updated_at`.

2. **`stock_logs`**: Full audit trail of all stock increments/decrements.
   - `id`, `component_id`, `change_amount`, `new_quantity`, `reason`, `created_at`.

3. **`draft_orders` & `draft_order_items`**: AI/User purchase plan staging.
   - `draft_orders`: `id`, `title`, `description`, `status` (`draft`, `ready`, `ordered`, `archived`), `total_estimated_price`, `notes`.
   - `draft_order_items`:
     - `draft_order_id` (FK -> `draft_orders.id`)
     - `title`, `product_id`, `url`, `price`, `price_value`, `quantity`, `in_stock`, `source`.
     - `is_purchased` (INTEGER, 0 or 1): Track whether physical item has been bought.
     - `purchased_at` (TIMESTAMP): Purchase timestamp.
     - `transferred_to_inventory` (INTEGER, 0 or 1): Prevents double-stocking.
     - `inventory_component_id` (INTEGER FK -> `components.id`): Auto-linked local stock ID.

4. **`cart_items`**: Transient shopping cart before bulk export to Robotistan.
   - `id`, `product_id`, `title`, `price`, `price_value`, `url`, `quantity`, `created_at`.

5. **`component_aliases` & `component_knowledge`**: Dynamic learning & equivalents.
   - Prevents hardcoded lookup tables in code. Stores canonical keys and discovered marketplace aliases.

6. **`users` & `sessions`**: Security authentication.
   - PBKDF2-HMAC-SHA256 password hashing with unique random salts.
   - 30-day bearer session tokens in `localStorage`.

---

## 4. Key Workflows & Business Logic

### A. LiveSearch & Quick-Stock Add (Component Form)
- When typing into "Parça Adı" (`#form-name`):
  1. Instant (0ms) memory scan of `allComponentsCache` using normalized compact strings (`normalize_compact`: strips spaces, hyphens, punctuation).
  2. 150ms debounced call to `/api/components/suggest?q=...`.
- If an **existing inventory item** is selected:
  - Form switches automatically to `#modal-quick-stock` view.
  - Shows existing quantity and storage location.
  - Asks directly: *"Bu parçadan kaç adet eklemek istiyorsunuz?"* with focused input.
  - Includes **`[↩ Geri Dön / Yanlış Seçim]`** button which restores user's typed input without losing context.
  - Includes *"Ayrı Parça Olarak Ekle"* and *"Tüm Alanları Düzenle"* options.
- If a **standard catalog template** is selected:
  - Auto-fills canonical name, category, package, and electrical value.
  - Automatically moves cursor focus to `#form-quantity`.

### B. Direct Inline Stock Quantity Editing
- All table quantity columns (Inventory table, Cart table, Draft Orders table) feature:
  - Minus button (`-`), Number Input (`<input type="number">`), Plus button (`+`).
  - Clicking the number automatically highlights it (`onfocus="this.select()"`).
  - Users can type numbers like `50` or `100` and press `Enter` or click outside (`blur`).
  - Sends direct `PUT /api/components/<id>` or `POST /adjust` to update SQLite and log the audit entry.

### C. Multi-Vendor Market Search & Price Comparison
- Scrapes 4 major Turkish vendors: **Robotistan**, **Robotronik**, **Direnc.net**, **Motorobit**.
- **Motorobit Protection:** Explicitly rejects `-en` subdomains to prevent corrupted currency exchange rates.
- **Spec & Role Distinction:** Separates bare ICs from breakout boards (e.g. SOP-8 TP4056 chip at 8 TL vs. TP4056 charging module with protection at 14 TL).
- **Pack Multipliers:** Detects pack quantities like "10'lu", "5 Adet" to calculate accurate per-unit costs.
- **Same-Day Shipping Consolidation Rule:** If Robotistan is within 100 TL of the cheapest competitor, Robotistan is recommended to save on split cargo fees and delivery delays.

### D. Draft Orders Purchase Tracking & Inventory Transfer
- Items in drafts can be flagged as **"Satın Aldım"** (`is_purchased = 1`).
- Once marked, they move to the "Satın Alınanlar" section with a **"Stoğa Aktar"** action.
- "Stoğa Aktar" checks if the component already exists in `components` (incrementing stock) or creates a new component entry, setting `transferred_to_inventory = 1` and recording `inventory_component_id`.

---

## 5. Production Deployment Notes (`ms`)

### Server Details
- **SSH Target:** `ssh ms`
- **Application Directory:** `/var/www/electra`
- **PM2 Process Name:** `electra` (Process ID: `3`)
- **Internal Port:** `8085` (Binds to `0.0.0.0:8085`)
- **Public Domain:** `https://electra.matelab.dev`
- **Nginx Config:** Proxies `https://electra.matelab.dev` -> `http://127.0.0.1:8085`

### Authentication Credentials
- **HTTP Basic Auth & Web Login:**
  - **Username:** `admin`
  - **Password:** `alp236330`

### One-Line Deploy Command
```bash
git add . && git commit -m "feat/fix: description" && git push origin main && ssh ms "cd /var/www/electra && git pull origin main && pm2 restart electra"
```

### Health Check & API Verification
```bash
# Check stats
ssh ms "curl -s -u admin:alp236330 http://127.0.0.1:8085/api/stats"

# Check PM2 status
ssh ms "pm2 status electra"

# View real-time logs
ssh ms "pm2 logs electra --lines 50"
```

---

## 6. MCP Integration Configuration

To link Electra to local AI assistants:

```json
{
  "mcpServers": {
    "electra": {
      "command": "python3",
      "args": [
        "/Users/emrullahardic/Documents/antigravity/nifty-tesla/mcp_server.py"
      ],
      "env": {
        "ELECTRA_DB_PATH": "/Users/emrullahardic/Documents/antigravity/nifty-tesla/electro_stock.db"
      }
    }
  }
}
```

---

## 7. Guidelines for AI Agents Modifying This Repository

1. **Zero Unnecessary Dependencies:** Do not introduce Flask, FastAPI, React, Node.js build steps, or npm packages. Keep the architecture ultra-lightweight and dependency-free.
2. **Preserve Database Backward Compatibility:** When modifying schema in [`electro_db.py`](file:///Users/emrullahardic/Documents/antigravity/nifty-tesla/electro_db.py), always use `CREATE TABLE IF NOT EXISTS` and runtime `ALTER TABLE ADD COLUMN` migration checks inside `init_db()`.
3. **Price and Stock Invariants:** Never show a price without KDV normalization or without checking `in_stock`. Always ignore English mirror URLs from local scrapers.
4. **Deploy & Sync Discipline:** Always verify local changes via `git status`, test syntax with `node -c static/app.js` and `python3 -m py_compile`, push to GitHub `origin/main`, pull on `ssh ms`, and restart PM2.
