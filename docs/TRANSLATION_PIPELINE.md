# Sarman TRANSLATE — oyun keşfi ve yerelleştirme mimarisi

## 1. Oyun keşfi: kurulum ile lisansı ayır

Uygulama oyunları platform izlerinden keşfeder; hiçbir platform hesabının parolasını istemez ve oyun dosyalarını tarama sırasında değiştirmez.

- **Steam:** Steam kurulum kayıtları, `libraryfolders.vdf` ve `appmanifest_*.acf` dosyaları okunur. Bu, o Steam kütüphanesinde kurulu oyunları bulur; hesabın tüm satın alma/lisans geçmişini kanıtlamaz.
- **Epic Games:** Epic Launcher'ın yerel `*.item` kurulum manifestleri okunur. Bu da kurulu oyunları gösterir; Epic hesabındaki kurulmamış tüm sahip olunan oyunları göstermez.
- **Microsoft Store / Xbox:** Windows Game DVR / GameConfigStore oyun kayıtları ve `C:\\XboxGames` kurulumları incelenir. WindowsApps içindeki oyunlar için kayıtlı çalıştırılabilir dosya ve paket manifesti kullanılabilir. Microsoft Store lisans kataloğuna dair genel, herkese açık bir yerel API bulunmadığından lisans sahipliği iddiası gösterilmez.
- **Diğer klasörler:** Kullanıcının Games/Oyunlar klasörleri ve seçtiği özel klasörler ek kaynak olabilir. Sıradan uygulamalar oyun diye gösterilmemeli; güven düzeyi düşük adaylar ayrı işaretlenmelidir.

Platformların tam sahip olunan oyun kütüphanelerini listelemek ileride resmi OAuth/izinli API entegrasyonlarıyla ayrıca ele alınabilir. Parola kazıma, istemci veritabanı kırma veya lisans atlatma yapılmaz.

## 2. Çeviri iş akışı

1. **Oyun seçimi:** Bulunan oyun, platform, kurulum yolu ve algılama kaynağı gösterilir.
2. **Metin arayıcı:** Yalnızca bilinen metin/kaynak dosyalarını tarar; ikili dosyaları, büyük arşivleri ve oyun kayıtlarını değiştirmez. Dosya türü/engine adaptörleri kullanır.
3. **Metin çıkarıcı:** JSON, XML, CSV, INI, PO, RESX ve düz metin gibi formatlar için ayrı okuyucu/yazıcılar. Unity/Unreal ve özel arşiv biçimleri ayrı adaptör olarak eklenir; desteklenmeyen dosyalar açıkça raporlanır.
4. **Çeviri çalışma alanı:** Kaynak metin, hedef dil, bağlam/dosya, karakter sınırı, durum (bekliyor/çevrildi/kontrol gerekli) ve arama/filtre. Yinelenen metinler birleştirilir.
5. **Çeviri motoru:** Kullanıcının Gemini anahtarıyla küçük partiler halinde çeviri. Yer tutucular, biçim kodları, HTML/JSON etiketleri, satır sonları ve değişkenler kilitlenir; yanıt doğrulanmadan kabul edilmez. İlerleme yerel kaydedilir, kota aşımında kuyruk duraklatılır.
6. **Kontrol:** Kaynak-hedef boşluğu, bozulmuş placeholder, eksik satır, beklenmeyen uzunluk ve biçim hataları raporlanır. Kullanıcı satırları düzenleyip onaylar.
7. **Yama oluşturucu:** Onaylı çevirilerden yalnızca çeviri verisini içeren, manifestli ZIP paketi üretir. Oyun motoruna özgü çıktı adaptörü hedef yolu belirler.
8. **Kurulum ve geri alma:** Önce uyumluluk kontrolü ve yedek; sonra açık kullanıcı onayıyla yükleme. Geri alma kaydı her dosyayı takip eder.

## 3. Tasarım ilkeleri

- Koyu, sade Sarman arayüzü; ölçülü bakır/turuncu vurgu.
- Ana alanlar: **Oyunlar**, **Metinleri Tara**, **Çeviri Atölyesi**, **Yama Oluştur**, **Yama Merkezi**, **Ayarlar**.
- Ağır tarama ve API çağrıları arka plan iş parçacıklarında; arayüz donmaz.
- Kaynak dosyalar varsayılan olarak salt okunur; orijinal dosyaya yazma yalnızca yama kurulurken ve onayla.
- Her oyun/engine adaptörü ayrı modül; evrensel uyumluluk iddiası yok.
- DRM, lisans doğrulaması atlatma, anti-cheat müdahalesi, korsan oyun/asset dağıtımı ve oynanış değişikliği kapsam dışıdır.

## 4. Aşamalı geliştirme

- Aşama A: platformlardan kurulu oyun keşfi ve güvenilir liste.
- Aşama B: metin dosyası arama/çıkarma ve tarama raporu.
- Aşama C: Gemini çeviri kuyruğu, checkpoint ve kalite kontrolleri.
- Aşama D: oyun/engine adaptörleri ve yama oluşturucu.
- Aşama E: güvenli kurulum, yedekleme, geri alma ve test matrisi.
