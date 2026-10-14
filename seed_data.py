"""
Örnek Elektronik Parça Başlangıç Verisi (Seed Data)
Dirençler, kondansatörler, mikrokontrolcüler, sensörler ve ARIZALI/ÇIKMA parçalar içerir.
"""

import electro_db

SAMPLE_COMPONENTS = [
    # Dirençler (Resistors)
    {
        "name": "10k Ohm Metal Film Direnç",
        "category": "resistor",
        "value": "10kΩ",
        "package": "Through-Hole (THT) 1/4W",
        "quantity": 45,
        "min_quantity": 10,
        "status": "working",
        "location": "Direnç Çekmecesi A-1",
        "notes": "%1 tolerans, mavi gövde",
        "tags": "direnç, pull-up, 10k"
    },
    {
        "name": "220 Ohm Karbon Film Direnç",
        "category": "resistor",
        "value": "220Ω",
        "package": "THT 1/4W",
        "quantity": 30,
        "min_quantity": 10,
        "status": "working",
        "location": "Direnç Çekmecesi A-2",
        "notes": "LED akım sınırlama için ideal",
        "tags": "direnç, led, 220r"
    },
    {
        "name": "1k Ohm Direnç",
        "category": "resistor",
        "value": "1kΩ",
        "package": "THT 1/4W",
        "quantity": 25,
        "min_quantity": 5,
        "status": "working",
        "location": "Direnç Çekmecesi A-3",
        "notes": "%5 tolerans",
        "tags": "direnç, 1k"
    },
    {
        "name": "4.7k Ohm Direnç",
        "category": "resistor",
        "value": "4.7kΩ",
        "package": "THT 1/4W",
        "quantity": 8,
        "min_quantity": 5,
        "status": "working",
        "location": "Direnç Çekmecesi A-4",
        "notes": "I2C ve OneWire (DS18B20) pull-up için",
        "tags": "direnç, i2c, onewire"
    },

    # Kondansatörler (Capacitors)
    {
        "name": "100nF (0.1uF) Seramik Kondansatör",
        "category": "capacitor",
        "value": "100nF",
        "package": "THT 50V",
        "quantity": 50,
        "min_quantity": 15,
        "status": "working",
        "location": "Kondansatör Çekmecesi B-1",
        "notes": "Parazit önleme / Decoupling kondansatörü (104 kodlu)",
        "tags": "kondansatör, 104, decoupling"
    },
    {
        "name": "10uF Elektrolitik Kondansatör",
        "category": "capacitor",
        "value": "10uF",
        "package": "Radial 25V",
        "quantity": 12,
        "min_quantity": 5,
        "status": "working",
        "location": "Kondansatör Çekmecesi B-2",
        "notes": "Kutuplu elektrolitik",
        "tags": "kondansatör, filtre"
    },

    # Yarıiletkenler / Diyot & LED
    {
        "name": "1N4007 Doğrultucu Diyot",
        "category": "diode_led",
        "value": "1000V 1A",
        "package": "DO-41",
        "quantity": 20,
        "min_quantity": 5,
        "status": "working",
        "location": "Yarıiletken Çekmecesi C-1",
        "notes": "Röle bobin koruma (flyback) için kullanılır",
        "tags": "diyot, flyback, koruma"
    },
    {
        "name": "5mm Kırmızı LED",
        "category": "diode_led",
        "value": "2.0V 20mA",
        "package": "5mm Dip",
        "quantity": 40,
        "min_quantity": 10,
        "status": "working",
        "location": "LED Kutusu C-2",
        "notes": "Şeffaf kırmızı",
        "tags": "led, gösterge, kırmızı"
    },

    # Transistörler
    {
        "name": "2N2222 NPN Transistör",
        "category": "transistor",
        "value": "40V 800mA",
        "package": "TO-92",
        "quantity": 15,
        "min_quantity": 5,
        "status": "working",
        "location": "Transistör Çekmecesi C-3",
        "notes": "Genel anahtarlama ve amplifikasyon",
        "tags": "transistor, npn, switch"
    },
    {
        "name": "IRFZ44N N-Kanal Güç MOSFET",
        "category": "transistor",
        "value": "55V 49A",
        "package": "TO-220",
        "quantity": 4,
        "min_quantity": 2,
        "status": "working",
        "location": "Güç Elemanları Çekmecesi C-4",
        "notes": "DC Motor ve yüksek akım şerit LED sürücü için",
        "tags": "mosfet, guc, pwm"
    },

    # Mikrodenetleyiciler & Geliştirme Kartları
    {
        "name": "ESP32 NodeMCU WiFi + Bluetooth Geliştirme Kartı (30 Pin)",
        "category": "ic_mcu",
        "value": "ESP-WROOM-32",
        "package": "DIP-30 Modül",
        "quantity": 2,
        "min_quantity": 1,
        "status": "working",
        "location": "MCU Kutusu D-1",
        "notes": "CP2102 USB çipli, Micro-USB",
        "tags": "esp32, wifi, bluetooth, iot"
    },
    {
        "name": "Arduino Nano V3 (Klon CH340)",
        "category": "ic_mcu",
        "value": "ATmega328P 16MHz",
        "package": "DIP-30 Modül",
        "quantity": 1,
        "min_quantity": 1,
        "status": "working",
        "location": "MCU Kutusu D-2",
        "notes": "Mini-USB bağlantılı, 5V",
        "tags": "arduino, nano, atmega328"
    },

    # Sensörler
    {
        "name": "DHT11 Sıcaklık ve Nem Sensörü",
        "category": "sensor",
        "value": "0-50°C / %20-90 RH",
        "package": "4-Pin Modül",
        "quantity": 2,
        "min_quantity": 1,
        "status": "working",
        "location": "Sensör Kutusu E-1",
        "notes": "Tek hat dijital haberleşme",
        "tags": "sensor, sicaklik, nem, dht11"
    },
    {
        "name": "HC-SR04 Ultrasonik Mesafe Sensörü",
        "category": "sensor",
        "value": "2cm - 400cm",
        "package": "4-Pin Modül",
        "quantity": 2,
        "min_quantity": 1,
        "status": "working",
        "location": "Sensör Kutusu E-2",
        "notes": "5V besleme, Trigger/Echo",
        "tags": "sensor, ultrasonik, mesafe"
    },

    # Modüller
    {
        "name": "5V Tekli Röle Modülü",
        "category": "module",
        "value": "250VAC 10A / 30VDC 10A",
        "package": "Optokuplörlü Modül",
        "quantity": 3,
        "min_quantity": 1,
        "status": "working",
        "location": "Modül Kutusu F-1",
        "notes": "Tetikleme: Low/High seçilebilir",
        "tags": "role, relay, 220v"
    },
    {
        "name": "0.96 Inç I2C OLED Ekran (SSD1306)",
        "category": "module",
        "value": "128x64 Piksel Mavi/Sarı",
        "package": "4-Pin I2C Modül",
        "quantity": 1,
        "min_quantity": 1,
        "status": "working",
        "location": "Ekran Kutusu F-2",
        "notes": "I2C adresi: 0x3C",
        "tags": "ekran, oled, ssd1306, i2c"
    },
    {
        "name": "TP4056 Type-C Lityum Pil Şarj Modülü",
        "category": "power",
        "value": "5V 1A (Korumalı)",
        "package": "Modül",
        "quantity": 5,
        "min_quantity": 2,
        "status": "working",
        "location": "Güç Modülleri F-3",
        "notes": "18650 şarjı için koruma devreli (DW01)",
        "tags": "pil, sarj, tp4056, li-ion"
    },

    # Prototipleme & Bağlantı
    {
        "name": "Erkek-Erkek Jumper Kablo Seti (40 Parça 20cm)",
        "category": "connector",
        "value": "20cm",
        "package": "Dupont",
        "quantity": 2,
        "min_quantity": 1,
        "status": "working",
        "location": "Kablo Askısı G-1",
        "notes": "Breadboard bağlantısı",
        "tags": "kablo, jumper, prototip"
    },
    {
        "name": "MB-102 Şeffaf Breadboard (830 Delikli)",
        "category": "connector",
        "value": "830 Nokta",
        "package": "Standard Breadboard",
        "quantity": 2,
        "min_quantity": 1,
        "status": "working",
        "location": "Çalışma Masası Raf 1",
        "notes": "Güç raylı prototipleme tahtası",
        "tags": "breadboard, devre tahtasi"
    },

    # ⚠️ KULLANICININ ÖZELLİKLE BELİRTTİĞİ ARIZALI / ÇIKMA / ŞÜPHELİ PARÇALAR
    {
        "name": "ESP32 WROOM DevKit (Arızalı Regülatör)",
        "category": "broken_scrap",
        "value": "ESP32 30-Pin",
        "package": "DIP-30",
        "quantity": 1,
        "min_quantity": 0,
        "status": "defective",
        "location": "Arızalı Parça Kutusu #1",
        "notes": "3.3V AMS1117 voltaj regülatörü aşırı ısınıyor ve çöktü. Harici 3.3V verilirse ESP32 çipi sağlam çalışıyor!",
        "tags": "arizali, esp32, regulator, tamir_bekliyor"
    },
    {
        "name": "L298N Çift Motor Sürücü Modülü (Yanık Çip)",
        "category": "broken_scrap",
        "value": "2A Dual H-Bridge",
        "package": "Modül",
        "quantity": 1,
        "min_quantity": 0,
        "status": "defective",
        "location": "Arızalı Parça Kutusu #1",
        "notes": "Klemens kısa devre oldu, L298 entegresi yandı. Soğutucusu ve klemensleri yedek parça olarak sökülebilir.",
        "tags": "arizali, motor, cikma, hurda"
    },
    {
        "name": "SG90 Mikro Servo Motor (Sıyrık Dişli)",
        "category": "broken_scrap",
        "value": "9g Servo",
        "package": "Mikro Servo",
        "quantity": 2,
        "min_quantity": 0,
        "status": "defective",
        "location": "Arızalı Parça Kutusu #2",
        "notes": "Plastik ana dişlilerden biri kırık / sıyırıyor. Küçük DC motoru ve potansiyometresi sağlam, sökülebilir.",
        "tags": "arizali, servo, sg90, cikma"
    },
    {
        "name": "16x2 Karakter LCD Ekran (Mavi Arka Işık)",
        "category": "module",
        "value": "HD44780 1602",
        "package": "16-Pin THT",
        "quantity": 1,
        "min_quantity": 0,
        "status": "untested",
        "location": "Şüpheli Parçalar Çekmecesi",
        "notes": "Eski bir cihazdan söküldü, pinout ve sağlamlık henüz test edilmedi. I2C sırtlığı yok.",
        "tags": "lcd, cikma, test_edilecek"
    },
    {
        "name": "Arduino Uno R3 Klon (USB Tanınmıyor)",
        "category": "broken_scrap",
        "value": "ATmega328P",
        "package": "DIP-28 Soketli",
        "quantity": 1,
        "min_quantity": 0,
        "status": "defective",
        "location": "Arızalı Parça Kutusu #1",
        "notes": "CH340 USB çipi PC tarafından görülmüyor. Ancak ATmega328P mikrodenetleyicisi soketli olduğu için sökülüp sağlam kullanılabilir!",
        "tags": "arizali, arduino, atmega328p, cikma"
    }
]


def seed():
    print("Veritabanı başlatılıyor...")
    electro_db.init_db()

    print(f"{len(SAMPLE_COMPONENTS)} örnek elektronik bileşen ekleniyor...")
    for comp in SAMPLE_COMPONENTS:
        electro_db.add_component(**comp)

    stats = electro_db.get_summary_stats()
    print("\n✅ Başarıyla eklendi! Özet Stok İstatistikleri:")
    print(f" - Toplam Parça Çeşidi: {stats['total_items']}")
    print(f" - Toplam Adet: {stats['total_quantity']}")
    print(f" - Sağlam / Kullanıma Hazır: {stats['working_count']}")
    print(f" - Arızalı / Bozuk Parçalar: {stats['defective_count']}")
    print(f" - Test Bekleyen / Çıkma: {stats['untested_count'] + stats['salvage_count']}")
    print(f" - Kritik Stok Uyarıları: {stats['low_stock_count']}")


if __name__ == "__main__":
    seed()
