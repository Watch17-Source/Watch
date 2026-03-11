"""WATCH Device (ESP32-S3 + MicroPython v1.27.0)

Behavior summary (per your spec):
- Device stays powered and listens to the local WATCH server (Raspberry Pi).
- Guards control per-device trigger/kill times via the web UI.
- At trigger time, device auto-calibrates (RGB LED blinks GREEN every 2s).
- After calibration, device arms and monitors RCWL-0516 for motion/presence.
- Every second: prints "HUMAN DETECTED" or "NO HUMAN" (plus state, if DEBUG).
- When intruder/motion is detected during armed time:
    * Buzzers alarm continuously
    * RGB LED blinks RED every second
    * Device sends JSON alert to server immediately
- When guards click "Okay" in the web UI:
    * Server sends ACK_ALARM command
    * Device stops alarm and pauses for 1 hour
    * After pause, returns to normal armed behavior if still within curfew time window

Notes:
- RCWL-0516 detects motion (Doppler radar), not humans specifically.
- The calibration + filtering aims to MINIMIZE false alarms.

File layout:
- config.py
- net.py
- rcwl_presence.py
- actuators.py
- main.py (this file) -- runs on boot
"""

import time
import uasyncio as asyncio
import ujson

import config
from net import NetManager
from rcwl_presence import RCWLMonitor, PresenceDetector, load_calibration, save_calibration
from actuators import RgbLed, BuzzerPair


CAL_FILE = "rcwl_cal.json"


# ----------------------------
# Simple server clock estimator
# ----------------------------

class ServerClock:
    def __init__(self):
        self._sec_of_day = None
        self._sync_ms = None

    @staticmethod
    def _hhmm_to_sec(hhmm):
        try:
            hh, mm = hhmm.split(":")
            h = int(hh); m = int(mm)
            if h < 0 or h > 23 or m < 0 or m > 59:
                return None
            return h * 3600 + m * 60
        except Exception:
            return None

    @staticmethod
    def _sec_to_hhmm(sec):
        sec = int(sec) % 86400
        h = sec // 3600
        m = (sec % 3600) // 60
        return "%02d:%02d" % (h, m)

    def update_from_server(self, server_hhmm):
        s = self._hhmm_to_sec(server_hhmm)
        if s is None:
            return
        self._sec_of_day = s
        self._sync_ms = time.ticks_ms()

    def now_sec(self):
        if self._sec_of_day is None or self._sync_ms is None:
            return None
        elapsed = time.ticks_diff(time.ticks_ms(), self._sync_ms) // 1000
        return (self._sec_of_day + elapsed) % 86400

    def now_hhmm(self):
        s = self.now_sec()
        if s is None:
            return None
        return self._sec_to_hhmm(s)


def hhmm_to_sec(hhmm):
    try:
        hh, mm = hhmm.split(":")
        return int(hh) * 3600 + int(mm) * 60
    except Exception:
        return None


def within_window(now_sec, trigger_hhmm, kill_hhmm):
    t = hhmm_to_sec(trigger_hhmm)
    k = hhmm_to_sec(kill_hhmm)
    if now_sec is None or t is None or k is None:
        return False
    if t <= k:
        return (now_sec >= t) and (now_sec < k)
    # spans midnight (e.g., 22:00 -> 05:00)
    return (now_sec >= t) or (now_sec < k)


# ----------------------------
# WATCH server client
# ----------------------------

class WatchClient:
    def __init__(self, net: NetManager):
        self.net = net
        self.base = config.SERVER_BASE_URL.rstrip("/")
        self.device_id = config.DEVICE_ID
        self.token = config.DEVICE_TOKEN
        self.headers = {"X-Device-Token": self.token}

    def url(self, path):
        return self.base + path

    def sync(self, state):
        url = self.url("/api/v1/device/%d/sync?state=%s" % (self.device_id, state))
        return self.net.get_json(url, headers=self.headers)

    def heartbeat(self, state):
        url = self.url("/api/v1/device/%d/heartbeat" % self.device_id)
        payload = {"state": state}
        return self.net.post_json(url, payload, headers=self.headers)

    def event(self, event_type, state, details=None, command_id=None):
        url = self.url("/api/v1/device/%d/event" % self.device_id)
        payload = {"type": event_type, "state": state}
        if isinstance(details, dict):
            payload["details"] = details
        if command_id is not None:
            payload["command_id"] = int(command_id)
        return self.net.post_json(url, payload, headers=self.headers)


# ----------------------------
# Device state machine
# ----------------------------

STATE_WAITING = "WAITING"        # disarmed
STATE_CALIBRATING = "CALIBRATING"
STATE_ARMED = "ARMED"
STATE_ALARMING = "ALARMING"
STATE_PAUSED = "PAUSED"


class WatchDevice:
    def __init__(self):
        self.led = RgbLed(
            config.LED_R_PIN, config.LED_G_PIN, config.LED_B_PIN,
            common_anode=config.LED_COMMON_ANODE
        )
        self.buzzers = BuzzerPair(config.BUZZER1_PIN, config.BUZZER2_PIN)

        self.mon = RCWLMonitor(config.RCWL_OUT_PIN, active_level=1, sample_ms=config.SAMPLE_MS, use_pulldown=True)
        self.detector = PresenceDetector(hits_window_s=config.HITS_WINDOW_S, presence_hold_s=config.PRESENCE_HOLD_S)

        self.clock = ServerClock()

        self.net = NetManager(
            config.WIFI_SSID, config.WIFI_PASSWORD,
            use_static_ip=config.USE_STATIC_IP,
            static_cfg=(config.STATIC_IP, config.NETMASK, config.GATEWAY, config.DNS) if config.USE_STATIC_IP else None,
            debug=config.DEBUG
        )
        self.client = WatchClient(self.net)

        # Config from server (defaults until first sync)
        self.enabled = True
        self.trigger_time = "22:00"
        self.kill_time = "05:00"
        self.pause_after_ack_s = config.DEFAULT_PAUSE_AFTER_ACK_S

        # Runtime state
        self.state = STATE_WAITING
        self._boot_ms = time.ticks_ms()

        self._last_sync_ms = time.ticks_add(time.ticks_ms(), -10_000)
        self._last_hb_ms = time.ticks_add(time.ticks_ms(), -10_000)

        self._alarm_reported = False
        self._pending_alarm_send = False

        self._pause_until_ms = None

        # Calibration state
        self._cal_seconds_done = 0
        self._cal_high_ratios = []
        self._cal_rises = []

        # Try to load previous calibration (so a reboot during curfew doesn't require waiting)
        cal = load_calibration(CAL_FILE)
        if cal:
            try:
                self.detector.load(cal)
                if config.DEBUG:
                    print("[CAL] Loaded saved calibration:", cal)
            except Exception as e:
                if config.DEBUG:
                    print("[CAL] Failed to load calibration:", e)

    def uptime_s(self):
        return time.ticks_diff(time.ticks_ms(), self._boot_ms) // 1000

    def set_led_waiting(self):
        # Off (power saving)
        self.led.off()

    def set_led_calibrating(self, tick_s):
        # Blink GREEN every 2 seconds
        on = (tick_s % 2 == 0)
        self.led.set(r=False, g=on, b=False)

    def set_led_armed(self):
        # Optional: dim indicator. We'll do OFF by default.
        self.led.off()

    def set_led_alarm(self, tick_s):
        # Blink RED every second
        on = (tick_s % 2 == 0)
        self.led.set(r=on, g=False, b=False)

    def set_led_paused(self, tick_s):
        # Blink BLUE every 5 seconds (quick "paused" hint)
        on = (tick_s % 5 == 0)
        self.led.set(r=False, g=False, b=on)

    def buzz_on(self):
        self.buzzers.on()

    def buzz_off(self):
        self.buzzers.off()

    def start_calibration(self):
        self.state = STATE_CALIBRATING
        self._cal_seconds_done = 0
        self._cal_high_ratios = []
        self._cal_rises = []
        self._alarm_reported = False
        self._pending_alarm_send = False
        self.buzz_off()

        if config.DEBUG:
            print("[STATE] -> CALIBRATING (%ds)" % config.CALIBRATION_S)

    def finish_calibration(self):
        self.detector.compute_thresholds(self._cal_high_ratios, self._cal_rises)
        save_calibration(CAL_FILE, self.detector.export())
        self.state = STATE_ARMED
        if config.DEBUG:
            print("[CAL] Done. th_high_ratio=%.3f th_hits=%d" % (self.detector.th_high_ratio, self.detector.th_hits_in_window))
            print("[STATE] -> ARMED")

    def start_alarm(self):
        self.state = STATE_ALARMING
        self.buzz_on()
        self._pending_alarm_send = True
        self._alarm_reported = False
        if config.DEBUG:
            print("[STATE] -> ALARMING")

    def stop_alarm_and_pause(self, pause_for_s):
        self.buzz_off()
        self.state = STATE_PAUSED
        self._pause_until_ms = time.ticks_add(time.ticks_ms(), int(pause_for_s) * 1000)
        self._alarm_reported = False
        self._pending_alarm_send = False
        if config.DEBUG:
            print("[STATE] -> PAUSED (%ds)" % int(pause_for_s))

    def pause_expired(self):
        if self._pause_until_ms is None:
            return True
        return time.ticks_diff(time.ticks_ms(), self._pause_until_ms) >= 0

    def disarm(self):
        if self.state != STATE_WAITING:
            if config.DEBUG:
                print("[STATE] -> WAITING (disarmed)")
        self.state = STATE_WAITING
        self.led.off()
        self.buzz_off()
        self._pause_until_ms = None
        self._alarm_reported = False
        self._pending_alarm_send = False

    def apply_server_config(self, cfg):
        if not isinstance(cfg, dict):
            return
        self.enabled = bool(cfg.get("enabled", True))
        self.trigger_time = str(cfg.get("trigger_time", self.trigger_time))
        self.kill_time = str(cfg.get("kill_time", self.kill_time))
        try:
            self.pause_after_ack_s = int(cfg.get("pause_after_ack_s", self.pause_after_ack_s))
        except Exception:
            pass

    def handle_commands(self, commands):
        if not isinstance(commands, list):
            return

        for c in commands:
            try:
                cmd_id = int(c.get("id", 0))
                cmd = str(c.get("cmd", "")).upper()
                payload = c.get("payload") if isinstance(c.get("payload"), dict) else {}
            except Exception:
                continue

            if config.DEBUG:
                print("[CMD] got", cmd, "id", cmd_id, "payload", payload)

            if cmd == "ACK_ALARM":
                pause_for = int(payload.get("pause_for_s", self.pause_after_ack_s))
                # Stop alarm even if already stopped
                self.stop_alarm_and_pause(pause_for)
                # Confirm receipt to server
                self.client.event("ACK_RECEIVED", self.state)
                # Clear command on server
                self.client.event("COMMAND_CLEARED", self.state, command_id=cmd_id)

            # Future extensibility (not required, but safe)
            elif cmd == "ARM_NOW":
                # Force calibration then arm
                self.start_calibration()
                self.client.event("COMMAND_CLEARED", self.state, command_id=cmd_id)

            elif cmd == "DISARM_NOW":
                self.disarm()
                self.client.event("COMMAND_CLEARED", self.state, command_id=cmd_id)

            elif cmd == "RECALIBRATE":
                self.start_calibration()
                self.client.event("COMMAND_CLEARED", self.state, command_id=cmd_id)

            else:
                # Unknown command: clear it so it doesn't loop forever
                self.client.event("COMMAND_CLEARED", self.state, command_id=cmd_id)

    async def sampler_task(self):
        while True:
            self.mon.sample_once()
            await asyncio.sleep_ms(config.SAMPLE_MS)

    async def network_task(self):
        # Initial Wi-Fi connect
        self.net.connect()

        while True:
            # Choose sync speed based on state
            interval = config.ALARM_SYNC_INTERVAL_S if self.state == STATE_ALARMING else config.SYNC_INTERVAL_S

            # Sync when due
            if time.ticks_diff(time.ticks_ms(), self._last_sync_ms) >= interval * 1000:
                self._last_sync_ms = time.ticks_ms()

                if self.net.ensure():
                    ok, data = self.client.sync(self.state)
                    if ok and data and data.get("ok"):
                        # Update server clock
                        self.clock.update_from_server(data.get("server_hhmm", ""))
                        # Apply config
                        self.apply_server_config(data.get("config", {}))
                        # Handle commands
                        self.handle_commands(data.get("commands", []))

            # Heartbeat when due
            if time.ticks_diff(time.ticks_ms(), self._last_hb_ms) >= config.HEARTBEAT_INTERVAL_S * 1000:
                self._last_hb_ms = time.ticks_ms()
                if self.net.ensure():
                    self.client.heartbeat(self.state)

            # Send pending alarm event (retry until success)
            if self._pending_alarm_send and (not self._alarm_reported):
                if self.net.ensure():
                    ok, data = self.client.event("ALARM_START", self.state, details={"room": config.ROOM_NAME})
                    if ok and data and data.get("ok"):
                        self._alarm_reported = True
                        if config.DEBUG:
                            print("[NET] Alarm reported to server:", data)

            await asyncio.sleep(0.2)

    async def control_task(self):
        # Warm-up ignore time
        if config.DEBUG:
            print("[BOOT] Warming up for", config.WARMUP_S, "seconds...")
        for i in range(config.WARMUP_S):
            self.set_led_waiting()
            await asyncio.sleep(1)
        if config.DEBUG:
            print("[BOOT] Warm-up done.")

        # Main 1-second loop
        tick = 0
        while True:
            tick += 1

            # Get time-of-day from server clock if available
            now_sec = self.clock.now_sec()
            now_hhmm = self.clock.now_hhmm() or "--:--"

            # Determine desired arming state
            should_arm = self.enabled and within_window(now_sec, self.trigger_time, self.kill_time)

            # Handle pause expiration
            if self.state == STATE_PAUSED:
                self.set_led_paused(tick)
                if self.pause_expired():
                    # After pause, if still within window, recalibrate quickly (better stability)
                    if should_arm:
                        self.start_calibration()
                    else:
                        self.disarm()

            # If outside curfew window, disarm regardless
            if not should_arm and self.state not in (STATE_WAITING,):
                # If we were alarming, end case
                if self.state == STATE_ALARMING:
                    self.client.event("ALARM_END", self.state)
                self.disarm()

            # If we should arm and we're waiting -> start calibration
            if should_arm and self.state == STATE_WAITING:
                self.start_calibration()

            # Calibration process: collect per-second stats
            if self.state == STATE_CALIBRATING:
                self.set_led_calibrating(tick)
                sec = self.mon.pop_second_stats()
                self._cal_high_ratios.append(float(sec["high_ratio"]))
                self._cal_rises.append(float(sec["rises"]))
                self._cal_seconds_done += 1

                if config.DEBUG:
                    print("[CAL] %02d/%02d hr=%.3f rises=%d (server %s)" %
                          (self._cal_seconds_done, config.CALIBRATION_S, sec["high_ratio"], sec["rises"], now_hhmm))

                if self._cal_seconds_done >= config.CALIBRATION_S:
                    self.finish_calibration()

                # During calibration, we still print required signal line:
                print("[%5ds %s] NO HUMAN" % (self.uptime_s(), now_hhmm))
                await asyncio.sleep(1)
                continue

            # Armed: evaluate presence
            if self.state == STATE_ARMED:
                self.set_led_armed()
                sec = self.mon.pop_second_stats()
                hits = self.mon.hits_in_window(config.HITS_WINDOW_S)
                present, motion = self.detector.update(sec, hits, active_level=1)

                # Print signal every second (required)
                if present:
                    print("[%5ds %s] HUMAN DETECTED" % (self.uptime_s(), now_hhmm))
                else:
                    print("[%5ds %s] NO HUMAN" % (self.uptime_s(), now_hhmm))

                # Trigger alarm on presence
                if present:
                    self.start_alarm()

                await asyncio.sleep(1)
                continue

            # Alarming: keep alarm until ACK received
            if self.state == STATE_ALARMING:
                self.set_led_alarm(tick)
                # keep buzzers on
                self.buzz_on()

                # Still print required signal
                # (We show HUMAN DETECTED because alarm state is triggered by presence)
                print("[%5ds %s] HUMAN DETECTED" % (self.uptime_s(), now_hhmm))

                await asyncio.sleep(1)
                continue

            # Waiting / default
            if self.state == STATE_WAITING:
                self.set_led_waiting()
                self.buzz_off()
                print("[%5ds %s] NO HUMAN" % (self.uptime_s(), now_hhmm))
                await asyncio.sleep(1)
                continue

            # Fallback
            await asyncio.sleep(1)

    async def run(self):
        # Validate token
        if config.DEVICE_TOKEN == "PASTE_TOKEN_HERE" or not config.DEVICE_TOKEN:
            print("ERROR: Set DEVICE_TOKEN in config.py (copy it from the WATCH server Add Device page).")
            while True:
                self.led.set(r=True, g=False, b=False)  # solid red to signal misconfig
                await asyncio.sleep(1)

        asyncio.create_task(self.sampler_task())
        asyncio.create_task(self.network_task())
        await self.control_task()


async def main():
    d = WatchDevice()
    await d.run()


try:
    asyncio.run(main())
finally:
    try:
        asyncio.new_event_loop()
    except Exception:
        pass
