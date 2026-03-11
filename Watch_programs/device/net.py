"""Network helpers for WATCH device (MicroPython)."""

import time
import socket
import network
import ujson

try:
    import urequests as requests
except ImportError:
    import requests  # type: ignore


class NetManager:
    def __init__(self, ssid, password, *, use_static_ip=False, static_cfg=None, debug=False):
        self.ssid = ssid
        self.password = password
        self.use_static_ip = use_static_ip
        self.static_cfg = static_cfg or None
        self.debug = debug

        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)

        # Keep HTTP from hanging forever on a bad LAN link
        try:
            socket.setdefaulttimeout(2)
        except Exception:
            pass

    def connect(self, timeout_s=20):
        if self.wlan.isconnected():
            return True

        if self.debug:
            print("[NET] Connecting to Wi-Fi...")

        if self.use_static_ip and self.static_cfg:
            try:
                self.wlan.ifconfig(self.static_cfg)
            except Exception as e:
                if self.debug:
                    print("[NET] Static IP ifconfig failed:", e)

        try:
            self.wlan.connect(self.ssid, self.password)
        except Exception as e:
            if self.debug:
                print("[NET] wlan.connect error:", e)
            return False

        t0 = time.ticks_ms()
        while not self.wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_s * 1000:
                if self.debug:
                    print("[NET] Wi-Fi connect timeout")
                return False
            time.sleep_ms(200)

        if self.debug:
            print("[NET] Connected:", self.wlan.ifconfig())
        return True

    def ensure(self):
        if self.wlan.isconnected():
            return True
        return self.connect()

    def get_json(self, url, headers=None):
        headers = headers or {}
        try:
            r = requests.get(url, headers=headers)
            try:
                data = r.json()
            except Exception:
                data = ujson.loads(r.text)
            finally:
                r.close()
            return True, data
        except Exception as e:
            if self.debug:
                print("[NET] GET failed:", url, e)
            return False, None

    def post_json(self, url, payload, headers=None):
        headers = headers or {}
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        body = ujson.dumps(payload)
        try:
            r = requests.post(url, data=body, headers=headers)
            try:
                data = r.json()
            except Exception:
                data = ujson.loads(r.text)
            finally:
                r.close()
            return True, data
        except Exception as e:
            if self.debug:
                print("[NET] POST failed:", url, e)
            return False, None
