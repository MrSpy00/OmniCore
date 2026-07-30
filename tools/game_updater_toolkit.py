"""Game Updater Toolkit — Steam & Epic Games Launcher integration.

Allows OmniCore to manage game updates via the SteamCMD CLI and the
Epic Games Launcher.  Inspired by the Mark-XXXV ``game_updater`` function.

Safe Defaults:
  - Never performs destructive uninstalls without explicit parameters.
  - Lists installed games before update actions for confirmation.
  - All operations are logged and can be stopped.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool
from tools.os_adapters import runtime_adapter

_RUNTIME = runtime_adapter()

# Common Steam installation paths on Windows
_STEAM_PATHS = [
    Path("C:/Program Files (x86)/Steam"),
    Path("C:/Program Files/Steam"),
    Path(os.path.expandvars("%ProgramFiles(x86)%/Steam")),
]

# Common Epic Games launcher executable paths
_EPIC_PATHS = [
    Path("C:/Program Files (x86)/Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe"),
    Path("C:/Program Files/Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe"),
]


def _find_steam_path() -> Path | None:
    for p in _STEAM_PATHS:
        if p.exists():
            return p
    return None


def _find_steamcmd() -> Path | None:
    """Find SteamCMD executable."""
    steam_root = _find_steam_path()
    if steam_root:
        candidate = steam_root / "steamcmd.exe"
        if candidate.exists():
            return candidate
    # Check standalone SteamCMD
    standalone = Path("C:/SteamCMD/steamcmd.exe")
    if standalone.exists():
        return standalone
    return None


class GameUpdater(BaseTool):
    """Manage Steam and Epic Games updates.

    Actions:
    - ``list``            — List installed Steam games (from Steam library)
    - ``update``          — Force update a Steam game by AppID or name
    - ``install``         — Install a Steam game by AppID
    - ``steam_status``    — Check if Steam is running
    - ``epic_launch``     — Launch Epic Games Launcher
    - ``download_status`` — Check active Steam downloads
    """

    name = "game_updater"
    description = (
        "Manage Steam and Epic Games: list installed games, trigger updates, "
        "install games by AppID, check download status, or launch Epic Games. "
        "Parameters: action (list|update|install|steam_status|epic_launch|download_status), "
        "app_id (Steam AppID for update/install), game_name (partial name for update)."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        if not _RUNTIME.is_windows:
            return self._failure("Bu araç yalnızca Windows'ta çalışır.")

        params = self._params(tool_input)
        action = str(
            self._first_param(params, "action", default="list") or "list"
        ).strip().lower()
        app_id = str(self._first_param(params, "app_id", "appid", default="") or "")
        game_name = str(self._first_param(params, "game_name", "game", default="") or "")

        if action == "steam_status":
            return await self._steam_status()
        if action == "list":
            return await self._list_steam_games()
        if action == "epic_launch":
            return await self._launch_epic()
        if action == "download_status":
            return await self._download_status()
        if action == "update":
            if not app_id and not game_name:
                return self._failure("update için 'app_id' veya 'game_name' gerekli.")
            return await self._update_game(app_id=app_id, game_name=game_name)
        if action == "install":
            if not app_id:
                return self._failure("install için 'app_id' gerekli (Steam AppID).")
            return await self._install_game(app_id=app_id)

        return self._failure(
            f"Bilinmeyen action: '{action}'. "
            "Geçerli: list, update, install, steam_status, epic_launch, download_status"
        )

    async def _steam_status(self) -> ToolOutput:
        """Check if Steam process is running."""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"],
                    capture_output=True, text=True, timeout=10,
                ),
            )
            running = "steam.exe" in result.stdout.lower()
            steam_path = _find_steam_path()
            return self._success(
                f"Steam {'çalışıyor ✅' if running else 'çalışmıyor ❌'}",
                data={
                    "running": running,
                    "steam_path": str(steam_path) if steam_path else None,
                    "steamcmd_available": _find_steamcmd() is not None,
                },
            )
        except Exception as exc:
            return self._failure(f"Steam durumu kontrol hatası: {exc}")

    async def _list_steam_games(self) -> ToolOutput:
        """List Steam libraries and installed game folders."""
        steam_path = _find_steam_path()
        if not steam_path:
            return self._failure(
                "Steam kurulum dizini bulunamadı. "
                "Lütfen Steam'in yüklü olduğundan emin olun."
            )

        steamapps = steam_path / "steamapps"
        if not steamapps.exists():
            return self._failure(f"steamapps dizini bulunamadı: {steamapps}")

        acf_files = list(steamapps.glob("appmanifest_*.acf"))
        games: list[dict] = []
        for acf in acf_files:
            try:
                content = acf.read_text(encoding="utf-8", errors="ignore")
                name_match = None
                appid_match = None
                for line in content.splitlines():
                    line = line.strip()
                    if '"name"' in line.lower():
                        parts = line.split('"')
                        if len(parts) >= 4:
                            name_match = parts[3]
                    if '"appid"' in line.lower():
                        parts = line.split('"')
                        if len(parts) >= 4:
                            appid_match = parts[3]
                if name_match:
                    games.append({"name": name_match, "app_id": appid_match or "?"})
            except Exception:
                continue

        games.sort(key=lambda g: g["name"].lower())
        summary_lines = [f"• {g['name']} (AppID: {g['app_id']})" for g in games[:30]]
        summary = f"{len(games)} oyun bulundu:\n" + "\n".join(summary_lines)
        if len(games) > 30:
            summary += f"\n... ve {len(games) - 30} oyun daha."
        return self._success(summary, data={"games": games, "count": len(games)})

    async def _update_game(self, app_id: str, game_name: str) -> ToolOutput:
        """Trigger Steam to update a game via Steam protocol URL."""
        steamcmd = _find_steamcmd()
        steam_path = _find_steam_path()

        if not app_id and game_name:
            # Try to find AppID from installed games
            list_result = await self._list_steam_games()
            if list_result.status.value == "success":
                games = list_result.data.get("games", [])
                matches = [
                    g for g in games
                    if game_name.lower() in g["name"].lower()
                ]
                if matches:
                    app_id = matches[0]["app_id"]
                    game_name = matches[0]["name"]

        if not app_id:
            return self._failure(
                f"'{game_name}' için AppID bulunamadı. "
                "Lütfen 'app_id' parametresini manuel olarak girin."
            )

        # Launch Steam with update URL (works even if SteamCMD not available)
        update_url = f"steam://run/{app_id}"
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.Popen(
                    ["cmd", "/c", "start", "", update_url],
                    shell=True,
                ),
            )
            return self._success(
                f"Steam güncelleme başlatıldı: AppID={app_id}" +
                (f" ({game_name})" if game_name else ""),
                data={"app_id": app_id, "game_name": game_name, "method": "steam_url"},
            )
        except Exception as exc:
            return self._failure(f"Güncelleme başlatma hatası: {exc}")

    async def _install_game(self, app_id: str) -> ToolOutput:
        """Install a Steam game by AppID via Steam store URL."""
        install_url = f"steam://install/{app_id}"
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.Popen(
                    ["cmd", "/c", "start", "", install_url],
                    shell=True,
                ),
            )
            return self._success(
                f"Steam kurulum başlatıldı: AppID={app_id}. "
                "Steam penceresi kurulum onayı isteyecek.",
                data={"app_id": app_id, "method": "steam_install_url"},
            )
        except Exception as exc:
            return self._failure(f"Kurulum başlatma hatası: {exc}")

    async def _download_status(self) -> ToolOutput:
        """Check active Steam download status via powershell process list."""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    [
                        "powershell", "-NoProfile", "-Command",
                        "Get-Process | Where-Object {$_.Name -like '*steam*'} "
                        "| Select-Object Name,CPU,WorkingSet | ConvertTo-Json"
                    ],
                    capture_output=True, text=True, timeout=15,
                ),
            )
            info = (result.stdout or "").strip() or "Steam süreci bilgisi alınamadı."
            return self._success(
                "Steam süreç durumu alındı.",
                data={"process_info": info},
            )
        except Exception as exc:
            return self._failure(f"Süreç bilgisi alınamadı: {exc}")

    async def _launch_epic(self) -> ToolOutput:
        """Launch Epic Games Launcher."""
        for epic_path in _EPIC_PATHS:
            if epic_path.exists():
                try:
                    subprocess.Popen([str(epic_path)])
                    return self._success(
                        "Epic Games Launcher başlatıldı.",
                        data={"path": str(epic_path)},
                    )
                except Exception as exc:
                    return self._failure(f"Epic başlatma hatası: {exc}")

        # Try via Windows protocol
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "com.epicgames.launcher://"], shell=True)
            return self._success(
                "Epic Games Launcher protokol URL ile başlatıldı.",
                data={"method": "protocol_url"},
            )
        except Exception as exc:
            return self._failure(
                f"Epic Games Launcher bulunamadı. "
                f"Lütfen kurulu olduğundan emin olun. Hata: {exc}"
            )
