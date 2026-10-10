import yfinance as yf
import requests
import datetime
import time
import pandas as pd
import numpy as np
import os

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

# BIST 100 Hisse Listesi (Geniş Tarama)
BIST_100 = [
    # Holdingler
    "TAVHL.IS", "EKGYO.IS", 
    # Sanayi ve Üretim
    "AKSA.IS", "KRDMA.IS", "KRDMD.IS", "KRDMB.IS", "ISDMR.IS", "EREGL.IS", 
    # Enerji
    "ARFYE.IS", "ENKAI.IS", "GWIND.IS", "SMRTG.IS", "AKSEN.IS", "AYEN.IS", "EUPWR.IS", "EMPA.IS", "BETAE.IS" "ENTRA.IS",
    # Perakende ve Gıda
    "BIMAS.IS", "SOKM.IS", 
    # Teknoloji
    "LOGO.IS", "KONTR.IS", "KLSER.IS", "NETAS.IS", "FORTE.IS", "ALTNY.IS", "NETCD.IS", "SDTTR.IS",
    # Havacılık ve Ulaştırma
    "THYAO.IS", "PGSUS.IS", "TCELL.IS", "TTKOM.IS",
    # Çimento ve Yapı
    "AKCNS.IS", "CIMSA.IS", "NUHCM.IS", "KLKIM.IS", "QUAGR.IS", "BIENY.IS", "BUCIM.IS",
    # Kimya ve İlaç
    "AKSA.IS", "HEKTS.IS", "KMPUR.IS", "SASA.IS", "TKFEN.IS", "TMPOL.IS", "PNLSN.IS",
    # Diğer Popüler
    "LILAK.IS", "OZRDN.IS", "INTET.IS", "MASFN.IS", "UCAYM.IS", "EKIM.IS", "BNTAS.IS", "CGCAM.IS", "ORZAX.IS", "EFOR.IS"
    
]

def telegram_mesaj_gonder(mesaj):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "HTML"}
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram gönderim hatası: {e}")

def rsi_hesapla(veri, periyot=14):
    delta = veri['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periyot).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periyot).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def macd_hesapla(veri, fast=12, slow=26, signal=9):
    ema_fast = veri['Close'].ewm(span=fast, adjust=False).mean()
    ema_slow = veri['Close'].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line.iloc[-1], signal_line.iloc[-1], macd_line.iloc[-2] if len(macd_line) >= 2 else macd_line.iloc[-1]

def bollinger_bands_hesapla(veri, periyot=20, std_dev=2):
    ma = veri['Close'].rolling(window=periyot).mean()
    std = veri['Close'].rolling(window=periyot).std()
    upper = (ma + (std * std_dev))
    lower = (ma - (std * std_dev))
    band_genisligi = (upper - lower) / ma
    min_genislik = band_genisligi.rolling(window=20).min().iloc[-1]
    mevcut_genislik = band_genisligi.iloc[-1]
    sikisma_orani = mevcut_genislik / min_genislik if min_genislik > 0 else 1.0
    return upper.iloc[-1], ma.iloc[-1], lower.iloc[-1], sikisma_orani

def obv_hesapla(veri):
    obv = [0]
    for i in range(1, len(veri)):
        if veri['Close'].iloc[i] > veri['Close'].iloc[i-1]:
            obv.append(obv[-1] + veri['Volume'].iloc[i])
        elif veri['Close'].iloc[i] < veri['Close'].iloc[i-1]:
            obv.append(obv[-1] - veri['Volume'].iloc[i])
        else:
            obv.append(obv[-1])
    obv_series = pd.Series(obv, index=veri.index)
    return obv_series.iloc[-1], obv_series.rolling(window=20).mean().iloc[-1]

def super_sinyal_kontrol(temiz_hisse, fiyat, fiyat_degisim, hacim_orani, 
                         rsi, macd_line, signal_line, macd_dun, 
                         bb_upper, bb_middle, bb_lower, sikisma_orani):
    """Sadece süper sinyal verenleri döndürür"""
    super_al = None
    super_sat = None
    
    # KURAL 1: SÜPER AL - RSI < 30 + Hacim > 2.0x + MACD Al
    if rsi < 30 and hacim_orani > 2.0 and macd_line > signal_line:
        super_al = (
            f"🟢 <b>SÜPER AL: {temiz_hisse}</b>\n"
            f"⚡ RSI: {rsi:.1f} (Aşırı Satım)\n"
            f"⚡ Hacim: {hacim_orani:.2f}x (Patlama!)\n"
            f"⚡ MACD: Al Sinyali\n"
            f"💰 Fiyat: {fiyat:.2f} TL ({fiyat_degisim:+.2f}%)"
        )
    
    # KURAL 2: SÜPER SAT - RSI > 70 + Hacim > 2.0x + MACD Sat
    elif rsi > 70 and hacim_orani > 2.0 and macd_line < signal_line:
        super_sat = (
            f" <b>SÜPER SAT: {temiz_hisse}</b>\n"
            f" RSI: {rsi:.1f} (Aşırı Alım)\n"
            f"⚡ Hacim: {hacim_orani:.2f}x (Patlama!)\n"
            f"⚡ MACD: Sat Sinyali\n"
            f"💰 Fiyat: {fiyat:.2f} TL ({fiyat_degisim:+.2f}%)"
        )
    
    # KURAL 3: MACD SIFIR KESİŞİMİ (YUKARI)
    if macd_dun < 0 and macd_line > 0 and hacim_orani > 1.5:
        super_al = (
            f"⚡ <b>MACD SIFIR KESİŞİMİ (YUKARI): {temiz_hisse}</b>\n"
            f"🔥 MACD sıfırı YUKARI kesti!\n"
            f"⚡ Hacim: {hacim_orani:.2f}x\n"
            f"💰 Fiyat: {fiyat:.2f} TL ({fiyat_degisim:+.2f}%)\n"
            f" Güçlü trend başlangıcı!"
        )
    
    # KURAL 4: MACD SIFIR KESİŞİMİ (AŞAĞI)
    elif macd_dun > 0 and macd_line < 0 and hacim_orani > 1.5:
        super_sat = (
            f"⚡ <b>MACD SIFIR KESİŞİMİ (AŞAĞI): {temiz_hisse}</b>\n"
            f" MACD sıfırı AŞAĞI kesti!\n"
            f" Hacim: {hacim_orani:.2f}x\n"
            f"💰 Fiyat: {fiyat:.2f} TL ({fiyat_degisim:+.2f}%)\n"
            f"📉 Güçlü düşüş başlangıcı!"
        )
    
    # KURAL 5: BB SIKIŞMASI + HACİM (YUKARI PATLAMA)
    if sikisma_orani < 1.3 and hacim_orani > 1.5 and fiyat > bb_middle:
        super_al = (
            f"🎯 <b>BB SIKIŞMASI (YUKARI): {temiz_hisse}</b>\n"
            f"🔔 Band SIKIŞTI ({sikisma_orani:.2f}x)\n"
            f"⚡ Hacim: {hacim_orani:.2f}x\n"
            f"📊 Fiyat orta band ÜSTÜNDE\n"
            f"💰 Fiyat: {fiyat:.2f} TL ({fiyat_degisim:+.2f}%)\n"
            f"🚀 Büyük yükseliş bekleniyor!"
        )
    
    # KURAL 6: BB SIKIŞMASI + HACİM (AŞAĞI PATLAMA)
    elif sikisma_orani < 1.3 and hacim_orani > 1.5 and fiyat < bb_middle:
        super_sat = (
            f"🎯 <b>BB SIKIŞMASI (AŞAĞI): {temiz_hisse}</b>\n"
            f"🔔 Band SIKIŞTI ({sikisma_orani:.2f}x)\n"
            f"⚡ Hacim: {hacim_orani:.2f}x\n"
            f"📊 Fiyat orta band ALTINDA\n"
            f"💰 Fiyat: {fiyat:.2f} TL ({fiyat_degisim:+.2f}%)\n"
            f"⚠️ Büyük düşüş bekleniyor!"
        )
    
    return super_al, super_sat

def hisse_tarama():
    super_al_sinyalleri = []
    super_sat_sinyalleri = []
    taranan = 0
    hata_sayisi = 0
    
    print("\n🔍 BIST 100 Geniş Tarama Başlıyor...")
    print(f"📅 Tarih: {datetime.date.today()}")
    print(f"📊 Toplam {len(BIST_100)} hisse taranacak...")
    print("-" * 60)
    
    for i, hisse in enumerate(BIST_100, 1):
        try:
            ticker = yf.Ticker(hisse)
            veri = ticker.history(period="1y")
            
            if len(veri) < 50:
                continue
            
            taranan += 1
            bugun = veri.iloc[-1]
            dun = veri.iloc[-2]
            
            fiyat = bugun['Close']
            fiyat_degisim = ((bugun['Close'] - dun['Close']) / dun['Close']) * 100
            
            hacim_20g_ort = veri['Volume'].rolling(window=20).mean().iloc[-1]
            hacim_orani = bugun['Volume'] / hacim_20g_ort if hacim_20g_ort > 0 else 0
            
            rsi = rsi_hesapla(veri)
            macd_line, signal_line, macd_dun = macd_hesapla(veri)
            bb_upper, bb_middle, bb_lower, sikisma_orani = bollinger_bands_hesapla(veri)
            obv, obv_ma = obv_hesapla(veri)
            
            temiz_hisse = hisse.replace(".IS", "")
            
            # Süper sinyal kontrolü
            super_al, super_sat = super_sinyal_kontrol(
                temiz_hisse, fiyat, fiyat_degisim, hacim_orani,
                rsi, macd_line, signal_line, macd_dun,
                bb_upper, bb_middle, bb_lower, sikisma_orani
            )
            
            if super_al:
                super_al_sinyalleri.append(super_al)
                print(f"🟢 [{i}/{len(BIST_100)}] {temiz_hisse}: SÜPER AL!")
            
            if super_sat:
                super_sat_sinyalleri.append(super_sat)
                print(f"🔴 [{i}/{len(BIST_100)}] {temiz_hisse}: SÜPER SAT!")
            
            if i % 20 == 0:
                print(f"⏳ İlerleme: {i}/{len(BIST_100)} hisse tarandı...")
            
            time.sleep(0.8)  # Yahoo rate limit için
                
        except Exception as e:
            hata_sayisi += 1
            if hata_sayisi <= 3:
                print(f"❌ [{i}/{len(BIST_100)}] {hisse} hata: {e}")
            continue

    # ========================================================================
    # TELEGRAM MESAJI OLUŞTUR
    # ========================================================================
    toplam_alarm = len(super_al_sinyalleri) + len(super_sat_sinyalleri)
    
    if toplam_alarm > 0:
        # Alarm var!
        mesaj = f"🚨 <b>BIST_TAKIP ALARM RAPORU</b>\n"
        mesaj += f" {datetime.date.today()}\n"
        mesaj += f"📊 Taranan: {taranan} hisse\n"
        mesaj += f"🚨 Toplam Alarm: <b>{toplam_alarm}</b>\n\n"
        
        if super_al_sinyalleri:
            mesaj += f"<b> AL SİNYALLERİ ({len(super_al_sinyalleri)}):</b>\n\n"
            mesaj += "\n\n".join(super_al_sinyalleri)
            mesaj += "\n\n"
        
        if super_sat_sinyalleri:
            mesaj += f"<b> SAT SİNYALLERİ ({len(super_sat_sinyalleri)}):</b>\n\n"
            mesaj += "\n\n".join(super_sat_sinyalleri)
        
        mesaj += "\n\n<i>⚠️ Bu sinyaller nadir kombinasyonlardır. Yatırım tavsiyesi değildir.</i>"
    else:
        # Alarm yok
        mesaj = f"✅ <b>BIST_TAKIP - ALARM YOK</b>\n"
        mesaj += f"📅 {datetime.date.today()}\n"
        mesaj += f"📊 Taranan: {taranan} hisse\n\n"
        mesaj += f"Bugün süper sinyal veren hisse bulunamadı.\n"
        mesaj += f"Piyasa sakin seyrediyor.\n\n"
        mesaj += f"<i>⚠️ Yatırım tavsiyesi değildir.</i>"
    
    telegram_mesaj_gonder(mesaj)
    print("\n" + "=" * 60)
    print(f"✅ Rapor gönderildi! {toplam_alarm} alarm")

if __name__ == "__main__":
    hisse_tarama()