# OmniCore — Kurulum Kılavuzu

> OmniCore, Windows, Linux ve macOS üzerinde çalışan çok-provider'lı bir yapay zeka asistanıdır.

---

## 📋 Gereksinimler

| Gereksinim | Minimum Sürüm | Kontrol Komutu |
|---|---|---|
| Python | 3.12+ | `python --version` |
| uv (paket yöneticisi) | 0.4+ | `uv --version` |
| Git | 2.0+ | `git --version` |

---

## ⚡ Hızlı Kurulum (Önerilen)

### Windows — Otomatik Kurulum

```bat
:: 1. Projeyi klonla
git clone https://github.com/MrSpy00/OmniCore.git
cd OmniCore

:: 2. Kurulum yöneticisini çalıştır
setup.bat
```

Açılan menüden **[1] Full Install** seçin. Kurulum:
- Python sürümünü kontrol eder
- `uv` yoksa kurar
- Tüm bağımlılıkları yükler
- `.env.example` → `.env` kopyalar
- PATH'i ayarlar (terminal yeniden başlatması gerekebilir)

---

## 🔧 Manuel Kurulum

```bash
# 1. Repo klonla
git clone https://github.com/MrSpy00/OmniCore.git
cd OmniCore

# 2. uv kur (yoksa)
pip install uv   # veya: curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Bağımlılıkları yükle
uv sync

# 4. .env dosyasını oluştur
cp .env.example .env   # Windows: copy .env.example .env

# 5. API Key'leri ekle (.env dosyasını düzenle)
notepad .env   # veya istediğiniz editörü kullanın
```

---

## 🔑 API Key Ayarlama

`.env` dosyasını açın ve kullanmak istediğiniz provider için API key girin:

### Gemini (Google AI Studio) — Ücretsiz tier var
```env
LLM_PROVIDER=gemini
GOOGLE_API_KEY=AI...
OMNI_LLM_MODEL=gemini-2.5-flash
```
API key al: https://aistudio.google.com/app/apikey

### Groq — Hızlı, ücretsiz tier
```env
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
```
API key al: https://console.groq.com/keys

### OpenAI (ChatGPT)
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```
API key al: https://platform.openai.com/api-keys

### Anthropic (Claude)
```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-haiku-3-5
```
API key al: https://console.anthropic.com/account/keys

### DeepSeek — Düşük maliyetli
```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
```
API key al: https://platform.deepseek.com/api_keys

### Mistral
```env
LLM_PROVIDER=mistral
MISTRAL_API_KEY=...
```
API key al: https://console.mistral.ai/api-keys

### Ollama — Yerel, internetsiz, ücretsiz
```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2
```
Ollama kur: https://ollama.ai/download  
Sonra model indir: `ollama pull llama3.2`

---

## 🚀 OmniCore'u Başlatma

### Yöntem 1: Herhangi Bir Konumdan (PATH kurulduysa)
```bash
omnicore         # CLI modu (varsayılan)
omnicore --mode cli
omnicore --mode telegram
omnicore --mode rest
omnicore --debug  # Debug log çıktısı ile
```

### Yöntem 2: uv ile (her zaman çalışır)
```bash
uv run omnicore
uv run omnicore --mode rest --debug
```

### Yöntem 3: setup.bat menüsü
```bat
setup.bat
# Menüden [6] Launch CLI seçin
```

---

## 🛠️ Sorun Giderme

### ❌ `omnicore` is not recognized
```bat
:: Çözüm 1: uv kullan
uv run omnicore

:: Çözüm 2: setup.bat ile PATH düzelt
setup.bat
:: [1] Full Install → PATH ayarlanır

:: Çözüm 3: Manuel PATH ekle
set PATH=%PATH%;X:\Projects\ActiveProjects\OmniCore\.venv\Scripts
```

### ❌ API key not valid / INVALID_ARGUMENT
- `.env` dosyasındaki API key'in doğru olduğunu kontrol edin
- Key'in başında/sonunda boşluk olmadığına dikkat edin
- Gemini için: aistudio.google.com → yeni key oluşturun

### ❌ Model not found / 404 NOT_FOUND
- Gemini 2.0 Flash kaldırıldı. `.env`'de `OMNI_LLM_MODEL=gemini-2.5-flash` kullanın
- Veya OmniCore içinde `/setmodel gemini-2.5-flash` yazın

### ❌ ModuleNotFoundError
```bash
uv sync  # Bağımlılıkları yeniden kur
```

---

## 📁 Proje Yapısı

```
OmniCore/
├── .env.example        # Örnek yapılandırma
├── .env                # Gerçek yapılandırma (gitignore'da)
├── setup.bat           # Windows kurulum yöneticisi
├── pyproject.toml      # Proje tanımı ve bağımlılıklar
├── config/
│   └── settings.py     # Tüm ayarlar
├── core/
│   ├── router.py       # Ana LLM yönlendirici
│   ├── guardian.py     # Güvenlik katmanı
│   └── planner.py      # Görev planlayıcı
├── interfaces/
│   ├── cli.py          # Terminal arayüzü
│   ├── telegram_bot.py # Telegram entegrasyonu
│   └── rest_api.py     # REST API
├── tools/              # 56+ araç (dosya, web, terminal, vs.)
├── memory/             # Kısa ve uzun süreli bellek
└── tests/              # Test suite
```
