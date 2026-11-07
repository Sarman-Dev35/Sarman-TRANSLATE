# Sarman TRANSLATE — main dalı uçtan uca denetimi

Denetim tarihi: 2026-11-07
Denetlenen dal: main
Denetlenen son uygulama kodu: d6e58d39c6dcf46deb6b8b780140e91e315d138
Dokümantasyon güncellemesi: e009b12178cd7e356eb57bf2ea489fd803958a9d

## Bu denetimde bulunan ve düzeltilen sorunlar

1. **Açılışta çift oyun taraması:** Tarama hem MainWindow.__init__ hem de main() içinden zamanlanıyordu. İki QThread art arda başlatılabilir ve ilk thread referansı kaybolabilirdi. İkinci zamanlayıcı kaldırıldı ve start_scan çalışan tarama varken yeniden başlamayacak şekilde korundu.
2. **Eski oyun seçiminin ekranda kalması:** Yeniden tarama sonrası tablo seçimi ve yama hedefi sıfırlanıyor.
3. **Geçersiz ZIP seçimi sonrası eski paket bilgilerinin kalması:** Hatalı paket seçilince etiketler ve kurulum durumu da temizleniyor.
4. **JSON anahtarlarının hatalı eşlenmesi:** Nokta, eğik çizgi, köşeli parantez veya tilde içeren JSON anahtarları eski nokta-ayraçlı konum biçiminde güvenilir şekilde dışa aktarılamıyordu. Yeni kayıtlar JSON Pointer kaçışlaması kullanıyor; eski çalışma dosyaları için geriye dönük okuma korunuyor.
5. **CSV yerel ayar başlıkları:** key,en-US,fr-FR gibi başlıklar artık İngilizce kaynak sütununu seçiyor; diğer dil sütunları çevrilecek kaynak olarak alınmıyor.
6. **Oyun metni tarama performansı:** Önceki rglob yaklaşımı atlanacak klasörlerin içine de yürüyebiliyordu. Tarama artık dizinleri gezerken Binaries, bin, cache vb. klasörleri önceden buduyor, sembolik bağlantıları atlıyor ve dosya/dizin sayısını sınırlıyor.
7. **Kota testi ile gerçek çeviri kuyruğu arasındaki kopukluk:** Önceki komut yalnızca ayarlar penceresinde sayaç gösteriyordu. Şimdi test süresi yerel bir dosyada saklanıyor; süre etkin iken Çeviri Atölyesi'nde kuyruk API çağrısı göndermeden duraklıyor, çalışma kaydediliyor. Süre sona erdiğinde kullanıcı bekleyenleri yeniden başlatabiliyor. Test gerçek Gemini kotasını tüketmiyor.
8. **Gemini model listesi:** models.list sayfalandırması eklendi; yalnızca generateContent destekleyen modeller gösteriliyor. Kullanıcının seçtiği model API anahtarı testinden sonra korunuyor.
9. **PyInstaller keyring paketlemesi:** Windows build komutuna --copy-metadata keyring eklendi.
10. **Build kontrolü:** Windows EXE workflow'u artık yalnızca elle workflow_dispatch ile başlatılır. Main'e kod gönderilmesi yeni build başlatmaz.

## Otomatik doğrulama

Son başarılı Windows test koşusu:
- Workflow run: 42365753784
- Sonuç: **24 test geçti**
- compileall: başarılı
- Birim testleri: başarılı
- Windows masaüstü UI smoke testi: başarılı
- Oyun keşfi smoke testi: başarılı

Bu testler kaynak kod ve UI bileşenlerinin otomatik doğrulamasıdır; her gerçek oyunla uyumluluk veya gerçek Gemini hesabıyla çeviri kalitesini kanıtlamaz.

## API incelemesi

- Uygulama Gemini REST models.list ve models.generateContent uç noktalarını kullanır.
- Model listesi API anahtarıyla sorgulanır; generateContent destekleyen modeller filtrelenir.
- API anahtarı x-goog-api-key başlığında gönderilir; URL'ye eklenmez.
- Çeviri yanıtı JSON olarak istenir ve kayıt kimlikleri/yer tutucular doğrulanır.
- HTTP 429 veya RESOURCE_EXHAUSTED kota/durum hatası olarak ele alınır; tamamlanan satırlar çalışma dosyasına kaydedilir.
- Gerçek ücretsiz kota, erişilebilir model ve limitler Google Cloud projesine göre değişir. Modelin listede görünmesi ücretsiz erişim garantisi değildir.
- Test kotası akışı artık gerçek API çağrısı yapmadan kuyruk duraklatma davranışını doğrular.

Google'ın resmi belgeleri:
- https://ai.google.dev/api/generate-content
- https://ai.google.dev/api/models
- https://ai.google.dev/gemini-api/docs/troubleshooting

## Hâlâ eksik / gerçek test gerektirenler

1. **Gerçek oyun uçtan uca testi yapılmadı.** Deltarune dahil gerçek bir oyunda metin çıkarma, yama üretme, oyunun yamayı yüklemesi ve geri alma doğrulanmadı.
2. **Motor adaptörleri yok:** Unity .assets, Unreal .pak/.locres, GameMaker paketleri, XML/RESX/PO ve özel arşivler için adaptörler gerekli. JSON/CSV/TXT/INI dışındaki formatlar bu sürümde otomatik çevrilmez.
3. **Oyun motoruna yükleme yöntemi:** Metin dosyasını aynı göreli yola kopyalamak oyunun onu okuyacağını garanti etmez. Oyun/engine bazında hedef dosya ve dil etkinleştirme stratejisi gerekir.
4. **Mağaza kapsamı:** Steam, Epic, Windows GameConfigStore, XboxGames ve sınırlı yerel klasör keşfi var. GOG, EA app, Ubisoft Connect, Battle.net ve diğer mağazalar için adaptör yok.
5. **Lisans sahipliği:** Kurulu oyunları bulur; hesapların kurulmamış oyun kütüphanelerini veya satın alma geçmişini sorgulamaz.
6. **Dil tespiti:** TR/EN/DE etiketleri klasör ve dosya adı ipuçlarıdır; oyunun gerçekten desteklediği dil menülerini doğrulamaz.
7. **Windows imzası:** Geçerli Authenticode sertifikası ve GitHub secrets olmadan EXE imzasız kalır. Sarman Studios dosya metadata'sı SmartScreen güveni sağlamaz.
8. **Frozen EXE doğrulaması:** Merge sırasında tetiklenen build, eski merge commit'i 8afb040ad03439142e51dee20d1d33e754cece36 için başarılı oldu; fakat denetim sırasında eklenen son kod değişiklikleri bu artifact içinde değildir. Son sürümün EXE build'i ve paketlenmiş keyring davranışı henüz doğrulanmadı.
9. **Gerçek API entegrasyon testi:** Otomatik testler API yanıtlarını mock eder. Gerçek API anahtarıyla bağlantı ve çeviri çağrısı henüz bu denetimde çalıştırılmadı.
10. **UI görsel/manuel testi:** Windows smoke testi pencereyi oluşturuyor; farklı DPI, ekran boyutları, yüksek metin uzunlukları ve gerçek kullanıcı etkileşimi elle gözden geçirilmedi.

## Build durumu ve güvenlik

Main'e merge işlemi sonrasında eski Windows Build workflow'u push ile otomatik çalıştı ve başarılı oldu. Bu, build'in bu denetimden önce tamamlandığı anlamına gelir; denetim kodu içeren son sürümün build'i değildir. Bu durum fark edilince workflow workflow_dispatch olarak değiştirildi. Bundan sonra kullanıcı açıkça onaylamadan yeni Windows EXE build'i otomatik başlamaz.

## Sonuç

Main dalında otomatik oyun tarama, çeviri iş akışı, JSON/CSV doğruluğu, tarama sınırları, kota simülasyonu ve Gemini model keşfi güçlendirildi. **24 otomatik test ve Windows UI smoke testi başarılıdır.** Bununla birlikte gerçek oyun adaptörleri, gerçek Gemini isteği, farklı Windows ekran koşulları ve denetim sonrası EXE build'i henüz doğrulanmadı. Bu yüzden son build'i almadan önce Deltarune demo gibi gerçek bir hedef oyun üzerinde güvenli, salt okunur tarama ve ardından test kopyasında yama denemesi yapılmalıdır.
