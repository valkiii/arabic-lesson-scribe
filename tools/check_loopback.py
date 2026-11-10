"""Standalone check for a Windows PC: list audio devices, record 5 seconds of the computer's sound and of the
microphone, save them as WAV files and print the levels.

Usage (Windows, from the repo root or with the app's Python):
    python tools/check_loopback.py [seconds] [output_folder]

Play some sound (music, a video) through the DEFAULT speakers or headphones while it runs and speak a little.
Needs: pip install PyAudioWPatch==0.2.12.9 sounddevice==0.5.6 numpy
Writes system.wav (16 kHz mono) and mic.wav next to this script (or into output_folder). Exit code 0 when both
were captured, 1 when the computer's sound was silent or missing, 2 on an error.
"""
from __future__ import annotations

import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent


def to16k(x: np.ndarray, rate: int) -> np.ndarray:
    """Quick and simple (linear interpolation) is enough for a level check; the app uses a better resampler."""
    if rate == 16000 or len(x) == 0:
        return x
    n = int(len(x) * 16000 / rate)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)


def save(path: Path, x: np.ndarray) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(np.clip(x, -32768, 32767).astype("<i2").tobytes())


def level(x: np.ndarray) -> tuple[float, float]:
    if len(x) == 0:
        return 0.0, 0.0
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2)) / 32768), float(np.max(np.abs(x)) / 32768)


def main() -> int:
    if sys.platform != "win32":
        print("This check only makes sense on Windows (WASAPI loopback).")
        return 2
    import pyaudiowpatch as pyaudio
    import sounddevice as sd

    pa = pyaudio.PyAudio()
    loops = list(pa.get_loopback_device_info_generator())
    print("Output devices that can be recorded (loopback):")
    for d in loops:
        print(f"  [{d['index']}] {d['name']}  {int(d['defaultSampleRate'])} Hz, {d['maxInputChannels']} ch")
    print("Microphones:")
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and d["hostapi"] == sd.default.hostapi:
            print(f"  [{i}] {d['name']}")
    try:
        dev = pa.get_default_wasapi_loopback()
    except Exception as e:  # noqa: BLE001
        print("No default output device:", e)
        return 2
    print(f"\nRecording {SECONDS:g} s from: {dev['name']}  (play sound now, and speak)")

    rate, ch = int(dev["defaultSampleRate"]), int(dev["maxInputChannels"])
    sys_blocks: list[np.ndarray] = []
    t0 = time.monotonic()
    first_cb = []

    def cb(data, frames, ti, status):
        if not first_cb:
            first_cb.append(time.monotonic() - t0)
        sys_blocks.append(np.frombuffer(data, dtype=np.int16).reshape(-1, ch).mean(axis=1))
        return (None, pyaudio.paContinue)

    stream = pa.open(format=pyaudio.paInt16, channels=ch, rate=rate, frames_per_buffer=rate // 10, input=True,
                     input_device_index=dev["index"], stream_callback=cb)
    mic = sd.rec(int(SECONDS * 16000), samplerate=16000, channels=1, dtype="int16")
    time.sleep(SECONDS)
    stream.stop_stream(); stream.close(); pa.terminate()
    sd.wait()

    system = to16k(np.concatenate(sys_blocks), rate) if sys_blocks else np.zeros(0)
    micx = mic.reshape(-1).astype(np.float64)
    save(OUT / "system.wav", system)
    save(OUT / "mic.wav", micx)
    sl, sp = level(system)
    ml, mp = level(micx)
    result = {"system_seconds_received": round(len(system) / 16000, 2), "system_rms": round(sl, 4), "system_peak": round(sp, 4),
              "system_first_data_after_s": None if not first_cb else round(first_cb[0], 2),
              "mic_rms": round(ml, 4), "mic_peak": round(mp, 4), "files": [str(OUT / "system.wav"), str(OUT / "mic.wav")]}
    print(json.dumps(result, indent=2))
    print("\nNote: if system_seconds_received is much less than the duration, loopback delivers nothing while no sound "
          "plays. That is normal; the app fills the gaps with silence.")
    if sl < 0.002:
        print("PROBLEM: the computer's sound is silent. Was something playing on the default output?")
        return 1
    if ml < 0.002:
        print("WARNING: the microphone is silent (muted, or blocked by the Windows privacy setting).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print("ERROR:", e)
        sys.exit(2)
