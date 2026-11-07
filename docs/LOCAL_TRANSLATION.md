# Yerel çeviri motoru

Sarman TRANSLATE'in yerel motoru Argos Translate ile İngilizce → Türkçe çalışır. İlk kullanımda dil paketi bir kez indirilir; sonraki çeviriler internet/API anahtarı/kota gerektirmez. Model boyutu sürüme göre değiştiğinden sabit bir MB değeri garanti edilmez. Model paketi uygulama kurulumuna gömülmez.

Çeviri hafızası `%LOCALAPPDATA%\\Sarman\\TRANSLATE\\translation-memory.sqlite3` altında tutulur. Aynı kaynak metin daha sonra tekrar çevrilmez. Oyun yer tutucuları (ör. `{player}`, `%s`, `\\n`) çevirmeden önce korunur ve sonuç doğrulanır.

İlk sürüm kaynak dili İngilizce, hedef dili Türkçedir. Başka dil çiftleri ayrı model paketleriyle eklenebilir. Argos çıktısı makine çevirisidir; özellikle karakter diyalogları kullanıcı tarafından gözden geçirilmelidir.
