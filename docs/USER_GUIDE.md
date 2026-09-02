# OmniCore — Kullanım Kılavuzu / User Guide

## Gateway Modları

| Mod | Komut | Açıklama |
|-----|-------|----------|
| **CLI** | `uv run omnicore` | Etkileşimli terminal REPL |
| **HUD** | `uv run omnicore --mode hud` | Cyberpunk ASCII dashboard + CLI |
| **REST** | `uv run omnicore --mode rest` | FastAPI HTTP API (port 8000) |
| **Telegram** | `uv run omnicore --mode telegram` | Telegram bot |
| **MCP** | `uv run omnicore --mode mcp` | MCP JSON-RPC 2.0 (IDE entegrasyonu) |
| **Voice** | `uv run omnicore --mode voice` | Gerçek zamanlı duplex ses motoru |

## Slash Komutları

| Komut | Açıklama |
|-------|----------|
| `/help` | Tüm komutların listesi |
| `/plan` | Plan modunu aç/kapat (destructive adımlar dry-run) |
| `/doctor` | Sistem durumu ve provider bilgisi |
| `/memory` | Uzun vadeli hafıza önizleme |
| `/reset` | Bu konuşmanın geçmişini temizle |
| `/models` | Kullanılabilir LLM modellerini listele |
| `/setmodel <id>` | Aktif modeli değiştir (oturuma özel) |
| `/commit` | Git commit yardımcısı |

### Onay Modları

```bash
.omnicore approve yes    # Otomatik onay modu
.omnicore approve ask    # Manuel onay modu (varsayılan)
```

## Örnek Kullanım Senaryoları

### Dosya İşlemleri
```
> masaüstündeki tüm txt dosyalarını listele
> belgeler klasörünü Mevcut Belge altına taşı
> notepad.txt dosyasının içeriğini göster
```

### Web Otomasyonu
```
> google'da "Python async programming" ara
> https://example.com adresinin içeriğini çek
> ekran görüntüsü al
```

### Sistem Yönetimi
```
> disk kullanımını göster
> chrome processes'leri kapat
> wifi şifremi göster
```

### Geliştirme
```
> bu projede "TODO" ara
> main branch'e commit at
> kodu ruff ile formatla
```

### Medya
```
> bu YouTube videosunu indir
> Spotify'da bir sonraki şarkıya geç
> ses kaydı başlat (10 saniye)
```

## Bellek Sistemi

OmniCore 3 katmanlı bir bellek sistemi kullanır:

1. **Kısa Vadeli Hafıza (ShortTermMemory)**: Son 50 mesaj (conversation bazlı sliding window)
2. **Uzun Vadeli Hafıza (LongTermMemory)**: ChromaDB vektör deposu (semantik hatırlama)
3. **Durum Takipçisi (StateTracker)**: SQLite — görevler, denetim günlüğü, zamanlanmış işler

OmniCore otomatik olarak konuşmalardan bilgi çıkarır ve bunları uzun vadeli bellekte saklar.

## Otonom Görev Zamanlama

```bash
# Sabah briefing'i (her gün 08:00'de otomatik)
# Sandbox temizliği (her Pazar 03:00'de otomatik)
```

Kullanıcı tanımlı hatırlatıcılar `sched_add_dynamic_reminder` aracı ile oluşturulabilir.

## REST API Kullanımı

```bash
# Sağlık kontrolü
curl http://localhost:8000/health

# Sohbet
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "merhaba", "user_id": "kullanici1"}'
```

API key ile koruma (isteğe bağlı):
```bash
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message": "merhaba"}'
```

## MCP Entegrasyonu

VS Code, Cursor, Zed veya Claude Desktop'ta MCP sunucusu olarak çalıştırın:

```json
{
  "mcpServers": {
    "omnicore": {
      "command": "uv",
      "args": ["run", "omnicore", "--mode", "mcp"]
    }
  }
}
```
