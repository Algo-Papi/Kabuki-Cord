from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "web" / "assets" / "kabuki-launch-theme.wav"
SAMPLE_RATE = 44_100
DURATION = 6.25
TAU = math.tau


def main() -> None:
    random.seed(92817)
    length = int(SAMPLE_RATE * DURATION)
    left = [0.0] * length
    right = [0.0] * length

    # Taiko entrance pattern.
    for t, freq, amp in [
        (0.08, 64, 1.05),
        (0.42, 52, 0.72),
        (0.76, 84, 0.92),
        (1.36, 58, 1.0),
        (1.68, 104, 0.62),
        (2.18, 49, 1.08),
        (2.48, 72, 0.7),
        (3.16, 45, 1.15),
        (3.42, 92, 0.78),
        (4.05, 56, 1.0),
        (4.48, 78, 0.76),
        (5.18, 42, 1.2),
    ]:
        add_stereo(left, right, t, taiko(freq, 0.72, amp), pan=0.0)

    # Fast roll into the final logo snap.
    for index in range(12):
        t = 4.62 + index * 0.052
        add_stereo(left, right, t, taiko(110 + index * 2.5, 0.22, 0.28 + index * 0.018), pan=(-1) ** index * 0.18)

    # Hand-clap / hyoshigi-style accents.
    for t, pan, amp in [
        (0.30, -0.15, 0.46),
        (0.60, 0.18, 0.38),
        (1.18, 0.1, 0.42),
        (1.94, -0.2, 0.34),
        (2.78, 0.2, 0.42),
        (3.82, -0.12, 0.48),
        (5.02, 0.0, 0.55),
    ]:
        add_stereo(left, right, t, clap(amp), pan=pan)

    # Shamisen/koto-like pluck figure.
    notes = [
        (0.20, 293.66, -0.45, 0.24),
        (0.52, 349.23, 0.38, 0.2),
        (0.84, 440.00, -0.3, 0.22),
        (1.12, 523.25, 0.32, 0.18),
        (1.52, 440.00, -0.36, 0.2),
        (1.84, 392.00, 0.26, 0.18),
        (2.26, 329.63, -0.42, 0.22),
        (2.58, 493.88, 0.38, 0.18),
        (3.08, 587.33, -0.28, 0.19),
        (3.54, 440.00, 0.35, 0.18),
        (4.10, 523.25, -0.34, 0.2),
        (4.38, 659.25, 0.38, 0.18),
        (5.34, 293.66, -0.2, 0.26),
    ]
    for t, freq, pan, amp in notes:
        add_stereo(left, right, t, pluck(freq, 1.05, amp), pan=pan)

    # Shakuhachi-ish breathy glides.
    add_stereo(left, right, 0.95, flute_glide(392.0, 523.25, 1.5, 0.2), pan=-0.18)
    add_stereo(left, right, 2.62, flute_glide(329.63, 587.33, 1.65, 0.24), pan=0.2)
    add_stereo(left, right, 4.28, flute_glide(440.0, 659.25, 1.45, 0.22), pan=0.0)

    # Layered theatrical chorus shouts.
    for t, amp in [(0.72, 0.34), (1.38, 0.42), (2.20, 0.48), (3.18, 0.54), (5.18, 0.7)]:
        add_stereo(left, right, t, chorus_ha(0.72, amp), pan=0.0)

    apply_echo(left, right, delay=0.145, gain=0.18)
    apply_echo(left, right, delay=0.315, gain=0.1)
    soft_limit(left)
    soft_limit(right)
    normalize(left, right, peak=0.94)
    write_wav(OUTPUT, left, right)
    print(f"wrote {OUTPUT}")


def add_stereo(left: list[float], right: list[float], start: float, samples: list[float], pan: float) -> None:
    offset = int(start * SAMPLE_RATE)
    left_gain = math.cos((pan + 1.0) * math.pi / 4.0)
    right_gain = math.sin((pan + 1.0) * math.pi / 4.0)
    for index, sample in enumerate(samples):
        pos = offset + index
        if 0 <= pos < len(left):
            left[pos] += sample * left_gain
            right[pos] += sample * right_gain


def taiko(freq: float, duration: float, amp: float) -> list[float]:
    count = int(SAMPLE_RATE * duration)
    out = [0.0] * count
    phase = 0.0
    for i in range(count):
        t = i / SAMPLE_RATE
        pitch = freq * (1.0 + 1.25 * math.exp(-t * 18.0))
        phase += TAU * pitch / SAMPLE_RATE
        body = math.sin(phase) + 0.38 * math.sin(phase * 2.02)
        skin = (random.random() * 2.0 - 1.0) * math.exp(-t * 42.0)
        env = math.exp(-t * 5.6)
        out[i] = math.tanh((body * env + skin * 0.32) * amp * 1.6) * 0.72
    return out


def clap(amp: float) -> list[float]:
    duration = 0.18
    count = int(SAMPLE_RATE * duration)
    out = [0.0] * count
    for i in range(count):
        t = i / SAMPLE_RATE
        burst = sum(
            max(0.0, 1.0 - abs(t - center) / 0.018)
            for center in (0.008, 0.028, 0.052)
        )
        wood = math.sin(TAU * 1550 * t) * math.exp(-t * 30)
        noise = (random.random() * 2.0 - 1.0) * burst * math.exp(-t * 10)
        out[i] = (noise * 0.74 + wood * 0.26) * amp
    return out


def pluck(freq: float, duration: float, amp: float) -> list[float]:
    count = int(SAMPLE_RATE * duration)
    delay = max(2, int(SAMPLE_RATE / freq))
    line = [random.random() * 2.0 - 1.0 for _ in range(delay)]
    out = []
    pick = 0
    for i in range(count):
        current = line[pick]
        nxt = line[(pick + 1) % delay]
        line[pick] = 0.495 * (current + nxt)
        pick = (pick + 1) % delay
        t = i / SAMPLE_RATE
        buzz = math.sin(TAU * freq * 2.01 * t) * math.exp(-t * 12.0) * 0.18
        out.append((current + buzz) * amp * math.exp(-t * 0.8))
    return out


def flute_glide(start_freq: float, end_freq: float, duration: float, amp: float) -> list[float]:
    count = int(SAMPLE_RATE * duration)
    out = [0.0] * count
    phase = 0.0
    for i in range(count):
        x = i / max(1, count - 1)
        t = i / SAMPLE_RATE
        env = min(1.0, x / 0.16) * min(1.0, (1.0 - x) / 0.18)
        freq = start_freq + (end_freq - start_freq) * (0.5 - 0.5 * math.cos(math.pi * x))
        freq += math.sin(TAU * 5.2 * t) * 4.5
        phase += TAU * freq / SAMPLE_RATE
        breath = (random.random() * 2.0 - 1.0) * 0.045
        tone = math.sin(phase) + 0.22 * math.sin(phase * 2.0) + 0.08 * math.sin(phase * 3.01)
        out[i] = (tone * 0.78 + breath) * env * amp
    return out


def chorus_ha(duration: float, amp: float) -> list[float]:
    count = int(SAMPLE_RATE * duration)
    out = [0.0] * count
    bases = [128.0, 151.0, 186.0, 224.0, 256.0]
    detunes = [-0.018, -0.007, 0.004, 0.012, 0.021]
    phases = [random.random() * TAU for _ in bases]
    for i in range(count):
        t = i / SAMPLE_RATE
        x = i / max(1, count - 1)
        env = min(1.0, x / 0.07) * math.exp(-t * 3.7)
        voice = 0.0
        for idx, base in enumerate(bases):
            freq = base * (1.0 + detunes[idx]) + math.sin(TAU * 4.1 * t + idx) * 1.6
            phases[idx] += TAU * freq / SAMPLE_RATE
            p = phases[idx]
            voice += (
                math.sin(p) * 0.56
                + math.sin(p * 2.0) * 0.22
                + math.sin(p * 3.0) * 0.12
                + math.sin(p * 5.0) * 0.05
            )
        noise = (random.random() * 2.0 - 1.0) * math.exp(-t * 18.0) * 0.32
        out[i] = math.tanh((voice / len(bases) + noise) * 2.0) * env * amp
    return out


def apply_echo(left: list[float], right: list[float], delay: float, gain: float) -> None:
    offset = int(delay * SAMPLE_RATE)
    for i in range(offset, len(left)):
        left[i] += left[i - offset] * gain
        right[i] += right[i - offset] * gain


def soft_limit(samples: list[float]) -> None:
    for i, sample in enumerate(samples):
        samples[i] = math.tanh(sample * 1.35) / math.tanh(1.35)


def normalize(left: list[float], right: list[float], peak: float) -> None:
    current = max(max(abs(x) for x in left), max(abs(x) for x in right), 0.001)
    gain = peak / current
    for i in range(len(left)):
        left[i] *= gain
        right[i] *= gain


def write_wav(path: Path, left: list[float], right: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for l_sample, r_sample in zip(left, right):
            frames.extend(struct.pack("<h", int(max(-1.0, min(1.0, l_sample)) * 32767)))
            frames.extend(struct.pack("<h", int(max(-1.0, min(1.0, r_sample)) * 32767)))
        wav.writeframes(frames)


if __name__ == "__main__":
    main()
