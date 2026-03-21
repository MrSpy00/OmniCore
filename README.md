# OmniCore V32.0 - THE-OMNICORE-APEX-SINGULARITY

OmniCore is an autonomous execution platform that turns natural-language intent into real, auditable system action across CLI, GUI, browser, and vision loops.

V32.0 establishes **Universal App Mastery**: OmniCore no longer behaves like a fixed-app automation script. It behaves like a domain-adaptive control system that can discover, reason, and act across unknown software surfaces.

## Executive Positioning

- Mission: Convert intent into safe execution with evidence-backed outcomes.
- Principle: Plan -> Verify -> Execute -> Audit -> Recover.
- Outcome: A production-grade, multi-domain control plane for real environments.

## V32.0 Core Leap

V32.0 delivers five strategic upgrades:

1. Universal App Mastery (not app-specific macros)
2. Bilingual enterprise documentation standard (EN + TR)
3. Zero-defect polish and lint discipline
4. Immortal rate-limit continuity with no-wait key rotation
5. Vision-first GUI completion loop for unknown UI states

## Universal App Mastery

OmniCore now operates through a hybrid execution model:

- CLI/Process actions for deterministic shell-level control
- GUI actions for native desktop interfaces
- Vision-guided correction for uncertain screen state
- Browser automation for web surfaces

When an app or domain is unknown, OmniCore can:

1. Gather context with `web_deep_crawl`
2. Build a domain understanding snapshot
3. Compose the right tool chain dynamically
4. Execute with Guardian-governed safety checks

This turns OmniCore from static automation into adaptive operational intelligence.

## 10 Core Domains

OmniCore V32.0 is organized around ten execution domains:

1. System
2. Filesystem
3. Process
4. Network
5. UI
6. Media
7. Vision
8. Browser
9. DevOps
10. Security

## Risk Model and Guardian Governance

Every action is classified by risk and routed through policy:

- Low: read-only observation
- Medium: controlled non-destructive mutation
- High: impactful system/process/network changes
- Critical: irreversible or security-sensitive operations

Guardian enforces human-in-the-loop checkpoints for high and critical paths, with explicit intent validation and audit trace retention.

## Immortal 429 Rotator (No-Wait Continuity)

Provider rate-limit failures are handled with immediate, sequential API key rotation:

- Detect 429
- Rotate key instantly
- Retry immediately (no blocking wait)
- Continue until success or pool exhaustion

This preserves operational flow under provider-side quota pressure.

## Universal Vision-GUI Loop

For uncertain or changing interfaces, OmniCore executes a closed correction cycle:

1. Observe screen state
2. Ground target intent
3. Execute interaction
4. Re-observe and validate
5. Retry/correct if mismatch

This enables stable completion even in dynamic, non-deterministic GUI conditions.

## Architecture Overview

```text
User Intent
  -> Interface Layer (CLI / Telegram / API)
  -> Cognitive Router
  -> Planner
  -> Guardian (Risk + HITL)
  -> Recovery Engine
  -> Dynamic Tool Registry
  -> Execution (CLI + GUI + Vision + Browser)
  -> Audit + Memory Persistence
  -> Final Response
```

## Repository Structure

```text
config/          runtime settings and environment contracts
core/            router, planner, guardian, recovery
interfaces/      CLI, Telegram, API gateways
memory/          short-term, long-term, sqlite state/audit
models/          typed contracts and schemas
scheduler/       autonomous job and pulse flows
scripts/         startup entrypoints
tools/           dynamically discovered toolkits
tests/           regression and behavior verification
```

## Setup

```bash
git clone <repo-url>
cd OmniCore
uv sync
uv run playwright install chromium
cp .env.example .env
```

## Run

```bash
# CLI mode
uv run python scripts/run.py --mode cli

# Telegram mode
uv run python scripts/run.py --mode telegram
```

## Quality Gates

```bash
uv run ruff check --fix .
uv run pytest -v
```

## Security and Operations Notes

- Do not commit secrets or local runtime artifacts.
- Keep destructive operations behind Guardian policy.
- Keep retries observable and auditable.
- Prefer adaptive domain discovery over hardcoded one-off logic.

---

# OmniCore V32.0 - THE-OMNICORE-APEX-SINGULARITY (Turkce)

OmniCore, dogal dil ile verilen hedefleri gercek ve izlenebilir sistem aksiyonlarina donusturen otonom bir yurutme platformudur. CLI, GUI, browser ve vision akislari birlikte calisir.

V32.0 ile OmniCore, sabit uygulama otomasyonundan cikarak **Evrensel Uygulama Hakimiyeti** seviyesine tasinmistir.

## Stratejik Konum

- Misyon: Niyeti guvenli sekilde eyleme donusturmek.
- Prensip: Planla -> Dogrula -> Uygula -> Kaydet -> Kurtar.
- Cikti: Uretim seviyesi, cok-domain, denetlenebilir kontrol duzlemi.

## V32.0 Buyuk Sicrama

V32.0 bes ana yetenek getirir:

1. Evrensel uygulama kontrolu (uygulama-ozel makro degil)
2. Kurumsal cift dilli dokumantasyon standardi (EN + TR)
3. Sifir-kusur cilasi ve lint disiplini
4. Beklemesiz 429 anahtar rotasyonu ile kesintisiz devam
5. Bilinmeyen arayuzlerde vision destekli GUI tamamlama dongusu

## Evrensel Uygulama Hakimiyeti

OmniCore artik hibrit yurutme modelinde calisir:

- CLI/Process ile deterministik kontrol
- GUI ile masaustu etkileşim
- Vision ile durum dogrulama ve duzeltme
- Browser otomasyonu ile web yuzeyleri

Bilinmeyen bir domain veya uygulamada OmniCore:

1. `web_deep_crawl` ile hizli bilgi toplar
2. Domain baglamini cikarir
3. Uygun arac zincirini dinamik kurar
4. Guardian guvencesi ile yurutur

Boylece OmniCore, sabit script mantigindan cikarak adaptif operasyon zekasina donusur.

## 10 Cekirdek Domain

1. System
2. Filesystem
3. Process
4. Network
5. UI
6. Media
7. Vision
8. Browser
9. DevOps
10. Security

## Risk Modeli ve Guardian

Her aksiyon risk sinifina gore yonetilir:

- Low: sadece gozlem
- Medium: kontrollu, geri alinabilir degisiklik
- High: etkili sistem/process/network mutasyonu
- Critical: geri donusu zor veya guvenlik-hassas adim

Guardian, High ve Critical aksiyonlarda insan-onayli guvenlik kapisi uygular ve denetim kaydi olusturur.

## Immortal 429 Rotator (Bekleme Yok)

Rate-limit durumunda akis asagidaki gibi calisir:

- 429 algilanir
- Anahtar aninda degistirilir
- Beklemeden tekrar denenir
- Basari veya havuz bitene kadar devam edilir

Bu mimari, kota baskisinda dahi operasyon surekliligi saglar.

## Evrensel Vision-GUI Dongusu

Arayuz belirsizse OmniCore kapali bir duzeltme dongusu kullanir:

1. Ekrani gozlemle
2. Hedefi sabitle
3. Etkilesimi uygula
4. Yeniden gozlemle
5. Sapma varsa duzelt ve tekrar dene

Bu sayede degisken GUI durumlarinda dahi tamamlanma kalitesi korunur.

## Mimari Ozet

```text
Kullanici Niyeti
  -> Arayuz Katmani (CLI / Telegram / API)
  -> Cognitive Router
  -> Planner
  -> Guardian (Risk + HITL)
  -> Recovery Engine
  -> Dynamic Tool Registry
  -> Execution (CLI + GUI + Vision + Browser)
  -> Audit + Memory
  -> Sonuc
```

## Kurulum

```bash
git clone <repo-url>
cd OmniCore
uv sync
uv run playwright install chromium
cp .env.example .env
```

## Calistirma

```bash
# CLI modu
uv run python scripts/run.py --mode cli

# Telegram modu
uv run python scripts/run.py --mode telegram
```

## Kalite Kapilari

```bash
uv run ruff check --fix .
uv run pytest -v
```

## Operasyon Notlari

- Gizli bilgi ve runtime artefaktlarini commitlemeyin.
- Yikici aksiyonlari Guardian politikasi arkasinda tutun.
- Retry davranisini her zaman denetlenebilir kilin.
- Sabit tekil scriptler yerine domain-adaptif yaklasimi tercih edin.
