"""Global Hotkey Kayıt Modülü — Kısayol tuşları ile Spotlight'ı açar/kapatır.

Windows'ta `keyboard` kütüphanesi ile global hotkey kaydı yapar.
"""

from __future__ import annotations

from collections.abc import Callable

from config.logging import get_logger

logger = get_logger(__name__)

try:
    import keyboard as _keyboard

    _KEYBOARD_AVAILABLE = True
except ImportError:
    _KEYBOARD_AVAILABLE = False


def register_global_hotkey(
    callback: Callable[[], None],
    hotkey: str = "ctrl+space",
) -> bool:
    """Global bir kısayol tuşu kaydı yapar.

    Args:
        callback: Kısayol tuşuna basıldığında çağrılacak fonksiyon.
        hotkey: Kısayol tuşu deseni (varsayılan: Ctrl+Space).

    Returns:
        True eğer başarıyla kaydedildiyse.
    """
    if not _KEYBOARD_AVAILABLE:
        logger.warning("spotlight.hotkey_not_available", hint="keyboard kütüphanesi yüklü değil")
        return False

    def _handler() -> None:
        try:
            callback()
        except Exception as exc:
            logger.error("spotlight.hotkey_error", error=str(exc))

    try:
        _keyboard.add_hotkey(hotkey, _handler, suppress=False, timeout=1)
        logger.info("spotlight.hotkey_registered", hotkey=hotkey)
        return True
    except Exception as exc:
        logger.error("spotlight.hotkey_register_failed", error=str(exc))
        return False


def unregister_all_hotkeys() -> None:
    """Tüm kayıtlı global hotkey'leri kaldırır."""
    if _KEYBOARD_AVAILABLE:
        try:
            _keyboard.unhook_all()
        except Exception:
            pass
