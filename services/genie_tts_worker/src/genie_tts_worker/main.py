"""Command-line entrypoint for the offline Unix-socket Worker."""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
from pathlib import Path

from genie_tts_worker.engine import GenieEngine
from genie_tts_worker.paths import SpeechPathPolicy
from genie_tts_worker.server import GenieWorkerServer
from genie_tts_worker.text_frontends import SpeechFrontendRegistry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yuki offline Genie-TTS Worker")
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--speech-root", type=Path, required=True)
    parser.add_argument("--socket-mode", default="0660")
    parser.add_argument("--idle-recycle-seconds", type=float, default=0)
    return parser


def configure_offline_environment(genie_data_dir: Path) -> None:
    os.environ["GENIE_DATA_DIR"] = str(genie_data_dir.resolve())
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


async def run(args: argparse.Namespace) -> None:
    configure_offline_environment(args.data_dir)
    paths = SpeechPathPolicy(args.speech_root)
    engine = GenieEngine(paths=paths, genie_data_dir=args.data_dir)
    japanese_frontend = SpeechFrontendRegistry.build_japanese(
        enabled=_env_bool("SPEECH_JP_KATAKANA_ENABLED", True),
        asset_dir=Path(
            os.environ.get(
                "SPEECH_JP_KATAKANA_ASSET_DIR",
                "/data/speech/japanese_frontend/models",
            )
        ),
        lexicon_path=Path(
            os.environ.get(
                "SPEECH_JP_KATAKANA_LEXICON",
                "/data/speech/japanese_frontend/lexicon.toml",
            )
        ),
    )
    server = GenieWorkerServer(
        socket_path=args.socket,
        engine=engine,
        socket_mode=int(args.socket_mode, 8),
        idle_recycle_seconds=max(0.0, args.idle_recycle_seconds),
        text_frontends=japanese_frontend,
    )
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, lambda: asyncio.create_task(server.request_shutdown()))
    await server.start()
    await server.serve_until_shutdown()


def main() -> None:
    asyncio.run(run(_parser().parse_args()))


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


if __name__ == "__main__":
    main()
