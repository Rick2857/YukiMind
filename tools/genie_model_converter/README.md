# Genie model converter

This tool is intentionally separate from the production Bot and Worker. It installs
PyTorch only in the conversion environment and calls Genie-TTS 2.0.2's official
`convert_to_onnx(torch_pth_path, torch_ckpt_path, output_dir)` API.

```bash
cd tools/genie_model_converter
uv run --with . yuki-genie-convert \
  --pth /models/voice.pth --ckpt /models/voice.ckpt \
  --output /tmp/yuki-profile --profile-id yuki --display-name Yuki \
  --model-version v2proplus --language zh \
  --reference-audio /models/neutral.wav --reference-text "你好。"
```

Inspect the generated `profile.toml`, then import the whole output directory with
`qq-ai-bot-cli speech profile import /tmp/yuki-profile`. No model is downloaded by
Yuki, and conversion never runs in the production Worker.
