#!/usr/bin/env python3
"""
ElectroStock MCP Server (Model Context Protocol)
Model Context Protocol uyumlu JSON-RPC 2.0 stdio sunucusu.
Herhangi bir AI asistanı (Cursor, Claude Desktop, Antigravity, Windsurf vb.) ile doğrudan entegre olur.

Yetenekler:
1. Kullanıcının elektronik parça stoğunu sorgulama (Sağlam, Arızalı, Lokasyon).
2. "Şu projeyi yapmak istiyorum" denildiğinde stoktaki uygun parçaları önerme.
3. Arızalı parçalar hakkında uyarma (boşuna bir daha almayı veya devreyi yakmayı engeller).
4. Stokta olmayan parçalar için Robotistan'dan aktif stok ve canlı fiyat sorgulama.
5. Sohbette yeni parça ekleme veya stok güncelleme.
"""

import sys
import json
import logging
from typing import Dict, Any, List, Optional
import electro_db
import project_matcher
from robotistan_scraper import scraper

# Logları stderr'e yaz (stdio MCP protokolünde stdout yalnızca JSON-RPC içindir)
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[MCP %(levelname)s] %(message)s")


TOOLS = [
    {
        "name": "electro_suggest_project_components",
        "description": (
            "Verilen bir elektronik proje fikrini veya devre şemasını analiz eder. "
            "Kullanıcının yerel envanterindeki SAĞLAM parçaları, saklama lokasyonlarını ve adetlerini listeler. "
            "Kullanıcının elinde bu parçaya ait ARIZALI bir parça varsa kullanıcıyı özellikle uyarır (boşuna bir daha almaması için). "
            "Eksik parçaları saptar ve Robotistan'da canlı arama yaparak aktif stokta olan uygun ürünleri fiyat ve linkleriyle sunar."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_description": {
                    "type": "string",
                    "description": "Yapılmak istenen proje açıklaması (örn: 'ESP32 ile Bluetooth kontrollü röle devresi' veya 'Arduino ve nem sensörü ile otomatik çiçek sulama')"
                },
                "check_robotistan": {
                    "type": "boolean",
                    "description": "Eksik parçalar için Robotistan canlı fiyat ve stok taraması yapılsın mı (varsayılan: true)",
                    "default": True
                }
            },
            "required": ["project_description"]
        }
    },
    {
        "name": "electro_search_inventory",
        "description": (
            "Kullanıcının yerel elektronik parça envanterinde detaylı arama yapar. "
            "İsim, değer (10k, 100nF), kılıf (DIP, SMD), lokasyon veya çalışma durumuna (sağlam/arızalı) göre filtreler."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Arama sözcüğü veya parça kodu (örn: 'esp32', '10k', 'diyot', 'röle')"
                },
                "category": {
                    "type": "string",
                    "description": "Kategori: resistor, capacitor, diode_led, transistor, ic_mcu, sensor, module, connector, power, passive_other, broken_scrap"
                },
                "status": {
                    "type": "string",
                    "description": "Parça durumu: 'working' (sağlam), 'defective' (arızalı), 'untested' (test bekliyor), 'salvage' (çıkma)"
                },
                "low_stock_only": {
                    "type": "boolean",
                    "description": "Yalnızca kritik stok seviyesine düşmüş veya bitmiş parçaları getir",
                    "default": False
                }
            }
        }
    },
    {
        "name": "electro_search_robotistan",
        "description": (
            "Robotistan.com üzerinde canlı elektronik parça araması yapar. "
            "Ürünün aktif stokta olup olmadığını (Stokta Var / Tükendi), güncel TL fiyatını ve doğrudan ürün sayfasının linkini çeker."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Robotistan'da aranacak ürün (örn: 'SG90 servo', 'BME280', 'ESP32-S3', '10k potansiyometre')"
                },
                "only_in_stock": {
                    "type": "boolean",
                    "description": "Yalnızca aktif stokta olan ürünleri listele",
                    "default": True
                },
                "limit": {
                    "type": "integer",
                    "description": "Maksimum ürün sayısı (varsayılan: 5)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "electro_add_component",
        "description": (
            "Kullanıcının atölye stok takip sistemine yeni bir elektronik parça ekler."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Parçanın tam adı (örn: 'ESP32 DevKit V1', '10k Direnç')"
                },
                "category": {
                    "type": "string",
                    "description": "Kategori: resistor, capacitor, diode_led, transistor, ic_mcu, sensor, module, connector, power, broken_scrap"
                },
                "value": {
                    "type": "string",
                    "description": "Değer veya teknik özellik (örn: '10kΩ', '100nF 50V', '5V 10A')"
                },
                "package": {
                    "type": "string",
                    "description": "Kılıf tipi (örn: 'DIP-8', 'SMD 0805', 'TO-220', 'Modül')"
                },
                "quantity": {
                    "type": "integer",
                    "description": "Mevcut adet"
                },
                "min_quantity": {
                    "type": "integer",
                    "description": "Kritik stok uyarı eşiği (varsayılan: 2)",
                    "default": 2
                },
                "status": {
                    "type": "string",
                    "description": "Durum: 'working' (sağlam), 'defective' (arızalı), 'untested' (test bekliyor), 'salvage' (çıkma)",
                    "default": "working"
                },
                "location": {
                    "type": "string",
                    "description": "Saklama kutusu / çekmece (örn: 'Çekmece A-2', 'Direnç Kutusu #1', 'Arızalı Sepeti')"
                },
                "notes": {
                    "type": "string",
                    "description": "Notlar veya arıza sebebi (örn: 'Regülatörü yanık, harici 3.3V ile çalışır')"
                }
            },
            "required": ["name", "category", "quantity"]
        }
    },
    {
        "name": "electro_update_stock",
        "description": (
            "Bir bileşenin stok miktarını artırır/azaltır veya çalışma durumunu (sağlam / arızalı) günceller."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "component_id": {
                    "type": "integer",
                    "description": "Güncellenecek bileşenin ID numarası"
                },
                "delta": {
                    "type": "integer",
                    "description": "Miktar değişimi (artırmak için pozitif örn: 5, projede kullanıp azaltmak için negatif örn: -2)"
                },
                "status": {
                    "type": "string",
                    "description": "Yeni durum (örn: 'defective' yapılarak arızalıya taşınabilir)"
                },
                "reason": {
                    "type": "string",
                    "description": "Değişiklik sebebi (örn: 'Projede harcandı', 'Denerken yandı')"
                }
            },
            "required": ["component_id"]
        }
    },
    {
        "name": "electro_get_defective_parts",
        "description": (
            "Kullanıcının atölyesinde bulunan tüm arızalı, hurda veya test bekleyen parçaları ve arıza notlarını listeler. "
            "Yeni parça sipariş etmeden önce yedek olarak değerlendirilebilecek parçaları görmeyi sağlar."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "electro_get_inventory_summary",
        "description": (
            "Elektronik atölyesindeki toplam stok durumunu, sağlam vs. arızalı sayılarını, kritik stok uyarılarını ve saklama lokasyonlarını özetler."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "electro_add_to_cart",
        "description": (
            "Robotistan'dan sipariş edilecek eksik veya yeni bir elektronik bileşeni atölye alışveriş sepetine ekler."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Ürün başlığı"},
                "url": {"type": "string", "description": "Robotistan ürün linki"},
                "price": {"type": "string", "description": "Fiyat (örn: '420,31 TL')"},
                "price_value": {"type": "number", "description": "Sayısal TL fiyatı (örn: 420.31)"},
                "product_id": {"type": "integer", "description": "Robotistan T-Soft Product ID numarası"},
                "quantity": {"type": "integer", "description": "Adet (varsayılan: 1)", "default": 1}
            },
            "required": ["title", "url", "price"]
        }
    },
    {
        "name": "electro_get_cart",
        "description": (
            "Robotistan atölye sepetindeki tüm ürünleri, toplam tutarı ve Robotistan sepetine toplu aktarma bilgilerini getirir."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "electro_clear_cart",
        "description": (
            "Robotistan atölye alışveriş sepetini tamamen temizler / boşaltır."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "electro_plan_project_draft_order",
        "description": (
            "Kullanıcının proje fikrini analiz eder, stoktaki sağlam/arızalı parçaları kontrol eder, "
            "eksik parçaları Robotistan'da canlı tarar ve doğrudan bir 'Draft (Taslak) Sipariş Listesi' oluşturup kaydeder. "
            "Kullanıcı bu taslağı web arayüzünde inceleyebilir ve tek tıkla sepete aktarabilir."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_description": {
                    "type": "string",
                    "description": "Proje fikri veya devre gereksinimi (örn: 'ESP32 ile WiFi kontrollü otomatik çiçek sulama sistemi')"
                },
                "auto_create_draft": {
                    "type": "boolean",
                    "description": "Eksik parçalar için taslak sipariş listesi otomatik oluşturulup kaydedilsin mi (varsayılan: true)",
                    "default": True
                }
            },
            "required": ["project_description"]
        }
    },
    {
        "name": "electro_create_draft_order",
        "description": (
            "Robotistan'dan veya başka kaynaklardan alınacak parçalar için yeni bir taslak (draft) sipariş listesi oluşturur."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Sipariş taslağının başlığı (örn: 'Akıllı Sera Parça Listesi')"},
                "description": {"type": "string", "description": "Proje veya sipariş açıklaması"},
                "items": {
                    "type": "array",
                    "description": "Sipariş kalemleri listesi",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Ürün adı"},
                            "product_id": {"type": "integer", "description": "Robotistan PID (varsa)"},
                            "url": {"type": "string", "description": "Ürün linki"},
                            "price": {"type": "string", "description": "Fiyat (örn: '45,20 TL')"},
                            "price_value": {"type": "number", "description": "Sayısal fiyat"},
                            "quantity": {"type": "integer", "description": "Adet", "default": 1},
                            "notes": {"type": "string", "description": "Rol veya kullanım notu"}
                        },
                        "required": ["title"]
                    }
                },
                "notes": {"type": "string", "description": "Ek notlar"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "electro_list_draft_orders",
        "description": (
            "Daha önce AI veya kullanıcı tarafından oluşturulmuş tüm taslak (draft) sipariş listelerini özetler."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filtre: 'draft', 'ready', 'ordered', 'all'", "default": "all"}
            }
        }
    },
    {
        "name": "electro_get_draft_order",
        "description": (
            "Belirli bir taslak sipariş listesinin tüm kalemlerini, ürün linklerini, fiyatlarını ve stok durumlarını getirir."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "integer", "description": "Taslak sipariş ID numarası"}
            },
            "required": ["draft_id"]
        }
    },
    {
        "name": "electro_apply_draft_order_to_cart",
        "description": (
            "Belirtilen taslak sipariş listesindeki tüm Robotistan ürünlerini tek hamlede aktif alışveriş sepetine aktarır."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "integer", "description": "Aktarılacak taslak sipariş ID numarası"}
            },
            "required": ["draft_id"]
        }
    },
    {
        "name": "electro_remove_draft_order_item",
        "description": (
            "Taslak (draft) sipariş listesinden tek bir kalemi çıkarır/siler ve taslağın toplam tutarını otomatik günceller."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "integer",
                    "description": "Taslak siparişten çıkarılacak kalemin ID numarası"
                }
            },
            "required": ["item_id"]
        }
    }
]



RESOURCES = [
    {
        "uri": "electro://inventory",
        "name": "Elektronik Parça Envanteri",
        "description": "Mevcut tüm parçaların anlık tam listesi",
        "mimeType": "application/json"
    },
    {
        "uri": "electro://low-stock",
        "name": "Kritik Seviyedeki Parçalar",
        "description": "Kritik stok eşiğinin altına düşen parçalar",
        "mimeType": "application/json"
    },
    {
        "uri": "electro://defective-parts",
        "name": "Arızalı ve Çıkma Parçalar",
        "description": "Tamir bekleyen veya parça sökülecek arızalı elemanlar",
        "mimeType": "application/json"
    }
]


class MCPServer:
    def __init__(self):
        electro_db.init_db()

    def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        msg_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        logging.info(f"Gelen İstek: {method} (id={msg_id})")

        # 1. Initialize
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                        "resources": {}
                    },
                    "serverInfo": {
                        "name": "electro-stock-mcp",
                        "version": "1.0.0"
                    }
                }
            }

        # 2. Notifications
        if method == "notifications/initialized":
            logging.info("İstemci başarıyla bağlandı ve ilklendirildi.")
            return None

        # 3. Ping
        if method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

        # 4. Tools List
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": TOOLS
                }
            }

        # 5. Tools Call
        if method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})
            return self.dispatch_tool(msg_id, tool_name, args)

        # 6. Resources List
        if method == "resources/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "resources": RESOURCES
                }
            }

        # 7. Resources Read
        if method == "resources/read":
            uri = params.get("uri")
            return self.read_resource(msg_id, uri)

        # Bilinmeyen metod
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }

    def dispatch_tool(self, msg_id: Any, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        logging.info(f"Tool çağrısı: {tool_name} with args: {args}")
        try:
            if tool_name == "electro_suggest_project_components":
                desc = args.get("project_description", "")
                chk_rob = args.get("check_robotistan", True)
                analysis = project_matcher.match_project_components(
                    project_description=desc,
                    check_robotistan=chk_rob
                )
                formatted_md = project_matcher.format_project_analysis_markdown(analysis)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": formatted_md}
                        ],
                        "isError": False
                    }
                }

            elif tool_name == "electro_search_inventory":
                q = args.get("query", "")
                cat = args.get("category", "")
                st = args.get("status", "")
                low_stock = args.get("low_stock_only", False)
                results = electro_db.search_components(
                    query=q,
                    category=cat,
                    status=st,
                    low_stock_only=low_stock
                )
                summary_text = f"Toplam {len(results)} parça bulundu:\n\n"
                for r in results:
                    durum_adi = electro_db.STATUSES.get(r['status'], r['status'])
                    summary_text += f"- **{r['name']}** [{durum_adi}] | Değer: {r['value'] or '-'} | Adet: {r['quantity']} | Konum: {r['location'] or 'Belirtilmemiş'}\n"
                    if r['notes']:
                        summary_text += f"  *Not:* {r['notes']}\n"

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": summary_text}
                        ],
                        "structured_data": results
                    }
                }

            elif tool_name == "electro_search_robotistan":
                q = args.get("query", "")
                only_stock = args.get("only_in_stock", True)
                limit = args.get("limit", 5)
                rob_res = scraper.search(query=q, only_in_stock=only_stock, limit=limit)
                
                md = [f"### 🌐 Robotistan Arama Sonuçları: '{q}'\n"]
                md.append(f"Toplam {rob_res.get('total_found', 0)} ürün bulundu (Aktif stokta: {rob_res.get('in_stock_count', 0)}):\n")
                
                results = rob_res.get("results", [])
                if not results:
                    md.append("Aradığınız kritere uygun ürün bulunamadı.")
                else:
                    for item in results:
                        stok_badge = "🟢 Stokta Var" if item["in_stock"] else "🔴 Tükendi"
                        md.append(f"- [{item['title']}]({item['url']}) — **{item['price']}** ({stok_badge})")

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": "\n".join(md)}
                        ]
                    }
                }

            elif tool_name == "electro_add_component":
                comp_id = electro_db.add_component(
                    name=args.get("name"),
                    category=args.get("category"),
                    value=args.get("value", ""),
                    package=args.get("package", ""),
                    quantity=args.get("quantity", 1),
                    min_quantity=args.get("min_quantity", 2),
                    status=args.get("status", "working"),
                    location=args.get("location", ""),
                    notes=args.get("notes", "")
                )
                msg = f"✅ Parça başarıyla envantere eklendi! (ID: {comp_id}, İsim: {args.get('name')}, Adet: {args.get('quantity')}, Konum: {args.get('location') or 'Belirtilmedi'})"
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": msg}],
                        "component_id": comp_id
                    }
                }

            elif tool_name == "electro_update_stock":
                comp_id = args.get("component_id")
                delta = args.get("delta")
                new_status = args.get("status")
                reason = args.get("reason", "")

                output_parts = []
                if delta is not None:
                    new_qty = electro_db.adjust_stock(comp_id, delta, reason=reason)
                    output_parts.append(f"Yeni stok adedi: {new_qty}")

                if new_status:
                    electro_db.update_component(comp_id, status=new_status)
                    durum_adi = electro_db.STATUSES.get(new_status, new_status)
                    output_parts.append(f"Yeni durum: {durum_adi}")

                msg = f"✅ Bileşen (ID: {comp_id}) güncellendi: {', '.join(output_parts)}"
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": msg}]
                    }
                }

            elif tool_name == "electro_get_defective_parts":
                defective = electro_db.get_defective_components()
                md = ["## ⚠️ Atölyedeki Arızalı, Şüpheli ve Hurda Parçalar\n"]
                md.append("Aşağıdaki parçalar bozuk veya test bekliyor olarak kayıtlıdır. Yenisini almadan önce tamir edilebilir veya üzerindeki sağlam bileşenler (örn: entegre, soket, soğutucu) sökülebilir:\n")
                if not defective:
                    md.append("Kayıtlı arızalı parça bulunmuyor.")
                else:
                    for d in defective:
                        st = electro_db.STATUSES.get(d['status'], d['status'])
                        md.append(f"- **{d['name']}** [{st}]")
                        md.append(f"  📍 **Saklama Yeri:** {d['location'] or 'Arızalı Kutusu'}")
                        md.append(f"  📝 **Arıza Detayı / Not:** {d['notes'] or 'Not belirtilmemiş'}\n")

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "\n".join(md)}]
                    }
                }

            elif tool_name == "electro_get_inventory_summary":
                stats = electro_db.get_summary_stats()
                md = [
                    "# 📊 Atölye Stok Özeti",
                    f"- **Toplam Parça Çeşidi:** {stats['total_items']}",
                    f"- **Toplam Parça Adedi:** {stats['total_quantity']}",
                    f"- **🟢 Sağlam / Kullanıma Hazır:** {stats['working_count']} çeşit",
                    f"- **🔴 Arızalı / Bozuk:** {stats['defective_count']} çeşit",
                    f"- **🟡 Test Bekleyen / Çıkma:** {stats['untested_count'] + stats['salvage_count']} çeşit",
                    f"- **⚠️ Kritik Stok Uyarısı (Tükenen/Biten):** {stats['low_stock_count']} çeşit",
                    f"- **📍 Tanımlı Saklama Lokasyonları:** {', '.join(stats['locations']) if stats['locations'] else 'Yok'}"
                ]
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "\n".join(md)}]
                    }
                }

            elif tool_name == "electro_add_to_cart":
                title = args.get("title")
                url = args.get("url")
                price = args.get("price")
                price_val = args.get("price_value", 0.0)
                pid = args.get("product_id")
                qty = args.get("quantity", 1)
                item_id = electro_db.add_to_cart(
                    title=title, url=url, price=price,
                    price_value=price_val, product_id=pid, quantity=qty
                )
                msg = f"🛒 Ürün sepete eklendi: **{title}** ({qty} Adet - {price})"
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": msg}],
                        "cart_item_id": item_id
                    }
                }

            elif tool_name == "electro_get_cart":
                cart = electro_db.get_cart_items()
                items = cart.get("items", [])
                md = ["# 🛒 Robotistan Atölye Alışveriş Sepeti\n"]
                if not items:
                    md.append("Sepetiniz şu anda boş.")
                else:
                    for it in items:
                        pid_str = f" [PID: {it['product_id']}]" if it.get("product_id") else ""
                        md.append(f"- **{it['title']}**{pid_str}")
                        md.append(f"  Adet: {it['quantity']} | Birim Fiyat: {it['price']} | [Ürün Sayfası]({it['url']})\n")
                    md.append(f"💰 **Toplam Tutar:** ~{cart.get('total_price_tl', 0)} TL ({cart.get('total_quantity', 0)} parça)")

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "\n".join(md)}],
                        "cart_data": cart
                    }
                }

            elif tool_name == "electro_clear_cart":
                electro_db.clear_cart()
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "✅ Robotistan sepeti tamamen boşaltıldı."}]
                    }
                }

            elif tool_name == "electro_plan_project_draft_order":
                desc = args.get("project_description", "")
                auto_draft = args.get("auto_create_draft", True)
                analysis = project_matcher.match_project_components(
                    project_description=desc,
                    check_robotistan=True,
                    auto_create_draft_order=auto_draft
                )
                formatted_md = project_matcher.format_project_analysis_markdown(analysis)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": formatted_md}],
                        "analysis": analysis,
                        "draft_order_id": analysis.get("draft_order_id")
                    }
                }

            elif tool_name == "electro_create_draft_order":
                title = args.get("title", "Taslak Sipariş")
                desc = args.get("description", "")
                items = args.get("items", [])
                notes = args.get("notes", "")
                draft_id = electro_db.create_draft_order(
                    title=title, description=desc, items=items, notes=notes
                )
                msg = f"📋 Taslak sipariş listesi başarıyla oluşturuldu!\n- **ID:** #{draft_id}\n- **Başlık:** {title}\n- **Kalem Sayısı:** {len(items)}\nWeb arayüzünde 'Draft Siparişler' sekmesinden görebilir veya sepete aktarabilirsiniz."
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": msg}],
                        "draft_order_id": draft_id
                    }
                }

            elif tool_name == "electro_list_draft_orders":
                st = args.get("status", "")
                orders = electro_db.get_draft_orders(status=st)
                md = ["# 📋 Kayıtlı Taslak Sipariş Listeleri (Draft Orders)\n"]
                if not orders:
                    md.append("Kayıtlı herhangi bir taslak sipariş listesi bulunmuyor.")
                else:
                    for o in orders:
                        md.append(f"- **#{o['id']} - {o['title']}** [{o['status']}]")
                        md.append(f"  Tahmini Tutar: ~{o['total_estimated_price']} TL | Kalem Sayısı: {o['item_count']} | Tarih: {o['updated_at'][:16]}")
                        if o.get("description"):
                            md.append(f"  *Proje:* {o['description']}")
                        md.append("")
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "\n".join(md)}],
                        "draft_orders": orders
                    }
                }

            elif tool_name == "electro_get_draft_order":
                did = args.get("draft_id")
                order = electro_db.get_draft_order_by_id(did)
                if not order:
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32602, "message": f"Draft order #{did} bulunamadı."}
                    }

                md = [f"# 📋 Taslak Sipariş Detayı: #{order['id']} - {order['title']}\n"]
                md.append(f"- **Durum:** {order['status']}")
                md.append(f"- **Açıklama:** {order.get('description', '-')}")
                md.append(f"- **Toplam Kalem:** {order['item_count']} ({order['total_quantity']} adet)")
                md.append(f"- **Tahmini Toplam Tutar:** ~{order['total_estimated_price']} TL\n")
                md.append("### Kalemler:")
                for it in order.get("items", []):
                    stok_badge = "🟢 Stokta Var" if it.get("in_stock") else "🔴 Tükendi"
                    link_str = f" | [Robotistan Linki]({it['url']})" if it.get("url") else ""
                    pid_str = f" [PID: {it['product_id']}]" if it.get("product_id") else ""
                    md.append(f"- **{it['title']}**{pid_str} — {it['quantity']} Adet x {it.get('price', 'Fiyat Yok')} ({stok_badge}){link_str}")
                    if it.get("notes"):
                        md.append(f"  *Not:* {it['notes']}")

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "\n".join(md)}],
                        "draft_order": order
                    }
                }

            elif tool_name == "electro_apply_draft_order_to_cart":
                did = args.get("draft_id")
                res = electro_db.apply_draft_order_to_cart(did)
                if not res.get("success"):
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32602, "message": res.get("error", "Aktarım başarısız")}
                    }

                msg = f"🛒 **{res['title']}** taslağındaki {res['added_items_count']} parça Robotistan alışveriş sepetinize aktarıldı!"
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": msg}],
                        "result": res
                    }
                }

            elif tool_name == "electro_remove_draft_order_item":
                item_id = int(args.get("item_id", 0))
                success = electro_db.delete_draft_order_item(item_id)
                if success:
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [{"type": "text", "text": f"✅ Kalem #{item_id} taslak sipariş listesinden başarıyla çıkarıldı."}],
                            "success": True
                        }
                    }
                else:
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32602, "message": f"Kalem #{item_id} bulunamadı veya silinemedi."}
                    }

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Bilinmeyen tool: {tool_name}"}
                }


        except Exception as e:
            logging.error(f"Tool yürütme hatası: {e}", exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"Hata oluştu: {str(e)}"}],
                    "isError": True
                }
            }

    def read_resource(self, msg_id: Any, uri: str) -> Dict[str, Any]:
        try:
            if uri == "electro://inventory":
                all_items = electro_db.search_components(limit=500)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(all_items, ensure_ascii=False, indent=2)
                            }
                        ]
                    }
                }
            elif uri == "electro://low-stock":
                low_stock = electro_db.get_low_stock_components()
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(low_stock, ensure_ascii=False, indent=2)
                            }
                        ]
                    }
                }
            elif uri == "electro://defective-parts":
                defective = electro_db.get_defective_components()
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(defective, ensure_ascii=False, indent=2)
                            }
                        ]
                    }
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32602, "message": f"Geçersiz URI: {uri}"}
                }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32603, "message": str(e)}
            }

    def run(self):
        logging.info("ElectroStock MCP Sunucusu stdio modunda başlatıldı.")
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue

                request = json.loads(line)
                response = self.handle_request(request)

                if response is not None:
                    out = json.dumps(response, ensure_ascii=False)
                    sys.stdout.write(out + "\n")
                    sys.stdout.flush()

            except Exception as e:
                logging.error(f"Girdi işleme hatası: {e}", exc_info=True)


def run_remote_bridge(remote_url: str, token: str = ""):
    """stdio üzerinden gelen JSON-RPC mesajlarını uzaktaki Electra HTTP/MCP sunucusuna yönlendirir."""
    import urllib.request
    import urllib.parse

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = remote_url
    if token and "token=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}token={urllib.parse.quote(token)}"

    sys.stderr.write(f"[Electra MCP Bridge] Uzak sunucuya bağlanılıyor: {url}\n")
    sys.stderr.flush()

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            req = urllib.request.Request(
                url,
                data=line.encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                resp_data = resp.read().decode("utf-8")
                if resp_data:
                    sys.stdout.write(resp_data + "\n")
                    sys.stdout.flush()
        except (IOError, KeyboardInterrupt):
            break
        except Exception as e:
            sys.stderr.write(f"[Electra MCP Bridge Hatası]: {e}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ElectroStock MCP Sunucusu")
    parser.add_argument("--remote", type=str, default="", help="Uzak Electra sunucusu URL'si (örn: https://electra.matelab.dev/mcp)")
    parser.add_argument("--token", type=str, default="", help="Kimlik doğrulama tokenı veya admin şifresi")
    parsed_args = parser.parse_args()

    if parsed_args.remote:
        run_remote_bridge(parsed_args.remote, parsed_args.token)
    else:
        server = MCPServer()
        server.run()

