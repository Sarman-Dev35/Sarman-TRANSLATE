# Sarman TRANSLATE

Sarman TRANSLATE, oyunların metinlerini/dil dosyalarını bulmaya ve yerelleştirme yamalarını yönetmeye odaklanan hafif bir masaüstü aracıdır. Yapay zekâ zorunlu değildir: temel algılama ve dosya işlemleri yerel, küçük Python modülleriyle çalışır. İleride isteğe bağlı çeviri sağlayıcıları eklenebilir.

## Mevcut masaüstü prototipi
- Koyu, sade arayüz; Sarman turuncusu vurgu rengi.
- Steam kütüphanelerini ve kurulu oyun manifestlerini keşfeder.
- Epic Games Launcher kurulum manifestlerini tarar.
- Yaygın oyun klasörlerini ek kaynak olarak tarar.
- Oyunları arama ve seçme.
- Yama Merkezi üzerinden uyumlu ZIP yama paketini seçme, doğrulama ve hedef oyuna yükleme.
- Var olan hedef dosyalar için yerel yedek oluşturma ve son Sarman yamasını geri alma.
- Oyun taraması salt okunurdur. Yama yükleme yalnızca kullanıcı onayıyla yapılır.

## Yama paketi biçimi

Yama, kök dizininde sarman-patch.json bulunan bir ZIP dosyası olmalıdır. Dosyalar paket içinde belirtilen kaynak konumlarında bulunur.

Örnek paket yapısı:

```text
MyTurkishPatch.zip
├── sarman-patch.json
└── files/
    ├── lang/
    │   └── tr.json
    └── localization/
        └── strings.csv
```

Örnek manifest:

```json
{
  "name": "Örnek Türkçe Yama",
  "version": "1.0.0",
  "files": [
    {
      "source": "files/lang/tr.json",
      "target": "Game_Data/StreamingAssets/lang/tr.json"
    },
    {
      "source": "files/localization/strings.csv",
      "target": "Game_Data/Localization/strings.csv"
    }
  ]
}
```

- source: ZIP içindeki dosyanın yolu.
- target: seçilen oyun klasörüne göre göreli hedef yol.
- Mutlak yollar ve .. ile oyun klasörü dışına çıkma reddedilir.
- Paket kendi başına bir oyun dilini etkinleştirmeyi garanti etmez. Oyunun dil menüsüne yeni dil ekleme yöntemi oyun/engine entegrasyonuna bağlıdır.
- Yalnızca güvendiğin kaynaklardan indirdiğin yamaları kullan. Çevrimiçi/anti-cheat korumalı oyunlarda dosya yaması uygulama.

## Geliştirme

Python 3.11 veya üzeri önerilir.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Windows EXE derleme

```powershell
pip install -r requirements.txt
pyinstaller --noconfirm --clean --windowed --name "Sarman TRANSLATE" --collect-all PySide6 main.py
```

Çıktı: dist/Sarman TRANSLATE/Sarman TRANSLATE.exe

## Güvenlik ve kapsam

Bu prototip genel amaçlı mod yöneticisi değildir; yalnızca yerelleştirme/dil dosyası paketleri için tasarlanır. Oyun dosyaları tarama sırasında değiştirilmez. Yama yüklenirken mevcut dosyalar kullanıcı profili altındaki Sarman yedek klasörüne kopyalanır; yeni dosyalar için geri alma kaydı tutulur. Oyun dosyalarını değiştiren işlemlerden önce onay istenir.

Her oyun aynı dil dosyası biçimini kullanmaz. Unity, Unreal ve özel motorlar için uygun çıkarıcılar/entegrasyonlar ayrıca geliştirilecektir. Şu anki ZIP yükleyicisi, yalnızca dosyaları manifestteki hedeflere kopyalayabilen oyun yamalarını destekler; dil menüsüne otomatik kayıt her oyunda mümkün değildir.

## Katkı

Dil profilleri, dosya biçimi çözücüleri, kalite kontrolleri ve oyun motoru yerelleştirme entegrasyonları için katkılar memnuniyetle karşılanır. Oynanış veya hile modifikasyonları kapsam dışıdır.
