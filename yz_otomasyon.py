"""
╔══════════════════════════════════════════════════════╗
║         YZ OTOMASYON KONTROL SİSTEMİ v1.0           ║
║         Yerel YZ + USB Donanım Kontrolü             ║
║         Windows / Pico / Arduino / ESP32            ║
╚══════════════════════════════════════════════════════╝

Kurulum:
    pip install pyserial ollama

Ollama model:
    ollama pull gemma2:2b
"""

import tkinter as tk
from tkinter import scrolledtext, ttk
import serial
import serial.tools.list_ports
import threading
import time
import json
import re
import random
import subprocess
import sys
import os
import requests
from datetime import datetime

# ─────────────────────────────────────────────
#  OLLAMA OTOMATİK BAŞLATICI
# ─────────────────────────────────────────────

def ollama_calisiyormu():
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except:
        return False

def ollama_baslat():
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                ["ollama", "serve"],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        else:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        # Başlamasını bekle
        for _ in range(15):
            time.sleep(1)
            if ollama_calisiyormu():
                return True
        return False
    except:
        return False

def model_yukluMu(model_adi):
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        modeller = [m["name"] for m in r.json().get("models", [])]
        return any(model_adi in m for m in modeller)
    except:
        return False

def model_indir(model_adi):
    try:
        subprocess.Popen(
            ["ollama", "pull", model_adi],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        # İndirme tamamlanana kadar bekle (max 5 dakika)
        for _ in range(300):
            time.sleep(1)
            if model_yukluMu(model_adi):
                return True
        return False
    except:
        return False

def sistem_hazirla(durum_cb=None):
    """Ollama başlat, model indir — GUI açılmadan önce çalışır."""
    def bildir(metin):
        if durum_cb:
            durum_cb(metin)

    bildir("Ollama kontrol ediliyor...")
    if not ollama_calisiyormu():
        bildir("Ollama başlatılıyor...")
        ok = ollama_baslat()
        if not ok:
            bildir("⚠️ Ollama başlatılamadı! Lütfen kurun: ollama.com")
            time.sleep(3)
            return False

    bildir("Model kontrol ediliyor...")
    if not model_yukluMu(MODEL_ADI):
        bildir(f"Model indiriliyor: {MODEL_ADI} (birkaç dakika sürebilir...)")
        ok = model_indir(MODEL_ADI)
        if not ok:
            bildir(f"⚠️ Model indirilemedi: {MODEL_ADI}")
            time.sleep(3)
            return False

    bildir("✅ Sistem hazır!")
    time.sleep(1)
    return True

import ollama

# ─────────────────────────────────────────────
#  AYARLAR
# ─────────────────────────────────────────────
MODEL_ADI    = "gemma2:2b"
BAUD_RATE    = 115200
GUNCELLEME   = 500   # ms — sensör okuma aralığı

# Giriş pinleri (sensörler — veri OKUR)
GIRIS_PINLERI = {
    "ISI"    : 0,   # Analog — ısı sensörü
    "NEM"    : 1,   # Analog — nem sensörü
    "YANGIN" : 2,   # Dijital — duman/alev
    "BASINC" : 3,   # Analog — basınç
    "HAVA"   : 4,   # Analog — hava kalitesi
    "GIRIS5" : 5,   # Genel amaçlı
}

# Çıkış pinleri (aktüatörler — KONTROL EDER)
CIKIS_PINLERI = {
    "FAN"      : 10,
    "MOTOR1"   : 11,
    "MOTOR2"   : 12,
    "MOTOR3"   : 13,
    "MOTOR4"   : 14,
    "KLIMA"    : 15,
    "ISIK"     : 16,
    "ALARM"    : 17,
}

# Eşik değerleri (YZ bu değerlere göre karar verir)
ESIKLER = {
    "ISI_MAX"    : 35,   # °C üstü → fan devreye
    "ISI_MIN"    : 10,   # °C altı → ısıtıcı uyarısı
    "NEM_MAX"    : 80,   # % üstü → havalandırma
    "BASINC_MAX" : 700,  # üstü → alarm
}

# ─────────────────────────────────────────────
#  NEON RENK PALETİ
# ─────────────────────────────────────────────
RENKLER = {
    "bg"          : "#0a0a0f",
    "panel"       : "#0f0f1a",
    "panel2"      : "#12121f",
    "neon_cyan"   : "#00fff5",
    "neon_green"  : "#00ff88",
    "neon_red"    : "#ff0044",
    "neon_orange" : "#ff6600",
    "neon_yellow" : "#ffee00",
    "neon_blue"   : "#0088ff",
    "neon_purple" : "#cc00ff",
    "text"        : "#e0e0ff",
    "text_dim"    : "#5a5a8a",
    "border"      : "#1a1a3a",
    "border_glow" : "#00fff520",
}

# ─────────────────────────────────────────────
#  DONANIM YÖNETİCİSİ
# ─────────────────────────────────────────────
class DonarimYonetici:
    def __init__(self):
        self.seri       = None
        self.kart_adi   = "Bağlı değil"
        self.port_adi   = None
        self.bagli      = False
        self.sensor_veri = {k: 0 for k in GIRIS_PINLERI}
        self.cikis_durumu = {k: False for k in CIKIS_PINLERI}

    def kart_tara(self):
        portlar = serial.tools.list_ports.comports()
        bulunanlar = []
        for p in portlar:
            vid = p.vid
            pid = p.pid
            isimler = {
                (0x2E8A, 0x0005): "Raspberry Pi Pico",
                (0x2E8A, 0x000A): "Raspberry Pi Pico W",
                (0x303A, 0x1001): "ESP32-S3",
                (0x303A, 0x6001): "ESP32-C3",
                (0x2341, 0x0043): "Arduino Uno",
                (0x2341, 0x0010): "Arduino Mega",
                (0x10C4, 0xEA60): "ESP32 (CP2102)",
                (0x1A86, 0x7523): "Arduino/ESP (CH340)",
            }
            ad = isimler.get((vid, pid), f"USB Cihaz ({p.description[:20]})")
            bulunanlar.append({"port": p.device, "kart": ad})
        return bulunanlar

    def baglan(self, port):
        try:
            self.seri     = serial.Serial(port, BAUD_RATE, timeout=1)
            self.port_adi = port
            self.bagli    = True
            time.sleep(2)
            kartlar = self.kart_tara()
            for k in kartlar:
                if k["port"] == port:
                    self.kart_adi = k["kart"]
                    break
            return True
        except Exception as e:
            self.bagli = False
            return False

    def baglantiyi_kes(self):
        if self.seri and self.seri.is_open:
            self.seri.close()
        self.bagli    = False
        self.kart_adi = "Bağlı değil"

    def komut_gonder(self, komut_dict):
        if not self.bagli or not self.seri:
            return {"hata": "Bağlı değil"}
        try:
            self.seri.write((json.dumps(komut_dict) + "\n").encode())
            time.sleep(0.05)
            yanit = self.seri.readline().decode().strip()
            return json.loads(yanit) if yanit else {}
        except:
            return {"hata": "İletişim hatası"}

    def pin_yaz(self, pin_no, deger):
        return self.komut_gonder({"cmd": "pin_yaz", "pin": pin_no, "deger": deger})

    def analog_oku(self, pin_no):
        r = self.komut_gonder({"cmd": "analog_oku", "pin": pin_no})
        return r.get("analog", 0)

    def dijital_oku(self, pin_no):
        r = self.komut_gonder({"cmd": "pin_oku", "pin": pin_no})
        return r.get("deger", 0)

    def sensor_guncelle(self):
        """Tüm giriş pinlerini oku."""
        if not self.bagli:
            # Bağlı değilse simüle et (test için)
            self.sensor_veri["ISI"]    = round(random.uniform(20, 45), 1)
            self.sensor_veri["NEM"]    = round(random.uniform(40, 90), 1)
            self.sensor_veri["YANGIN"] = random.choice([0, 0, 0, 1])
            self.sensor_veri["BASINC"] = round(random.uniform(600, 750), 1)
            self.sensor_veri["HAVA"]   = round(random.uniform(100, 800), 0)
            self.sensor_veri["GIRIS5"] = 0
            return

        self.sensor_veri["ISI"]    = round(self.analog_oku(GIRIS_PINLERI["ISI"]) * 3.3 / 4096 * 100, 1)
        self.sensor_veri["NEM"]    = round(self.analog_oku(GIRIS_PINLERI["NEM"]) / 4096 * 100, 1)
        self.sensor_veri["YANGIN"] = self.dijital_oku(GIRIS_PINLERI["YANGIN"])
        self.sensor_veri["BASINC"] = round(self.analog_oku(GIRIS_PINLERI["BASINC"]) * 3.3 / 4096 * 1000, 1)
        self.sensor_veri["HAVA"]   = self.analog_oku(GIRIS_PINLERI["HAVA"])
        self.sensor_veri["GIRIS5"] = self.dijital_oku(GIRIS_PINLERI["GIRIS5"])

    def cikis_toggle(self, ad):
        yeni = not self.cikis_durumu[ad]
        self.cikis_durumu[ad] = yeni
        pin = CIKIS_PINLERI[ad]
        self.pin_yaz(pin, 1 if yeni else 0)
        return yeni

    def acil_stop(self):
        for ad, pin in CIKIS_PINLERI.items():
            self.pin_yaz(pin, 0)
            self.cikis_durumu[ad] = False


# ─────────────────────────────────────────────
#  YZ BEYNİ
# ─────────────────────────────────────────────
class YZBeyin:
    def __init__(self, donarim: DonarimYonetici):
        self.donarim  = donarim
        self.gecmis   = []
        self.otonom   = False

    def sistem_durumu_metin(self):
        v = self.donarim.sensor_veri
        c = self.donarim.cikis_durumu
        return (
            f"SENSÖRLER: Isı={v['ISI']}°C, Nem={v['NEM']}%, "
            f"Yangın={'VAR!' if v['YANGIN'] else 'Yok'}, "
            f"Basınç={v['BASINC']}, Hava={v['HAVA']}\n"
            f"ÇIKIŞLAR: Fan={'ON' if c['FAN'] else 'OFF'}, "
            f"Motor1={'ON' if c['MOTOR1'] else 'OFF'}, "
            f"Klima={'ON' if c['KLIMA'] else 'OFF'}, "
            f"Işık={'ON' if c['ISIK'] else 'OFF'}, "
            f"Alarm={'ON' if c['ALARM'] else 'OFF'}"
        )

    def sor(self, kullanici_mesaji, otonom=False):
        sistem = (
            "Sen endüstriyel bir otomasyon yapay zekasısın. Türkçe konuş.\n"
            "Sensör verilerini analiz et, tehlikeli durumları tespit et, çıkışları kontrol et.\n"
            "Cevabının SONUNA yalnızca şu etiketlerden BİRİNİ ekle (açıklama yapma):\n"
            "[CIKIS:FAN:1] veya [CIKIS:FAN:0] veya [CIKIS:MOTOR1:1] veya [CIKIS:KLIMA:1] "
            "veya [CIKIS:ISIK:1] veya [CIKIS:ALARM:1] veya [CIKIS:YOK]\n"
            "Birden fazla çıkış gerekiyorsa hepsini art arda yaz.\n"
            f"\nANLIK SİSTEM DURUMU:\n{self.sistem_durumu_metin()}\n"
            f"Zaman: {datetime.now().strftime('%H:%M:%S')}"
        )

        mesajlar = [{"role": "system", "content": sistem}]
        for m in self.gecmis[-6:]:
            mesajlar.append(m)
        mesajlar.append({"role": "user", "content": kullanici_mesaji})

        try:
            response = ollama.chat(
                model=MODEL_ADI,
                messages=mesajlar,
                options={"temperature": 0.4, "num_predict": 400, "num_ctx": 2048}
            )
            cevap = response['message']['content'].strip()

            # Komutları yakala ve çalıştır
            komutlar = re.findall(r'\[CIKIS:(\w+):(\w+)\]', cevap)
            for ad, deger in komutlar:
                if ad in CIKIS_PINLERI and deger in ("0", "1"):
                    yeni_deger = deger == "1"
                    self.donarim.cikis_durumu[ad] = yeni_deger
                    self.donarim.pin_yaz(CIKIS_PINLERI[ad], int(deger))

            # Cevabı temizle
            cevap = re.sub(r'\[CIKIS:\w+:\w+\]', '', cevap).strip()
            cevap = re.sub(r'\[CIKIS:YOK\]', '', cevap).strip()
            cevap = re.sub(r'\s{2,}', ' ', cevap).strip()

            self.gecmis.append({"role": "user",      "content": kullanici_mesaji})
            self.gecmis.append({"role": "assistant", "content": cevap})
            if len(self.gecmis) > 20:
                self.gecmis = self.gecmis[-20:]

            return cevap, komutlar

        except Exception as e:
            return f"⚠️ YZ Hatası: {e}", []

    def otonom_analiz(self):
        """Kullanıcı yokken YZ kendi analiz eder."""
        v = self.donarim.sensor_veri
        uyarilar = []

        if v["ISI"] > ESIKLER["ISI_MAX"]:
            uyarilar.append(f"Isı kritik: {v['ISI']}°C")
        if v["NEM"] > ESIKLER["NEM_MAX"]:
            uyarilar.append(f"Nem yüksek: {v['NEM']}%")
        if v["YANGIN"]:
            uyarilar.append("YANGIN ALGILANDI!")
        if v["BASINC"] > ESIKLER["BASINC_MAX"]:
            uyarilar.append(f"Basınç yüksek: {v['BASINC']}")

        if uyarilar:
            soru = f"Uyarılar tespit edildi: {', '.join(uyarilar)}. Ne yapmalıyım?"
            return self.sor(soru, otonom=True)
        return None, []


# ─────────────────────────────────────────────
#  ANA GUI
# ─────────────────────────────────────────────
class OtomasyonGUI:
    def __init__(self):
        self.donarim = DonarimYonetici()
        self.yz      = YZBeyin(self.donarim)
        self.otonom_aktif = False

        self.pencere = tk.Tk()
        self.pencere.title("YZ OTOMASYON SİSTEMİ v1.0")
        self.pencere.configure(bg=RENKLER["bg"])
        self.pencere.geometry("1100x780")
        self.pencere.minsize(900, 650)

        self._arayuz_kur()
        self._sensor_dongusu()

    # ── ARAYÜZ ──────────────────────────────
    def _arayuz_kur(self):
        # Üst başlık
        baslik_frame = tk.Frame(self.pencere, bg=RENKLER["bg"], pady=8)
        baslik_frame.pack(fill=tk.X, padx=15)

        tk.Label(baslik_frame, text="⚡ YZ OTOMASYON KONTROLü",
                 font=("Courier", 18, "bold"),
                 fg=RENKLER["neon_cyan"], bg=RENKLER["bg"]).pack(side=tk.LEFT)

        self.baglanti_label = tk.Label(baslik_frame,
                 text="● BAĞLI DEĞİL",
                 font=("Courier", 10, "bold"),
                 fg=RENKLER["neon_red"], bg=RENKLER["bg"])
        self.baglanti_label.pack(side=tk.RIGHT, padx=10)

        self.saat_label = tk.Label(baslik_frame, text="",
                 font=("Courier", 10),
                 fg=RENKLER["text_dim"], bg=RENKLER["bg"])
        self.saat_label.pack(side=tk.RIGHT, padx=20)

        # Ayırıcı
        tk.Frame(self.pencere, bg=RENKLER["neon_cyan"], height=1).pack(fill=tk.X, padx=15)

        # Ana içerik
        ana = tk.Frame(self.pencere, bg=RENKLER["bg"])
        ana.pack(fill=tk.BOTH, expand=True, padx=15, pady=8)

        # Sol panel
        sol = tk.Frame(ana, bg=RENKLER["bg"], width=320)
        sol.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        sol.pack_propagate(False)

        self._baglanti_paneli(sol)
        self._sensor_paneli(sol)
        self._cikis_paneli(sol)

        # Sağ panel
        sag = tk.Frame(ana, bg=RENKLER["bg"])
        sag.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._yz_paneli(sag)
        self._giris_paneli(sag)

        self._saat_guncelle()

    def _panel_baslik(self, parent, metin, renk=None):
        renk = renk or RENKLER["neon_cyan"]
        f = tk.Frame(parent, bg=RENKLER["panel"], bd=0,
                     highlightbackground=RENKLER["border"], highlightthickness=1)
        f.pack(fill=tk.X, pady=(0, 6))
        tk.Label(f, text=metin, font=("Courier", 9, "bold"),
                 fg=renk, bg=RENKLER["panel"], pady=4).pack()
        return f

    def _baglanti_paneli(self, parent):
        self._panel_baslik(parent, "── BAĞLANTI ──", RENKLER["neon_blue"])

        frame = tk.Frame(parent, bg=RENKLER["panel"],
                         highlightbackground=RENKLER["border"], highlightthickness=1)
        frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(frame, text="Port:", font=("Courier", 9),
                 fg=RENKLER["text_dim"], bg=RENKLER["panel"]).pack(anchor=tk.W, padx=8, pady=(6, 0))

        port_frame = tk.Frame(frame, bg=RENKLER["panel"])
        port_frame.pack(fill=tk.X, padx=8, pady=4)

        self.port_combo = ttk.Combobox(port_frame, width=14, font=("Courier", 9))
        self.port_combo.pack(side=tk.LEFT)

        tk.Button(port_frame, text="🔍", font=("Courier", 9),
                  bg=RENKLER["panel2"], fg=RENKLER["neon_blue"],
                  relief=tk.FLAT, cursor="hand2",
                  command=self._port_tara).pack(side=tk.LEFT, padx=4)

        btn_frame = tk.Frame(frame, bg=RENKLER["panel"])
        btn_frame.pack(fill=tk.X, padx=8, pady=(0, 8))

        self.baglan_btn = tk.Button(btn_frame, text="BAĞLAN",
                  font=("Courier", 9, "bold"),
                  bg=RENKLER["neon_green"], fg=RENKLER["bg"],
                  relief=tk.FLAT, cursor="hand2", padx=10,
                  command=self._baglan_toggle)
        self.baglan_btn.pack(side=tk.LEFT)

        self.kart_label = tk.Label(frame, text="Kart: —",
                  font=("Courier", 8), fg=RENKLER["text_dim"], bg=RENKLER["panel"])
        self.kart_label.pack(anchor=tk.W, padx=8, pady=(0, 6))

        self._port_tara()

    def _sensor_paneli(self, parent):
        self._panel_baslik(parent, "── SENSÖRLER (GİRİŞ) ──", RENKLER["neon_green"])

        frame = tk.Frame(parent, bg=RENKLER["panel"],
                         highlightbackground=RENKLER["border"], highlightthickness=1)
        frame.pack(fill=tk.X, pady=(0, 8))

        self.sensor_labellar = {}
        self.sensor_barlar   = {}

        for i, (ad, _) in enumerate(GIRIS_PINLERI.items()):
            satir = tk.Frame(frame, bg=RENKLER["panel"])
            satir.pack(fill=tk.X, padx=8, pady=2)

            tk.Label(satir, text=f"{ad:<8}", font=("Courier", 8),
                     fg=RENKLER["text_dim"], bg=RENKLER["panel"], width=8, anchor=tk.W).pack(side=tk.LEFT)

            bar = tk.Canvas(satir, width=80, height=10,
                            bg=RENKLER["panel2"], highlightthickness=0)
            bar.pack(side=tk.LEFT, padx=4)
            self.sensor_barlar[ad] = bar

            lbl = tk.Label(satir, text="0", font=("Courier", 8, "bold"),
                           fg=RENKLER["neon_green"], bg=RENKLER["panel"], width=8)
            lbl.pack(side=tk.LEFT)
            self.sensor_labellar[ad] = lbl

        # Boşluk
        tk.Frame(frame, bg=RENKLER["panel"], height=4).pack()

    def _cikis_paneli(self, parent):
        self._panel_baslik(parent, "── ÇIKIŞLAR / KONTROL ──", RENKLER["neon_orange"])

        frame = tk.Frame(parent, bg=RENKLER["panel"],
                         highlightbackground=RENKLER["border"], highlightthickness=1)
        frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.cikis_butonlar = {}

        butonlar = [
            ("FAN",    "🌀 FAN"),
            ("MOTOR1", "⚙ MOTOR1"),
            ("MOTOR2", "⚙ MOTOR2"),
            ("MOTOR3", "⚙ MOTOR3"),
            ("MOTOR4", "⚙ MOTOR4"),
            ("KLIMA",  "❄ KLİMA"),
            ("ISIK",   "💡 IŞIK"),
            ("ALARM",  "🔔 ALARM"),
        ]

        grid = tk.Frame(frame, bg=RENKLER["panel"])
        grid.pack(padx=8, pady=8, fill=tk.X)

        for i, (ad, etiket) in enumerate(butonlar):
            satir = i // 2
            sutun = i % 2
            btn = tk.Button(grid, text=etiket,
                            font=("Courier", 8, "bold"),
                            bg=RENKLER["panel2"],
                            fg=RENKLER["text_dim"],
                            relief=tk.FLAT, cursor="hand2",
                            width=12, pady=4,
                            command=lambda a=ad: self._cikis_toggle(a))
            btn.grid(row=satir, column=sutun, padx=3, pady=3, sticky="ew")
            self.cikis_butonlar[ad] = btn

        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        # Acil Stop
        tk.Button(frame, text="⛔ ACİL STOP",
                  font=("Courier", 11, "bold"),
                  bg=RENKLER["neon_red"], fg="white",
                  relief=tk.FLAT, cursor="hand2", pady=8,
                  command=self._acil_stop).pack(fill=tk.X, padx=8, pady=(4, 8))

    def _yz_paneli(self, parent):
        self._panel_baslik(parent, "── YZ KARAR MERKEZİ ──", RENKLER["neon_purple"])

        frame = tk.Frame(parent, bg=RENKLER["panel"],
                         highlightbackground=RENKLER["border"], highlightthickness=1)
        frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        # Otonom mod butonu
        ust = tk.Frame(frame, bg=RENKLER["panel"])
        ust.pack(fill=tk.X, padx=8, pady=(6, 4))

        self.otonom_btn = tk.Button(ust, text="🤖 OTONOM MOD: KAPALI",
                  font=("Courier", 8, "bold"),
                  bg=RENKLER["panel2"], fg=RENKLER["text_dim"],
                  relief=tk.FLAT, cursor="hand2",
                  command=self._otonom_toggle)
        self.otonom_btn.pack(side=tk.LEFT)

        # YZ log ekranı
        self.yz_log = scrolledtext.ScrolledText(frame,
                  font=("Courier", 9),
                  bg=RENKLER["panel2"], fg=RENKLER["neon_green"],
                  insertbackground=RENKLER["neon_cyan"],
                  relief=tk.FLAT, wrap=tk.WORD,
                  state=tk.DISABLED)
        self.yz_log.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # Renk etiketleri
        self.yz_log.tag_config("yz",      foreground=RENKLER["neon_cyan"])
        self.yz_log.tag_config("kullanici", foreground=RENKLER["neon_yellow"])
        self.yz_log.tag_config("sistem",  foreground=RENKLER["neon_orange"])
        self.yz_log.tag_config("hata",    foreground=RENKLER["neon_red"])
        self.yz_log.tag_config("komut",   foreground=RENKLER["neon_purple"])

    def _giris_paneli(self, parent):
        frame = tk.Frame(parent, bg=RENKLER["bg"])
        frame.pack(fill=tk.X, pady=(0, 4))

        self.giris_entry = tk.Entry(frame,
                  font=("Courier", 11),
                  bg=RENKLER["panel"], fg=RENKLER["neon_cyan"],
                  insertbackground=RENKLER["neon_cyan"],
                  relief=tk.FLAT, bd=8)
        self.giris_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.giris_entry.bind("<Return>", self._mesaj_gonder)

        tk.Button(frame, text="GÖNDER ▶",
                  font=("Courier", 10, "bold"),
                  bg=RENKLER["neon_cyan"], fg=RENKLER["bg"],
                  relief=tk.FLAT, cursor="hand2", padx=12,
                  command=self._mesaj_gonder).pack(side=tk.LEFT)

    # ── OLAYLAR ─────────────────────────────
    def _port_tara(self):
        kartlar = self.donarim.kart_tara()
        portlar = [k["port"] for k in kartlar]
        self.port_combo["values"] = portlar
        if portlar:
            self.port_combo.set(portlar[0])
        else:
            self.port_combo.set("Port bulunamadı")

    def _baglan_toggle(self):
        if self.donarim.bagli:
            self.donarim.baglantiyi_kes()
            self.baglan_btn.config(text="BAĞLAN", bg=RENKLER["neon_green"])
            self.baglanti_label.config(text="● BAĞLI DEĞİL", fg=RENKLER["neon_red"])
            self.kart_label.config(text="Kart: —")
            self._log_yaz("Bağlantı kesildi.\n", "sistem")
        else:
            port = self.port_combo.get()
            if not port or "bulunamadı" in port:
                self._log_yaz("⚠️ Port seçili değil!\n", "hata")
                return
            self._log_yaz(f"Bağlanılıyor: {port}...\n", "sistem")
            ok = self.donarim.baglan(port)
            if ok:
                self.baglan_btn.config(text="KES", bg=RENKLER["neon_red"])
                self.baglanti_label.config(
                    text=f"● {self.donarim.kart_adi}", fg=RENKLER["neon_green"])
                self.kart_label.config(text=f"Kart: {self.donarim.kart_adi}")
                self._log_yaz(f"✅ Bağlandı: {self.donarim.kart_adi}\n", "sistem")
            else:
                self._log_yaz("❌ Bağlantı başarısız!\n", "hata")

    def _cikis_toggle(self, ad):
        yeni = self.donarim.cikis_toggle(ad)
        btn  = self.cikis_butonlar[ad]
        if yeni:
            btn.config(bg=RENKLER["neon_orange"], fg=RENKLER["bg"])
        else:
            btn.config(bg=RENKLER["panel2"], fg=RENKLER["text_dim"])
        durum = "ON" if yeni else "OFF"
        self._log_yaz(f"🔧 Manuel: {ad} → {durum}\n", "sistem")

    def _acil_stop(self):
        self.donarim.acil_stop()
        for ad, btn in self.cikis_butonlar.items():
            btn.config(bg=RENKLER["panel2"], fg=RENKLER["text_dim"])
        self._log_yaz("⛔ ACİL STOP — Tüm çıkışlar kapatıldı!\n", "hata")

    def _otonom_toggle(self):
        self.otonom_aktif = not self.otonom_aktif
        if self.otonom_aktif:
            self.otonom_btn.config(
                text="🤖 OTONOM MOD: AÇIK",
                bg=RENKLER["neon_purple"], fg="white")
            self._log_yaz("🤖 Otonom mod aktif — YZ izlemeye başladı.\n", "komut")
        else:
            self.otonom_btn.config(
                text="🤖 OTONOM MOD: KAPALI",
                bg=RENKLER["panel2"], fg=RENKLER["text_dim"])
            self._log_yaz("🤖 Otonom mod kapatıldı.\n", "sistem")

    def _mesaj_gonder(self, event=None):
        metin = self.giris_entry.get().strip()
        if not metin:
            return
        self.giris_entry.delete(0, tk.END)
        self._log_yaz(f"\n👤 SİZ: {metin}\n", "kullanici")

        def yz_cevapla():
            cevap, komutlar = self.yz.sor(metin)
            self.pencere.after(0, lambda: self._yz_cevap_goster(cevap, komutlar))

        threading.Thread(target=yz_cevapla, daemon=True).start()

    def _yz_cevap_goster(self, cevap, komutlar):
        self._log_yaz(f"🤖 YZ: {cevap}\n", "yz")
        for ad, deger in komutlar:
            if ad in self.cikis_butonlar:
                btn = self.cikis_butonlar[ad]
                if deger == "1":
                    btn.config(bg=RENKLER["neon_orange"], fg=RENKLER["bg"])
                else:
                    btn.config(bg=RENKLER["panel2"], fg=RENKLER["text_dim"])
                self._log_yaz(f"   ⚡ YZ Kararı: {ad} → {'ON' if deger=='1' else 'OFF'}\n", "komut")

    def _log_yaz(self, metin, etiket="yz"):
        self.yz_log.config(state=tk.NORMAL)
        self.yz_log.insert(tk.END, metin, etiket)
        self.yz_log.see(tk.END)
        self.yz_log.config(state=tk.DISABLED)

    # ── DÖNGÜLER ────────────────────────────
    def _sensor_dongusu(self):
        def guncelle():
            self.donarim.sensor_guncelle()
            v = self.donarim.sensor_veri

            # Sensor etiketleri güncelle
            for ad, deger in v.items():
                if ad in self.sensor_labellar:
                    # Renk: tehlike seviyesine göre
                    if ad == "YANGIN" and deger:
                        renk = RENKLER["neon_red"]
                        metin = "YANGIN!"
                    elif ad == "ISI" and deger > ESIKLER["ISI_MAX"]:
                        renk = RENKLER["neon_red"]
                        metin = f"{deger}°C ⚠"
                    elif ad == "NEM" and deger > ESIKLER["NEM_MAX"]:
                        renk = RENKLER["neon_orange"]
                        metin = f"{deger}%"
                    else:
                        renk = RENKLER["neon_green"]
                        metin = str(deger)

                    self.sensor_labellar[ad].config(text=metin, fg=renk)

                    # Bar güncelle
                    if ad in self.sensor_barlar:
                        bar = self.sensor_barlar[ad]
                        bar.delete("all")
                        try:
                            oran = min(float(deger) / 100.0, 1.0)
                        except:
                            oran = 0
                        genislik = int(80 * oran)
                        bar.create_rectangle(0, 0, genislik, 10, fill=renk, outline="")

            # Otonom mod
            if self.otonom_aktif:
                cevap, komutlar = self.yz.otonom_analiz()
                if cevap:
                    self.pencere.after(0, lambda c=cevap, k=komutlar: self._yz_cevap_goster(c, k))

            self.pencere.after(GUNCELLEME, guncelle)

        self.pencere.after(GUNCELLEME, guncelle)

    def _saat_guncelle(self):
        self.saat_label.config(text=datetime.now().strftime("%H:%M:%S"))
        self.pencere.after(1000, self._saat_guncelle)

    def calistir(self):
        self._log_yaz("╔══════════════════════════════════════╗\n", "sistem")
        self._log_yaz("║   YZ OTOMASYON SİSTEMİ v1.0 HAZIR   ║\n", "sistem")
        self._log_yaz("╚══════════════════════════════════════╝\n", "sistem")
        self._log_yaz("USB kart bağla → BAĞLAN → Konuş veya Otonom Mod aç.\n\n", "sistem")
        self.pencere.mainloop()


# ─────────────────────────────────────────────
#  BAŞLAT
# ─────────────────────────────────────────────
if __name__ == "__main__":

    # ── YÜKLEME EKRANI ──────────────────────
    yukleme = tk.Tk()
    yukleme.title("YZ Otomasyon - Başlatılıyor...")
    yukleme.geometry("420x180")
    yukleme.configure(bg="#0a0a0f")
    yukleme.resizable(False, False)
    yukleme.eval('tk::PlaceWindow . center')

    tk.Label(yukleme, text="⚡ YZ OTOMASYON SİSTEMİ",
             font=("Courier", 14, "bold"),
             fg="#00fff5", bg="#0a0a0f").pack(pady=(20, 5))

    durum_lbl = tk.Label(yukleme, text="Başlatılıyor...",
             font=("Courier", 9),
             fg="#5a5a8a", bg="#0a0a0f")
    durum_lbl.pack(pady=5)

    progress = ttk.Progressbar(yukleme, mode="indeterminate", length=340)
    progress.pack(pady=10)
    progress.start(12)

    def durum_guncelle(metin):
        yukleme.after(0, lambda: durum_lbl.config(text=metin))

    def hazirla_ve_ac():
        ok = sistem_hazirla(durum_cb=durum_guncelle)
        def ac():
            progress.stop()
            yukleme.destroy()
            if ok:
                uygulama = OtomasyonGUI()
                uygulama.calistir()
            else:
                hata = tk.Tk()
                hata.title("Hata")
                hata.geometry("380x120")
                hata.configure(bg="#0a0a0f")
                tk.Label(hata, text="❌ Ollama kurulamadı!",
                         font=("Courier", 12, "bold"),
                         fg="#ff0044", bg="#0a0a0f").pack(pady=15)
                tk.Label(hata, text="ollama.com adresinden indirin.",
                         font=("Courier", 9),
                         fg="#5a5a8a", bg="#0a0a0f").pack()
                tk.Button(hata, text="Kapat", command=hata.destroy,
                          bg="#ff0044", fg="white",
                          font=("Courier", 9), relief=tk.FLAT).pack(pady=10)
                hata.mainloop()
        yukleme.after(0, ac)

    threading.Thread(target=hazirla_ve_ac, daemon=True).start()
    yukleme.mainloop()
