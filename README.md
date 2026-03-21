# OmniCore

OmniCore, V27.0 OpenClaw-Level AGI OS Agent olarak tasarlanmis; host sistemde gercek eylem yapan, dinamik arac yukleyen, planli calisan ve hatadan toparlanan bir operasyon motorudur.

## V27.0 OpenClaw Apex

- Router katmaninda kalici 429/Quota rotasyonu: client sifirlama + anahtar/model rotasyonu + temiz yeniden olusturma.
- Gemini vision akisinda coklu anahtar denemesi (`GOOGLE_API_KEY`, `_2`, `_3`) ve kota asiminda acik fallback mesaji.
- GUI hotkey parametre cozumleme sertlestirildi: `keys/key/hotkey` ve ilk deger fallback'i.
- Web tarafinda fiziksel kaydirma akisi eklendi (`web_execute_javascript` + `scroll_to_bottom=true`).
- Repo hijyeni guclendirildi; gecici/yerel ve hassas dosyalar ignore kapsaminda tutuldu.

## Cekirdek Yetenekler

- Dogal dili adim adim planlara ayirip araclari yurutme.
- Kisa sureli + uzun sureli bellek entegrasyonu.
- Yikici islemler icin HITL onay katmani.
- Tool hatalarinda retry ve hibrit GUI fallback stratejileri.
- Gercek OS dosya, surec, tarayici, ag ve GUI otomasyonu.

## Mimari

```text
Kullanici Istegi
  -> Gateway (CLI / Telegram / REST)
  -> Cognitive Router
  -> Planner
  -> Guardian (onay)
  -> Recovery Engine
  -> Tool Registry (dinamik)
  -> Sonuc Sentezi
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
# CLI
uv run python scripts/run.py --mode cli

# Telegram
uv run python scripts/run.py --mode telegram
```

## Ortam Degiskenleri

Temel degiskenler:

- `LLM_PROVIDER`
- `GOOGLE_API_KEY`, `GOOGLE_API_KEY_2`, `GOOGLE_API_KEY_3`
- `GROQ_API_KEY`, `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3`
- `OMNI_LLM_MODEL`
- `GROQ_PRIMARY_MODEL`, `GROQ_FALLBACK_MODEL_1`, `GROQ_FALLBACK_MODEL_2`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`
- `HITL_TIMEOUT_MINUTES`
- `HYBRID_FALLBACK_ENABLED`, `HYBRID_FALLBACK_MAX_STEPS`

## Kalite Kontrolleri

```bash
uv run ruff check .
uv run pytest -v
```

## Dizin Yapisi

```text
config/       ayarlar + logging
core/         router, planner, guardian, recovery
interfaces/   telegram, cli, rest
memory/       kisa/uzun bellek + sqlite state
models/       veri modelleri
scheduler/    gorev planlayici
tools/        dinamik araclar
tests/        pytest testleri
scripts/      calistirma scriptleri
```
