# OmniCore — Kullanım Kılavuzu

OmniCore, doğal dil komutları ve slash komutlarıyla kontrol edilen çok yetenekli bir yapay zeka asistanıdır.

---

## 🖥️ CLI (Terminal) Modu

```bash
omnicore        # veya: uv run omnicore
```

### Temel Kullanım

Terminale mesajınızı yazıp Enter'a basın:

```
[You] > Masaüstümdeki dosyaları listele
[You] > Python ile bir web scraper yaz
[You] > Hava durumu nedir?
[You] > Bana bir şiir yaz
```

### Çıkış
```
quit   exit   q   çık
```

---

## 📋 Slash Komutları

CLI'de `/` yazdığınızda Tab ile komutları tamamlayabilirsiniz.  
Sadece `/` yazıp Enter'a basarsanız komut menüsü gösterilir.

| Komut | Açıklama | Örnek |
|---|---|---|
| `/help` | Yardım bilgisi | `/help` |
| `/status` | Provider, model, sistem durumu | `/status` |
| `/models` | Tüm modeller ve API key durumu | `/models` |
| `/setmodel` | Model değiştir | `/setmodel gemini-2.5-pro` |
| `/provider` | Provider görüntüle/değiştir | `/provider openai` |
| `/name` | Görünen adı değiştir | `/name Aria` |
| `/plan` | Plan modunu aç/kapat | `/plan on` |
| `/doctor` | Sistem tanılaması | `/doctor` |
| `/memory` | Bellek önizleme | `/memory` |
| `/reset` | Konuşma geçmişini temizle | `/reset` |
| `/hud` | Cyberpunk HUD göster | `/hud` |

### `/models` — Model Listesi
```
[You] > /models

📋 Kullanılabilir LLM Modeller:

📌 GEMINI (✅ API key var) ← aktif provider:
  - gemini-2.5-flash [AKTİF]
    Gemini 2.5 Flash | ctx=1M | fastest
  - gemini-2.5-pro
    Gemini 2.5 Pro | ctx=2M | medium

📌 OPENAI (❌ API key yok):
  - gpt-4o
    (key yok) GPT-4o | ctx=128k | fast
...
```

### `/provider` — Provider Değiştirme
```
[You] > /provider           # Mevcut durumu göster
[You] > /provider groq      # Groq'a geç
[You] > /provider openai    # OpenAI'a geç
[You] > /provider auto      # Otomatik seçime bırak
```

### `/setmodel` — Model Değiştirme
```
[You] > /setmodel gemini-2.5-flash
[You] > /setmodel gemini-2.5-pro
[You] > /setmodel gpt-4o
[You] > /setmodel claude-haiku-3-5
```

### `/name` — Asistana İsim Ver
```
[You] > /name Aria          # Asistan artık "Aria" olarak görünür
[You] > /name               # İsmi varsayılana (OmniCore) döndür
```

---

## 🔄 Provider Sistemi

OmniCore birden fazla LLM provider'ını destekler. Her provider için `.env` dosyasında API key gereklidir.

### Desteklenen Provider'lar

| Provider | Ücretsiz | Hız | En İyi Model |
|---|---|---|---|
| **Gemini** | ✅ (sınırlı) | ⚡ Çok Hızlı | `gemini-2.5-flash` |
| **Groq** | ✅ (sınırlı) | ⚡⚡ En Hızlı | `openai/gpt-oss-120b` |
| **OpenAI** | ❌ | ⚡ Hızlı | `gpt-4o` |
| **Anthropic** | ❌ | 🐢 Yavaş | `claude-opus-4-5` |
| **DeepSeek** | ❌ (ucuz) | ⚡ Hızlı | `deepseek-chat` |
| **Mistral** | ❌ | ⚡ Hızlı | `mistral-large-latest` |
| **Ollama** | ✅ (yerel) | 🖥️ PC'ye göre | `llama3.2` |

### Otomatik Fallback
Context penceresi dolduğunda (>4000 token) sistem otomatik olarak daha büyük context'li bir provider'a geçebilir. Bu davranışı `/provider auto` veya `/provider <istediğiniz>` ile kontrol edebilirsiniz.

---

## 🛠️ Araçlar (Tools)

OmniCore 56+ araç içerir. Bazıları:

### Dosya Sistemi
- Dosya okuma, yazma, kopyalama, taşıma, silme
- Dizin listeleme, arama
- Glob pattern ile dosya arama

### Terminal / Komut Çalıştırma
- Shell komutları çalıştırma (Windows/Linux/macOS)
- PowerShell desteği
- Süreç yönetimi

### Web / Ağ
- Web sayfası okuma
- HTTP API çağrıları
- DNS sorguları

### Kod Geliştirme
- Python kodu yazma ve çalıştırma
- Git işlemleri
- Grep/Glob ile kod arama

### Güvenlik
- Şifreleme/Çözme
- Güvenli dosya işlemleri

---

## 📱 Telegram Modu

```bash
omnicore --mode telegram
```

Gereksinimler:
1. `TELEGRAM_BOT_TOKEN` `.env`'de tanımlı olmalı
2. `TELEGRAM_ALLOWED_USERS` boş = herkese açık, veya ID listesi

```env
TELEGRAM_BOT_TOKEN=1234567890:AAFxxx...
TELEGRAM_ALLOWED_USERS=123456789,987654321
```

---

## 🌐 REST API Modu

```bash
omnicore --mode rest
```

API adresi: `http://localhost:8080`

```bash
# Mesaj gönder
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Merhaba!", "user_id": "user1"}'

# Sağlık kontrolü
curl http://localhost:8080/health
```

Bearer token auth için `.env`'de:
```env
REST_API_KEY=gizli-token-buraya
```

```bash
curl -X POST http://localhost:8080/chat \
  -H "Authorization: Bearer gizli-token-buraya" \
  -H "Content-Type: application/json" \
  -d '{"message": "Selam"}'
```

---

## 🧠 Bellek Sistemi

OmniCore iki tür bellek kullanır:

**Kısa Süreli Bellek (Short-Term)**
- Aktif konuşma geçmişi
- `/reset` ile temizlenir

**Uzun Süreli Bellek (Long-Term)**
- ChromaDB vektör veritabanı
- Önemli bilgiler kalıcı olarak saklanır
- `/memory` ile önizleyin

---

## 🔐 Güvenlik (HITL Guardian)

Tehlikeli işlemler (dosya silme, sistem komutları) için onay mekanizması:

```
[OmniCore] rm -rf /tmp/test klasörünü silmek üzere.
Onaylıyor musunuz? (e/h): e
```

Plan modunda tüm adımlar kuru-run olarak çalışır:
```
[You] > /plan on    # Plan modunu aç (yıkıcı adımlar gerçek çalışmaz)
[You] > /plan off   # Plan modunu kapat
```

---

## ⚙️ Konfigürasyon

Tüm ayarlar `.env` dosyasından veya ortam değişkenlerinden okunur.

```bash
# Ortam değişkeni ile override
LLM_PROVIDER=groq omnicore

# Debug modunda başlat
omnicore --debug

# Farklı modda başlat
omnicore --mode rest
omnicore --mode telegram
```

---

## 📝 Kişiselleştirme

```bash
# OmniCore'a özel bir isim ver (kalıcı)
[You] > /name Aria
# → Tüm bannerlar ve yanıtlar "Aria" ismiyle gösterilir

# Veya .env ile:
USER_NAME=Aria
```

İsim her zaman `OmniCore` tabanlıdır; sadece görünen ad değişir.
