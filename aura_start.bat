@echo off
:: Aura-V Ölümsüzlük Başlatıcı
title AURA-V DIRILIS PROTOKOLU

:: Çalışma dizinini klasörüne odakla
cd /d "C:\Users\volka\AppData\Local\Programs\Python\Python311\deepsekYZ"

echo 🛡️ Aura-V Sistem Cekirdeginde Uyandiriliyor...

:: Python'u tam yol ile calistir (Tirnaklara dikkat!)
"C:\Users\volka\AppData\Local\Programs\Python\Python311\python.exe" "aura_v_ana_kod.py"

echo.
echo ⚠️ Baglanti koptu veya kod durdu.
pause