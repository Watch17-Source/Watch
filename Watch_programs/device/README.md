# WATCH Device (ESP32‑S3 + RCWL‑0516)

This folder is the **MicroPython** firmware for the classroom device.

- MicroPython target: **v1.27.0**
- Hardware: **ESP32‑S3 + RCWL‑0516 + RGB LED + 2 active buzzers**

---

## 1) Files

- `config.py` — edit Wi‑Fi, server IP, device ID, token, GPIO pins
- `main.py` — runs on boot
- `rcwl_presence.py` — sampling + calibration + filtering
- `net.py` — Wi‑Fi + HTTP
- `actuators.py` — RGB LED + buzzers

The device will also create:
- `rcwl_cal.json` — saved calibration thresholds

---

## 2) Wiring

### RCWL‑0516 (5 pins)

| RCWL‑0516 Pin | Connect to |
|---|---|
| **VIN** | **5V** (ESP32 dev board 5V pin or regulated 5V) |
| **GND** | **GND** |
| **OUT** | ESP32 GPIO input (example: `GPIO4`, matches `RCWL_OUT_PIN`) |
| **3V3** | *Leave unconnected* (this is 3.3V output from module; usually unused) |
| **CDS** | *Leave unconnected* (optional light/disable control) |

> Important: Use a common ground between RCWL and ESP32.

**Stability tip:** Add 0.1µF + 10µF capacitors across VIN–GND near the RCWL module.

---

### RGB LED
- Use one resistor per channel (typical 220Ω–330Ω).
- Set `LED_COMMON_ANODE=True` if your LED is common-anode.

### Buzzers
- If your buzzers are 5V or draw significant current, drive them through a transistor/MOSFET.
- Simplest: NPN (2N2222) + base resistor (1k) per buzzer, buzzer to 5V, transistor to GND.

---

## 3) Install to ESP32 (example with mpremote)

From your PC:

```bash
pip install mpremote
mpremote connect /dev/ttyACM0 fs cp config.py :config.py
mpremote connect /dev/ttyACM0 fs cp net.py :net.py
mpremote connect /dev/ttyACM0 fs cp rcwl_presence.py :rcwl_presence.py
mpremote connect /dev/ttyACM0 fs cp actuators.py :actuators.py
mpremote connect /dev/ttyACM0 fs cp main.py :main.py
mpremote connect /dev/ttyACM0 reset
```

(Adjust port as needed.)

---

## 4) First boot checklist

1) Add device in the WATCH server UI (server/Add Device)
2) Copy the generated token
3) Paste into `DEVICE_TOKEN` in `config.py`
4) Reboot the ESP32

At curfew time, it will calibrate and then arm automatically.
