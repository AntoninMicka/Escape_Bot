#!/usr/bin/env python3
"""Generate the production Czech voice lines declared in scenario.json.

Install ``piper-tts`` and download a Czech Piper model first, then run this
script from the repository root. The output names are stable and match
``voice_id`` values used by the client. All scenario text stays local.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATH = ROOT / "backend" / "scenario.json"
OUTPUT_DIR = ROOT / "client" / "assets" / "voices"
PROFILES = {
    "captain": {"length_scale": "1.07", "pitch_factor": 0.94},
    "elara": {"length_scale": "0.96", "pitch_factor": 1.06},
}
PRONUNCIATION = {
    "elara_return_vector": {"MOTOR → STABILIZÁTOR → KRYSTAL": "motor, potom stabilizátor, potom krystal"},
}


def voice_lines(value: Any) -> dict[str, str]:
    found: dict[str, str] = {}
    if isinstance(value, dict):
        voice_id = value.get("voice_id")
        text = value.get("text")
        if isinstance(voice_id, str) and isinstance(text, str):
            found[voice_id] = text
        for child in value.values():
            found.update(voice_lines(child))
    elif isinstance(value, list):
        for child in value:
            found.update(voice_lines(child))
    return found


def spoken_text(voice_id: str, text: str) -> str:
    text = re.sub(r"\*[^*]+\*", "", text)
    for source, replacement in PRONUNCIATION.get(voice_id, {}).items():
        text = text.replace(source, replacement)
    return " ".join(text.split())


def generate_one(voice_id: str, text: str, overwrite: bool, model: Path) -> None:
    destination = OUTPUT_DIR / f"{voice_id}.mp3"
    if destination.exists() and not overwrite:
        print(f"skip {destination.relative_to(ROOT)}")
        return
    profile_name = "captain" if voice_id.startswith("captain_") else "elara"
    profile = PROFILES[profile_name]
    with tempfile.TemporaryDirectory(prefix="escape-bot-voice-") as temporary:
        raw = Path(temporary) / "raw.wav"
        subprocess.run([
            sys.executable, "-m", "piper", "--model", str(model), "--output_file", str(raw),
            "--length_scale", profile["length_scale"], "--sentence_silence", "0.18",
        ], input=spoken_text(voice_id, text), text=True, check=True)
        pitch = profile["pitch_factor"]
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw),
            "-af", f"asetrate=22050*{pitch},aresample=22050,atempo={1 / pitch},loudnorm=I=-16:TP=-1.5:LRA=11",
            "-codec:a", "libmp3lame", "-b:a", "96k",
            str(destination),
        ], check=True)
    print(f"write {destination.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--model", type=Path, required=True, help="Path to a local Czech Piper .onnx model")
    args = parser.parse_args()
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    lines = voice_lines(scenario)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for voice_id, text in sorted(lines.items()):
        generate_one(voice_id, text, args.overwrite, args.model)
    print(f"generated {len(lines)} voice lines with {args.model.name}")


if __name__ == "__main__":
    main()
