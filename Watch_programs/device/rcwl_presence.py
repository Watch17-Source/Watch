"""RCWL-0516 presence detection (MicroPython).

This is NOT true human identification. RCWL is a Doppler motion sensor.

This module:
- samples RCWL OUT frequently (default 50ms)
- aggregates per-second stats
- supports calibration in an empty room to set thresholds
- outputs a stable 'presence' boolean using hold time and rolling-window hits
"""

import time
import ujson
from machine import Pin


def now_ms():
    return time.ticks_ms()


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def stddev(xs, m=None):
    if not xs:
        return 0.0
    if m is None:
        m = mean(xs)
    var = 0.0
    for v in xs:
        d = v - m
        var += d * d
    var /= len(xs)
    return var ** 0.5


def clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


class RCWLMonitor:
    def __init__(self, out_pin, *, active_level=1, sample_ms=50, use_pulldown=True):
        self.active_level = 1 if active_level else 0
        self.sample_ms = int(sample_ms)

        pull = None
        if use_pulldown:
            try:
                pull = Pin.PULL_DOWN
            except Exception:
                pull = None

        try:
            self.pin = Pin(out_pin, Pin.IN, pull)
        except TypeError:
            self.pin = Pin(out_pin, Pin.IN)

        self._last_raw = 1 if self.pin.value() else 0
        self.last_raw = self._last_raw

        self._hits_ms = []
        self._sec_total = 0
        self._sec_high = 0
        self._sec_rises = 0

    def _is_active(self, raw):
        return 1 if raw == self.active_level else 0

    def sample_once(self):
        raw = 1 if self.pin.value() else 0
        self.last_raw = raw
        active = self._is_active(raw)
        last_active = self._is_active(self._last_raw)

        self._sec_total += 1
        if active:
            self._sec_high += 1

        if (not last_active) and active:
            t = now_ms()
            self._hits_ms.append(t)
            self._sec_rises += 1

        self._last_raw = raw

    def pop_second_stats(self):
        total = self._sec_total if self._sec_total else 1
        high_ratio = self._sec_high / total
        rises = self._sec_rises

        self._sec_total = 0
        self._sec_high = 0
        self._sec_rises = 0

        return {
            "t_ms": now_ms(),
            "raw": self.last_raw,
            "high_ratio": high_ratio,
            "rises": rises,
        }

    def hits_in_window(self, window_s):
        window_ms = int(window_s * 1000)
        t = now_ms()
        cutoff = time.ticks_add(t, -window_ms)
        new_hits = []
        for h in self._hits_ms:
            if time.ticks_diff(h, cutoff) >= 0:
                new_hits.append(h)
        self._hits_ms = new_hits
        return len(self._hits_ms)


class PresenceDetector:
    def __init__(self, *, hits_window_s=5, presence_hold_s=6):
        self.hits_window_s = int(hits_window_s)
        self.presence_hold_s = int(presence_hold_s)

        self.base_high_ratio = 0.0
        self.base_rises_per_sec = 0.0
        self.th_high_ratio = 0.20
        self.th_hits_in_window = 1

        self.last_motion_ms = time.ticks_add(now_ms(), -10_000_000)

    def export(self):
        return {
            "base_high_ratio": self.base_high_ratio,
            "base_rises_per_sec": self.base_rises_per_sec,
            "th_high_ratio": self.th_high_ratio,
            "th_hits_in_window": self.th_hits_in_window,
            "saved_at_ms": now_ms(),
        }

    def load(self, d):
        self.base_high_ratio = float(d.get("base_high_ratio", 0.0))
        self.base_rises_per_sec = float(d.get("base_rises_per_sec", 0.0))
        self.th_high_ratio = float(d.get("th_high_ratio", 0.20))
        self.th_hits_in_window = int(d.get("th_hits_in_window", 1))

    def compute_thresholds(self, high_ratios, rises_per_sec):
        m_hr = mean(high_ratios)
        s_hr = stddev(high_ratios, m_hr)

        m_rp = mean(rises_per_sec)
        s_rp = stddev(rises_per_sec, m_rp)

        self.base_high_ratio = m_hr
        self.base_rises_per_sec = m_rp

        hr_margin = max(3.0 * s_hr, 0.10)
        self.th_high_ratio = max(0.20, m_hr + hr_margin)
        self.th_high_ratio = clamp(self.th_high_ratio, 0.05, 0.95)

        baseline_hits = m_rp * self.hits_window_s
        window_std_est = s_rp * self.hits_window_s
        hits_margin = max(int(round(3.0 * window_std_est)), 1)
        self.th_hits_in_window = max(1, int(round(baseline_hits)) + hits_margin)
        self.th_hits_in_window = clamp(self.th_hits_in_window, 1, 50)

    def update(self, sec_stats, hits_in_window, *, active_level=1):
        hr = sec_stats["high_ratio"]
        motion = False

        if hr >= self.th_high_ratio:
            motion = True
        if hits_in_window >= self.th_hits_in_window:
            motion = True
        if sec_stats["raw"] == active_level:
            motion = True

        if motion:
            self.last_motion_ms = sec_stats["t_ms"]

        present = (time.ticks_diff(sec_stats["t_ms"], self.last_motion_ms) <= self.presence_hold_s * 1000)
        return present, motion


def save_calibration(path, cal_dict):
    try:
        with open(path, "w") as f:
            f.write(ujson.dumps(cal_dict))
        return True
    except Exception:
        return False


def load_calibration(path):
    try:
        with open(path, "r") as f:
            return ujson.loads(f.read())
    except Exception:
        return None
