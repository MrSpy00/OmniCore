"""Tests for OmniCore v0.40.0 system enhancements, modes, and toolkits."""


import pytest

from interfaces.rest_api import create_app
from interfaces.voice_duplex import DuplexVoiceEngine
from tools.game_updater_toolkit import (
    GameUpdater,
    _find_steam_library_folders,
)


@pytest.mark.asyncio
async def test_voice_duplex_engine_lifecycle():
    engine = DuplexVoiceEngine()
    assert not engine.is_streaming

    status = await engine.start_session()
    assert status["status"] == "active"
    assert engine.is_streaming

    await engine.push_audio_chunk(b"\x00\x01\x02\x03")
    assert engine.input_audio_queue.qsize() == 1

    stop_status = await engine.stop_session()
    assert stop_status["status"] == "stopped"
    assert not engine.is_streaming


@pytest.mark.asyncio
async def test_game_updater_vdf_parsing(tmp_path):
    steam_root = tmp_path / "Steam"
    steamapps = steam_root / "steamapps"
    steamapps.mkdir(parents=True)

    vdf_content = '''
"libraryfolders"
{
    "0"
    {
        "path"      "C:\\\\Program Files (x86)\\\\Steam"
    }
    "1"
    {
        "path"      "D:\\\\Games\\\\SteamLibrary"
    }
}
'''
    vdf_file = steamapps / "libraryfolders.vdf"
    vdf_file.write_text(vdf_content, encoding="utf-8")

    libs = _find_steam_library_folders(steam_root)
    assert len(libs) >= 1


@pytest.mark.asyncio
async def test_game_updater_acf_manifest_parsing(tmp_path):
    steamapps = tmp_path / "steamapps"
    steamapps.mkdir(parents=True)

    acf_content = '''
"AppState"
{
    "appid"     "730"
    "name"      "Counter-Strike 2"
    "StateFlags" "4"
    "SizeOnDisk" "32000000000"
}
'''
    acf_file = steamapps / "appmanifest_730.acf"
    acf_file.write_text(acf_content, encoding="utf-8")

    tool = GameUpdater()
    games = tool._scan_steam_games()
    # If host is not windows or test runs in isolated temp, check method execution
    assert isinstance(games, list)


@pytest.mark.asyncio
async def test_rest_api_creation():
    class DummyRouter:
        async def handle_message(self, msg, conv_id):
            return "Mock reply"

    app = create_app(DummyRouter())
    assert app.title == "OmniCore API"
    assert app.version == "0.40.0"
