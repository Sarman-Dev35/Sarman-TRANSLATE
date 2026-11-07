# Oyun motoru uyumluluk matrisi

Bu belge, uygulamanın gerçekten yaptığı işi ve motor bazında eksik kalanları ayırır. Motor algılama salt okunurdur; dosya açma, arşiv çıkarma, kod çalıştırma veya oyun dosyası değiştirmez.

| Motor / biçim | Algılama | Şu anki çeviri desteği | Eksik adaptör |
|---|---|---|---|
| Genel JSON / CSV / TXT / INI | Dosya uzantısı | Evet | Oyun dosyayı gerçekten yüklemiyorsa motor bağlayıcısı |
| RPG Maker MV/MZ | `www/data` işareti | Açık JSON dosyaları | Şifreli veri ve sürüm özelindeki biçimler |
| Unity | UnityPlayer.dll / GameAssembly.dll / globalgamemanagers | Açık metin dosyaları; StreamingAssets JSON uygun ise | AssetBundle, serialized .assets ve özel paketler |
| Unreal Engine | .pak / .utoc / UE4Game.exe işaretleri | Dışarı çıkarılmış açık metin dosyaları | .locres derleme, pak/IoStore yeniden paketleme |
| GameMaker | data.win / game.unx | Dışarıdaki JSON/CSV/TXT/INI | STRG kaynakları ve GameMaker veri dosyası yeniden oluşturma |
| Godot | .pck / Godot işaretleri | Dışarıdaki açık metin dosyaları | PCK arşiv desteği |
| Ren'Py | renpy / .rpy / .rpyc işaretleri | Dışarıdaki açık metin dosyaları | .rpy/.rpyc derleme ve yerleşik çeviri akışı |

## Araştırma ve adaptör adayları

- **GameMaker:** [UndertaleModTool](https://github.com/UnderminersTeam/UndertaleModTool) ve [resmî kullanım belgeleri](https://underminersteam.github.io/usage/getting-started/) `data.win` / `game.unx` açma ve düzenleme için güçlü bir topluluk çözümüdür. Proje GPL-3.0 lisanslıdır. Sarman TRANSLATE içine ikili dosya olarak kopyalamak veya kodunu bağlamak lisans uyumluluğu incelemesi gerektirir. İlk entegrasyon, kullanıcı tarafından ayrıca kurulan CLI + doğrulanmış script arayüzü olmalıdır; GUI otomasyonu veya doğrulanmamış script çalıştırma yapılmamalıdır.
- **Unity:** [Unity Localization veri dosyası tabloları](https://docs.unity.com/en-us/engine/6000.7/manual/localization/content-storage-and-loading/data-file-tables) StreamingAssets altında locale başına JSON gibi açık dosyaların kullanılabildiğini açıklar. Bu nedenle önce bu resmî açık dosya iş akışı desteklenmeli; AssetBundle/.assets düzenleme ayrı ve daha riskli aşama olmalıdır.
- **Unreal:** [Epic'in Localization Overview belgesi](https://dev.epicgames.com/documentation/unreal-engine/localization-overview-for-unreal-engine?lang=en-US) .locres dosyalarının derlenmiş ikili kültür kaynakları olduğunu ve runtime'da kullanıldığını açıklar. [UEExtractor](https://github.com/SolicenTEAM/UEExtractor) .pak/.utoc ve .locres için topluluk aracı adayıdır; MIT lisansı ve .NET 10 gereksinimi vardır. [UELocKit](https://github.com/AcTePuKc/uelockit) alternatif bir iş akışı sunar. Her oyun için paket şifreleme/IoStore uyumluluğu garanti edilmez.
- **Microsoft Store / Xbox:** [Microsoft GDK paketlenmiş kaynak yerelleştirme belgesi](https://learn.microsoft.com/en-us/gaming/gdk/docs/gdk-dev/game-principles/localization/localization_of_packaged_resources?view=gdk-2604) `resources.pri` ve paket kaynaklarının özel süreç gerektirdiğini gösterir. Kurulum klasörüne doğrudan yazmak her zaman doğru değildir.

## Güvenli entegrasyon sözleşmesi

Yeni bir motor adaptörü aşağıdaki arayüzü izlemelidir:

1. `probe(game_dir) -> EngineReport`: salt okunur motor ve sürüm tespiti.
2. `extract(game_dir, workspace_dir) -> list[TextEntry]`: yalnızca kullanıcı tarafından seçilen/erişilebilir dosyalardan metin çıkarma; orijinal oyuna yazmama.
3. `build(game_dir, workspace_dir, translations, output_dir) -> PatchPlan`: değişiklikleri ayrı bir çıktı klasörüne oluşturma.
4. `validate(game_dir, PatchPlan) -> ValidationReport`: sürüm, hedef yol, dosya sayısı, bütünlük ve çakışma kontrolü.
5. `install(PatchPlan)` yalnızca kullanıcı onayı, otomatik yedek ve geri alma günlüğünden sonra çalışmalıdır.

Adaptörler oyunun lisansını, DRM'ini, anti-cheat sistemini veya şifrelemesini aşmaya çalışmamalı; oyun varlıklarını veya çıkarılmış özgün metinleri dağıtmamalıdır. Bilinmeyen motorlarda otomatik yama üretmek yerine açıkça desteklenmeyen durum gösterilmelidir.

## Mevcut geliştirme kapsamı

Bu geliştirme adımı yalnızca motor parmak izi/uyumluluk raporunu ve mevcut metin dosyalarının biçim korumasını ekler. GameMaker, Unity serialized assets veya Unreal pak/locres için tam çıkarma-yeniden paketleme adaptörü henüz eklenmiş değildir. Bunlar harici araç lisansları, sürüm eşleşmesi, gerçek oyun kopyalarında round-trip testleri ve Windows dağıtım bağımlılıkları doğrulanmadan "destekleniyor" olarak işaretlenmeyecektir.
