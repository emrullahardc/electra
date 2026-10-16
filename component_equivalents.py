"""
ElectroStock - Kapsamlı Elektronik Komponent Eşdeğerlik, Muadil ve Çapraz Referans Motoru
Türkiye ve Dünya Maker/Elektronik Pazarında En Sık Kullanılan Parçalar ve Alternatifleri.

Kapsanan 11 Temel Kategori:
1. Mikrodenetleyiciler & IoT Geliştirme Kartları (ESP32, Arduino, STM32, RP2040)
2. Gerilim Regülatörleri (Linear LDO & Step-Down Buck: 7805, AMS1117, HT7833, LM2596, MP1584)
3. Güç MOSFET'leri & Sinyal Transistörleri (IRFZ44N, IRLZ44N, AO3401, 2N7002, BC547, 2N2222)
4. Doğrultucu & Schottky Diyotlar (1N4007, 1N5819, 1N4148, SS14, SS34)
5. Operasyonel Yükselteçler & Karşılaştırıcılar (LM358, MCP6002, NE5532, LM393, NE555)
6. Sıcaklık, Nem ve Basınç Sensörleri (DHT11, DHT22, AHT20, BME280, BMP280, DS18B20)
7. Hareket & İvmeölçer Sensörleri (LIS3DH, MMA8452Q, MPU6050, ADXL345)
8. Konum & GPS/GNSS Modülleri (NEO-6M, ATGM336H, MAX-M10S, NEO-M8N)
9. Motor Sürücüler (L298N, TB6612FNG, DRV8833, A4988, TMC2209)
10. Kablosuz & Bluetooth Modülleri (HC-05, JDY-31, HM-10, NRF24L01, SIM800L, A7670E)
11. Pil Şarj ve Koruma Devreleri (TP4056, MCP73831, 1S PCM/BMS, IP5306)
"""

import re
from typing import Dict, Any, List, Optional

EQUIVALENTS_DATABASE = [
    # -------------------------------------------------------------
    # 1. GPS / GNSS MODÜLLERİ
    # -------------------------------------------------------------
    {
        "category": "GPS / GNSS Konumlandırma Modülleri",
        "keywords": ["gps", "gnss", "neo-6m", "neo-7m", "neo-m8n", "atgm336h", "max-m10s", "l80", "sim28", "konum"],
        "summary": "Pilli IoT cihazları ve tasmalar için düşük akım tüketimli (ATGM336H / MAX-M10S) alternatifler öne çıkar.",
        "parts": [
            {
                "name": "u-blox NEO-6M",
                "features": "Tek bantlı GPS, UART 9600 bps, 3.3V - 5V çalışma, ~50 mA akım tüketimi.",
                "pros": "Çok yaygın, Arduino kütüphaneleriyle %100 uyumlu, ucuz.",
                "cons": "Sadece GPS destekler (GLONASS/BDS yok), yüksek akım tüketimi (pilli tasmalar için fazla), kapalı alanda zayıf.",
                "recommendation": "Sabit beslemeli prototipler ve araç takip için uygundur."
            },
            {
                "name": "ATGM336H",
                "features": "BDS + GPS çift sistemli GNSS, UART 9600 bps, 3.3V - 5V, ~25 mA akım tüketimi.",
                "pros": "NEO-6M ile pin ve komut uyumlu doğrudan drop-in muadil. Çok daha hızlı fix alır, yarı yarıya daha az güç tüketir.",
                "cons": "Çin menşeili Zhongke Micro üretimi, bazı clone kartlarda seramik anten kalitesi değişken.",
                "recommendation": "NEO-6M yerine en ekonomik ve doğrudan uyumlu alternatiftir."
            },
            {
                "name": "u-blox MAX-M10S",
                "features": "10. Nesil Ultra Düşük Güçlü GNSS (GPS L1 C/A, GLONASS L1, BeiDou B1, Galileo E1), 3.3V, ~10-15 mA akım, tek bant L1.",
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

    # -------------------------------------------------------------
    # 2. İVMEÖLÇER & HAREKET SENSÖRLERİ (IMU)
    # -------------------------------------------------------------
    {
        "category": "İvmeölçer & Hareket Sensörleri (IMU / Accelerometer)",
        "keywords": ["ivmeölçer", "ivme", "accelerometer", "lis3dh", "mma8452", "mpu6050", "adxl345", "bma250", "hareket"],
        "summary": "Pilli projelerde derin uykudan hareketle uyandırma (wake-on-motion) için LIS3DH veya MMA8452Q tercih edilir.",
        "parts": [
            {
                "name": "ST LIS3DH",
                "features": "3 Eksenli ultra düşük güçlü ivmeölçer, I2C/SPI, 2 µA uyku akımı, donanımsal hareket algılama kesmesi (wake-on-motion).",
                "pros": "Hayvan hareketsizken sistemi derin uykuya (deep-sleep) sokup, hayvan hareket edince ESP32'yi uyandırmak için ideal.",
                "cons": "Robotistan'da bazen stok tükenir, Direnç.net veya Robotronik'te bulunur."
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
                "cons": "Jiroskop devredeyken akım tüketimi çok yüksektir (~3.8 mA), pilli takip projeleri için pili çabuk tüketir."
            },
            {
                "name": "Analog Devices ADXL345",
                "features": "3 Eksenli yüksek çözünürlüklü ivmeölçer, I2C/SPI, ~40 µA akım.",
                "pros": "13-bit hassasiyet, endüstriyel güvenilirlik, geniş çalışma aralığı.",
                "cons": "Fiyatı MPU-6050 ve MMA8452'ye göre biraz daha yüksektir."
            }
        ]
    },

    # -------------------------------------------------------------
    # 3. MİKRODENETLEYİCİLER & GELİŞTİRME KARTLARI
    # -------------------------------------------------------------
    {
        "category": "Mikrokontrolcüler & Geliştirme Kartları (MCU)",
        "keywords": ["mcu", "esp32", "c3", "super mini", "xiao", "s3", "rp2040", "pro mini", "arduino", "nano", "uno", "stm32", "bluepill"],
        "summary": "Kompakt IoT için ESP32-C3 Super Mini, yüksek işlem gücü için ESP32-S3, ultra düşük uyku akımı için Pro Mini önerilir.",
        "parts": [
            {
                "name": "ESP32-C3 Super Mini",
                "features": "Tek Çekirdek RISC-V 160MHz, Wi-Fi 4 + BLE 5.0, 400KB SRAM, Type-C, ~22x18 mm.",
                "pros": "Kompakt, düşük maliyetli (~100-140 TL), BLE beacon ve Wi-Fi desteği, derin uykuda ~5 µA tüketim.",
                "cons": "Pin sayısı az (11 GPIO), harici anten konnektörü yok (seramik anteni var)."
            },
            {
                "name": "Seeed Studio XIAO ESP32C3",
                "features": "ESP32-C3 tabanlı, Type-C, yerleşik LiPo şarj devresi ve harici U.FL/IPEX anten soketi.",
                "pros": "Harici anten takılabilir (kutu dışına anten uzatmak için ideal), doğrudan pil şarj pini vardır.",
                "cons": "Super Mini klonlarına göre biraz daha pahalıdır (~200-250 TL)."
            },
            {
                "name": "ESP32 DevKit V1 (ESP-WROOM-32)",
                "features": "Çift Çekirdek Xtensa LX6 240MHz, 30 veya 38 pin, Wi-Fi + Klasik BT + BLE.",
                "pros": "Tüm projeler için evrensel kart, bol GPIO pini, geniş prototipleme alanı.",
                "cons": "Kart üstü AMS1117 ve USB çipi yüzünden derin uykuda bile ~10-15 mA harcar, pilli kullanıma modifikasyonsuz uymaz."
            },
            {
                "name": "Arduino Nano (ATmega328P / CH340)",
                "features": "8-bit AVR 16MHz, 5V çalışma, Mini/Type-C USB, 32KB Flash.",
                "pros": "5V sensör ve röleler için ideal, aşırı yaygın, breadboard uyumlu.",
                "cons": "Kablosuz bağlantı (Wi-Fi/BT) yok, 3.3V IoT cihazlarla doğrudan seviye uyumsuz."
            },
            {
                "name": "STM32F103C8T6 (BluePill)",
                "features": "ARM Cortex-M3 72MHz, 64KB Flash, 20KB SRAM, 3.3V mantık.",
                "pros": "Çok ucuz, Arduino IDE destekli, bol donanımsal timer ve ADC.",
                "cons": "Dahili kablosuz yok, ST-Link programlayıcı gerekebilir."
            },
            {
                "name": "Raspberry Pi Pico (RP2040)",
                "features": "Çift Çekirdek Cortex-M0+ 133MHz, 2MB Flash, PIO (Programlanabilir Giriş/Çıkış).",
                "pros": "Çok esnek donanım zamanlaması (PIO), MicroPython ve C++ desteği, ucuz.",
                "cons": "Temel modelinde Wi-Fi yoktur (Pico W modelinde Wi-Fi vardır)."
            }
        ]
    },

    # -------------------------------------------------------------
    # 4. GERİLİM REGÜLATÖRLERİ (LDO & STEP-DOWN BUCK)
    # -------------------------------------------------------------
    {
        "category": "Gerilim Regülatörleri (Linear LDO & Step-Down Buck)",
        "keywords": ["ldo", "regülatör", "ht7833", "me6211", "tps7a02", "xc6206", "ams1117", "7805", "lm2596", "mp1584", "mini360"],
        "summary": "Pilli projelerde boşta akım (quiescent current) kritiktir. AMS1117 (5mA) pili tüketirken, HT7833 (4µA) aylarca çalıştırır.",
        "parts": [
            {
                "name": "Holtek HT7833",
                "features": "3.3V 500mA Çıkış, Giriş: 8V'a kadar, Boşta Akım (Iq): ~4 µA, SOT-89 / TO-92.",
                "pros": "Pilli sistemler için mükemmel, ESP32'nin anlık 300mA Wi-Fi akım piklerini taşır, uyku akımını tüketmez.",
                "cons": "Genelde DIP/SMD entegre olarak satılır, kart şeklinde modülü nadirdir."
            },
            {
                "name": "Torex XC6206P332MR",
                "features": "3.3V 200mA Çıkış, Iq: ~1 µA, SOT-23.",
                "pros": "Ultra düşük boşta akım (1 µA), çok ucuz (~2-5 TL).",
                "cons": "Maksimum 200mA verir; ESP32 Wi-Fi piklerinde voltaj çökebilir, çıkışa 470µF kondansatör konmalıdır."
            },
            {
                "name": "MicrOne ME6211",
                "features": "3.3V 500mA Çıkış, Giriş: 6V, Iq: ~40 µA, Enable pini var, SOT-23-5.",
                "pros": "Geliştirme kartlarının çoğunda yerleşik bulunur, düşük drop-out.",
                "cons": "HT7833'e göre uyku akımı 10 kat fazladır."
            },
            {
                "name": "AMS1117-3.3",
                "features": "3.3V 1A Çıkış, SOT-223, Boşta Akım: ~5 - 10 mA (MİLİAMPER!).",
                "pros": "Her yerde bulunur, çok ucuz, 1A yüksek akım verir.",
                "cons": "⚠️ DİKKAT: Boşta 5-10 mA harcar! 1000mAh pili hiçbir şey yapmadan 4 günde bitirir. PİLLİ PROJELERDE KULLANILMAMALIDIR."
            },
            {
                "name": "LM7805 (7805)",
                "features": "5V 1.5A Klasik Lineer Regülatör, TO-220.",
                "pros": "Sağlam, yüksek gerilim (35V'a kadar) kaldırır, analog devrelerde gürültüsüz.",
                "cons": "Aşırı ısınır! 12V'tan 5V'a düşürürken enerjinin %58'ini ısı olarak havaya atar. Soğutucu gerektirir."
            },
            {
                "name": "MP1584EN Mini Step-Down Buck Modülü",
                "features": "Giriş: 4.5V-28V, Çıkış: 0.8V-20V ayarlanabilir, 3A, %92 verim, ~22x17 mm.",
                "pros": "7805 ve LM2596 yerine modern, minicik ve ısınmayan en iyi alternatiftir.",
                "cons": "Çıkış voltajını ayarlamak için trimpot tornavida ile ölçülerek ayarlanmalıdır."
            },
            {
                "name": "LM2596 Step-Down Modül",
                "features": "Giriş: 4V-40V, Çıkış: 1.25V-35V, 3A switching buck regülatör.",
                "pros": "Çok yaygın, vidası kolay ayarlanır, ekranlı modelleri vardır.",
                "cons": "Boyut olarak büyüktür (MP1584'ün 3 katı)."
            }
        ]
    },

    # -------------------------------------------------------------
    # 5. GÜÇ MOSFET'LERİ & SİNYAL TRANSİSTÖRLERİ
    # -------------------------------------------------------------
    {
        "category": "Güç MOSFET'leri & Sinyal Transistörleri",
        "keywords": ["mosfet", "transistör", "irfz44n", "irlz44n", "ao3400", "ao3401", "si2301", "2n7002", "bss138", "bc547", "2n2222", "tip120"],
        "summary": "Arduino/ESP32 ile doğrudan MOSFET sürmek için Logic-Level (IRLZ44N, AO3400) seçilmelidir. IRFZ44N 3.3V/5V'ta tam doyuma ulaşmaz.",
        "parts": [
            {
                "name": "IRFZ44N (Standart N-Kanal MOSFET)",
                "features": "TO-220, 55V / 49A, Rds(on) ~17.5 mΩ (10V Gate'te).",
                "pros": "Çok yaygın ve ucuz güç anahtarı.",
                "cons": "⚠️ Gate voltajı 10V ister! ESP32 (3.3V) veya Arduino (5V) ile sürüldüğünde tam açılmaz, aşırı ısınır."
            },
            {
                "name": "IRLZ44N (Logic-Level N-Kanal MOSFET)",
                "features": "TO-220, 55V / 47A, Rds(on) ~22 mΩ @ 4V Gate, 3V'ta iletime geçer.",
                "pros": "IRFZ44N'in DOĞRUDAN MİKROKONTROLCÜ UYUMLU MUADİLİDİR! Arduino ve ESP32 ile doğrudan tam doyumda sürülür.",
                "cons": "IRFZ44N'e göre piyasada bir tık daha az bulunur, Direnç.net ve Robotronik'te vardır."
            },
            {
                "name": "AO3400A (Logic N-Kanal SOT-23)",
                "features": "SOT-23 mini paket, 30V / 5.7A, Rds(on) ~26 mΩ @ 2.5V.",
                "pros": "Minik kartlarda 3-5 Amper motor, LED şerit, selenoid anahtarlamak için 3.3V uyumlu muhteşem MOSFET.",
                "cons": "SMD lehimleme gerektirir."
            },
            {
                "name": "AO3401A (P-Kanal High-Side SOT-23)",
                "features": "SOT-23 paket, -30V / -4.2A, Rds(on) ~45 mΩ @ 4.5V, Vgs(th) ~0.9V.",
                "pros": "GPS, sensör ve ekranların VCC besleme hattını uykuda kesmek (High-Side Switch) için dünya standardı.",
                "cons": "Ters polariteye dikkat edilmelidir."
            },
            {
                "name": "SI2301DS (P-Kanal SOT-23)",
                "features": "SOT-23, -20V / -2.8A, Rds(on) ~90 mΩ.",
                "pros": "AO3401A yerine doğrudan drop-in muadildir."
            },
            {
                "name": "2N7002 / BSS138 (Küçük Sinyal N-MOSFET)",
                "features": "SOT-23, 50V-60V / 200mA.",
                "pros": "I2C çift yönlü mantık seviye dönüştürücüler ve minik röle sürme için standart.",
                "cons": "Akımı düşüktür (200mA altı)."
            },
            {
                "name": "BC547 / 2N2222 (Genel NPN BJT)",
                "features": "TO-92, 40V-45V / 100mA-800mA Bipolar Transistör.",
                "pros": "Temel anahtarlama ve ses yükseltme için her elektronikçide olan parça.",
                "cons": "MOSFET'ler kadar verimli değildir, taban akımı (Ib) çeker."
            },
            {
                "name": "TIP120 / TIP122 (Darlington NPN)",
                "features": "TO-220, 60V-100V / 5A.",
                "pros": "Yüksek kazançlı transistör.",
                "cons": "Üzerinde 1.5V - 2V voltaj düşer, çok ısınır. Yerine IRLZ44N MOSFET kullanmak %100 daha verimlidir."
            }
        ]
    },

    # -------------------------------------------------------------
    # 6. DİYOTLAR & DOĞRULTUCULAR
    # -------------------------------------------------------------
    {
        "category": "Diyotlar & Schottky Doğrultucular",
        "keywords": ["diyot", "diode", "1n4007", "1n4001", "1n5819", "ss14", "1n5822", "ss34", "1n4148", "schottky"],
        "summary": "Pilli ve solar sistemlerde standart silikon diyotlar (0.7V düşüm) yerine Schottky diyot (0.3V düşüm) enerji tasarrufu sağlar.",
        "parts": [
            {
                "name": "1N4007 (1000V / 1A Silikon)",
                "features": "Genel doğrultucu diyot, ters gerilim koruması, Vf: ~0.7V - 1.0V.",
                "pros": "Dünyanın en çok üretilen diyotu, aşırı ucuz.",
                "cons": "Yavaş toparlanma (trr), 0.7V voltaj düşürür (pilli sistemlerde pil voltajını boşuna yer)."
            },
            {
                "name": "1N5819 / SS14 (40V / 1A Schottky)",
                "features": "Schottky bariyer diyot, Vf: ~0.3V - 0.4V, hızlı anahtarlama.",
                "pros": "1N4007 yerine pilli/solar devrelerde voltaj kaybını yarı yarıya düşürür.",
                "cons": "Ters kaçak akımı standart silikon diyotlara göre biraz daha yüksektir."
            },
            {
                "name": "1N5822 / SS34 (40V / 3A Schottky)",
                "features": "3A yüksek akımlı Schottky, Step-Down Buck devrelerinde freewheeling diyotu.",
                "pros": "Motor ters EMF koruması ve yüksek akımlı solar şarj için ideal.",
                "cons": "Fiziksel boyutu 1A diyotlara göre daha büyüktür."
            },
            {
                "name": "1N4148 / LL4148 (Hızlı Küçük Sinyal)",
                "features": "100V / 150mA, trr < 4ns yüksek hızlı silikon diyot.",
                "pros": "Mantık kapıları, sinyal kırpma, röle bobini ters voltaj koruması (flyback) için standart.",
                "cons": "Güç hatlarında doğrultma için kullanılmaz (maksimum 150-200mA)."
            }
        ]
    },

    # -------------------------------------------------------------
    # 7. OPERASYONEL YÜKSELTEÇLER & KARŞILAŞTIRICILAR
    # -------------------------------------------------------------
    {
        "category": "Operasyonel Yükselteçler (Op-Amp) & Karşılaştırıcılar",
        "keywords": ["opamp", "op-amp", "lm358", "mcp6002", "ne5532", "tl072", "lm393", "lm324", "ne555", "timer"],
        "summary": "3.3V tek kaynaklı mikrokontrolcü sistemlerinde LM358 yerine Rail-to-Rail MCP6002 tam 0V-3.3V salınım sağlar.",
        "parts": [
            {
                "name": "TI LM358",
                "features": "Çift Op-Amp, Tek kaynak 3V-32V, DIP-8 / SOIC-8.",
                "pros": "Her sensör modülünde bulunur, aşırı ucuz.",
                "cons": "Çıkışı pozitif beslemenin 1.5V altına kadar çıkabilir (5V beslemede max ~3.5V verir). 3.3V ADC okumalarında Rail-to-Rail değildir."
            },
            {
                "name": "Microchip MCP6002",
                "features": "Çift Op-Amp, 1.8V-6V besleme, Rail-to-Rail Giriş ve Çıkış (RRIO).",
                "pros": "LM358'in 3.3V ve 5V mikrokontrolcüler için MODERN MÜKEMMEL MUADİLİDİR! Çıkışı tam 0V'dan 3.3V'a kadar verir.",
                "cons": "Fiyatı LM358'e göre birkaç lira daha fazladır."
            },
            {
                "name": "TI NE5532",
                "features": "Çift düşük gürültülü yüksek hızlı ses (audio) Op-Amp'ı.",
                "pros": "Ses devrelerinde, pre-amfilerde LM358'den kat kat temiz ses verir.",
                "cons": "Simetrik çift besleme (±5V - ±15V) ister."
            },
            {
                "name": "TI LM393",
                "features": "Çift Karşılaştırıcı (Voltage Comparator), Açık Kollektör (Open-Collector) çıkış.",
                "pros": "Sensör eşik tetiklemelerinde (LDR, ses sensörü vb.) dijital çıkış üretmek için standart.",
                "cons": "Çıkışında pull-up direnci gerektirir."
            },
            {
                "name": "NE555 / TLC555 (Zamanlayıcı Timer)",
                "features": "Monostable / Astable kare dalga ve darbe üreteci.",
                "pros": "Saat frekansı ve PWM üretimi için efsanevi entegre.",
                "cons": "Standart NE555 5V altında kararsızlaşır; 3.3V sistemlerde CMOS versiyonu olan TLC555 veya LMC555 seçilmelidir."
            }
        ]
    },

    # -------------------------------------------------------------
    # 8. SICAKLIK, NEM VE BASINÇ SENSÖRLERİ
    # -------------------------------------------------------------
    {
        "category": "Sıcaklık, Nem ve Hava Kalitesi Sensörleri",
        "keywords": ["sıcaklık", "nem", "dht11", "dht22", "aht10", "aht20", "bme280", "bmp280", "ds18b20", "sht31", "basınç"],
        "summary": "Eski DHT11 yerine I2C üzerinden çok daha kararlı, ucuz ve hassas çalışan AHT20 veya BME280 önerilir.",
        "parts": [
            {
                "name": "DHT11 (Mavi Sensör)",
                "features": "Tek pinli özel protokol, Sıcaklık: 0-50°C (±2°C), Nem: %20-90 (±%5), 1 Hz okuma hızı.",
                "pros": "Çok ucuz, eğitim setlerinde yaygın.",
                "cons": "Hassasiyeti kötüdür, okuma sıklığı 1 saniyeden az olamaz, protokolü zaman zaman kilitlenir."
            },
            {
                "name": "DHT22 / AM2302 (Beyaz Sensör)",
                "features": "Sıcaklık: -40-80°C (±0.5°C), Nem: %0-100 (±%2).",
                "pros": "DHT11 ile aynı kütüphane, çok daha geniş aralık ve hassasiyet.",
                "cons": "Fiyatı BME280 ve AHT20 seviyesine yakındır, boyut olarak büyüktür."
            },
            {
                "name": "Aosong AHT20",
                "features": "I2C Dijital Sıcaklık & Nem, 2.0V - 5.5V, ±0.3°C, ±%2 RH.",
                "pros": "DHT11/DHT22 YERİNE MODERN EN İYİ ALTERNATİF! I2C ile kilitlenme yaşamaz, çok minik ve çok ucuz (~40-60 TL).",
                "cons": "Analog veya tek kablo değil, I2C hattı (SDA/SCL) gerektirir."
            },
            {
                "name": "Bosch BME280",
                "features": "Sıcaklık + Bağıl Nem + Barometrik Basınç (3'ü bir arada), I2C / SPI.",
                "pros": "Hava durumu istasyonları ve irtifa tahmini için altın standart. Aşırı hassas.",
                "cons": "Piyasada sadece basınç ölçen BMP280 ile karıştırılır; satın alırken 6 pinli veya nem özellikli olduğuna dikkat edilmelidir."
            },
            {
                "name": "Maxim DS18B20",
                "features": "1-Wire Dijital Sıcaklık, -55°C ile +125°C, paslanmaz çelik su geçirmez prob seçeneği.",
                "pros": "Su, toprak, kazan, dış ortam sıcaklığı için mükemmel. Tek bir dijital pine onlarca sensör paralel bağlanabilir.",
                "cons": "Sadece sıcaklık ölçer (nem ölçmez), 4.7k pull-up direnci ister."
            }
        ]
    },

    # -------------------------------------------------------------
    # 9. MOTOR SÜRÜCÜLER & RÖLE KARTLARI
    # -------------------------------------------------------------
    {
        "category": "Motor Sürücüler & Röle Modülleri",
        "keywords": ["motor sürücü", "l298n", "l293d", "tb6612", "drv8833", "a4988", "tmc2209", "tmc2208", "röle", "ssr"],
        "summary": "L298N enerji kaybı ve aşırı ısınma nedeniyle günümüzde terk edilmektedir; TB6612FNG veya DRV8833 MOSFET sürücüler %95 verimlidir.",
        "parts": [
            {
                "name": "L298N Çift H-Köprüsü Sürücü",
                "features": "Bipolar transistörlü çift DC motor / 1 Step motor sürücü, 2A kanal başı, 5V-35V.",
                "pros": "Ağır hizmet tipi büyük soğutucu, vidalı klemensler, her yerde bulunur.",
                "cons": "⚠️ Üzerinde 2V - 3V gerilim düşer! Motorlara tam pil voltajı gitmez, aşırı ısınır, 3.3V mantık seviyelerinde kararsızdır."
            },
            {
                "name": "Toshiba TB6612FNG",
                "features": "MOSFET H-Köprüsü, 1.2A sürekli (3.2A pik), 2.5V-13.5V motor, 2.7V-5.5V mantık.",
                "pros": "L298N'İN EN İYİ MODERN MUADİLİDİR! Isınmaz, voltaj düşürmez, miniciktir, 3.3V mikrokontrolcülerle %100 uyumludur.",
                "cons": "Maksimum gerilimi 13.5V ile sınırlıdır (24V motorları süremez)."
            },
            {
                "name": "TI DRV8833",
                "features": "Çift MOSFET köprüsü, 1.5A kanal başı, 2.7V-10.8V motor voltajı.",
                "pros": "Düşük voltajlı (1S LiPo veya 4xAA pil) pilli robotlar için mükemmel verimlilik.",
                "cons": "12V üstü motorlar için uygun değildir."
            },
            {
                "name": "Allegro A4988 (Step Motor Sürücü)",
                "features": "1/16 mikroadım, 35V / 2A, potansiyometre akım ayarlı.",
                "pros": "3D yazıcı ve CNC'lerde en yaygın ve ucuz step sürücü.",
                "cons": "Motor çalışırken tiz bir ıslık/çınlama sesi çıkarır (gürültülüdür)."
            },
            {
                "name": "Trinamic TMC2209 / TMC2208",
                "features": "StealthChop2 ultra sessiz step sürücü, 1/256 mikroadım, StallGuard (sensörsüz limit algılama).",
                "pros": "A4988 yerine drop-in takılır, motor sesini %100 keser, fısıltı sessizliğinde çalışır.",
                "cons": "Fiyatı A4988'in yaklaşık 2-3 katıdır."
            }
        ]
    },

    # -------------------------------------------------------------
    # 10. KABLOSUZ, BLUETOOTH & GSM MODÜLLERİ
    # -------------------------------------------------------------
    {
        "category": "Kablosuz Haberleşme (Bluetooth, RF, GSM / LTE)",
        "keywords": ["bluetooth", "hc-05", "hc-06", "jdy-31", "hm-10", "nrf24l01", "sim800l", "a7670e", "sim7600", "lora", "sx1278"],
        "summary": "SIM800L (2G) kapanan baz istasyonları nedeniyle risklidir; yeni projelerde 4G LTE (A7670E) tercih edilmelidir.",
        "parts": [
            {
                "name": "HC-05 / HC-06 (Bluetooth 2.0 SPP)",
                "features": "Klasik Bluetooth, Seri port (UART) profili, 5V besleme / 3.3V mantık.",
                "pros": "Android telefonlarla seri port gibi bağlanır, kullanımı çok kolaydır.",
                "cons": "iOS (iPhone/iPad) cihazlar klasik Bluetooth 2.0 desteklemez! Yüksek akım tüketir."
            },
            {
                "name": "HM-10 / AT-09 (Bluetooth 4.0 BLE)",
                "features": "Bluetooth Low Energy, UART şeffaf köprü.",
                "pros": "Hem iOS hem Android ile uyumludur, uyku modunda çok düşük akım çeker.",
                "cons": "Klasik Bluetooth SPP terminal uygulamalarıyla doğrudan bağlanmaz, BLE uygulaması gerektirir."
            },
            {
                "name": "JDY-31 Bluetooth Modülü",
                "features": "Bluetooth 3.0 SPP, HC-05/06 pin uyumlu drop-in muadil.",
                "pros": "HC-05'ten yarı yarıya daha ucuzdur (~40-60 TL), doğrudan yerine geçer.",
                "cons": "Sadece Android / PC destekler."
            },
            {
                "name": "SIMCom SIM800L (2G GSM / GPRS)",
                "features": "Dört bant 2G GSM/GPRS, SMS ve TCP/IP veri.",
                "pros": "Çok küçük ve ucuz (~100-150 TL).",
                "cons": "⚠️ DİKKAT: Türkiye'de ve dünyada 2G şebekeleri kademeli olarak kapatılmaktadır! İletişim kopmaları yaşanabilir. Anlık 2A akım pikleri ister."
            },
            {
                "name": "SIMCom A7670E / SIM7600E (4G LTE Cat-1)",
                "features": "4G LTE Cat-1 + 2G Fallback, GNSS opsiyonu, UART / USB.",
                "pros": "Geleceğe hazır, kesintisiz 4G mobil veri, tüm operatörlerle %100 uyumlu.",
                "cons": "SIM800L'e göre daha pahalıdır (~350-600 TL)."
            },
            {
                "name": "Nordic NRF24L01+ (2.4GHz RF)",
                "features": "2.4GHz ISM bant alıcı-verici, SPI arayüz, 250kbps - 2Mbps.",
                "pros": "İki Arduino arasında en ucuz ve en hızlı kablosuz haberleşme kartı.",
                "cons": "ESP32 varsa ESP-NOW protokolü ile NRF24'e hiç gerek kalmadan çok daha hızlı haberleşilir."
            }
        ]
    },

    # -------------------------------------------------------------
    # 11. PİL ŞARJ VE KORUMA DEVRELERİ (1S LiPo / Li-ion)
    # -------------------------------------------------------------
    {
        "category": "Pil Şarj ve Koruma Kartları (1S LiPo / Li-ion)",
        "keywords": ["şarj", "lipo şarj", "tp4056", "tp4057", "mcp73831", "ip5306", "pcm", "bms", "batarya koruma"],
        "summary": "1S LiPo pillerde aşırı deşarj pilin ölmesine yol açar; korumalı TP4056 veya harici PCM kartı şarttır.",
        "parts": [
            {
                "name": "TP4056 Korumalı Modül (DW01 + FS8205A)",
                "features": "1S LiPo/Li-ion 1A şarj, Type-C / Micro-USB giriş, dahili aşırı deşarj (2.5V) ve kısa devre koruması.",
                "pros": "Çok ucuz (~15-20 TL), hazır modül, pili derin deşarjdan ve aşırı akımdan korur.",
                "cons": "Fabrika çıkışı 1A akım küçük piller için (örn 500mAh) fazladır; Rprog direnci değiştirilmelidir."
            },
            {
                "name": "Microchip MCP73831",
                "features": "SOT-23-5 entegre, programlanabilir şarj akımı (15mA - 500mA), çok düşük ters kaçak akım.",
                "pros": "Küçük piller için aşırı kararlı ve hassas şarj, profesyonel PCB tasarımları için altın standart.",
                "cons": "Hazır modül olarak TP4056 kadar bol bulunmaz, entegre olarak satılır."
            },
            {
                "name": "Injoinic IP5306 PowerBank Entegresi",
                "features": "2.1A şarj + 5V 2.4A Senkron Boost dönüştürücü tek çipte, I2C pil yüzdesi takibi.",
                "pros": "Tek pilden hem 5V yüksek akım üretir hem Type-C'den hızlı şarj eder (M5Stack kartlarında kullanılır).",
                "cons": "Düşük akımlı IoT cihazlarda otomatik kapanma (auto-cutoff) yapabilir."
            },
            {
                "name": "1S 3.7V Mini PCM / BMS Koruma Kartı",
                "features": "Sadece pilin uçlarına lehimlenen yuvarlak/dikdörtgen minik koruma devresi (2.4V kesme, 4.28V aşırı şarj).",
                "pros": "Şarj devresinden bağımsız olarak pili doğrudan korur; korumasız pilleri güvenli hale getirir."
            }
        ]
    }
]


def find_component_equivalents(query: str) -> Optional[Dict[str, Any]]:
    """Girilen parça adı veya kategoriye göre eşdeğer ve muadil parça önerilerini döndürür."""
    q = query.strip().lower()
    if not q:
        return None

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
    if "summary" in best_match:
        md.append(f"💡 *Kategori İpucu:* {best_match['summary']}\n")

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


def find_component_equivalents_with_market(query: str, check_market_prices: bool = True) -> Dict[str, Any]:
    """
    Muadil parça önerisi yapar ve isteğe bağlı olarak bulunan alternatiflerin
    Türkiye pazarındaki (Robotronik, Robotistan, Direnç.net, Motorobit) canlı fiyat ve stoklarını getirir.
    """
    eq_res = find_component_equivalents(query)
    
    # Yerleşik veritabanında yoksa genel kategori analizi ve piyasa araması yap
    if not eq_res:
        import market_scraper
        market_res = market_scraper.search_market(query, only_in_stock=True, limit_per_vendor=2)
        md = [f"# 🔍 '{query}' İçin Piyasa Araması & Olası Alternatifler\n"]
        md.append("Bu parça yerleşik muadil kütüphanesinde doğrudan listelenmemiş, ancak Türkiye pazarında bulunan ürünler aşağıdadır:\n")
        for it in market_res.get("results", []):
            md.append(f"- **[{it['vendor']}] [{it['title']}]({it['url']})** — **{it['price']}**")
        
        return {
            "found_in_database": False,
            "query": query,
            "markdown_report": "\n".join(md),
            "market_results": market_res.get("results", [])
        }

    # Yerleşik veritabanında varsa ve piyasa fiyatları isteniyorsa
    if check_market_prices:
        try:
            import market_scraper
            market_lines = ["\n### 💰 Alternatiflerin Canlı Piyasa Fiyatları (Robotronik / Robotistan / Direnç.net / Motorobit):"]
            
            # İlk 2 alternatifi piyasada sorgula
            queried_parts = eq_res["equivalents"][:3]
            for p in queried_parts:
                p_name_short = p["name"].split("(")[0].strip()
                m_res = market_scraper.search_market(p_name_short, only_in_stock=True, limit_per_vendor=1, sort_by_price=True)
                cheapest = m_res.get("cheapest")
                if cheapest:
                    market_lines.append(f"- **{p['name']}**: En uygun **{cheapest['price']}** ([{cheapest['vendor']}]({cheapest['url']}))")
                else:
                    market_lines.append(f"- **{p['name']}**: *Türkiye pazarında aktif stok aranıyor*")

            eq_res["markdown_report"] += "\n" + "\n".join(market_lines)
        except Exception:
            pass

    eq_res["found_in_database"] = True
    return eq_res


get_component_equivalents = find_component_equivalents
