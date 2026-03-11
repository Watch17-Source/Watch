"""WATCH Device Configuration (ESP32-S3 + MicroPython v1.27.0)

Edit this file for each classroom device.

Wi‑Fi:
  SSID: routerssid
  PASS: routerwifipassword

Server:
  Raspberry Pi static IP: 192.168.68.58
Device (example reservation):
  192.168.68.51

IMPORTANT:
- After you add the device in the WATCH web UI, you will receive a DEVICE_TOKEN.
  Paste it below.
"""

# --------------------
# Identity / Server
# --------------------
SERVER_BASE_URL = "http://192.168.68.58"   # no https (LAN only)
DEVICE_ID = 1                               # set to the device id shown in the web UI
DEVICE_TOKEN = "PASTE_TOKEN_HERE"          # copy from Add Device result page
ROOM_NAME = "G12 - Manulat"           # optional, for local prints

# --------------------
# Wi‑Fi
# --------------------
WIFI_SSID = "wifissid"
WIFI_PASSWORD = "wifipassword"

# Optional: set a static IP on the ESP32 (usually NOT needed if you use router reservation)
USE_STATIC_IP = False
STATIC_IP = "192.168.1.2"
NETMASK = "255.255.255.0"
GATEWAY = "192.168.1.1"
DNS = "192.168.1.1"

# --------------------
# Hardware Pins
# --------------------
# RCWL-0516 OUT pin -> ESP32 GPIO input
RCWL_OUT_PIN = 8

# RGB LED pins (set any to None if unused)
# NOTE: Most ESP32 boards need a current-limiting resistor per LED channel (e.g., 220Ω–330Ω).
LED_R_PIN = 5
LED_G_PIN = 6
LED_B_PIN = 7

# If your RGB LED is common-anode, set this True (active LOW). If common-cathode, set False (active HIGH).
LED_COMMON_ANODE = False

# Active buzzers (recommended to drive via transistor if using 5V buzzers)
BUZZER1_PIN = 4
BUZZER2_PIN = 9

# --------------------
# Sensor tuning / timings
# --------------------
WARMUP_S = 10
CALIBRATION_S = 30

# Sampling (RCWL output is typically HIGH ~2–3s when triggered)
SAMPLE_MS = 50

# Presence smoothing
HITS_WINDOW_S = 5
PRESENCE_HOLD_S = 6

# Network polling
SYNC_INTERVAL_S = 5           # normal sync (config + commands)
ALARM_SYNC_INTERVAL_S = 1     # faster sync while alarming (to receive ACK quickly)
HEARTBEAT_INTERVAL_S = 15

# After guard acknowledges alarm, pause for inspection time
DEFAULT_PAUSE_AFTER_ACK_S = 3600

# Debug printing
DEBUG = True
