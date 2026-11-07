# Yerel yapay zekâ çeviri motoru

Sarman TRANSLATE, Qwen3 4B Instruct modelinin Q4_K_M GGUF kuantizasyonunu `llama.cpp` üzerinden yerel olarak çalıştırır. Model dosyası yaklaşık 2,5 GB'tır ve `%LOCALAPPDATA%\Sarman\TRANSLATE\models` içine indirilir. İlk indirme internet gerektirir; sonrasında metin çevirisi yerel bilgisayarda ve çevrimdışı yapılır.

## Çeviri yaklaşımı

- Model İngilizceden Türkçeye doğal oyun yerelleştirmesi yapması için yönlendirilir.
- Aynı dosyadaki yakın metin satırları bağlam olarak modele verilir. Bu, çok anlamlı kelimelerin, karakter seslerinin, deyimlerin ve kelime oyunlarının daha doğru yorumlanmasına yardımcı olur.
- Yerleşik oyun terimleri sözlüğü ve kullanıcı sözlüğü terimleri sabitler. Kullanıcı karşılıkları `%LOCALAPPDATA%\Sarman\TRANSLATE\glossary.json` içinde saklanır.
- `{player}`, `%s`, `[TAG]`, HTML benzeri etiketler ve kaçış dizileri modelden önce korunur. Model bunları değiştirdiyse çeviri güvenli kabul edilmez.
- Aynı kaynak, bağlam ve sözlük sürümü SQLite çeviri hafızasında saklanır.

## Donanım ve performans

İlk entegrasyon CPU üzerinde çalışır; CUDA kurulumuna ihtiyaç duymaz. 4B parametreli model ve 4096 token bağlamı için yeterli RAM gerekir. 16 GB RAM sistemlerde çalışması hedeflenir ancak hız işlemciye ve metin uzunluğuna bağlıdır. Model oyun dosyalarına gömülmez ve EXE içine paketlenmez.

## Model ve lisans

Ağırlıklar ilk kurulumda doğrudan resmi Qwen Hugging Face deposundan indirilir: `Qwen/Qwen3-4B-GGUF`. Bu model Apache 2.0 lisanslıdır. Sarman TRANSLATE model ağırlıklarını yeniden dağıtmaz; kullanıcı kendi bilgisayarına indirir. Modelin kendi lisans ve atıf dosyası kaynak depoda incelenebilir.

## Sınırlar

Bu model otomatik yerelleştirme yardımcısıdır; profesyonel insan editörün yerini garantiyle almaz. Özellikle mizah, kültürel göndermeler, karakter adları ve hikâye bağlamı son kontrolden geçirilmelidir. İlk sürüm İngilizce → Türkçe çiftini destekler.
