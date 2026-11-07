# Sarman TRANSLATE — uçtan uca denetim

Denetim tarihi: 2026-11-07  
Çalışma dalı: feature/complete-translation-mvp

## Bu turda yapılanlar

- Açılışta oyun kütüphanesi otomatik taranacak şekilde ayarlandı; kullanıcıdan oyun klasörü veya oyun dosyası seçmesi istenmiyor.
- Steam, Epic Games, Windows GameConfigStore, XboxGames ve bilinen yerel oyun klasörleri taranıyor.
- Kütüphaneye iki ayrı bilgi eklendi:
  - **Algılanan diller:** Dil klasörü/dosya adlarından bulunan TR, EN, DE, FR vb. ipuçları.
  - **Sarman yaması:** Uygulamanın yükleme günlüğünde kayıtlı olan dil yamaları.
- Dil ipucu taraması oyun başına 1.500 dizin ve 5.000 dosya ile sınırlandırıldı.
- Yama yükleme günlüğüne dil kodu ekleniyor; eski Türkçe yama kayıtları isimden tanınmaya çalışılıyor.
- Geri alma işlemi, oyun klasörünün dışına çıkan ve sembolik bağlantı kullanan hedefleri reddedecek şekilde sertleştirildi.
- Windows EXE'sine Sarman Studios şirket/ürün/sürüm bilgisi eklemek için PyInstaller version resource eklendi.
- Windows build workflow'una isteğe bağlı Authenticode imzalama eklendi. Sertifika yoksa workflow açıkça imzasız build uyarısı verir.

## Otomatik testlerde doğrulananlar

- Python modüllerinin derlenebilirliği (compileall).
- Birim testleri: JSON/CSV/INI çıkarma ve dışa aktarma, yer tutucu doğrulama, Gemini batch yanıtı, çalışma alanı kaydı, ZIP yama üretimi, yama kurulum/geri alma, yol geçişi reddi, Steam/Epic keşfi ve dil ipucu algılama.
- Windows runner üzerinde PySide6 masaüstü arayüzü açılış smoke testi.
- Windows keyring backend kontrolü.

Son başarılı Windows test koşusu (7 Kasım 2026, commit 9d3a6ac9): **17 test geçti**, UI smoke test başarılı. Bu denetim belgesi EXE build'in başarılı olduğunu iddia etmez.

## Henüz doğrulanmamış / tamamlanmamış noktalar

1. **Gerçek oyun üzerinde uçtan uca doğrulama yok.** Yama yükleme/geri alma geçici test klasörlerinde sınandı; gerçek kurulu bir oyunda henüz test edilmedi.
2. **Evrensel oyun desteği yok.** Metin çıkarma/dışa aktarma JSON, CSV, TXT ve INI ile sınırlı. Unity assets, Unreal pak, locres, XML/RESX/PO ve özel/şifreli arşivler için adaptörler eksik.
3. **Dil algısı bir ipucudur.** TR/EN etiketleri klasör ve dosya adlarından gelir; oyunun o dili menüde gerçekten desteklediğini veya seçebildiğini kanıtlamaz. Sarman yaması sütunu yalnızca uygulamanın yükleme günlüğünde bulunan yamaları gösterir.
4. **Platform kapsamı sınırlı.** Steam/Epic/Windows oyun kayıtları/XboxGames ve bazı standart klasörler taranır. GOG, EA app, Ubisoft Connect, Battle.net ve diğer mağazalar için özel keşif adaptörleri henüz yok.
5. **Lisans kütüphanesi doğrulaması yok.** Uygulama kurulu oyunları bulur; mağaza hesabındaki kurulmamış satın alımları veya lisans sahipliğini sorgulamaz. Parola, DRM veya anti-cheat atlatma yapılmaz.
6. **Oyun motoru entegrasyonu eksik.** Metin dosyasını güvenli biçimde yama klasörüne koymak, oyunun o dosyayı otomatik yükleyeceği anlamına gelmez. Her oyun/engine için doğru hedef ve dil etkinleştirme yöntemi gerekebilir.
7. **Windows imzası henüz etkin değil.** Geçerli bir kod imzalama sertifikası ve GitHub Actions secrets (WINDOWS_CERTIFICATE_BASE64, WINDOWS_CERTIFICATE_PASSWORD) eklenmeden EXE imzasız olur. Dosya özelliklerindeki Sarman Studios bilgisi tek başına SmartScreen güveni sağlamaz.
8. **Windows EXE build henüz çalıştırılmadı.** version_info.txt ve Authenticode adımı gerçek PyInstaller build'i üzerinde henüz doğrulanmadı. Build ancak ayrıca onay verildiğinde başlatılmalı.

## Sonuç

Otomatik kütüphane ve dil durumu görünümü eklendi. Test edilmiş MVP kapsamı sağlamlaştırıldı; ancak gerçek oyun/engine adaptörleri, ek mağaza keşfi, gerçek oyunla kurulum testi ve kod imzalama sertifikası olmadan ürünün tüm oyunlarda hazır veya Windows SmartScreen tarafından güvenilir olduğu söylenemez.
