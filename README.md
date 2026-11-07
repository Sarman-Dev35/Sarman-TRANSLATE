# Sarman TRANSLATE

AI destekli oyun yerelleştirme aracı. İlk prototip Windows üzerinde kurulu oyunları keşfeder; henüz oyun dosyalarını değiştirmez veya çeviri yaması üretmez.

## Özellikler (ilk prototip)
- Steam kütüphanelerini `libraryfolders.vdf` üzerinden keşfeder.
- Steam `appmanifest_*.acf` dosyalarından kurulu oyunları listeler.
- Epic Games Launcher kurulum manifestlerini tarar.
- Program Files ve yaygın oyun klasörlerini ek keşif kaynağı olarak tarar.
- Bulunan oyunları arama alanıyla filtreler.
- Tarama salt okunurdur; oyun dosyalarına yazmaz.

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
Çıktı: `dist/Sarman TRANSLATE/Sarman TRANSLATE.exe`

## Güvenlik ve kapsam
Bu sürüm yalnızca bilinen kurulum kayıtlarını ve klasör adlarını okur. Rastgele dosya çalıştırmaz, yönetici izni istemez ve oyun dosyalarını değiştirmez. Sonraki aşamalarda dil dosyası analizi, yedekleme, çeviri ve oyuna özgü dil entegrasyonları ayrı ve doğrulanabilir modüller olarak eklenecektir.

## Katkı
Pull request'ler memnuniyetle karşılanır. Oyun motoru entegrasyonları eklenirken yalnızca yerelleştirme verileriyle sınırlı kalınmalıdır.
