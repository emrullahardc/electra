"""
Elektronik Komponent Eşdeğerlik, Muadil ve Çapraz Referans Motoru
Maker ve IoT donanım projelerinde parça bulunamadığında veya optimize edilmesi
gerektiğinde (örn: pilli sistemde NEO-6M yerine ATGM336H / MAX-M10S) akıllı muadil önerir.
"""

import re
from typing import Dict, Any, List, Optional

EQUIVALENTS_DATABASE = [
    {
        "category": "GPS / GNSS Modülleri",
        "keywords": ["gps", "gnss", "neo-6m", "neo-7m", "neo-m8n", "atgm336h", "max-m10s", "l80", "sim28"],
        "parts": [
            {
                "name": "u-blox NEO-6M",
                "features": "Tek bantlı GPS, UART 9600 bps, 3.3V - 5V çalışma, ~50 mA akım tüketimi.",
                "pros": "Çok yaygın, Arduino kütüphaneleriyle %100 uyumlu, ucuz.",
                "cons": "Sadece GPS destekler (GLONASS/BDS yok), yüksek akım tüketimi (pilli tasmalar için fazla), kapalı alanda zayıf.",
                "recommendation": "Sabit beslemeli prototipler için uygundur."
            },
            {
                "name": "ATGM336H",
                "features": "BDS + GPS çift sistemli GNSS, UART 9600 bps, 3.3V - 5V, ~25 mA akım tüketimi.",
                "pros": "NEO-6M ile pin ve komut uyumlu doğrudan drop-in muadil. Çok daha hızlı fix alır, yarı yarıya daha az güç tüketir.",
                "cons": "Çin menşeili Zhongke Micro üretimi, bazı clone kartlarda anten kalitesi değişken.",
                "recommendation": "NEO-6M yerine en ekonomik ve doğrudan uyumlu alternatiftir."
            },
            {
                "name": "u-blox MAX-M10S",
                "features": "10. Nesil Ultra Düşük Güçlü GNSS (GPS+GLONASS+Galileo+BeiDou), 3.3V, ~10-15 mA akım, L1/L5.",
                "pros": "Dünya standartlarında konum hassasiyeti, 15 mA altı akım tüketimi ile pilli hayvan tasması / IoT takip için altın standart.",
                "cons": "Daha pahalı (~300-500 TL), lehimlenmesi hassas (breakout modül olarak tercih edilmeli).",
                "recommendation": "Koyun GPS tasması gibi pilli son ürün için en iyi seçimdir."
            },
            {
                "name": "u-blox NEO-M8N",
                "features": "Eşzamanlı GPS/GLONASS/BeiDou, UART + I2C + SPI, harici EEPROM ve pusula portu.",
                "pros": "Yüksek hassasiyet, drone ve otonom araçlar için standart.",
                "cons": "Daha yüksek akım (~65 mA), pilli tasmalar için aşırı güç tüketir."
            }
        ]
    },
    {
        "category": "İvmeölçer & Hareket Sensörleri (IMU / Accelerometer)",
        "keywords": ["ivmeölçer", "ivme", "accelerometer", "lis3dh", "mma8452", "mpu6050", "adxl345", "bma250"],
        "parts": [
            {
                "name": "ST LIS3DH",
                "features": "3 Eksenli ultra düşük güçlü ivmeölçer, I2C/SPI, 2 µA uyku akımı, donanımsal hareket algılama kesmesi (wake-on-motion).",
                "pros": "Hayvan hareketsizken sistemi derin uykuya (deep-sleep) sokup, hayvan hareket edince ESP32'yi uyandırmak için ideal.",
                "cons": "Robotistan'da bazen stok tükenir, Direnç.net veya AliExpress'te bulunur."
            },
            {
                "name": "NXP MMA8452Q",
                "features": "3 Eksenli ivmeölçer, I2C, 12-bit/8-bit çözünürlük, ~6 µA uyku akımı.",
                "pros": "LIS3DH yerine doğrudan kullanılabilir, kesme (interrupt) pinleriyle uyandırma destekler.",
                "cons": "LIS3DH'e göre biraz daha eski nesil."
            },
            {
                "name": "InvenSense MPU-6050",
                "features": "6 Eksenli (3 eksen ivme + 3 eksen jiroskop), I2C, ~3.8 mA akım.",
                "pros": "Her yerde bulunur, çok ucuz, bol kütüphane desteği.",
                "cons": "Jiroskop devredeyken akım tüketimi çok yüksektir, pilli tasma projeleri için pil ömrünü kısaltır."
            },
            {
                "name": "Analog Devices ADXL345",
                "features": "3 Eksenli yüksek çözünürlüklü ivmeölçer, I2C/SPI, ~40 µA akım.",
                "pros": "13-bit hassasiyet, endüstriyel güvenilirlik, geniş çalışma aralığı.",
                "cons": "Boyut olarak biraz daha büyük modül."
            }
        ]
    },
    {
        "category": "Mikrokontrolcüler (IoT & Mini Geliştirme Kartları)",
        "keywords": ["esp32", "mcu", "c3", "super mini", "xiao", "s3", "rp2040", "pro mini"],
        "parts": [
            {
                "name": "ESP32-C3 Super Mini",
                "features": "Tek Çekirdek RISC-V 160MHz, Wi-Fi 4 + BLE 5.0, 400KB SRAM, Type-C, ~22x18 mm.",
                "pros": "Kompakt, düşük maliyetli, BLE beacon ve Wi-Fi desteği, derin uykuda ~5 µA tüketim.",
                "cons": "Pin sayısı az (11 GPIO), harici anten konnektörü yok (seramik anteni var)."
            },
            {
                "name": "Seeed Studio XIAO ESP32C3",
                "features": "ESP32-C3 tabanlı, Type-C, yerleşik LiPo şarj devresi ve harici U.FL/IPEX anten soketi.",
                "pros": "Harici anten takılabilir (kutu dışına anten uzatmak için süper), doğrudan pil şarj pini vardır.",
                "cons": "Super Mini klonlarına göre biraz daha pahalıdır."
            },
            {
                "name": "Waveshare ESP32-S3 Zero",
                "features": "Çift Çekirdek Xtensa LX7 240MHz, Wi-Fi + BLE 5, Type-C, yerleşik RGB LED.",
                "pros": "Daha yüksek işlem gücü, yapay zeka/makine öğrenmesi modelleri çalıştırabilir.",
                "cons": "Akım tüketimi C3'e göre biraz daha yüksektir."
            },
            {
                "name": "Arduino Pro Mini (3.3V / 8MHz)",
                "features": "ATmega328P, 3.3V çalışma, dahili kablosuz yok.",
                "pros": "Regülatörsüz derin uyku akımı 1 µA altına iner, aşırı stabildir.",
                "cons": "Wi-Fi ve Bluetooth yoktur; veri aktarımı için harici GSM/LoRa modülü gerekir."
            }
        ]
    },
    {
        "category": "3.3V Düşük Boşta Akımlı LDO Regülatörler",
        "keywords": ["ldo", "regülatör", "ht7833", "me6211", "tps7a02", "xc6206", "ams1117"],
        "parts": [
            {
                "name": "Holtek HT7833",
                "features": "3.3V 500mA Çıkış, Giriş: 8V'a kadar, Boşta Akım (Iq): ~4 µA, SOT-89 / TO-92.",
                "pros": "Pilli sistemler için mükemmel, ESP32'nin anlık 300mA Wi-Fi akım piklerini taşır, uyku akımını tüketmez.",
                "cons": "Kendi başına breakout olarak satılmaz, lehimlenmesi gerekir."
            },
            {
                "name": "MicrOne ME6211",
                "features": "3.3V 500mA Çıkış, Giriş: 6V, Iq: ~40 µA, Enable pini var, SOT-23-5.",
                "pros": "Geliştirme kartlarının çoğunda yerleşik bulunur, düşük drop-out.",
                "cons": "HT7833'e göre uyku akımı 10 kat daha fazladır."
            },
            {
                "name": "Torex XC6206P332MR",
                "features": "3.3V 200mA Çıkış, Iq: ~1 µA, SOT-23.",
                "pros": "Ultra düşük boşta akım (1 µA), çok ucuz.",
                "cons": "Maksimum 200mA verir; ESP32 Wi-Fi piklerinde voltaj çökebilir, 470µF kondansatörle desteklenmelidir."
            },
            {
                "name": "AMS1117-3.3",
                "features": "3.3V 1A Çıkış, Iq: ~5 - 10 mA (MİLİAMPER!).",
                "pros": "Her yerde bulunur, çok ucuz, 1A yüksek akım.",
                "cons": "DİKKAT: Boşta 5-10 mA harcar! 1000mAh pili hiçbir şey yapmadan 4 günde bitirir. PİLLİ PROJELERDE KULLANILMAMALIDIR."
            }
        ]
    },
    {
        "category": "Güç Anahtarlama MOSFET'leri (P-Kanal / N-Kanal)",
        "keywords": ["mosfet", "ao3401", "si2301", "bss84", "2n7002", "bss138"],
        "parts": [
            {
                "name": "AO3401A (P-Kanal MOSFET)",
                "features": "SOT-23 paket, -30V / -4.2A, Rds(on) ~45 mΩ @ 4.5V, Vgs(th) ~0.9V.",
                "pros": "GPS gibi 3.3V çevre birimlerinin VCC hattını mikrokontrolcü GPIO'su ile tamamen kesmek (High-Side Switch) için ideal.",
                "cons": "Ters polariteye dikkat edilmelidir."
            },
            {
                "name": "SI2301DS (P-Kanal MOSFET)",
                "features": "SOT-23, -20V / -2.8A, Rds(on) ~90 mΩ.",
                "pros": "AO3401A yerine doğrudan drop-in muadildir."
            },
            {
                "name": "2N7002 (N-Kanal MOSFET)",
                "features": "SOT-23, 60V / 115mA, Rds(on) ~5 Ω.",
                "pros": "Küçük sinyal seviye dönüştürme ve röle/LED sürme için dünya standardı.",
                "cons": "Direnci yüksektir, yüksek akımlı yüklerde kullanılmaz."
            },
            {
                "name": "BSS138 (N-Kanal MOSFET)",
                "features": "SOT-23, 50V / 220mA, Rds(on) ~3.5 Ω.",
                "pros": "2N7002 yerine doğrudan kullanılabilir, I2C seviye dönüştürücülerde yaygındır."
            }
        ]
    },
    {
        "category": "Pil Şarj ve Koruma Kartları (1S LiPo / Li-ion)",
        "keywords": ["şarj", "lipo şarj", "tp4056", "tp4057", "mcp73831", "ip5306", "pcm", "bms"],
        "parts": [
            {
                "name": "TP4056 Korumalı Modül (DW01 + FS8205A)",
                "features": "1S LiPo/Li-ion 1A şarj, Type-C / Micro-USB giriş, dahili aşırı deşarj ve kısa devre koruması.",
                "pros": "Çok ucuz, hazır modül, pili 2.5V altına inmekten ve aşırı akımdan korur.",
                "cons": "Standart 1A direnci (1.2k) küçük piller için (örn 500mAh) çok yüksektir; Rprog direnci değiştirilmelidir."
            },
            {
                "name": "Microchip MCP73831",
                "features": "SOT-23-5 entegre, programlanabilir şarj akımı (15mA - 500mA), çok düşük kaçak akım.",
                "pros": "Küçük piller için aşırı kararlı ve hassas şarj, profesyonel PCB tasarımları için standart.",
                "cons": "Hazır modül olarak TP4056 kadar yaygın değildir, fiyatı biraz daha yüksektir."
            },
            {
                "name": "1S 3.7V Mini PCM / BMS Koruma Kartı",
                "features": "Sadece pilin uçlarına lehimlenen yuvarlak/dikdörtgen minik koruma devresi (2.4V kesme, 4.28V aşırı şarj).",
                "pros": "Şarj devresinden bağımsız olarak pili korur; korumasız pilleri güvenli hale getirir."
            }
        ]
    }
]


def find_component_equivalents(query: str) -> Optional[Dict[str, Any]]:
    """Girilen parça adı veya kategoriye göre eşdeğer ve muadil parça önerilerini döndürür."""
    q = query.strip().lower()
    
    # Doğrudan eşleşme veya anahtar kelime eşleşmesi ara
    best_match = None
    matched_part = None

    for category_group in EQUIVALENTS_DATABASE:
        # 1. Parça isimleri içinde ara
        for p in category_group["parts"]:
            p_name_lower = p["name"].lower()
            tokens = [t for t in re.split(r'[\s\-_/]+', p_name_lower) if len(t) > 2]
            if any(t in q for t in tokens) or q in p_name_lower or p_name_lower in q:
                best_match = category_group
                matched_part = p
                break
        if best_match:
            break

        # 2. Anahtar kelimelerde ara
        for kw in category_group["keywords"]:
            if kw in q:
                best_match = category_group
                break
        if best_match:
            break

    if not best_match:
        return None

    # Markdown formatında karşılaştırma raporu hazırla
    md = [f"# 🔄 Komponent Eşdeğerlik & Muadil Raporu: {best_match['category']}\n"]
    if matched_part:
        md.append(f"**Aranan Parça:** `{matched_part['name']}`\n")
        md.append(f"📌 **Özellikler:** {matched_part['features']}")
        if "pros" in matched_part:
            md.append(f"✅ **Avantajları:** {matched_part['pros']}")
        if "cons" in matched_part:
            md.append(f"⚠️ **Dezavantajları / Dikkat:** {matched_part['cons']}")
        if "recommendation" in matched_part:
            md.append(f"💡 **Öneri:** {matched_part['recommendation']}")
        md.append("\n### 🔁 Muadil ve Alternatif Parçalar:\n")

    for p in best_match["parts"]:
        if matched_part and p["name"] == matched_part["name"]:
            continue
        md.append(f"- **{p['name']}**")
        md.append(f"  • *Özellikler:* {p['features']}")
        if "pros" in p:
            md.append(f"  • *Avantajları:* {p['pros']}")
        if "cons" in p:
            md.append(f"  • *Dezavantajları:* {p['cons']}")
        if "recommendation" in p:
            md.append(f"  • *Öneri:* {p['recommendation']}")
        md.append("")

    return {
        "query": query,
        "category": best_match["category"],
        "matched_part": matched_part["name"] if matched_part else None,
        "equivalents": best_match["parts"],
        "markdown_report": "\n".join(md)
    }


get_component_equivalents = find_component_equivalents

