import sys
import RPIO
import Adafruit_MPR121.MPR121 as MPR121


class UI(object):
    WHEEL_SW = 22
    WHEEL_TB = 17
    WHEEL_TA = 27
    CAPA_IRQ = 8

    def __init__(self):
        RPIO.setmode(RPIO.BCM)
        RPIO.setup(UI.WHEEL_SW, RPIO.IN, pull_up_down=RPIO.PUD_UP)
        RPIO.setup(UI.CAPA_IRQ, RPIO.IN, pull_up_down=RPIO.PUD_UP)

        RPIO.add_interrupt_callback(UI.WHEEL_SW, self.wheel_pressed, threaded_callback=True, debounce_timeout_ms=10)
        self.wheel = Wheel(UI.WHEEL_TA, UI.WHEEL_TB)

        RPIO.wait_for_interrupts(threaded=True)

        self.cap = MPR121.MPR121()
        if not self.cap.begin():
            print('Error initializing MPR121.  Check your wiring!')
            sys.exit(1)

    def set_wheel_pressed_callback(self, callback=None):
        self.sw_cb = callback

    def wheel_pressed(self, gpio_id, val):
        print("gpio %s: %s" % (gpio_id, val))
        RPIO.set_pullupdn(UI.WHEEL_SW, RPIO.PUD_UP)
        if val == 0:
            self.sw_cb()



class Wheel(object):
    CW = 0
    CCW = 1

    def __init__(self, pin_a, pin_b, steps_per_turn = 96):
        self.pin_a = pin_a
        self.pin_b = pin_b
        self.steps_per_turn = steps_per_turn
        RPIO.setup(pin_a, RPIO.IN, pull_up_down=RPIO.PUD_UP)
        RPIO.setup(pin_b, RPIO.IN, pull_up_down=RPIO.PUD_UP)

        RPIO.add_interrupt_callback(pin_a, self.pin_a_changed, threaded_callback=True, debounce_timeout_ms=5)
        RPIO.add_interrupt_callback(pin_b, self.pin_b_changed, threaded_callback=True, debounce_timeout_ms=5)

        self.state_a = RPIO.input(pin_a)
        self.state_b = RPIO.input(pin_b)
        self.setup(0, 50, 100, 1, self.default_cb)

    def default_cb(self, val):
        print("val %s" % val)

    def setup(self, min, initial, max, turns, callback):
        print("Setting up wheel encoder: min %s initial %s max %s turns %s" % ( min, initial, max, turns))
        # raw_max - raw_min = turns * steps_per_turn
        # ? = 1
        self.raw_min = min * (turns * self.steps_per_turn) / (max - min)
        self.raw = initial * (turns * self.steps_per_turn) / (max - min)
        self.raw_max = max * (turns * self.steps_per_turn) / (max - min)
        self.max = max
        self.min = min
        self.turns = turns
        self.cb = callback

    def pin_a_changed(self, gpio_id, val):
        # RPIO.set_pullupdn(gpio_id, RPIO.PUD_UP)
        if self.state_b != RPIO.input(self.pin_b):
            return

        if self.state_a == val:
            return
        self.state_a = val

        if self.state_b == 1:
            if val == 0:
                dir = Wheel.CW
            else:
                dir = Wheel.CCW
        else:
            if val == 0:
                dir = Wheel.CCW
            else:
                dir = Wheel.CW

        if dir == Wheel.CW:
            self.raw = self.raw + 1
            if self.raw > self.raw_max:
                self.raw = self.raw_max
        else:
            self.raw = self.raw - 1
            if self.raw < self.raw_min:
                self.raw = self.raw_min

        self.cb(int(self.raw * (self.max - self.min) / (self.turns * self.steps_per_turn)))


    def pin_b_changed(self, gpio_id, val):
        # RPIO.set_pullupdn(gpio_id, RPIO.PUD_UP)
        if self.state_a != RPIO.input(self.pin_a):
            return

        if self.state_b == val:
            return
        self.state_b = val

        if self.state_a == 1:
            if val == 0:
                dir = Wheel.CCW
            else:
                dir = Wheel.CW
        else:
            if val == 0:
                dir = Wheel.CW
            else:
                dir = Wheel.CCW

        if dir == Wheel.CW:
            self.raw = self.raw + 1
            if self.raw > self.raw_max:
                self.raw = self.raw_max
        else:
            self.raw = self.raw - 1
            if self.raw < self.raw_min:
                self.raw = self.raw_min

        self.cb(int(self.raw * (self.max - self.min) / (self.turns * self.steps_per_turn)))