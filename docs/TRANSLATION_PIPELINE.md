# Sarman TRANSLATE — mevcut MVP mimarisi

## 1. Oyun keşfi

- **Steam:** Steam kayıt konumları, `libraryfolders.vdf` ve `appmanifest_*.acf`.
- **Epic Games:** Epic Launcher'ın yerel `*.item` manifestleri.
- **Microsoft Store / Xbox:** Windows GameConfigStore oyun kayıtları ve `XboxGames` klasörü.
- **Özel kütüphaneler:** Kullanıcının eklediği klasörler ve bilinen Games/Oyunlar dizinleri.

Bunlar yerel kurulum izleridir, tam lisans envanteri değildir. Kurulu olmayan sahip olunan oyunları platform hesaplarından listelemek bu MVP'nin kapsamında değildir. Parola toplama, lisans atlatma veya özel istemci veritabanı okuma yapılmaz.

## 2. Metin çıkarma

`translation_core.py` salt okunur tarama yapar. Şu an JSON string değerleri, CSV hücreleri ve TXT satırları çıkarılır. Boyut ve dosya sayısı sınırları vardır; ikili dosyalar okunmaz. CSV başlıkları için yaygın metin sütunu adları tanınır, başlık bulunamazsa sınırlı sütun aralığı aday kabul edilir.

Her kayıt dosya yolu, alan/satır konumu, kaynak metin, çeviri ve durum taşır. Çalışma dosyası kullanıcı profili altında JSON olarak saklanır. JSON/CSV/TXT dışa aktarımı yeni dosya içeriği üretir; oyun kaynak dosyalarına doğrudan yazmaz.

## 3. Çeviri motoru

`gemini_translator.py` kullanıcının kendi Gemini API anahtarıyla `generateContent` çağrısı yapar. Model adı doğrulanır; geçici sunucu/bağlantı hatalarında sınırlı yeniden deneme yapılır. 429 / RESOURCE_EXHAUSTED durumunda kuyruk duraklatılır. Tamamlanan satırlar anında kaydedilir.

Yer tutucular, format kodları, markup etiketleri ve satır sonları için kalite kontrolü vardır. Otomatik kontrol her dilbilimsel hatayı yakalayamaz; kullanıcı son kontrolü yapmalıdır. Kota limiti Google Cloud projesine bağlıdır; farklı bir API key aynı projede yeni kota sağlamaz.

## 4. Yama üretimi ve kurulum

Çevirilmiş desteklenen dosyalar manifestli ZIP'e alınır. Yükleyici yalnızca UTF-8 JSON/CSV/TXT kabul eder; yol geçişi, symlink, duplicate hedef, şifreli girdiler, dosya adedi/boyutu ve dosya uzantısı kontrolleri uygular. Her dosyanın önceki hali yedeklenir; kurulum hatasında mümkün olduğunca geri sarılır. Geri alma kaydı yerel kullanıcı verisindedir.

Paket dosyalarını oyun klasörüne kopyalamak oyunun bu dosyaları otomatik yükleyeceğini garanti etmez. Oyun motoruna özgü hedef yolu, dil menüsü kaydı veya arşiv entegrasyonu ayrıca geliştirilmelidir.

## 5. Bilinçli sınırlamalar

- XML, RESX, INI, PO, Unity/Unreal asset bundle ve özel arşiv desteği yok.
- Oyunların lisans sahipliği doğrulanmıyor.
- Çevrimiçi/anti-cheat korumalı oyunlara yama uygulama önerilmez.
- Kullanıcı klasöründeki her EXE'nin oyun olduğu kanıtlanamaz; özel klasör taraması aday gösterir.
- Her oyun için ayrı uyumluluk testi gerekir.
