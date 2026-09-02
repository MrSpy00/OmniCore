# OmniCore — Kurulum Kılavuzu / Installation Guide

## Ön Gereksinimler / Prerequisites

- **Python 3.12+** (projede `.python-version` dosyası ile sabitlenmiştir)
- **uv** — Python paket yöneticisi (önerilen) veya pip
- **Git**
- Windows, Linux veya macOS işletim sistemi

### uv Kurulumu

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Hızlı Başlangıç / Quick Start

### 1. Depoyu Klonlayın

```bash
git clone https://github.com/MrSpy00/OmniCore.git
cd OmniCore
```

### 2. Bağımlılıkları Kurun

```bash
uv sync
```

### 3. Ortam Değişkenlerini Yapılandırın

```bash
cp .env.example .env
```

`.env` dosyasını düzenleyin:

```env
# LLM Provider seçin (gemini veya groq)
LLM_PROVIDER=gemini

# Google Gemini API Key (gerekli)
GOOGLE_API_KEY=your-google-api-key-here

# Veya Groq API Key (gerekli)
GROQ_API_KEY=your-groq-api-key-here
```

### 4. Playwright Tarayıcılarını Kurun (Web otomasyonu için)

```bash
uv run playwright install chromium
```

### 5. OmniCore'u Başlatın

```bash
# CLI modu (varsayılan)
uv run omnicore

# Diğer modlar
uv run omnicore --mode hud        # Cyberpunk HUD
uv run omnicore --mode rest       # REST API (port 8000)
uv run omnicore --mode telegram   # Telegram bot
uv run omnicore --mode mcp        # MCP JSON-RPC (IDE entegrasyonu)
uv run omnicore --mode voice      # Sesli etkileşim
```

## API Key Nasıl Alınır?

### Google Gemini
1. https://aistudio.google.com/apikey adresine gidin
2. "Create API Key" butonuna tıklayın
3. Oluşturulan anahtarı `.env` dosyasına ekleyin

### Groq
1. https://console.groq.com/ adresine gidin
2. "API Keys" menüsünden yeni bir anahtar oluşturun
3. Anahtarı `.env` dosyasına ekleyin
- İsteğe bağlı: 3 anahtar desteği var (`GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3`)

## Platform Notları

### Windows
- `pywin32` ve `pycaw` kütüphaneleri otomatik kurulur
- Playwright Chromium tarayıcısı gerekli
- PowerShell erişimi gereken araçlar için yetki gerekebilir

### Linux
- `libglib2.0-0` ve benzeri sistem kütüphaneleri gerekebilir
- `sounddevice` için ALSA/PulseAudio gerekebilir

### macOS
- `pbcopy`/`pbpaste` clipboard desteği dahildir
- Homebrew ile bağımlılıklar kurulabilir

## Docker ile Kurulum

```bash
# .env dosyasını yapılandırın (yukarıdaki adımlar)

# Docker Compose ile başlatın
docker compose up -d

# Durdurmak için
docker compose down
```

## Sorun Giderme

### "ModuleNotFoundError" hatası
```bash
uv sync  # Bağımlılıkları yeniden kurun
```

### "API key not configured" hatası
`.env` dosyasında ilgili API key'inin dolu olduğundan emin olun.

### Playwright tarayıcı hatası
```bash
uv run playwright install chromium
```

### Veritabanı hatası
```bash
uv run python scripts/setup_db.py  # DB'yi yeniden oluşturun
```
