from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "web" / "assets" / "kabuki-launch-theme.wav"
SAMPLE_RATE = 44_100
BPM = 150
BEAT = 60 / BPM
DURATION = 7.2
TAU = math.tau


def main() -> None:
    random.seed(43019)
    length = int(SAMPLE_RATE * DURATION)
    left = [0.0] * length
    right = [0.0] * length

    # A measured action-anime style entrance: steady low drum, readable string
    # hook, restrained taiko accents, and one theatrical final shout.
    motif = [
        (0.00, 293.66),
        (0.50, 349.23),
        (1.00, 392.00),
        (1.50, 440.00),
        (2.00, 392.00),
        (2.50, 349.23),
        (3.00, 293.66),
        (3.50, 261.63),
    ]
    for bar in range(3):
        start = 0.28 + bar * 8 * BEAT
        for step, freq in motif:
            t = start + step * BEAT
            pan = -0.28 if int(step * 2) % 2 == 0 else 0.26
            add_stereo(left, right, t, plucked_string(freq, 0.62, 0.23 + bar * 0.025), pan=pan)
            if bar >= 1 and step in (1.0, 2.0, 3.0):
                add_stereo(left, right, t + 0.02, bowed_string(freq * 2.0, 0.46, 0.06), pan=-pan)

    # Pulse stays locked to the grid; no frantic fills.
    for beat in range(17):
        t = 0.08 + beat * BEAT
        if beat % 4 == 0:
            add_stereo(left, right, t, taiko(58, 0.42, 0.92), pan=0.0)
        elif beat % 4 == 2:
            add_stereo(left, right, t, taiko(74, 0.34, 0.54), pan=0.0)
        else:
            add_stereo(left, right, t, rim_click(0.15), pan=-0.1 if beat % 2 else 0.1)

    # A simple low string bed gives shape without noise.
    for t, freq in [(0.0, 146.83), (1.6, 174.61), (3.2, 196.00), (4.8, 174.61)]:
        add_stereo(left, right, t, low_string(freq, 1.8, 0.12), pan=0.0)

    # Short breathy flute answers, kept behind the hook.
    add_stereo(left, right, 1.62, flute_line(440.0, 523.25, 0.92, 0.11), pan=0.18)
    add_stereo(left, right, 3.22, flute_line(392.0, 587.33, 0.98, 0.12), pan=-0.18)
    add_stereo(left, right, 5.22, flute_line(349.23, 659.25, 0.78, 0.13), pan=0.0)

    # Final theatrical entrance hit.
    add_stereo(left, right, 5.72, taiko(48, 0.76, 1.05), pan=0.0)
    add_stereo(left, right, 5.78, chorus_ha(0.84, 0.34), pan=0.0)
    add_stereo(left, right, 5.94, cymbal_swell(0.62, 0.12), pan=0.0)
    add_stereo(left, right, 6.16, plucked_string(293.66, 0.82, 0.22), pan=-0.18)
    add_stereo(left, right, 6.28, bowed_string(587.33, 0.72, 0.08), pan=0.2)

    apply_room(left, right, delay=0.19, gain=0.12)
    apply_room(left, right, delay=0.37, gain=0.06)
    fade(left, fade_in=0.03, fade_out=0.55)
    fade(right, fade_in=0.03, fade_out=0.55)
    soft_limit(left)
    soft_limit(right)
    normalize(left, right, peak=0.9)
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
    out: list[float] = []
    phase = 0.0
    for i in range(count):
        t = i / SAMPLE_RATE
        pitch = freq * (1.0 + 0.42 * math.exp(-t * 15.0))
        phase += TAU * pitch / SAMPLE_RATE
        env = math.exp(-t * 7.2)
        body = math.sin(phase) + 0.24 * math.sin(phase * 2.01)
        tap = math.sin(TAU * 610 * t) * math.exp(-t * 42.0) * 0.12
        out.append(math.tanh((body * env + tap) * amp * 1.25) * 0.72)
    return out


def rim_click(amp: float) -> list[float]:
    duration = 0.09
    count = int(SAMPLE_RATE * duration)
    out: list[float] = []
    for i in range(count):
        t = i / SAMPLE_RATE
        env = math.exp(-t * 38.0)
        tone = math.sin(TAU * 980 * t) + 0.35 * math.sin(TAU * 1460 * t)
        out.append(tone * env * amp)
    return out


def plucked_string(freq: float, duration: float, amp: float) -> list[float]:
    count = int(SAMPLE_RATE * duration)
    delay = max(2, int(SAMPLE_RATE / freq))
    line = [random.uniform(-1.0, 1.0) for _ in range(delay)]
    out: list[float] = []
    index = 0
    for i in range(count):
        t = i / SAMPLE_RATE
        current = line[index]
        line[index] = 0.496 * (line[index] + line[(index + 1) % delay])
        index = (index + 1) % delay
        pick = math.sin(TAU * freq * 2.0 * t) * math.exp(-t * 18.0) * 0.08
        out.append((current * 0.9 + pick) * math.exp(-t * 1.55) * amp)
    return out


def bowed_string(freq: float, duration: float, amp: float) -> list[float]:
    count = int(SAMPLE_RATE * duration)
    out: list[float] = []
    phase = 0.0
    for i in range(count):
        x = i / max(1, count - 1)
        t = i / SAMPLE_RATE
        env = min(1.0, x / 0.16) * min(1.0, (1.0 - x) / 0.2)
        vibrato = math.sin(TAU * 5.8 * t) * 2.3
        phase += TAU * (freq + vibrato) / SAMPLE_RATE
        sawish = math.sin(phase) + 0.32 * math.sin(2 * phase) + 0.16 * math.sin(3 * phase)
        out.append(sawish * env * amp)
    return out


def low_string(freq: float, duration: float, amp: float) -> list[float]:
    count = int(SAMPLE_RATE * duration)
    out: list[float] = []
    phase = 0.0
    for i in range(count):
        x = i / max(1, count - 1)
        env = min(1.0, x / 0.3) * min(1.0, (1.0 - x) / 0.36)
        phase += TAU * freq / SAMPLE_RATE
        out.append((math.sin(phase) + 0.22 * math.sin(2 * phase)) * env * amp)
    return out


def flute_line(start_freq: float, end_freq: float, duration: float, amp: float) -> list[float]:
    count = int(SAMPLE_RATE * duration)
    out: list[float] = []
    phase = 0.0
    for i in range(count):
        x = i / max(1, count - 1)
        env = min(1.0, x / 0.18) * min(1.0, (1.0 - x) / 0.2)
        freq = start_freq + (end_freq - start_freq) * (0.5 - 0.5 * math.cos(math.pi * x))
        phase += TAU * freq / SAMPLE_RATE
        breath = random.uniform(-1.0, 1.0) * 0.012
        out.append((math.sin(phase) + 0.15 * math.sin(2 * phase) + breath) * env * amp)
    return out


def chorus_ha(duration: float, amp: float) -> list[float]:
    count = int(SAMPLE_RATE * duration)
    out: list[float] = []
    phases = [0.0, 0.8, 1.7]
    freqs = [138.0, 174.0, 220.0]
    for i in range(count):
        t = i / SAMPLE_RATE
        x = i / max(1, count - 1)
        env = min(1.0, x / 0.06) * math.exp(-t * 3.2)
        voice = 0.0
        for idx, freq in enumerate(freqs):
            phases[idx] += TAU * (freq + math.sin(TAU * 4.0 * t + idx) * 1.2) / SAMPLE_RATE
            voice += math.sin(phases[idx]) + 0.22 * math.sin(2 * phases[idx])
        out.append(math.tanh(voice / len(freqs) * 1.3) * env * amp)
    return out


def cymbal_swell(duration: float, amp: float) -> list[float]:
    count = int(SAMPLE_RATE * duration)
    out: list[float] = []
    last = 0.0
    for i in range(count):
        x = i / max(1, count - 1)
        noise = random.uniform(-1.0, 1.0)
        high = noise - last * 0.55
        last = noise
        env = min(1.0, x / 0.24) * min(1.0, (1.0 - x) / 0.18)
        out.append(high * env * amp)
    return out


def apply_room(left: list[float], right: list[float], delay: float, gain: float) -> None:
    offset = int(delay * SAMPLE_RATE)
    for i in range(offset, len(left)):
        left[i] += left[i - offset] * gain
        right[i] += right[i - offset] * gain


def fade(samples: list[float], *, fade_in: float, fade_out: float) -> None:
    fade_in_count = int(fade_in * SAMPLE_RATE)
    fade_out_count = int(fade_out * SAMPLE_RATE)
    for i in range(min(fade_in_count, len(samples))):
        samples[i] *= i / max(1, fade_in_count)
    for i in range(min(fade_out_count, len(samples))):
        pos = len(samples) - 1 - i
        samples[pos] *= i / max(1, fade_out_count)


def soft_limit(samples: list[float]) -> None:
    for i, sample in enumerate(samples):
        samples[i] = math.tanh(sample * 1.18) / math.tanh(1.18)


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
