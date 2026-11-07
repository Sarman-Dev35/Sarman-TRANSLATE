# Yerel oyun çeviri motoru

Sarman TRANSLATE, Tencent'in yalnızca çok dilli çeviri için tasarladığı Hy-MT2 1.8B modelini Q4_K_M GGUF biçiminde `llama.cpp` üzerinden yerel olarak çalıştırır. Model dosyası 1.133.080.448 bayttır (yaklaşık 1,13 GB). Paketlenmiş Windows uygulamasında model, `Sarman TRANSLATE.exe` dosyasının bulunduğu klasöre doğrudan indirilir; kaynak koddan çalıştırırken `%LOCALAPPDATA%\\Sarman\\TRANSLATE\\models` kullanılır. İlk indirme internet gerektirir; kurulumdan sonra çeviri tamamen çevrimdışı yapılır.

## Neden Hy-MT2?

- Sohbet veya genel amaçlı asistan modeli değildir; doğrudan çeviri görevlerine odaklanır.
- Türkçe dahil 33 dili destekler. Bu uygulamanın ilk hedefi İngilizce → Türkçe oyun metinleridir.
- Model, yalnızca çeviri talimatı ve metin alır; sohbet arayüzü veya sohbet geçmişi yoktur.
- Q4_K_M dosyası yaklaşık 1,13 GB'tır; önceki Qwen3 4B Q4_K_M dosyasından belirgin biçimde küçüktür.

## Çeviri yaklaşımı

- Aynı oyun dosyasındaki yakın satırlar ve oyun adı, belirsiz kelimeleri yorumlamak için bağlam olarak verilir.
- Yerleşik ve kullanıcı tarafından düzenlenebilir terim sözlüğü, oyun terimlerinin tutarlı kalmasını sağlar.
- `{player}`, `%s`, `[TAG]`, HTML benzeri etiketler ve kaçış dizileri modelden önce korunur. Model bunları değiştirdiyse çeviri güvenli kabul edilmez.
- Aynı kaynak metin, bağlam, oyun adı ve sözlük sürümü SQLite çeviri hafızasında tutulur. Tekrar eden metinler yeniden üretilmeden anında kullanılır.
- Model dosyası oyun dosyalarına veya EXE'ye gömülmez.

## Performans

İlk sürüm llama.cpp CPU çıkarımı kullanır ve CUDA kurulumu gerektirmez. Daha küçük model dosyası daha az depolama ve genellikle daha düşük bellek ihtiyacı sağlar; gerçek çeviri hızı işlemciye, metin uzunluğuna ve oyun dosyasındaki benzersiz satır sayısına bağlıdır. Bu nedenle belirli bir oyunun binlerce satırının saniyeler içinde biteceği garanti edilmez. Önbellek, yinelenen metinlerin tekrar çevrilmesini önler.

## Model yönetimi\n\nÇeviri Atölyesi içindeki **Modeli cihazdan kaldır** düğmesi, model belleğini kapatır ve EXE yanındaki model dosyasını (varsa yarım indirme dosyasını da) siler. Terim sözlüğü, çeviri hafızası ve oyun çalışma dosyaları korunur. Model dosyasını EXE klasörüne yazabilmek için uygulamanın yazma izni olan bir klasörde bulunması gerekir.\n\n## Model ve lisans

Model ağırlıkları ilk kurulumda doğrudan Tencent'in resmi Hugging Face deposundan indirilir: `tencent/Hy-MT2-1.8B-GGUF`. Model deposu Apache-2.0 lisansını belirtir. Sarman TRANSLATE model ağırlıklarını yeniden dağıtmaz; kullanıcı kendi bilgisayarına indirir. Dosyanın SHA-256 özeti indirme sonunda doğrulanır.

## Sınırlar

Bu model otomatik oyun yerelleştirme aracıdır; profesyonel insan editörün yerini garantiyle almaz. Özellikle karakter sesleri, hikâye göndermeleri ve kelime oyunları oyun bağlamına göre kontrol edilmelidir. İlk entegrasyon İngilizce → Türkçe akışını hedefler.
