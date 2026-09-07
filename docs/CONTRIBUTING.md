# OmniCore — Katkı Rehberi / Contributing Guide

## Geliştirme Ortamı Kurulumu

```bash
# 1. Depoyu klonlayın
git clone https://github.com/MrSpy00/OmniCore.git
cd OmniCore

# 2. Bağımlılıkları kurun (dev dahil)
uv sync

# 3. Pre-commit hook'larını kurun
uv run pre-commit install

# 4. Playwright kurun (web testleri için)
uv run playwright install chromium

# 5. Testleri çalıştırın
uv run pytest
```

## Kod Stili

- **Linter:** ruff (line-length=100, target=py312)
- **Format:** ruff format
- **Test:** pytest + pytest-asyncio (asyncio_mode=auto)

```bash
# Lint kontrolü
uv run ruff check .

# Otomatik düzeltme
uv run ruff check --fix .

# Format kontrolü
uv run ruff format --check .

# Format uygula
uv run ruff format .
```

## Test Yönergeleri

### Test Çalıştırma

```bash
# Tüm testler
uv run pytest

# Belirli dosya
uv run pytest tests/test_memory.py

# Verimli test
uv run pytest -x  # İlk hatada dur

# Detaylı çıktı
uv run pytest -v
```

### Test Yazma Kuralları

1. Her test dosyası `test_` ile başlamalı
2. Async testler `@pytest.mark.asyncio` ile işaretlenmeli (veya `asyncio_mode=auto`)
3. `tmp_path` fixture'i ile dosya sistemi izolasyonu sağlanmalı
4. `monkeypatch` ile ortam değişkenleri izole edilmeli
5. Ağ bağımlılıkları `monkeypatch` ile mock'lanmalı

### Örnek Test

```python
import pytest
from models.tools import ToolInput, ToolOutput, ToolStatus


@pytest.mark.asyncio
async def test_my_tool_success(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "test.db"))
    from config.settings import get_settings
    get_settings.cache_clear()

    tool = MyTool()
    result = await tool.execute(ToolInput(
        tool_name="my_tool",
        parameters={"path": "test.txt"},
    ))
    assert result.status == ToolStatus.SUCCESS
```

## Mimari Genel Bakış

```
OmniCore/
├── core/           # Merkezi beyin (CognitiveRouter, Planner, Guardian)
├── models/         # Pydantic veri modelleri
├── tools/          # 49 araç seti (BaseTool alt sınıfları)
├── memory/         # 3 katmanlı bellek sistemi
├── interfaces/     # Gateway'ler (CLI, REST, Telegram, MCP, HUD, Voice)
├── scheduler/      # APScheduler otonom zamanlama
├── config/         # Ayarlar ve loglama
├── scripts/        # Giriş noktası ve yardımcı scriptler
├── tests/          # pytest test suite
└── workspace/      # Özel kullanıcı araçları
```

### Veri Akışı

```
Kullanıcı → Interface → CognitiveRouter → LLM (Gemini/Groq)
                                       → Planner (çok adımlı plan)
                                       → Guardian (onay kapısı)
                                       → RecoveryEngine (hata düzeltme)
                                       → Tool → Sonuç → Kullanıcı
```

### Yeni Araç Nasıl Eklenir

1. `tools/` dizininde yeni `.py` dosyası oluşturun
2. `BaseTool` sınıfından türetilmiş sınıf yazın
3. `name`, `description`, `is_destructive` niteliklerini ayarlayın
4. `execute()` metodunu implemente edin
5. `tests/` dizininde test yazın
6. `tool_inventory_tables.md` dosyasını güncelleyin

Araçlar otomatik olarak `discover_tool_classes()` ile keşfedilir.

## PR Süreci

1. Feature branch oluşturun: `git checkout -b feature/yeni-ozellik`
2. Değişikliklerinizi yapın
3. Testleri çalıştırın: `uv run pytest`
4. Lint kontrolü: `uv run ruff check .`
5. Commit atın (conventional commits): `feat(router): yeni özellik ekle`
6. PR açın ve açıklamayı doldurun

## Commit Mesajı Formatı

```
<type>(<scope>): <description>

[optional body]
```

Türler: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`
