# OmniCore — API Referansı / API Reference

## REST API

Base URL: `http://localhost:8000`

### Endpoints

#### GET /health

Sağlık kontrolü.

**Response:**
```json
{"status": "ok"}
```

#### POST /chat

Ana sohbet endpoint'i.

**Headers:**
- `Content-Type: application/json`
- `Authorization: Bearer <api_key>` (isteğe bağlı)

**Request Body:**
```json
{
  "message": "merhaba, dosyalarımı listele",
  "user_id": "kullanici1",
  "conversation_id": "konu-123"
}
```

| Alan | Tip | Gerekli | Açıklama |
|------|-----|---------|----------|
| `message` | string | Evet | Kullanıcı mesajı |
| `user_id` | string | Hayır | Kullanıcı ID (varsayılan: "api_user") |
| `conversation_id` | string | Hayır | Konuşma ID (varsayılan: "api_default") |

**Response (200):**
```json
{
  "reply": "Dosyalarınız listeleniyor...",
  "conversation_id": "konu-123"
}
```

**Hata Kodları:**
- `401` — Eksik veya geçersiz Bearer token
- `403` — Geçersiz API key
- `429` — Hız limiti aşıldı (60 saniyede max 20 istek)
- `500` — İç sunucu hatası

### Rate Limiting

Varsayılan: 60 saniye pencerede maksimum 20 istek/user. 429 ile dönüş yapılır.

## MCP Gateway (JSON-RPC 2.0)

`uv run omnicore --mode mcp` ile stdio üzerinden çalışır.

### Methods

#### initialize
MCP bağlantısı başlatma.

#### tools/list
Tüm kayıtlı araçların listesini döndürür.

#### tools/call
Belirli bir aracı çağırır.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "os_list_dir",
    "arguments": {"path": "."}
  },
  "id": 1
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "result": {
    "content": [{"type": "text", "text": "Dosya listesi..."}]
  },
  "id": 1
}
```

## Araç Sistemi

### Araç Oluşturma

Özel araç oluşturmak için `BaseTool` sınıfını genişletin:

```python
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool

class MyCustomTool(BaseTool):
    name = "my_custom_tool"
    description = "Açıklama"
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        # Araç mantığı
        return self._success("Başarılı", data={"result": "..."})
```

### Araç Kayıt Sistemi

Araçlar `tools/` dizinindeki `BaseTool` alt sınıfları olarak otomatik keşfedilir. `tools/registry.py` kullanarak:
- `discover_tool_classes()` — Dinamik import ile tüm araçları bulur
- `load_custom_skills()` — `workspace/skills/` dizininden özel araçları yükler

### Araç Envanteri

49 araç seti, 100+ bireysel araç. Kategoriler:

| Ön Ek | Kategori | Örnekler |
|-------|----------|----------|
| `os_` | Dosya sistemi | `os_read_file`, `os_write_file`, `os_list_dir` |
| `sys_` | Sistem | `sys_process_list`, `sys_kill_process` |
| `web_` | Web | `web_search`, `web_fetch_url` |
| `gui_` | GUI otomasyon | `gui_screenshot`, `gui_click` |
| `media_` | Medya | `media_control_spotify` |
| `dev_` | Geliştirme | `dev_execute_python`, `dev_glob_search` |
| `sec_` | Güvenlik | `sec_encrypt_file`, `sec_decrypt_file` |
| `net_` | Ağ | `net_ping`, `net_port_scan` |
| `doc_` | Belge | `doc_read_pdf`, `doc_read_docx` |
| `sched_` | Zamanlama | `sched_add_dynamic_reminder` |

Detaylı envanter: `tool_inventory_tables.md`
