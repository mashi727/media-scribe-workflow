#!/usr/bin/env python3
"""同期済み出力の残差を冒頭/末尾で実測する（本セッションで繰り返し使った検証スニペット）。

    verify-sync-residual.py VIDEO OUTPUT [START_SS] [END_SS] [WIN]

VIDEO のスクラッチ音声と OUTPUT の音声を、指定2地点で相互相関して残差を出す。
冒頭≈末尾ならドリフトなし。両方 0 近傍なら同期成功。

注意: 片チャンネルだけを取り出して「両TXが混ざった映像スクラッチ」と相関すると、
もう一方がクロストーク的バイアスになり十数msずれて見える。必ずミックス同士で測ること。
"""
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np


def ext(path, ss, dur, rate=8000):
    fd, w = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(ss), "-t", str(dur),
                    "-i", path, "-vn", "-ac", "1", "-ar", str(rate),
                    "-c:a", "pcm_s16le", w], check=True)
    with wave.open(w, "rb") as wf:
        x = np.frombuffer(wf.readframes(wf.getnframes()), dtype="<i2").astype(float)
    os.remove(w)
    x -= x.mean()
    s = x.std()
    return x / s if s > 0 else x


def off(a, b, sr=8000):
    n = a.size + b.size - 1
    nf = 1 << (int(n - 1).bit_length())
    c = np.fft.irfft(np.fft.rfft(a, nf) * np.fft.rfft(b[::-1], nf), nf)[:n]
    i = int(np.argmax(c))
    return (i - (b.size - 1)) / sr, (c[i] - c.mean()) / (c.std() + 1e-12)


def main():
    vid, out = sys.argv[1], sys.argv[2]
    s0 = float(sys.argv[3]) if len(sys.argv) > 3 else 200
    s1 = float(sys.argv[4]) if len(sys.argv) > 4 else None
    win = float(sys.argv[5]) if len(sys.argv) > 5 else 120
    if s1 is None:
        d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                  "format=duration", "-of", "csv=p=0", vid],
                                 capture_output=True, text=True).stdout)
        s1 = d - win - 60
    for label, ss in (("冒頭", s0), ("末尾", s1)):
        v = ext(vid, ss, win)
        o = ext(out, ss, win)
        d, sc = off(o, v)
        print(f"  {label} t={ss:>8.0f}s : offset={d*1000:+7.1f}ms  score={sc:.0f}")


if __name__ == "__main__":
    main()
