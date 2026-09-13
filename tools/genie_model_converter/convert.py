"""Explicit offline model conversion; never imported by the production Bot or Worker."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _profile_toml(args: argparse.Namespace, audio_name: str) -> str:
    return f"""id = {_quote(args.profile_id)}
display_name = {_quote(args.display_name)}
provider = "genie"
engine_model_version = {_quote(args.model_version)}
language = {_quote(args.language)}
supported_languages = [{", ".join(_quote(item) for item in args.languages)}]
default_style = "neutral"
enabled = true
source = "user_supplied"
source_note = "Converted locally from user-supplied GPT-SoVITS weights"
license_note = "The deployer is responsible for model and source-audio rights"

[model]
path = "model"

[[references]]
id = "neutral"
style = "neutral"
aliases = ["日常", "平静"]
audio = {_quote(f"references/{audio_name}")}
text = {_quote(args.reference_text)}
language = {_quote(args.reference_language)}
enabled = true
priority = 0
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert local GPT-SoVITS V2/V2ProPlus weights for Yuki's Genie worker."
    )
    parser.add_argument("--pth", type=Path, required=True, help="GPT-SoVITS .pth file")
    parser.add_argument("--ckpt", type=Path, required=True, help="GPT .ckpt file")
    parser.add_argument("--output", type=Path, required=True, help="new voice-profile directory")
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--language", default="zh", choices=("zh", "jp", "en"))
    parser.add_argument(
        "--languages",
        nargs="+",
        choices=("zh", "jp", "en"),
        default=("zh",),
        help="target languages supported by the resulting profile",
    )
    parser.add_argument(
        "--reference-language",
        choices=("zh", "jp", "en"),
        help="language actually spoken in the reference audio",
    )
    parser.add_argument("--model-version", choices=("v2", "v2proplus"), required=True)
    parser.add_argument("--reference-audio", type=Path, required=True)
    parser.add_argument("--reference-text", required=True)
    args = parser.parse_args()
    args.reference_language = args.reference_language or args.language
    args.languages = tuple(dict.fromkeys(args.languages))
    if args.language not in args.languages:
        raise SystemExit("--language must also be present in --languages")

    for path, label in (
        (args.pth, "PTH model"),
        (args.ckpt, "CKPT model"),
        (args.reference_audio, "reference audio"),
    ):
        if not path.is_file():
            raise SystemExit(f"{label} does not exist: {path}")
    if args.output.exists():
        raise SystemExit("output directory already exists")

    model_directory = args.output / "model"
    reference_directory = args.output / "references"
    model_directory.mkdir(parents=True)
    reference_directory.mkdir()

    import genie_tts as genie

    genie.convert_to_onnx(
        torch_pth_path=str(args.pth.resolve()),
        torch_ckpt_path=str(args.ckpt.resolve()),
        output_dir=str(model_directory.resolve()),
    )
    audio_name = "neutral" + args.reference_audio.suffix.lower()
    shutil.copy2(args.reference_audio, reference_directory / audio_name)
    (args.output / "profile.toml").write_text(
        _profile_toml(args, audio_name),
        encoding="utf-8",
    )
    print(f"Converted profile: {args.output}")


if __name__ == "__main__":
    main()
