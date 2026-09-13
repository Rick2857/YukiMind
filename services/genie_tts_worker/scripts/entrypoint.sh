#!/bin/sh
set -eu

# Docker creates named/bind mount roots as root. Prepare only the two writable
# locations, then permanently drop privileges before importing Genie-TTS.
mkdir -p /run/yuki-speech /data/speech/cache
chown speech:speech /run/yuki-speech /data/speech/cache
chmod 0770 /run/yuki-speech /data/speech/cache

exec setpriv --reuid=10001 --regid=10001 --init-groups \
  python -m genie_tts_worker "$@"
