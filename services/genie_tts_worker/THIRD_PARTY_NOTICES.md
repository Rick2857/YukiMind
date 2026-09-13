# Third-party notices for YukiMind Genie-TTS Worker

YukiMind Worker code is distributed under the accompanying MIT License.
Installed Python and system packages retain their own licenses; the release
workflow publishes an SPDX SBOM for the exact image.

- `genie-tts==2.0.2`: package code declares MIT. GenieData, voice models,
  reference audio and other separately acquired assets are not included.
- The official image does not install `e2k` or distribute its dictionaries or
  trained weights. The optional source integration remains disabled unless a
  deployment operator builds a custom image and separately establishes the
  applicable rights.
