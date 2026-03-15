import requests

API_KEY  = "dada6312051f5f8a7cad3e9b87cd1034"
BASE_URL = "https://v3.football.api-sports.io"
HEADERS  = {"x-apisports-key": API_KEY}

# Türkiye Süper Lig aktif sezon
r = requests.get(f"{BASE_URL}/leagues", headers=HEADERS, params={"id": 203, "current": "true"})
veri = r.json()
for lig in veri.get('response', []):
    for sezon in lig.get('seasons', []):
        if sezon.get('current'):
            print(f"Aktif Sezon: {sezon['year']}")
            print(f"Başlangıç: {sezon['start']}")
            print(f"Bitiş: {sezon['end']}")
