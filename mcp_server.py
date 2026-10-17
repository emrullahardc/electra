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
import component_equivalents
import market_scraper
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
        "name": "electro_move_to_defective",
        "description": (
            "Sağlam bir bileşenden belirli bir adedi (veya tümünü) arızaya/çıkmaya/şüpheliye ayırır. "
            "Örneğin 5 adet sağlam ESP32'den 1'i bozulduğunda, sağlam stoğu 4'e düşürür ve arıza sebebiyle 1 adet arızalı kayıt oluşturur."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "component_id": {"type": "integer", "description": "Arızalanan bileşenin ID numarası"},
                "quantity": {"type": "integer", "description": "Arızaya ayrılacak adet (varsayılan: 1)"},
                "status": {"type": "string", "enum": ["defective", "untested", "salvage"], "description": "Yeni durum (varsayılan: 'defective')"},
                "notes": {"type": "string", "description": "Arıza sebebi veya teşhis notu (örn: 'Regülatörü yanık, MCU sağlam')"},
                "location": {"type": "string", "description": "Arızalı parçanın konulacağı saklama yeri (varsayılan: 'Arızalı Kutusu')"}
            },
            "required": ["component_id", "notes"]
        }
    },
    {
        "name": "electro_mark_repaired",
        "description": (
            "Arızalı/çıkma bir parçayı tamir edildiğinde sağlam stoğa geri alır. "
            "Eğer aynı parçanın mevcut bir sağlam kaydı varsa, mükerrer oluşturmak yerine sağlam stoka adet olarak ekler."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "defective_id": {"type": "integer", "description": "Tamir edilen arızalı parçanın ID numarası"},
                "quantity": {"type": "integer", "description": "Tamir edilen adet (boş bırakılırsa tümü)"},
                "location": {"type": "string", "description": "Sağlam parçanın konulacağı saklama yeri"}
            },
            "required": ["defective_id"]
        }
    },
    {
        "name": "electro_list_component_units",
        "description": (
            "Bir parçaya ait kayıtlı tüm tekil birimleri (IMEI, telefon numarası, MAC adresi, seri numarası) listeler. "
            "Örneğin 5 adet SIM800L veya 5 adet SIM kartın her birinin ayrı IMEI, telefon no veya durumlarını döner."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "component_id": {"type": "integer", "description": "Birimleri listelenecek parçanın ID numarası"}
            },
            "required": ["component_id"]
        }
    },
    {
        "name": "electro_add_component_unit",
        "description": (
            "Bir bileşene tekil bir IMEI, telefon numarası, MAC adresi veya seri numarası kaydeder. "
            "Örn: SIM800L için IMEI: '861234045678901', SIM Kart için Tel No: '05321234567' gibi."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "component_id": {"type": "integer", "description": "Bileşenin ID numarası"},
                "unit_identifier": {"type": "string", "description": "IMEI, seri numarası, telefon numarası veya MAC adresi"},
                "unit_type": {"type": "string", "enum": ["auto", "imei", "phone", "mac", "serial", "custom"], "description": "Birim türü (varsayılan: auto)"},
                "status": {"type": "string", "enum": ["working", "defective", "in_use", "untested"], "description": "Birim durumu (varsayılan: working)"},
                "notes": {"type": "string", "description": "Özel not (örn: 'BTK Kayıtlı', 'Turkcell IoT Hat', 'Yedek')"}
            },
            "required": ["component_id", "unit_identifier"]
        }
    },
    {
        "name": "electro_bulk_add_component_units",
        "description": (
            "Bir bileşene alt alta veya virgülle ayrılmış çoklu IMEI/seri no/telefon no listesini tek seferde kaydeder."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "component_id": {"type": "integer", "description": "Bileşenin ID numarası"},
                "units_text": {"type": "string", "description": "Alt alta veya virgülle ayrılmış IMEI/Seri no listesi. Satır formatı opsiyonel '861234... - Not' olabilir."},
                "default_type": {"type": "string", "enum": ["auto", "imei", "phone", "mac", "serial", "custom"], "default": "auto"},
                "status": {"type": "string", "enum": ["working", "defective", "in_use", "untested"], "default": "working"},
                "notes": {"type": "string", "description": "Genel not"}
            },
            "required": ["component_id", "units_text"]
        }
    },
    {
        "name": "electro_update_component_unit",
        "description": (
            "Kayıtlı bir tekil birimin (IMEI/seri no/tel no) durumunu ('working', 'defective', 'in_use'), kimliğini veya notunu günceller."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "unit_id": {"type": "integer", "description": "Birim ID numarası"},
                "unit_identifier": {"type": "string", "description": "Yeni kimlik dizgisi (isteğe bağlı)"},
                "unit_type": {"type": "string", "enum": ["imei", "phone", "mac", "serial", "custom"], "description": "Yeni birim türü"},
                "status": {"type": "string", "enum": ["working", "defective", "in_use", "untested"], "description": "Yeni durum"},
                "notes": {"type": "string", "description": "Yeni not"}
            },
            "required": ["unit_id"]
        }
    },
    {
        "name": "electro_delete_component_unit",
        "description": "Kayıtlı bir tekil birimi siler.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "unit_id": {"type": "integer", "description": "Silinecek birimin ID numarası"}
            },
            "required": ["unit_id"]
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
                "required_components": {
                    "type": "array",
                    "description": "Opsiyonel: Proje için gereken kesin parça / BOM listesi (örn: ['XL6009 Boost Kartı', 'PD65W Type-C Tetikleyici', '0-100V 10A Voltmetre Ampermetre', '6x30mm Sigorta Yuvası']). Belirtilirse genel şablon yerine doğrudan bu parçalar stokta taranır ve eksikler piyasada aranır.",
                    "items": {"type": "string"}
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
            "Taslak (draft) sipariş listesinden tek bir kalemi çıkarır/siler. "
            "Doğrudan kalemin ID'si ('item_id') verilerek VEYA taslak ID ('draft_id') + parça adı/anahtar kelime ('title_query') verilerek silinebilir."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "integer",
                    "description": "Taslak siparişten çıkarılacak kalemin ID numarası (örn: 13)"
                },
                "draft_id": {
                    "type": "integer",
                    "description": "Kalemin bulunduğu taslak sipariş ID'si (item_id bilinmiyorsa title_query ile birlikte kullanılır)"
                },
                "title_query": {
                    "type": "string",
                    "description": "Silinecek kalemin başlığı veya anahtar kelimesi (örn: 'MAX-M10S', 'LIS3DH')"
                }
            }
        }
    },
    {
        "name": "electro_add_draft_order_item",
        "description": (
            "Mevcut bir taslak (draft) sipariş listesine yeni bir ürün/parça kalemi ekler ve taslağın toplam tutarını günceller. "
            "Robotistan dışı parçalar için 'source' ('market', 'direnc', 'hiberbilisim', 'aliexpress', 'local') belirtilebilir."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "integer", "description": "Kalemin ekleneceği taslak sipariş ID numarası"},
                "title": {"type": "string", "description": "Parça/ürün adı (örn: '1S LiPo Koruma Kartı (PCM/BMS)')"},
                "quantity": {"type": "integer", "description": "Adet (varsayılan: 1)"},
                "price": {"type": "string", "description": "Metin fiyatı (örn: '25.00 TL')"},
                "price_value": {"type": "number", "description": "Sayısal TL fiyatı (örn: 25.0)"},
                "url": {"type": "string", "description": "Varsa ürün satın alma linki"},
                "source": {"type": "string", "description": "Tedarik kaynağı (örn: 'robotistan', 'direnc', 'hiberbilisim', 'market', 'aliexpress')", "default": "market"},
                "in_stock": {"type": "boolean", "description": "Stok durumu"},
                "notes": {"type": "string", "description": "Parça notu veya gereksinim açıklaması"}
            },
            "required": ["draft_id", "title"]
        }
    },
    {
        "name": "electro_mark_draft_item_purchased",
        "description": (
            "Taslak (draft) sipariş listesindeki bir ürünü/kalemi 'satın alındı' veya 'alınmadı/bekliyor' olarak işaretler. "
            "Kullanıcının satın aldığı parçaları henüz almadıklarından net bir şekilde ayırt etmesini sağlar."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "integer", "description": "Durumu değiştirilecek taslak kaleminin ID numarası"},
                "is_purchased": {
                    "type": "boolean",
                    "description": "True: Satın alındı olarak işaretle, False: Satın alınacaklara geri al (varsayılan: true)",
                    "default": True
                }
            },
            "required": ["item_id"]
        }
    },
    {
        "name": "electro_transfer_draft_item_to_inventory",
        "description": (
            "Taslak siparişte satın alınmış olarak işaretlenen bir parçayı doğrudan kullanıcının yerel çalışan envanter stoğuna aktarır. "
            "Envanterde aynı parçadan varsa adedini artırır, yoksa yeni bileşen kaydı açar."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "integer", "description": "Stoğa aktarılacak taslak kaleminin ID numarası"},
                "category": {
                    "type": "string",
                    "description": "Bileşen kategorisi (boş bırakılırsa parça adından otomatik tahmin edilir): resistor, capacitor, diode_led, transistor, ic_mcu, sensor, module, connector, power, passive_other"
                },
                "location": {"type": "string", "description": "Atölyedeki saklama gözü/kutusu (örn: 'A1', 'Kutu-3', 'Çekmece 2')"},
                "notes": {"type": "string", "description": "Ek açıklama veya notlar"}
            },
            "required": ["item_id"]
        }
    },
    {
        "name": "electro_get_product_details",
        "description": (
            "Robotistan veya diğer elektronik mağaza ürün sayfasının detaylı teknik özelliklerini (boyut, konnektör tipi, koruma devresi, voltaj, kapasite, ağırlık, parametre tablosu) çeker ve karşılaştırma için özetler."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "İncelenecek ürünün tam web linki"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "electro_get_component_equivalents",
        "description": (
            "Bir elektronik komponentin (MOSFET, LDO regülatör, op-amp, mikrodenetleyici, sensör, motor sürücü vb.) doğrudan yerine geçebilecek (drop-in) veya daha düşük güç/maliyet sağlayan alternatiflerini karşılaştırmalı olarak listeler. İsteğe bağlı olarak bulunan muadillerin Türkiye marketlerindeki (Robotronik, Robotistan, Direnç.net, Motorobit) canlı stok ve fiyatlarını çeker."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "component_name": {
                    "type": "string",
                    "description": "Muadili aranan parça veya kategori adı (örn: 'IRFZ44N', 'LM358', 'DHT11', 'L298N', 'NEO-6M', '7805', 'HC-05')"
                },
                "check_market_prices": {
                    "type": "boolean",
                    "description": "Muadiller için Türk tedarikçilerinden canlı fiyat ve stok taraması yapılsın mı (varsayılan: true)",
                    "default": True
                }
            },
            "required": ["component_name"]
        }
    },
    {
        "name": "electro_save_component_knowledge",
        "description": (
            "Dinamik muadil ve bileşen bilgi bankasına yeni bir parça veya kategori ekler/günceller. "
            "Böylece Electra yeni alternatifleri ve mühendislik notlarını SQLite hafızasında tutar."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Bileşen kategorisi (örn: 'Akım / Voltaj Sensörleri', 'GPS / GNSS Modülleri')"},
                "part_name": {"type": "string", "description": "Parça adı ve modeli (örn: 'INA219', 'ACS712', 'CH340G')"},
                "features": {"type": "string", "description": "Teknik özellikleri (çalışma voltajı, akım, protokol)"},
                "pros": {"type": "string", "description": "Avantajları"},
                "cons": {"type": "string", "description": "Dezavantajları ve dikkat edilmesi gerekenler"},
                "keywords": {"type": "string", "description": "Arama için virgülle ayrılmış anahtar kelimeler"},
                "summary": {"type": "string", "description": "Kategori özeti veya seçim ipucu"}
            },
            "required": ["category", "part_name"]
        }
    },
    {
        "name": "electro_search_market",
        "description": (
            "Türkiye'deki büyük elektronik ve robotik parça marketlerinde "
            "(Robotronik, Robotistan, Direnç.net, Motorobit) eşzamanlı canlı arama yapar. "
            "Fiyatları yan yana kıyaslar, en ucuz mağazayı tespit eder, doğrudan satın alma linklerini ve stok durumlarını listeler."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Aranacak elektronik komponent veya ürün (örn: 'ESP32-C3', 'SG90', 'TP4056', 'BMP280', '1S Lipo Pil')"
                },
                "vendor": {
                    "type": "string",
                    "description": "Belirli bir mağaza veya hepsi: 'all' (tüm siteler), 'robotronik', 'robotistan', 'direnc', 'motorobit'",
                    "default": "all"
                },
                "only_in_stock": {
                    "type": "boolean",
                    "description": "Yalnızca aktif stokta olan ürünleri listele",
                    "default": True
                },
                "limit_per_vendor": {
                    "type": "integer",
                    "description": "Mağaza başına maksimum ürün sayısı (varsayılan: 4)",
                    "default": 4
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "electro_search_robotronik",
        "description": (
            "Robotronik (robotronik.com.tr) üzerinde canlı parça araması yapar. "
            "Özellikle uygun fiyatlı Arduino, ESP32, sensör, LiPo ve robotik modülleri için Türkiye'nin en hesaplı marketlerinden biridir."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Robotronik'te aranacak ürün (örn: 'ESP32-S3', 'SG90', 'Lipo Pil')"},
                "only_in_stock": {"type": "boolean", "default": True},
                "limit": {"type": "integer", "default": 6}
            },
            "required": ["query"]
        }
    },
    {
        "name": "electro_search_direnc",
        "description": (
            "Direnç.net (direnc.net) üzerinde canlı parça araması yapar. "
            "Türkiye'nin en zengin entegre, yarıiletken, pasif komponent (direnç, kondansatör), konnektör ve röle arşivine sahiptir."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Direnç.net'te aranacak ürün (örn: 'AO3401A', '2N7002', 'ESP32', 'TPS7A02')"},
                "only_in_stock": {"type": "boolean", "default": True},
                "limit": {"type": "integer", "default": 6}
            },
            "required": ["query"]
        }
    },
    {
        "name": "electro_compare_part_prices",
        "description": (
            "Bir parça için Robotistan, Robotronik, Direnç.net ve Motorobit mağazalarındaki canlı fiyatları tek bir tabloda kıyaslar. "
            "Kullanıcının Robotistan'dan aynı gün kargo alması ve diğer mağazaların harici kargo ücreti (~40-75 TL) eklemesi kuralını işletir. "
            "Fiyat farkı 100 TL veya altındaysa doğrudan Robotistan'ı önerir; fark 100 TL'den fazlaysa kullanıcıya sorulacak net karşılaştırma sorusunu ('prompt_question') üretir."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "part_name": {"type": "string", "description": "Fiyatı kıyaslanacak parça adı (örn: 'ESP32-C3 Super Mini', 'SG90 Servo', 'TP4056')"}
            },
            "required": ["part_name"]
        }
    },
    {
        "name": "electro_find_best_bom_deal",
        "description": (
            "Verilen bir proje malzeme listesindeki (BOM) tüm parçaları Türkiye mağazalarında (Robotronik, Robotistan, Direnç.net, Motorobit) tarar. "
            "Robotistan'ı aynı gün teslimatlı birincil mağaza kabul ederek ve harici mağazaların tahmini kargo ücretlerini (~50 TL) hesaba katarak "
            "Akıllı Sipariş Dağılımı (Smart Landed Cost Plan) çıkarır. 100 TL altı farklarda gereksiz kargo ve bekleme süresini önler."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "components": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Proje için gereken parça adları listesi (örn: ['ESP32-C3', 'SG90 servo', 'TP4056', '1S Lipo 1000mAh'])"
                },
                "auto_create_split_drafts": {
                    "type": "boolean",
                    "description": "Tedarikçilere göre ayrılmış taslak sipariş listeleri (örn: 'Robotronik Sepeti', 'Direnç.net Sepeti') otomatik oluşturulsun mu",
                    "default": False
                }
            },
            "required": ["components"]
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
                    },
                    "instructions": (
                        "ElectroStock / Electra Karar ve Davranış İlkeleri:\n"
                        "1. ROBOTİSTAN ÖNCELİĞİ VE KARGO KURALI: Kullanıcı Robotistan'dan aynı gün teslimat almaktadır. "
                        "Diğer sitelerden (Direnç.net, Robotronik, Motorobit) sipariş vermek minimum ~40-75 TL ek kargo ücreti "
                        "ve bekleme süresi oluşturur.\n"
                        "2. FİYAT FARKI ≤ 100 TL İSE: Bir parça Robotistan'da varsa ve en ucuz alternatif mağazayla arasındaki "
                        "fiyat farkı 100 TL veya altındaysa, ek kargo ödememek ve aynı gün teslim almak için doğrudan Robotistan'ı tercih et.\n"
                        "3. FİYAT FARKI > 100 TL İSE: Başka mağazadaki parça Robotistan'dan 100 TL'den fazla daha ucuzsa, "
                        "doğrudan o mağazayı eklemek yerine KULLANICIYA SOR: 'Bu parça Robotistan'da X TL (Aynı gün kargo), "
                        "fakat [Mağaza]'da Y TL (Z TL daha ucuz). Kargo süresini bekleyip [Mağaza] üzerinden mi alalım, "
                        "yoksa aynı gün gelmesi için Robotistan'ı mı seçelim?'.\n"
                        "4. ROBOTİSTAN'DA STOK YOKSA: En uygun alternatif mağazayı açıkça belirterek taslağa ekle.\n"
                        "5. ANLAMSAL VE TEKNİK UYUMLULUK DİKKATİ:\n"
                        "   - PİL / BATARYA: Pil ararken 'koruma kartı' (BMS/PCM), şarj devresi, yuva veya gösterge gibi aksesuarları ASLA pil sanma. Sadece gerçek kimyasal hücreleri/bataryaları (LiPo/18650) seç.\n"
                        "   - KONNEKTÖR: Pin sayısına dikkat et (örn: 2 pin istendiyse 4 veya 6 pinli ürünleri eşleştirme).\n"
                        "   - KONDANSATÖR: SMD/Seramik (MLCC) istendiyse 63V Elektrolitik kutu/can tipi seçme; montaj ve dielektrik tipini kontrol et.\n"
                        "   - DİRENÇ: El lehimine uygunluk (DIP / THT 1/4W) veya SMD (0805 vb.) kılıf ayrımına dikkat et.\n"
                        "6. DONANIM VE ALIAS BİLİNCİ: Bir parça Robotistan'da ana adıyla (örn: NEO-6M) bulunamazsa, popüler kart/modül kodunu (örn: GY-NEO6MV2) veya muadilini (ATGM336H) mutlaka tara."
                    )
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

            elif tool_name == "electro_move_to_defective":
                comp_id = args.get("component_id")
                qty = int(args.get("quantity", 1))
                status_val = str(args.get("status", "defective"))
                notes = str(args.get("notes", "")).strip()
                loc = str(args.get("location", "Arızalı Kutusu")).strip()

                res = electro_db.move_component_to_defective(
                    component_id=comp_id,
                    qty_to_move=qty,
                    target_status=status_val,
                    defect_notes=notes,
                    new_location=loc
                )
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"⚠️ {res['message']}"}],
                        "data": res
                    }
                }

            elif tool_name == "electro_mark_repaired":
                def_id = args.get("defective_id")
                qty = args.get("quantity")
                loc = str(args.get("location", "")).strip()

                res = electro_db.mark_component_repaired(
                    defective_id=def_id,
                    repaired_qty=int(qty) if qty is not None else None,
                    target_location=loc
                )
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"✅ {res['message']}"}],
                        "data": res
                    }
                }

            elif tool_name == "electro_list_component_units":
                comp_id = int(args.get("component_id"))
                comp = electro_db.get_component(comp_id)
                if not comp:
                    raise ValueError(f"ID #{comp_id} olan bileşen bulunamadı.")
                units = electro_db.get_component_units(comp_id)
                md = [f"## 📱 '{comp['name']}' Tekil Birim / IMEI / Seri No Listesi ({len(units)} adet)\n"]
                if not units:
                    md.append("Bu parçaya kayıtlı IMEI, seri no veya telefon no bulunmuyor.")
                else:
                    for u in units:
                        st = electro_db.STATUSES.get(u['status'], u['status'])
                        md.append(f"- **{u['unit_identifier']}** `[{u['unit_type'].upper()}]` — Durum: **{st}**")
                        if u.get('notes'):
                            md.append(f"  📝 Not: {u['notes']}")
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "\n".join(md)}],
                        "units": units
                    }
                }

            elif tool_name == "electro_add_component_unit":
                comp_id = int(args.get("component_id"))
                ident = str(args.get("unit_identifier", "")).strip()
                u_type = str(args.get("unit_type", "auto"))
                st = str(args.get("status", "working"))
                notes = str(args.get("notes", "")).strip()

                uid = electro_db.add_component_unit(comp_id, ident, unit_type=u_type, status=st, notes=notes)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"✅ Birim ({ident}) başarıyla kaydedildi (ID: #{uid})"}],
                        "unit_id": uid
                    }
                }

            elif tool_name == "electro_bulk_add_component_units":
                comp_id = int(args.get("component_id"))
                text = str(args.get("units_text", "")).strip()
                def_type = str(args.get("default_type", "auto"))
                st = str(args.get("status", "working"))
                notes = str(args.get("notes", "")).strip()

                added = electro_db.bulk_add_component_units(comp_id, text, default_type=def_type, status=st, notes=notes)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"✅ Toplam {len(added)} adet birim (IMEI/seri no) başarıyla kaydedildi."}],
                        "added_count": len(added),
                        "units": added
                    }
                }

            elif tool_name == "electro_update_component_unit":
                uid = int(args.get("unit_id"))
                ident = args.get("unit_identifier")
                u_type = args.get("unit_type")
                st = args.get("status")
                notes = args.get("notes")

                success = electro_db.update_component_unit(uid, unit_identifier=ident, unit_type=u_type, status=st, notes=notes)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"✅ Birim #{uid} güncellendi." if success else f"❌ Birim #{uid} bulunamadı."}],
                        "success": success
                    }
                }

            elif tool_name == "electro_delete_component_unit":
                uid = int(args.get("unit_id"))
                success = electro_db.delete_component_unit(uid)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"🗑️ Birim #{uid} silindi." if success else f"❌ Birim #{uid} bulunamadı."}],
                        "success": success
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
                    md.append(f"💰 **Toplam Tutar:** ~{float(cart.get('total_price_tl') or 0):.2f} TL ({cart.get('total_quantity', 0)} parça)")

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
                custom_reqs = args.get("required_components") or args.get("custom_requirements")
                auto_draft = args.get("auto_create_draft", True)
                analysis = project_matcher.match_project_components(
                    project_description=desc,
                    custom_requirements=custom_reqs,
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
                        md.append(f"  Tahmini Tutar: ~{float(o.get('total_estimated_price') or 0):.2f} TL | Kalem Sayısı: {o['item_count']} | Tarih: {o['updated_at'][:16]}")
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

                items = order.get("items", [])
                pending_items = [it for it in items if not it.get("is_purchased")]
                purchased_items = [it for it in items if it.get("is_purchased")]

                md = [f"# 📋 Taslak Sipariş Detayı: #{order['id']} - {order['title']}\n"]
                md.append(f"- **Durum:** {order['status']}")
                md.append(f"- **Açıklama:** {order.get('description', '-')}")
                md.append(f"- **Toplam Kalem:** {order['item_count']} ({order['total_quantity']} adet)")
                md.append(f"- **Satın Alınacak Tutar:** ~{float(order.get('pending_estimated_price') or 0):.2f} TL ({len(pending_items)} Kalem)")
                if purchased_items:
                    md.append(f"- **Satın Alınan Tutar:** ~{float(order.get('purchased_total_price') or 0):.2f} TL ({len(purchased_items)} Kalem)")
                md.append("")

                md.append(f"### 🛒 Satın Alınacaklar ({len(pending_items)} Kalem):")
                if not pending_items:
                    md.append("*Tüm kalemler satın alındı! 🎉*")
                for it in pending_items:
                    if not it.get("url"):
                        stok_badge = "⚪ Piyasada Aranacak"
                    elif it.get("in_stock"):
                        stok_badge = "🟢 Stokta Var"
                    else:
                        stok_badge = "🔴 Tükendi"

                    source_tag = f" [{it.get('source').upper()}]" if it.get("source") and it.get("source") != "robotistan" else ""
                    link_str = f" | [Ürün Linki]({it['url']})" if it.get("url") else ""
                    pid_str = f" [PID: {it['product_id']}]" if it.get("product_id") else ""
                    price_str = it.get('price') or (f"{it['price_value']} TL" if it.get('price_value') else "Fiyat Belirtilmedi")
                    
                    md.append(f"- **[Kalem ID: #{it['id']}]{source_tag} {it['title']}**{pid_str} — {it['quantity']} Adet x {price_str} ({stok_badge}){link_str}")
                    if it.get("notes"):
                        md.append(f"  *Not:* {it['notes']}")

                if purchased_items:
                    md.append(f"\n### ✅ Satın Alınanlar ({len(purchased_items)} Kalem):")
                    for it in purchased_items:
                        stk_info = f" [📦 Stoğa Eklendi - #{it.get('inventory_component_id')}]" if it.get("transferred_to_inventory") else " [⏳ Henüz Stoğa Aktarılmadı]"
                        price_str = f"{it['price_value']} TL" if it.get('price_value') else ""
                        purchased_date = f" ({it['purchased_at'][:10]})" if it.get("purchased_at") else ""
                        md.append(f"- **[Kalem ID: #{it['id']}] ~~{it['title']}~~** — {it['quantity']} Adet x {price_str}{stk_info}{purchased_date}")

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "\n".join(md)}],
                        "draft_order": order
                    }
                }

            elif tool_name == "electro_mark_draft_item_purchased":
                item_id = int(args.get("item_id", 0))
                is_purchased = bool(args.get("is_purchased", True))
                if not item_id:
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32602, "message": "Lütfen 'item_id' belirtin."}
                    }
                success = electro_db.mark_draft_order_item_purchased(item_id, is_purchased)
                if not success:
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32602, "message": f"Kalem #{item_id} bulunamadı veya güncellenemedi."}
                    }
                action_text = "Satın alındı olarak işaretlendi! ✅" if is_purchased else "Satın alınacaklara geri alındı ↩"
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Kalem #{item_id}: {action_text}"}],
                        "item_id": item_id,
                        "is_purchased": is_purchased
                    }
                }

            elif tool_name == "electro_transfer_draft_item_to_inventory":
                item_id = int(args.get("item_id", 0))
                cat = args.get("category", "")
                loc = args.get("location", "")
                notes = args.get("notes", "")
                if not item_id:
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32602, "message": "Lütfen 'item_id' belirtin."}
                    }
                res = electro_db.transfer_draft_item_to_inventory(item_id, category=cat, location=loc, notes=notes)
                if not res.get("success"):
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32602, "message": res.get("error", "Stoğa aktarılamadı")}
                    }
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"📦 {res['message']}"}],
                        "transfer_result": res
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
                item_id = args.get("item_id")
                draft_id = args.get("draft_id")
                title_query = args.get("title_query") or args.get("title")

                if item_id:
                    item_id = int(item_id)
                    success = electro_db.delete_draft_order_item(item_id)
                    if success:
                        return {
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "result": {
                                "content": [{"type": "text", "text": f"✅ Kalem #{item_id} taslak sipariş listesinden başarıyla çıkarıldı."}],
                                "success": True,
                                "deleted_item_id": item_id
                            }
                        }
                    else:
                        return {
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "error": {"code": -32602, "message": f"Kalem #{item_id} bulunamadı veya silinemedi."}
                        }
                elif draft_id and title_query:
                    del_res = electro_db.delete_draft_order_item_by_query(int(draft_id), str(title_query))
                    if del_res:
                        return {
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "result": {
                                "content": [{"type": "text", "text": f"✅ '{del_res['title']}' (Kalem #{del_res['id']}) taslak #{draft_id} listesinden başarıyla silindi."}],
                                "success": True,
                                "deleted_item": del_res
                            }
                        }
                    else:
                        return {
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "error": {"code": -32602, "message": f"Taslak #{draft_id} içinde '{title_query}' ile eşleşen bir kalem bulunamadı."}
                        }
                else:
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32602, "message": "Lütfen silinecek kalemin 'item_id' numarasını veya 'draft_id' + 'title_query' parametrelerini belirtin."}
                    }

            elif tool_name == "electro_add_draft_order_item":
                draft_id = int(args.get("draft_id", 0))
                title = str(args.get("title", "")).strip()
                if not draft_id or not title:
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32602, "message": "Lütfen 'draft_id' ve 'title' belirtin."}
                    }

                url = str(args.get("url", "")).strip()
                in_stock = bool(args.get("in_stock", True if url else False))
                source = str(args.get("source", "")).strip() or ("robotistan" if url else "market")
                price = str(args.get("price", "")).strip()
                price_val = float(args.get("price_value") or 0.0)

                new_item_id = electro_db.add_item_to_draft_order(
                    draft_id=draft_id,
                    item={
                        "title": title,
                        "product_id": args.get("product_id"),
                        "url": url,
                        "price": price,
                        "price_value": price_val,
                        "quantity": int(args.get("quantity", 1)),
                        "in_stock": in_stock,
                        "source": source,
                        "notes": str(args.get("notes", "")).strip()
                    }
                )
                msg = f"✅ '{title}' (Kalem #{new_item_id}) [Kaynak: {source.upper()}] taslak #{draft_id} listesine başarıyla eklendi!"
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": msg}],
                        "success": True,
                        "item_id": new_item_id,
                        "draft_id": draft_id
                    }
                }

            elif tool_name == "electro_get_product_details":
                p_url = str(args.get("url", "")).strip()
                details = market_scraper.get_universal_product_details(p_url)
                if details.get("error"):
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32602, "message": details["error"]}
                    }

                md = [f"# 🔍 Ürün Teknik Detayları: {details['title']}\n"]
                md.append(f"- **Fiyat:** {details['price']}")
                md.append(f"- **Stok Durumu:** {details['stock_status']}")
                md.append(f"- **Ürün Linki:** [Ürün Sayfasını Aç]({details['url']})\n")

                if details.get("specs"):
                    md.append("### 📋 Teknik Özellikler & Parametreler:")
                    for sp in details["specs"]:
                        md.append(f"- {sp}")
                    md.append("")

                if details.get("description"):
                    md.append("### 📝 Ürün Açıklaması:")
                    md.append(details["description"])

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "\n".join(md)}],
                        "details": details
                    }
                }

            elif tool_name == "electro_get_component_equivalents":
                c_name = str(args.get("component_name", "")).strip()
                check_prices = bool(args.get("check_market_prices", True))
                eq_res = component_equivalents.find_component_equivalents_with_market(c_name, check_market_prices=check_prices)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": eq_res["markdown_report"]}],
                        "data": eq_res
                    }
                }

            elif tool_name == "electro_save_component_knowledge":
                cat = str(args.get("category", "")).strip()
                p_name = str(args.get("part_name", "")).strip()
                feats = str(args.get("features", "")).strip()
                pros = str(args.get("pros", "")).strip()
                cons = str(args.get("cons", "")).strip()
                kws = str(args.get("keywords", "")).strip()
                summ = str(args.get("summary", "")).strip()
                row_id = component_equivalents.save_learned_equivalent(
                    category=cat,
                    part_name=p_name,
                    features=feats,
                    pros=pros,
                    cons=cons,
                    keywords=kws,
                    summary=summ
                )
                msg = f"✅ `{p_name}` ({cat}) başarıyla dinamik bilgi bankasına kaydedildi."
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": msg}],
                        "data": {"id": row_id, "category": cat, "part_name": p_name, "success": True}
                    }
                }

            elif tool_name == "electro_search_market":
                q = str(args.get("query", "")).strip()
                v = str(args.get("vendor", "all")).strip().lower()
                vendors = [v] if v and v != "all" else None
                only_stock = bool(args.get("only_in_stock", True))
                limit = int(args.get("limit_per_vendor", 4))

                market_res = market_scraper.search_market(
                    query=q,
                    vendors=vendors,
                    only_in_stock=only_stock,
                    limit_per_vendor=limit
                )

                md = [f"# 🛒 Türkiye Elektronik Pazarı Arama Sonuçları: '{q}'\n"]
                counts = market_res.get("vendor_counts", {})
                count_str = " • ".join([f"{market_scraper.VENDORS.get(k, {}).get('name', k)}: {cnt}" for k, cnt in counts.items()])
                md.append(f"**Taranan Mağazalar:** {count_str}")
                md.append(f"**Toplam Bulunan Ürün:** {market_res.get('total_results', 0)} (Stokta Olan: {market_res.get('in_stock_results', 0)})\n")

                cheapest = market_res.get("cheapest")
                if cheapest:
                    md.append(f"⭐ **En Uygun Fiyat:** [{cheapest['vendor']}] {cheapest['title']} — **{cheapest['price']}** ([Ürünü Gör]({cheapest['url']}))\n")

                md.append("### 📦 Mağazalara Göre Ürünler (Ucuzdan Pahalıya):")
                for r in market_res.get("results", []):
                    badge = "🟢 Stokta Var" if r.get("in_stock") else "🔴 Tükendi"
                    cheap_tag = " ⭐ *(En Ucuz!)*" if r.get("is_cheapest") else ""
                    md.append(f"- **[{r['vendor']}] [{r['title']}]({r['url']})** — **{r['price']}** ({badge}){cheap_tag}")

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "\n".join(md)}],
                        "data": market_res
                    }
                }

            elif tool_name == "electro_search_robotronik":
                q = str(args.get("query", "")).strip()
                only_stock = bool(args.get("only_in_stock", True))
                limit = int(args.get("limit", 6))
                m_res = market_scraper.search_market(query=q, vendors=["robotronik"], only_in_stock=only_stock, limit_per_vendor=limit)
                items = m_res.get("results", [])

                md = [f"# 🤖 Robotronik.com.tr Arama Sonuçları: '{q}'\n"]
                md.append(f"Toplam {len(items)} uyumlu ürün bulundu.\n")
                if not items:
                    md.append("Aradığınız kritere uygun ürün bulunamadı.")
                for r in items:
                    badge = "🟢 Stokta Var" if r.get("in_stock") else "🔴 Tükendi"
                    md.append(f"- **[{r['title']}]({r['url']})** — **{r['price']}** ({badge})")

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "\n".join(md)}],
                        "items": items
                    }
                }

            elif tool_name == "electro_search_direnc":
                q = str(args.get("query", "")).strip()
                only_stock = bool(args.get("only_in_stock", True))
                limit = int(args.get("limit", 6))
                m_res = market_scraper.search_market(query=q, vendors=["direnc"], only_in_stock=only_stock, limit_per_vendor=limit)
                items = m_res.get("results", [])

                md = [f"# ⚡ Direnç.net Arama Sonuçları: '{q}'\n"]
                md.append(f"Toplam {len(items)} uyumlu ürün bulundu.\n")
                if not items:
                    md.append("Aradığınız kritere uygun ürün bulunamadı.")
                for r in items:
                    badge = "🟢 Stokta Var" if r.get("in_stock") else "🔴 Tükendi"
                    md.append(f"- **[{r['title']}]({r['url']})** — **{r['price']}** ({badge})")

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "\n".join(md)}],
                        "items": items
                    }
                }

            elif tool_name == "electro_compare_part_prices":
                part_name = str(args.get("part_name", "")).strip()
                comp_res = market_scraper.search_market(part_name, only_in_stock=True, limit_per_vendor=2, sort_by_price=True)
                results = comp_res.get("results", [])
                decision = comp_res.get("decision_advice", {})

                # Yerel envanter kontrolü
                local_hits = []
                try:
                    from component_matcher import evaluate_component_relevance
                    for lc in electro_db.search_components(query=part_name):
                        if lc.get("status") == "working" and lc.get("quantity", 0) > 0:
                            if evaluate_component_relevance(part_name, lc.get("name", ""))[0]:
                                local_hits.append(lc)
                except Exception:
                    pass

                md = [f"# ⚖️ Parça Fiyat Karşılaştırması: '{part_name}'\n"]
                if local_hits:
                    lh = local_hits[0]
                    md.append(f"🏠 **Yerel Envanterinizde Mevcut:** **`{lh['name']}`** ({lh['quantity']} Adet, Çalışıyor — Konum: {lh.get('location') or 'Belirtilmemiş'})\n")

                cheapest = comp_res.get("cheapest")
                if cheapest:
                    md.append(f"🏆 **En Uygun Fiyat:** **{cheapest['price']}** ({cheapest['vendor']}) — [{cheapest['title']}]({cheapest['url']})\n")

                if decision:
                    md.append("### 🎯 Akıllı Satın Alma & Kargo Tavsiyesi:")
                    if decision.get("action") == "prefer_robotistan":
                        md.append(f"- ✅ **Tavsiye:** **Robotistan (Aynı Gün Teslimat)**")
                        md.append(f"- ℹ️ **Gerekçe:** {decision.get('summary')}\n")
                    elif decision.get("action") == "ask_user":
                        md.append(f"- ⚠️ **Fiyat Farkı > 100 TL:** {decision.get('summary')}")
                        md.append(f"- ❓ **Kullanıcıya Sorulacak Soru:** *\"{decision.get('prompt_question')}\"*\n")
                    elif decision.get("action") == "external_vendor":
                        md.append(f"- 📦 **Robotistan Stoğu Yok:** {decision.get('summary')}\n")

                if results:
                    md.append("| Mağaza | Ürün Adı | Fiyat | Stok | Link |")
                    md.append("|---|---|---|---|---|")
                    for r in results:
                        best_icon = "⭐ **EN UCUZ**" if r.get("is_cheapest") else ""
                        stok_str = "🟢 Stokta" if r.get("in_stock") else "🔴 Tükendi"
                        md.append(f"| **{r['vendor']}** {best_icon} | {r['title']} | **{r['price']}** | {stok_str} | [Ürünü Aç]({r['url']}) |")
                else:
                    sugg = market_scraper.get_suggested_sourcing_channel(part_name)
                    md.append(f"⚠️ Türkiye yerel perakende mağazalarında (Robotistan, Robotronik, Direnç.net, Motorobit) **`{part_name}`** için uyumlu aktif stok bulunamadı.")
                    md.append(f"👉 **Önerilen Tedarik Kanalı:** {sugg}")

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "\n".join(md)}],
                        "data": comp_res,
                        "local_inventory": local_hits,
                        "decision_advice": decision
                    }
                }

            elif tool_name == "electro_find_best_bom_deal":
                components = args.get("components", [])
                auto_split = bool(args.get("auto_create_split_drafts", False))
                bom_res = market_scraper.compare_bom_prices(parts=components, only_in_stock=True)

                total_req = bom_res.get("total_items_requested", 0)
                found_cnt = bom_res.get("found_items_count", 0)
                unfound_cnt = bom_res.get("unfound_items_count", 0)
                local_hits = bom_res.get("local_inventory_hits", [])

                md = ["# 🎯 Akıllı Çoklu Mağaza BOM & Satın Alma Planı\n"]
                md.append(f"**Talep Edilen Parça Sayısı:** {total_req} (🟢 Türkiye'de Bulunan: {found_cnt} • ⚠️ Alternatif/Yurt Dışı: {unfound_cnt} • 🏠 Envanterde Mevcut: {len(local_hits)})")
                md.append(f"**Türkiye Mağazaları Parça Maliyeti:** ~{bom_res.get('total_smart_parts_cost', 0.0):.2f} TL")
                if bom_res.get("estimated_shipping_total", 0.0) > 0:
                    md.append(f"**Tahmini Harici Kargo Ücreti ({bom_res.get('external_vendor_count')} Harici Mağaza):** ~{bom_res.get('estimated_shipping_total', 0.0):.2f} TL")
                    md.append(f"**Toplam Landed Maliyet (Kargo Dahil):** **~{bom_res.get('total_landed_cost', 0.0):.2f} TL**\n")
                else:
                    md.append(f"**Tüm Parçalar Robotistan'dan (0 TL Harici Kargo & Aynı Gün Teslimat):** **~{bom_res.get('total_landed_cost', 0.0):.2f} TL**\n")

                if local_hits:
                    md.append("### 🏠 Kendi Envanterinizde (Atölyede) Zaten Bulunan Parçalar:")
                    for lh in local_hits:
                        m0 = lh["matches"][0]
                        md.append(f"- **{lh['part_query']}** 👉 Envanterde **`{m0['name']}`** ({m0['quantity']} Adet, Çalışıyor) mevcut! Satın almanıza gerek olmayabilir.")
                    md.append("")

                smart_plan = bom_res.get("smart_plan", {})
                prompt_qs = bom_res.get("prompt_questions", [])
                unfound_items = bom_res.get("unfound_items", [])

                if prompt_qs:
                    md.append("### ❓ Kullanıcı Onayı Gereken Kalemler (Fark > 100 TL veya Özel Durum):")
                    for pq in prompt_qs:
                        md.append(f"- **{pq['part']}**: {pq['question']}")
                    md.append("")

                created_drafts = []

                for v_key, items in smart_plan.items():
                    v_name = market_scraper.VENDORS.get(v_key, {}).get("name", v_key.upper())
                    v_total = sum(it.get("price_value", 0.0) for it in items)
                    shipping_badge = " (Aynı Gün • 0 TL Ek Kargo)" if v_key == "robotistan" else " (~50 TL Kargo)"
                    md.append(f"### 🏪 {v_name}{shipping_badge} — {len(items)} Kalem • ~{v_total:.2f} TL:")
                    for it in items:
                        reason = f" *(Nedeni: {it.get('assigned_reason')})*" if it.get("assigned_reason") else ""
                        md.append(f"- **{it['title']}** — **{it['price']}** ([İncele]({it['url']})){reason}")
                    md.append("")

                    if auto_split:
                        draft_title = f"BOM – {v_name} Sepeti"
                        draft_items = [{
                            "title": it["title"],
                            "url": it["url"],
                            "price": it["price"],
                            "price_value": it["price_value"],
                            "quantity": 1,
                            "source": v_key,
                            "in_stock": True,
                            "notes": it.get("assigned_reason", f"{v_name} seçeneği")
                        } for it in items]
                        did = electro_db.create_draft_order(
                            title=draft_title,
                            description=f"Optimal BOM analizi ile {v_name} üzerinden seçilen parçalar.",
                            items=draft_items
                        )
                        created_drafts.append({"draft_id": did, "vendor": v_name, "count": len(draft_items)})

                if unfound_items:
                    md.append(f"### ⚠️ Türkiye Mağazalarında Stokta Bulunamayan Parçalar ({len(unfound_items)} Kalem):")
                    md.append("Aşağıdaki parçalar taranan Türkiye perakende mağazalarında (Robotistan, Robotronik, Direnç.net, Motorobit) stokta bulunamadı. Bu parçaların proje için yurt dışından (AliExpress / JLCPCB) veya distribütörlerden temin edilmesi önerilir:")
                    for uf in unfound_items:
                        md.append(f"- **{uf['part_query']}**: {uf.get('reason')} 👉 *Önerilen Tedarik:* **{uf.get('suggested_channel')}**")
                    md.append("")

                if created_drafts:
                    md.append("### 📝 Otomatik Oluşturulan Taslak Siparişler:")
                    for cd in created_drafts:
                        md.append(f"- **Draft #{cd['draft_id']}**: {cd['vendor']} ({cd['count']} Kalem)")


                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "\n".join(md)}],
                        "bom_data": bom_res,
                        "created_drafts": created_drafts,
                        "prompt_questions": prompt_qs,
                        "unfound_items": unfound_items
                    }
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

