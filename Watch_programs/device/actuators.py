"""LED + buzzer control for WATCH device (MicroPython)."""

from machine import Pin


class RgbLed:
    def __init__(self, r_pin=None, g_pin=None, b_pin=None, *, common_anode=False):
        self.common_anode = bool(common_anode)
        self.r = Pin(r_pin, Pin.OUT) if r_pin is not None else None
        self.g = Pin(g_pin, Pin.OUT) if g_pin is not None else None
        self.b = Pin(b_pin, Pin.OUT) if b_pin is not None else None
        self.off()

    def _write(self, pin, on):
        if pin is None:
            return
        # common anode: ON = 0, OFF = 1
        if self.common_anode:
            pin.value(0 if on else 1)
        else:
            pin.value(1 if on else 0)

    def set(self, r=False, g=False, b=False):
        self._write(self.r, r)
        self._write(self.g, g)
        self._write(self.b, b)

    def off(self):
        self.set(False, False, False)


class BuzzerPair:
    def __init__(self, pin1=None, pin2=None, *, active_high=True):
        self.active_high = bool(active_high)
        self.p1 = Pin(pin1, Pin.OUT) if pin1 is not None else None
        self.p2 = Pin(pin2, Pin.OUT) if pin2 is not None else None
        self.off()

    def _write(self, pin, on):
        if pin is None:
            return
        if self.active_high:
            pin.value(1 if on else 0)
        else:
            pin.value(0 if on else 1)

    def on(self):
        self._write(self.p1, True)
        self._write(self.p2, True)

    def off(self):
        self._write(self.p1, False)
        self._write(self.p2, False)
