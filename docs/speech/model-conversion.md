# 模型转换

运行时 Worker 只加载 ONNX，不安装 PyTorch。转换使用独立的
`tools/genie_model_converter/` 环境：

```bash
cd tools/genie_model_converter
uv run --with . yuki-genie-convert --pth voice.pth --ckpt voice.ckpt \
  --output ./yuki-profile --profile-id yuki --display-name Yuki \
  --model-version v2proplus --language zh --languages zh jp \
  --reference-audio neutral.wav --reference-text "おはようございます。" \
  --reference-language jp
```

工具调用 Genie-TTS 2.0.2 官方 `convert_to_onnx`，仅接受 V2/V2ProPlus。完成后审阅
`profile.toml`，再通过主项目 CLI 导入。生产镜像、Bot 和 Worker 均不包含转换依赖。

`--language` 是默认目标语言，`--languages` 是这个声线允许的所有目标语言，
`--reference-language` 则必须与参考音频实际发音一致。三者不要求相同；例如上面的日语参考音频
可以服务于中文和日文合成。转换结束后可以在 Manifest 中继续加入其他风格 reference。
