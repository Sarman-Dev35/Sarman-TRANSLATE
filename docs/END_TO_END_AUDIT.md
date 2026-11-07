# Sarman TRANSLATE — main dalı uçtan uca denetimi

Denetim tarihi: 2026-11-07
Denetlenen dal: main
Denetlenen main HEAD: 4450c734d65180d29f92d57fd6845c2d470ad9b6
Son doğrulanan uygulama/test kodu: cb9214d978f5c0e5172c495ce078b5b6aa64aad2

## Bu denetimde bulunan ve düzeltilen sorunlar

1. **Açılışta çift oyun taraması:** Tarama hem MainWindow.__init__ hem de main() içinden zamanlanıyordu. İki QThread art arda başlatılabilir ve ilk thread referansı kaybolabilirdi. İkinci zamanlayıcı kaldırıldı ve start_scan çalışan tarama varken yeniden başlamayacak şekilde korundu.
2. **Eski oyun seçiminin ekranda kalması:** Yeniden tarama sonrası tablo seçimi ve yama hedefi sıfırlanıyor.
3. **Geçersiz ZIP seçimi sonrası eski paket bilgilerinin kalması:** Hatalı paket seçilince etiketler ve kurulum durumu da temizleniyor.
4. **JSON anahtarlarının hatalı eşlenmesi:** Nokta, eğik çizgi, köşeli parantez veya tilde içeren JSON anahtarları artık JSON Pointer kaçışlamasıyla doğru eşleniyor. Eski çalışma dosyalarının locator biçimi için geriye dönük okuma korundu. JSON kök değerinin string olması da destekleniyor.
5. **CSV yerel ayar başlıkları:** key,en-US,fr-FR gibi başlıklar artık İngilizce kaynak sütununu seçiyor; diğer dil sütunları çevrilecek kaynak olarak alınmıyor.
6. **Kaynak metin değişikliği:** Çalışma alanı tarandıktan sonra oyun dosyası değişmiş veya silinmişse eski çeviri yeni metnin üzerine sessizce yazılmıyor; dışa aktarma durdurulup yeniden tarama isteniyor.
7. **Satır sonlarının korunması:** INI/TXT/CSV/JSON dışa aktarımında CRLF/LF satır sonu biçimi korunuyor. Dosya okuma newline normalizasyonu yapmadan gerçekleştiriliyor.
8. **Oyun metni tarama performansı:** Önceki rglob yaklaşımı atlanacak klasörlerin içine de yürüyebiliyordu. Tarama artık dizinleri gezerken Binaries, bin, cache vb. klasörleri önceden buduyor, sembolik bağlantıları atlıyor ve dosya/dizin sayısını sınırlıyor.
9. **Çeviri Atölyesi performansı:** Her çeviri satırında tüm tablo yeniden çizilmiyor. Satır hücreleri yerinde güncelleniyor ve çalışma alanı zamanlayıcılı otomatik kaydediliyor; kota/hata/tamamlanma/kapama anında bekleyen kayıt diske yazılıyor.
10. **Kota testi ile gerçek çeviri kuyruğu arasındaki kopukluk:** Test süresi yerel bir dosyada saklanıyor; süre etkin iken Çeviri Atölyesi'nde kuyruk API çağrısı göndermeden duraklıyor, çalışma kaydediliyor. Süre sona erdiğinde kullanıcı bekleyenleri yeniden başlatabiliyor. Test gerçek Gemini kotasını tüketmiyor.
11. **Gemini model listesi:** models.list sayfalandırması eklendi; yalnızca generateContent destekleyen modeller gösteriliyor. Kullanıcının seçtiği model korunuyor. Eski sabit gemini-2.5-flash fallback kaldırıldı; model listesi API'den alınmadan çeviri başlatılamıyor.
12. **Gemini model uyumluluğu:** Model JSON response mode desteklemiyorsa uygulama prompt ile JSON isteyip yanıtı yine doğrulayarak ikinci bir yola geçebiliyor. HTTP 408 ve geçici 5xx hatalarında Retry-After/exponential backoff kullanılıyor.
13. **API anahtarı güvenliği:** Windows'ta yalnızca WinVaultKeyring/Windows Credential Manager kabul ediliyor. Güvenli backend yoksa API anahtarı güvensiz bir depoya yazılmıyor. Windows smoke testi backend sınıfını doğruluyor.
14. **Yama yolu güvenliği:** Windows için geçersiz karakterler ve CON/PRN/AUX/NUL/COM/LPT gibi ayrılmış aygıt adları reddediliyor.
15. **Hata teşhisi:** Pencere modundaki EXE'de görünmeyebilecek beklenmeyen hatalar yerel, dönen application.log dosyasına yazılıyor. Günlükler %LOCALAPPDATA%/Sarman/TRANSLATE/logs altında tutuluyor.
16. **Build kontrolü:** Windows EXE workflow'u yalnızca elle workflow_dispatch ile başlatılır. Main'e kod gönderilmesi yeni build başlatmaz. Bir sonraki manuel build workflow'unda paketlenmiş EXE'nin 8 saniyelik açılış smoke testi de bulunuyor.

## Otomatik doğrulama

Son başarılı Windows test koşusu:
- Workflow run: 42366203409
- Sonuç: **32 test geçti**
- Python compileall: başarılı
- Birim testleri: başarılı
- Windows masaüstü UI smoke testi: başarılı
- Smoke test; pencere yapısını, 5 sütunlu kütüphaneyi, WinVaultKeyring backend'ini, Çeviri Atölyesi tablosunu, satır güncellemesini, otomatik kaydetme zamanlayıcısını ve Gemini ayar penceresini doğruluyor.

Bu testler kaynak kod ve UI bileşenlerinin otomatik doğrulamasıdır; her gerçek oyunla uyumluluk veya gerçek Gemini hesabıyla çeviri kalitesini kanıtlamaz.

## Gemini API incelemesi

- Uygulama Gemini REST models.list ve models.generateContent uç noktalarını kullanır.
- Model listesi sayfalandırılır; generateContent destekleyen modeller filtrelenir.
- API anahtarı x-goog-api-key başlığında gönderilir; URL'ye eklenmez.
- Çeviri yanıtı JSON olarak istenir ve kayıt kimlikleri/yer tutucular doğrulanır.
- JSON response mode desteklenmeyen modelde prompt tabanlı JSON fallback denenir.
- HTTP 429 veya RESOURCE_EXHAUSTED kota/durum hatası olarak ele alınır; tamamlanan satırlar çalışma dosyasına kaydedilir.
- Geçici 408/5xx hatalarında sınırlı retry/backoff vardır.
- Gerçek ücretsiz kota, erişilebilir model ve limitler Google Cloud projesine göre değişir. Modelin listede görünmesi ücretsiz erişim garantisi değildir.
- Test kotası akışı gerçek API çağrısı yapmadan kuyruk duraklatma davranışını doğrular.
- Otomatik testler API yanıtlarını mock eder; gerçek API anahtarıyla generateContent çağrısı bu denetimde çalıştırılmadı.

Google'ın resmi belgeleri:
- https://ai.google.dev/api/generate-content
- https://ai.google.dev/api/models
- https://ai.google.dev/gemini-api/docs/troubleshooting

## Hâlâ eksik / gerçek test gerektirenler

1. **Gerçek oyun uçtan uca testi yapılmadı.** Deltarune dahil gerçek bir oyunda metin çıkarma, yama üretme, oyunun yamayı yüklemesi ve geri alma doğrulanmadı.
2. **Motor adaptörleri yok:** Unity .assets, Unreal .pak/.locres, GameMaker paketleri, XML/RESX/PO ve özel arşivler için adaptörler gerekli. JSON/CSV/TXT/INI dışındaki formatlar bu sürümde otomatik çevrilmez.
3. **Oyun motoruna yükleme yöntemi:** Metin dosyasını aynı göreli yola kopyalamak oyunun onu okuyacağını garanti etmez. Oyun/engine bazında hedef dosya ve dil etkinleştirme stratejisi gerekir.
4. **Mağaza kapsamı:** Steam, Epic, Windows GameConfigStore, XboxGames ve sınırlı yerel klasör keşfi var. GOG, EA app, Ubisoft Connect, Battle.net ve diğer mağazalar için özel adaptörler eksik.
5. **Lisans sahipliği:** Kurulu oyunları bulur; hesapların kurulmamış oyun kütüphanelerini veya satın alma geçmişini sorgulamaz.
6. **Dil tespiti:** TR/EN/DE etiketleri klasör ve dosya adı ipuçlarıdır; oyunun gerçekten desteklediği dil menülerini doğrulamaz.
7. **Hedef dil seçimi:** Mevcut çeviri akışı varsayılan olarak Türkçe üretir; kullanıcı arayüzünde genel hedef dil seçimi henüz yok.
8. **Windows imzası:** Geçerli Authenticode sertifikası ve GitHub secrets olmadan EXE imzasız kalır. Sarman Studios dosya metadata'sı SmartScreen güveni sağlamaz.
9. **Son EXE build'i:** Denetim kodunu içeren güncel main sürümü henüz build edilmedi. Build workflow'undaki paketlenmiş EXE açılış smoke testi de henüz çalıştırılmadı.
10. **UI manuel görsel testi:** Windows smoke testi bileşenleri oluşturuyor; farklı DPI, ekran boyutları, uzun metinler ve gerçek kullanıcı etkileşimi elle gözden geçirilmedi.

## Build durumu ve güvenlik

Main'e merge işlemi sonrasında eski Windows Build workflow'u push ile otomatik çalıştı ve başarılı oldu. Bu run, eski merge commit'i 8afb040ad03439142e51dee20d1d33e754cece36 içindi; denetim sırasında eklenen son kod değişikliklerini içermiyor. Bu durum fark edilince workflow workflow_dispatch olarak değiştirildi. Bundan sonra kullanıcı açıkça onaylamadan yeni Windows EXE build'i otomatik başlamaz.

## Sonuç

Main dalında açılış taraması, oyun kütüphanesi, JSON/CSV doğruluğu, stale-source koruması, tarama sınırları, çeviri tablosu performansı, kota simülasyonu, Gemini model keşfi ve Windows kimlik bilgisi güvenliği güçlendirildi. **32 otomatik test ve Windows UI smoke testi başarılıdır.** Ancak gerçek oyun adaptörleri, gerçek Gemini isteği, farklı Windows ekran koşulları ve denetim sonrası EXE build'i henüz doğrulanmadı. Son build'den önce Deltarune demo gibi gerçek bir hedef oyun üzerinde salt okunur tarama ve test kopyasında yama denemesi yapılmalıdır.
