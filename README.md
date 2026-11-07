# Sarman TRANSLATE

Sarman TRANSLATE, Windows için oyun yerelleştirme çalışma alanıdır. Kurulu oyunları yerel platform kayıtlarından keşfeder, desteklenen metin dosyalarını tarar, Gemini ile çeviri yapar, çevirileri doğrular ve geri alınabilir ZIP yama paketleri üretir.

> Bu sürüm bir MVP'dir. Her oyun motorunu, şifreli arşivi veya çevrimiçi/anti-cheat oyununu desteklediği iddia edilmez.

## Mevcut özellikler

- Koyu Sarman arayüzü; ölçülü bakır/turuncu vurgu.
- Steam kurulum manifestleri, Epic Launcher `*.item` kayıtları, Windows GameConfigStore ve XboxGames klasörleri üzerinden yerel oyun keşfi.
- Açılışta otomatik oyun kütüphanesi taraması; kullanıcıdan oyun klasörü seçmesini istemez.
- Oyun dosyalarının adlarından ve `Localization` / `Languages` benzeri klasörlerden dil dosyası ipuçları (TR, EN, DE, FR vb.) algılama.
- Her oyun satırında algılanan diller ve etkin Sarman yama dillerini ayrı gösterme.
- Oyun adına, platforma ve yola göre arama.
- JSON, CSV, TXT ve INI metin dosyalarını salt okunur tarama.
- Çeviri Atölyesi: kaynak/çeviri tabloları, elle düzenleme, Gemini kuyruğu ve yerel çalışma kaydı.
- Gemini model listesini API'den alma; kullanıcı kendi API anahtarını ekler.
- Windows kimlik bilgisi kasasında yerel API anahtarı saklama ve silme.
- Yer tutucu/biçim kodu ve satır sonu kalite kontrolü.
- Desteklenen JSON/CSV/TXT/INI dosyalarından manifestli ZIP yama oluşturma.
- Yama paketinde yol geçişi, symlink, dosya sayısı/boyutu, dosya türü ve UTF-8 kontrolleri.
- Yama yüklemeden önce dosya yedeği; işlem hatasında geri sarma ve son yamayı geri alma.
- Kota/bağlantı hatasında tamamlanan çevirileri kaydetme; daha sonra bekleyenleri sürdürme.

## Oyun keşfi ve lisanslar

Oyun keşfi **kurulu oyunları** otomatik bulur; hesapların tüm satın alma geçmişini veya kurulmamış oyun sahipliğini kanıtlamaz. Steam `appmanifest` ve Epic yerel kurulum manifestleri yalnızca kurulu oyunların yerel izleridir. Microsoft Store/Xbox tespiti Windows oyun kayıtlarına ve XboxGames klasörüne dayanır; her Store oyununun erişilebilir oyun dosyası veya yazılabilir kurulum klasörü olacağı garanti edilmez.

Uygulama platform parolası istemez, istemci veritabanlarını kırmaz, lisans/DRM/anti-cheat doğrulamasını aşmaz. Steam, Epic, Microsoft Store/Xbox ve yaygın yerel oyun klasörleri taranır. Desteklenmeyen mağazalar veya özel konumlar otomatik algılanmayabilir; uygulama bu durumda kullanıcıdan oyun dosyalarını seçmesini zorunlu kılmaz.

## Çeviri Atölyesi

1. Oyun kütüphanesinde oyunu seç.
2. **Çeviri Atölyesi** düğmesine bas.
3. **Metinleri tara** ile desteklenen dosyaları keşfet.
4. Ayarlar > Gemini API bölümünde kendi anahtarını ekle ve bağlantıyı test et.
5. **Bekleyenleri çevir** ile sırayı çalıştır. Her tamamlanan satır yerel çalışma dosyasına kaydedilir.
6. Çevirileri tabloda elle düzenleyip gözden geçir.
7. **Yama ZIP'i oluştur** ile dışa aktar.

Çeviri çalışma kayıtları `%LOCALAPPDATA%\Sarman\TRANSLATE\workspaces` altında tutulur. API anahtarı `keyring` üzerinden Windows kimlik bilgisi kasasına yazılır; uygulama kaynak koduna, oyun dosyalarına veya GitHub'a eklenmez.

Gemini kotası Google Cloud projesine ve modele göre değişir. Aynı projede yeni API anahtarı oluşturmak proje kotasını artırmaz. Gerçek kota yenileme zamanı API tarafından kesin verilmediğinde uygulama tahmini geri sayım göstermez. Ücretsiz kullanımın kapsamı Google tarafından belirlenir; ücretsiz erişim veya limitsiz kullanım garantisi yoktur.

## Desteklenen dosya biçimleri ve sınırlar

Şu an çıkarma ve dışa aktarma için doğrulanmış biçimler: **JSON, CSV, TXT, INI**. Kütüphanedeki TR/EN/DE gibi etiketler oyun klasöründeki dil dosyası/klasörü ipuçlarıdır; oyunun bu dili ayarlardan etkinleştirebildiğini garanti etmez. `Sarman yaması` sütunu ise yalnızca Sarman TRANSLATE tarafından yüklenmiş ve kaydı bulunan yamaları gösterir. Diğer dosyalar (XML, RESX, PO, Unity/Unreal paketleri, özel arşivler, ikili varlıklar) bu sürümde otomatik değiştirilmez. Oyun motoruna özgü dil kayıt/etkinleştirme adımları ayrı adaptör gerektirir.

Yama paketi yalnızca UTF-8 JSON/CSV/TXT/INI metin dosyalarını kabul eder. Paket dosyalarını oyuna kopyalamak, oyunun yeni dosya yolunu otomatik olarak yükleyeceğini garanti etmez. İlk denemeyi gerçek oyun yerine test kopyasında yap.

## Yama paketi biçimi

ZIP kökünde `sarman-patch.json` bulunmalıdır:

```json
{
  "name": "Örnek Türkçe Yama",
  "version": "1.0.0",
  "language": "tr",
  "files": [
    {
      "source": "files/lang/tr.json",
      "target": "Game_Data/StreamingAssets/lang/tr.json"
    }
  ]
}
```

- `source`: ZIP içindeki UTF-8 metin dosyası.
- `target`: oyun klasörüne göre göreli hedef.
- Yalnızca `.json`, `.csv`, `.txt`, `.ini` hedefleri kabul edilir.
- Mutlak yollar, `..`, ADS/drive yolları, sembolik bağlantılar, şifreli ZIP girdileri ve aşırı büyük paketler reddedilir.
- Kurulum yalnızca kullanıcı onayıyla yapılır; geri alma için her hedefin önceki durumu yedeklenir.

## Geliştirme ve test

Python 3.11 önerilir.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m compileall -q .
python -m unittest discover -s tests -v
python main.py
```

## Windows güveni ve dijital imza

Windows'ta yayıncı adının güvenilir görünmesi için EXE'nin geçerli bir Authenticode kod imzasıyla imzalanması gerekir. Build workflow'u isteğe bağlı imzalama adımını destekler. GitHub Actions secrets bölümüne `WINDOWS_CERTIFICATE_BASE64` (PFX sertifikasının Base64 içeriği) ve `WINDOWS_CERTIFICATE_PASSWORD` eklenirse EXE SHA-256 ile imzalanır ve imza doğrulanır. PFX dosyası build artifact'ına eklenmez.

Kod imzalama sertifikası satın alınmalı ve yayıncı kimliğiyle eşleşmelidir; bu proje kendiliğinden sertifika üretemez. Sertifika eklenmezse çıktı **imzasız** kalır ve Windows SmartScreen "Bilinmeyen yayıncı" uyarısı gösterebilir. Geçerli imza bile SmartScreen itibarını veya her bilgisayarda uyarısız açılmayı garanti etmez; itibar zamanla ve indirme geçmişiyle oluşabilir. Sertifika/özel anahtar asla Git deposuna konmamalıdır.

## Windows EXE build

Build yalnızca açıkça başlatıldığında/ana dala alındığında çalıştırılmalıdır. Bu feature branch üzerindeki test workflow'u **Windows EXE build başlatmaz**.

```powershell
pip install -r requirements.txt
pyinstaller --noconfirm --clean --windowed --name "Sarman TRANSLATE" --collect-all PySide6 --collect-all keyring main.py
```

Çıktı: `dist/Sarman TRANSLATE/Sarman TRANSLATE.exe`

## Kapsam dışı

- Oynanış, hile, grafik veya rastgele modifikasyon.
- DRM, lisans doğrulaması veya anti-cheat atlatma.
- Korsan oyun/asset dağıtımı.
- Şifreli/özel oyun arşivlerini zorla açma.
- Evrensel oyun uyumluluğu iddiası.

