# Sarman TRANSLATE

Sarman TRANSLATE, Windows için oyun yerelleştirme çalışma alanıdır. Kurulu oyunları yerel platform kayıtlarından keşfeder, desteklenen metin dosyalarını tarar, yerel sinir ağı modeliyle çeviri yapar, çevirileri doğrular ve geri alınabilir ZIP yama paketleri üretir.

> Bu sürüm bir MVP'dir. Her oyun motorunu, şifreli arşivi veya çevrimiçi/anti-cheat oyununu desteklediği iddia edilmez.

## Mevcut özellikler

- Koyu Sarman arayüzü; ölçülü bakır/turuncu vurgu.
- Steam kurulum manifestleri, Epic Launcher `*.item` kayıtları, Windows GameConfigStore ve XboxGames klasörleri üzerinden yerel oyun keşfi.
- Açılışta otomatik oyun kütüphanesi taraması; kullanıcıdan oyun klasörü seçmesini istemez.
- Oyun dosyalarının adlarından ve `Localization` / `Languages` benzeri klasörlerden dil dosyası ipuçları (TR, EN, DE, FR vb.) algılama.
- Her oyun satırında algılanan diller ve etkin Sarman yama dillerini ayrı gösterme.
- Oyun adına, platforma ve yola göre arama.
- JSON, CSV, TXT ve INI metin dosyalarını salt okunur tarama.
- Çeviri Atölyesi: kaynak/çeviri tabloları, elle düzenleme, yerel çeviri kuyruğu ve yerel çalışma kaydı.
- Argos tabanlı İngilizce → Türkçe yerel sinir ağı modeli; ilk kurulumdan sonra çevrimdışı kullanım.
- Tekrarlanan metinler için SQLite çeviri hafızası ve kullanıcı tarafından düzenlenebilir oyun terimleri sözlüğü.
- Yer tutucu/biçim kodu ve satır sonu kalite kontrolü.
- Desteklenen JSON/CSV/TXT/INI dosyalarından manifestli ZIP yama oluşturma.
- Yama paketinde yol geçişi, symlink, dosya sayısı/boyutu, dosya türü ve UTF-8 kontrolleri.
- Yama yüklemeden önce dosya yedeği; işlem hatasında geri sarma ve son yamayı geri alma.
- Tamamlanan çevirileri otomatik kaydetme; kesilen işlere daha sonra devam etme.
- Seçili oyun için tüm Sarman yamalarını yedeklerden geri yükleyerek topluca kaldırma.

## Oyun keşfi ve lisanslar

Oyun keşfi **kurulu oyunları** otomatik bulur; hesapların tüm satın alma geçmişini veya kurulmamış oyun sahipliğini kanıtlamaz. Steam `appmanifest` ve Epic yerel kurulum manifestleri yalnızca kurulu oyunların yerel izleridir. Microsoft Store/Xbox tespiti Windows oyun kayıtlarına ve XboxGames klasörüne dayanır; her Store oyununun erişilebilir oyun dosyası veya yazılabilir kurulum klasörü olacağı garanti edilmez.

Uygulama platform parolası istemez, istemci veritabanlarını kırmaz, lisans/DRM/anti-cheat doğrulamasını aşmaz. Steam, Epic, Microsoft Store/Xbox ve yaygın yerel oyun klasörleri taranır. Desteklenmeyen mağazalar veya özel konumlar otomatik algılanmayabilir; uygulama bu durumda kullanıcıdan oyun dosyalarını seçmesini zorunlu kılmaz.

## Çeviri Atölyesi

1. Oyun kütüphanesinde oyunu seç.
2. **Çeviri Atölyesi** düğmesine bas.
3. **Metinleri tara** ile desteklenen dosyaları keşfet.
4. **Yerel modeli kur** ile İngilizce → Türkçe modelini bir kez indir.
5. **Bekleyenleri çevir** ile çevrimdışı çeviriyi başlat. Terim sözlüğünden oyuna özel karşılıklar ekleyebilirsin.
6. Çevirileri tabloda elle düzenleyip gözden geçir.
7. **Yama ZIP'i oluştur** ile dışa aktar.

Çeviri çalışma kayıtları `%LOCALAPPDATA%\Sarman\TRANSLATE\workspaces` altında tutulur. API anahtarı yalnızca Windows Credential Manager (WinVaultKeyring) üzerinden saklanır; güvenli backend yoksa kaydetme reddedilir. Anahtar kaynak koduna, oyun dosyalarına veya GitHub'a eklenmez. Beklenmeyen uygulama hataları `%LOCALAPPDATA%\Sarman\TRANSLATE\logs\application.log` dosyasına dönen günlüklerle kaydedilir.

Gemini kotası Google Cloud projesine ve modele göre değişir. Aynı projede yeni API anahtarı oluşturmak proje kotasını artırmaz. Gerçek kota yenileme zamanı API tarafından kesin verilmediğinde uygulama tahmini geri sayım göstermez. Ücretsiz kullanımın kapsamı Google tarafından belirlenir; ücretsiz erişim veya limitsiz kullanım garantisi yoktur. Gemini model listesi `models.list` sayfaları üzerinden alınır ve `generateContent` destekleyen modeller filtrelenir; listelenen modelin ücretsiz veya bu projede kullanılabilir olduğu garanti edilmez.

Kota akışını gerçek API kotasını tüketmeden denemek için Gemini API penceresindeki test komutlarından birini kullan: `/kotabitimiuyarısı1dk`, `/kotabitimiuyarısı1saat` veya `/kotabitimiuyarısıgünlük`. Sayaç çalışırken ayar penceresini kapatıp Çeviri Atölyesi'nde bekleyen çeviriyi başlat. Kuyruk API isteği göndermeden test amaçlı duraklatılır, çalışma kaydedilir; süre sona erdiğinde yeniden **Bekleyenleri çevir** ile devam edebilirsin. Bu simülasyon gerçek Gemini kotasını tüketmez.

## Desteklenen dosya biçimleri ve sınırlar

Şu an çıkarma ve dışa aktarma için doğrulanmış biçimler: **JSON, CSV, TXT, INI**. Kütüphanedeki TR/EN/DE gibi etiketler oyun klasöründeki dil dosyası/klasörü ipuçlarıdır; oyunun bu dili ayarlardan etkinleştirebildiğini garanti etmez. `Sarman yaması` sütunu ise yalnızca Sarman TRANSLATE tarafından yüklenmiş ve kaydı bulunan yamaları gösterir. Diğer dosyalar (XML, RESX, PO, Unity/Unreal paketleri, özel arşivler, ikili varlıklar) bu sürümde otomatik değiştirilmez. Oyun motoruna özgü dil kayıt/etkinleştirme adımları ayrı adaptör gerektirir.

Yama paketi yalnızca UTF-8 JSON/CSV/TXT/INI metin dosyalarını kabul eder. Paket dosyalarını oyuna kopyalamak, oyunun yeni dosya yolunu otomatik olarak yükleyeceğini garanti etmez. İlk denemeyi gerçek oyun yerine test kopyasında yap.

## Motor algılama ve uyumluluk raporu

Çeviri Atölyesi artık oyun klasörünü salt okunur biçimde inceleyerek GameMaker, Unity, Unreal Engine, Godot, Ren'Py ve RPG Maker için motor ipuçlarını ve desteklenen metin dosyalarının sayısını gösterir. Bu bir uyumluluk garantisi değildir; özel ikili biçimleri otomatik açmaz. Motorlara göre gerçek destek sınırları, araştırma bağlantıları ve güvenli adaptör tasarımı için [`docs/ENGINE_SUPPORT.md`](docs/ENGINE_SUPPORT.md) dosyasına bak.

Dışa aktarma sırasında UTF-8 BOM, JSON girintisi/ASCII kaçış tercihi ve son satır sonu korunmaya çalışılır. CSV/TSV için ayraç, tırnaklama ve satır sonu kaynağa göre algılanır. Bu koruma oyun motorunun dosyayı kabul edeceği anlamına gelmez; her oyunda kopya üzerinde doğrulama gerekir.

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

Windows'ta yayıncı adının güvenilir görünmesi için EXE'nin geçerli bir Authenticode kod imzasıyla imzalanması gerekir. Build workflow'u isteğe bağlı imzalama adımını destekler. GitHub Actions secrets bölümüne `WINDOWS_CERTIFICATE_BASE64` (PFX sertifikasının Base64 içeriği) ve `WINDOWS_CERTIFICATE_PASSWORD` eklenirse paket içindeki `.exe`, `.dll` ve `.pyd` dosyaları SHA-256 ile imzalanır; her dosyanın imzası `signtool verify /pa` ile doğrulanır. PFX dosyası build artifact'ına eklenmez. Sertifika yoksa workflow yalnızca uyarı verir ve imzasız geliştirme çıktısı üretir.

Kod imzalama sertifikası satın alınmalı ve yayıncı kimliğiyle eşleşmelidir; bu proje kendiliğinden sertifika üretemez. Sertifika eklenmezse çıktı **imzasız** kalır ve Windows SmartScreen "Bilinmeyen yayıncı" uyarısı gösterebilir. Geçerli imza bile SmartScreen veya Smart App Control tarafından her bilgisayarda otomatik izin verileceğini garanti etmez. Smart App Control ayrıca Microsoft'un bulut tabanlı uygulama güvenliği/itibar değerlendirmesini yapar; imza tek başına kesin geçiş bileti değildir. İmzasız bir dosya için güvenlik korumalarını kapatmak yerine yayıncı sertifikası, temiz build zinciri ve Microsoft'un itibar değerlendirmesi kullanılmalıdır. Sertifika/özel anahtar asla Git deposuna konmamalıdır.

## Windows EXE build

Windows EXE build workflow'u yalnızca GitHub Actions içinden elle başlatılır (**workflow_dispatch**). Kodun main dalına gönderilmesi artık otomatik EXE build başlatmaz; bu, denetim ve test tamamlanmadan build alınmasını önler.

```powershell
pip install -r requirements.txt
pyinstaller --noconfirm --clean --windowed --name "Sarman TRANSLATE" --version-file version_info.txt --collect-all PySide6 --collect-all keyring --copy-metadata keyring main.py
```

Çıktı: `dist/Sarman TRANSLATE/Sarman TRANSLATE.exe`

## Kapsam dışı

- Oynanış, hile, grafik veya rastgele modifikasyon.
- DRM, lisans doğrulaması veya anti-cheat atlatma.
- Korsan oyun/asset dağıtımı.
- Şifreli/özel oyun arşivlerini zorla açma.
- Evrensel oyun uyumluluğu iddiası.

