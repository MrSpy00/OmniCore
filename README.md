# OmniCore V28 - Zenith Edition

OmniCore is a production-oriented autonomous operations agent that plans, executes, verifies, and reports real actions across OS, browser, network, data, and workflow layers.

This V28 release focuses on three major outcomes:
- architectural hardening across `core/`, `memory/`, `models/`, `interfaces/`, and `tools/`
- expanded high-value tool surface for analysis and validation workflows
- operational documentation uplift with enterprise-ready onboarding quality

## Executive Summary

- **Mission**: Turn natural-language objectives into safe, auditable, tool-driven execution.
- **Control Plane**: Cognitive Router + Planner + Guardian + Recovery Engine.
- **Data Plane**: Dynamic tool registry with structured input/output contracts.
- **Memory**: Short-term sliding context + long-term semantic memory + SQLite state/audit.
- **Interface Layer**: CLI and Telegram gateways (REST scaffold present in project layout).

## What Is New in V28

### Architectural Hardening

- Strengthened SQLite state safety with guarded connection access (`_require_db`) and explicit runtime initialization errors.
- Added serialized write path (`_write_lock` + `_execute_write`) for safer concurrent task/audit/job commits.
- Enabled database safety pragmas and deterministic table-creation commit behavior.
- Added duplicate tool-name detection during dynamic discovery with structured warning logs.

### New Advanced Tools

The following tools were introduced in `tools/insight_toolkit.py`:

- `data_hash_text` - deterministic text hashing (`md5`, `sha1`, `sha256`, `sha512`)
- `text_profile_basic` - structural text profiling (chars/words/lines/top tokens)
- `data_validate_json` - JSON validation with optional required-key assertions
- `data_csv_profile` - CSV profiling (columns, row counts, null-like density, preview)
- `os_path_inspect` - host path metadata inspection (existence/type/size/timestamps)

These tools are auto-registered by the existing dynamic discovery mechanism.

## Core Architecture

```text
User Intent
  -> Interface Gateway (CLI / Telegram / REST)
  -> Cognitive Router (LLM routing + plan decision)
  -> Planner (step graph)
  -> Guardian (HITL policy for destructive actions)
  -> Recovery Engine (retry + fallback orchestration)
  -> Tool Registry (dynamic runtime inventory)
  -> Execution + Audit + Memory persistence
  -> Final response synthesis
```

## Repository Structure

```text
config/          runtime settings, env contract, logging
core/            router, planner, guardian, recovery
interfaces/      cli, telegram, rest api gateways
memory/          short-term, long-term, sqlite state tracker
models/          canonical pydantic contracts
scheduler/       autonomous pulse / scheduled workflows
scripts/         application entrypoints
tools/           dynamically discovered toolkits
tests/           regression and behavior test suite
```

## Runtime Requirements

- Python 3.12+
- `uv` package manager/runtime
- Playwright Chromium (for web automation features)
- Optional platform-specific dependencies for selected advanced toolkits

## Quick Start

```bash
git clone <repo-url>
cd OmniCore
uv sync
uv run playwright install chromium
cp .env.example .env
```

## Run Modes

```bash
# CLI mode
uv run python scripts/run.py --mode cli

# Telegram mode
uv run python scripts/run.py --mode telegram
```

## Configuration Overview

Primary environment variables include:

- `LLM_PROVIDER`
- `OMNI_LLM_MODEL`
- `GOOGLE_API_KEY`, `GOOGLE_API_KEY_2`, `GOOGLE_API_KEY_3`
- `GROQ_API_KEY`, `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3`
- `GROQ_PRIMARY_MODEL`, `GROQ_FALLBACK_MODEL_1`, `GROQ_FALLBACK_MODEL_2`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`
- `HITL_TIMEOUT_MINUTES`
- `HYBRID_FALLBACK_ENABLED`, `HYBRID_FALLBACK_MAX_STEPS`

## Safety and Governance

- Destructive operations are flagged by tool metadata and routed through Guardian approval logic.
- Execution outcomes are recorded into audit logs with structured status context.
- Recovery Engine provides resilience via retry strategies and fallback pathways.
- Router-side key/model rotation mitigates provider-level transient quotas and rate limits.

## Development Workflow

Quality gate commands:

```bash
uv run ruff check --fix .
uv run pytest -v
```

Recommended branch discipline:

- Keep commits atomic by concern (tooling, memory, docs, tests).
- Avoid committing local runtime artifacts and secret-bearing files.
- Validate all interfaces after changes that affect shared models.

## Versioning Intent

- **V26** established robust desktop execution reliability.
- **V27** delivered key-rotation and fallback resilience improvements.
- **V28** extends toward a "Zenith" milestone: architecture integrity + richer tool intelligence + enterprise-grade documentation.

## License and Usage Notes

This repository is designed for controlled automation use. Before production deployment, ensure policy alignment for:

- local system automation permissions
- third-party API quota and billing controls
- audit retention and compliance obligations

---

# OmniCore V28 - Zenith Surumu (Turkce)

OmniCore, dogal dil ile verilen hedefleri guvenli, izlenebilir ve arac odakli sekilde gercek sistem eylemlerine donusturen uretim odakli otonom operasyon ajanidir.

V28 surumu uc ana basliga odaklanir:
- `core/`, `memory/`, `models/`, `interfaces/`, `tools/` katmanlarinda mimari sertlestirme
- analiz/dogrulama odakli yuksek degerli yeni araclar
- kurumsal kullanim seviyesinde kapsamli dokumantasyon iyilestirmesi

## Ozet

- **Misyon**: Kullanici niyetini planla, araclarla uygula, sonucu dogrula ve raporla.
- **Kontrol Duzlemi**: Cognitive Router + Planner + Guardian + Recovery Engine.
- **Veri Duzlemi**: Yapilandirilmis girdi/cikti kontratlarina sahip dinamik arac kaydi.
- **Bellek**: Kisa sureli baglam + uzun sureli anlamsal bellek + SQLite durum/kayit sistemi.
- **Arayuz Katmani**: CLI ve Telegram gecitleri (REST iskeleti proje yapisinda mevcut).

## V28 Ile Gelen Yenilikler

### Mimari Sertlestirme

- SQLite durum yonetimi guclendirildi: korumali baglanti erisimi (`_require_db`) ve acik baslatma hatasi.
- Eszamanli yazma guvenligi icin seri yazma yolu eklendi (`_write_lock` + `_execute_write`).
- Veritabani pragmalari ve tablo olusturma adiminda kararlı commit davranisi iyilestirildi.
- Dinamik arac kesfinde ayni isimli araclar icin tespit + uyari loglari eklendi.

### Yeni Gelismis Araclar

`tools/insight_toolkit.py` dosyasi ile eklenen araclar:

- `data_hash_text` - metin icin deterministik hash (md5/sha1/sha256/sha512)
- `text_profile_basic` - metin yapisal profili (karakter/kelime/satir/en sik token)
- `data_validate_json` - JSON dogrulama ve zorunlu anahtar kontrolu
- `data_csv_profile` - CSV profil analizi (sutun/satir/null benzeri deger yogunlugu/onizleme)
- `os_path_inspect` - yol metadatasi inceleme (varlik/tip/boyut/zaman damgalari)

Bu araclar mevcut dinamik kesif mekanizmasi ile otomatik kaydedilir.

## Cekirdek Mimari

```text
Kullanici Istegi
  -> Arayuz Gecidi (CLI / Telegram / REST)
  -> Cognitive Router (LLM yonlendirme + plan karari)
  -> Planner (adim plani)
  -> Guardian (yikici islemler icin HITL onayi)
  -> Recovery Engine (retry + fallback)
  -> Tool Registry (dinamik arac envanteri)
  -> Calistirma + Audit + Bellek kaliciligi
  -> Son cevap sentezi
```

## Proje Dizinleri

```text
config/          ayarlar, ortam degiskenleri, logging
core/            router, planner, guardian, recovery
interfaces/      cli, telegram, rest api gecitleri
memory/          kisa/uzun bellek, sqlite state tracker
models/          pydantic veri kontratlari
scheduler/       otonom zamanlayici akislar
scripts/         giris komutlari
tools/           dinamik kesfedilen arac kutuphaneleri
tests/           regresyon ve davranis testleri
```

## Calisma Gereksinimleri

- Python 3.12+
- `uv` paket yoneticisi
- Playwright Chromium (web otomasyon ozellikleri icin)
- Bazi gelismis araclar icin platforma bagli opsiyonel bagimliliklar

## Hizli Kurulum

```bash
git clone <repo-url>
cd OmniCore
uv sync
uv run playwright install chromium
cp .env.example .env
```

## Calistirma Modlari

```bash
# CLI modu
uv run python scripts/run.py --mode cli

# Telegram modu
uv run python scripts/run.py --mode telegram
```

## Konfigurasyon Ozet

Temel ortam degiskenleri:

- `LLM_PROVIDER`
- `OMNI_LLM_MODEL`
- `GOOGLE_API_KEY`, `GOOGLE_API_KEY_2`, `GOOGLE_API_KEY_3`
- `GROQ_API_KEY`, `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3`
- `GROQ_PRIMARY_MODEL`, `GROQ_FALLBACK_MODEL_1`, `GROQ_FALLBACK_MODEL_2`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`
- `HITL_TIMEOUT_MINUTES`
- `HYBRID_FALLBACK_ENABLED`, `HYBRID_FALLBACK_MAX_STEPS`

## Guvenlik ve Yonetisim

- Yikici islemler arac metadata'si ile isaretlenir ve Guardian onay katmanina gider.
- Calistirma sonuclari, durum bilgisi ile audit kaydina yazilir.
- Recovery Engine, retry ve fallback stratejileriyle dayaniklilik saglar.
- Router tarafindaki key/model rotasyonu kota ve rate-limit sorunlarini azaltir.

## Gelistirme Akisi

Kalite komutlari:

```bash
uv run ruff check --fix .
uv run pytest -v
```

Onereilen disiplin:

- Commitleri konu bazli atomik tut (tooling, memory, docs, tests).
- Yerel calisma artefaktlari ve gizli dosyalari commit etme.
- Ortak modelleri etkileyen degisikliklerde tum arayuzleri dogrula.

## Surum Yonelimi

- **V26** masaustu eylem guvenilirligini saglamlastirdi.
- **V27** key-rotation ve fallback dayanikliligini guclendirdi.
- **V28** "Zenith" hedefine ilerler: mimari butunluk + daha zengin arac zekasi + kurumsal dokumantasyon kalitesi.

## Lisans ve Kullanim Notu

Bu repo kontrollu otomasyon amaciyla tasarlanmistir. Uretimde kullanmadan once su basliklarda uygunluk kontrolu yapilmalidir:

- sistem otomasyon yetkileri
- ucuncu taraf API kota ve faturalama yonetimi
- audit kayit saklama ve uyumluluk zorunluluklari
