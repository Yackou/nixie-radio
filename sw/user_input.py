import sys
import RPIO
import MPR121


class UI(object):
	WHEEL_SW = 22
	WHEEL_TB = 17
	WHEEL_TA = 27
	CAPA_IRQ = 4
	CAPA_TOP = 6
	CAPA_MID = 0
	CAPA_BOT = 11

	def __init__(self):
		RPIO.setmode(RPIO.BCM)
		RPIO.setup(UI.WHEEL_SW, RPIO.IN, pull_up_down=RPIO.PUD_UP)
		RPIO.setup(UI.CAPA_IRQ, RPIO.IN, pull_up_down=RPIO.PUD_UP)

		RPIO.add_interrupt_callback(UI.WHEEL_SW, self.wheel_pressed, threaded_callback=False, debounce_timeout_ms=40)
		self.wheel = Wheel(UI.WHEEL_TA, UI.WHEEL_TB)

		RPIO.wait_for_interrupts(threaded=True, epoll_timeout=10)
		# Bug in RPIO? seems the pull UP has to be done twice...
		RPIO.setup(UI.WHEEL_SW, RPIO.IN, pull_up_down=RPIO.PUD_UP)

		self.cap = MPR121.MPR121()
		if not self.cap.begin():
			print('Error initializing MPR121.  Check your wiring!')
			sys.exit(1)
		RPIO.add_interrupt_callback(UI.CAPA_IRQ, self.touch_pressed, threaded_callback=False)

	def set_wheel_pressed_callback(self, callback=None):
		self.sw_cb = callback

	def set_top_pressed_callback(self, callback=None):
		self.top_cb = callback

	def set_middle_pressed_callback(self, callback=None):
		self.middle_cb = callback

	def set_bottom_pressed_callback(self, callback=None):
		self.bottom_cb = callback

	def wheel_pressed(self, gpio_id, val):
		print("Wheel: %s" % val)
		if val == 0:
			self.sw_cb()

	def touch_pressed(self, gpio_id, val):
		#print("Touch: %s" % val)
		RPIO.set_pullupdn(UI.CAPA_IRQ, RPIO.PUD_UP)
		if val == 0:
			current_touched = self.cap.touched()
			# Check each pin's last and current state to see if it was pressed or released.
			pin_bit = 1 << UI.CAPA_TOP
			if current_touched & pin_bit:
					self.top_cb()
					print "T",
			else:
					print "-",
			print "  ",
			pin_bit = 1 << UI.CAPA_MID
			if current_touched & pin_bit:
					self.middle_cb()
					print "M",
			else:
					print "-",
			print "  ",
			pin_bit = 1 << UI.CAPA_BOT
			if current_touched & pin_bit:
					self.bottom_cb()
					print "B",
			else:
					print "-",
			print ""


class Wheel(object):
	CW = 0
	CCW = 1

	def __init__(self, pin_a, pin_b, steps_per_turn = 96):
		self.pin_a = pin_a
		self.pin_b = pin_b
		self.steps_per_turn = steps_per_turn
		RPIO.setup(pin_a, RPIO.IN, pull_up_down=RPIO.PUD_UP)
		RPIO.setup(pin_b, RPIO.IN, pull_up_down=RPIO.PUD_UP)

		RPIO.add_interrupt_callback(pin_a, self.pin_a_changed, threaded_callback=False, debounce_timeout_ms=5)
		RPIO.add_interrupt_callback(pin_b, self.pin_b_changed, threaded_callback=False, debounce_timeout_ms=5)

		self.state_a = RPIO.input(pin_a)
		self.state_b = RPIO.input(pin_b)
		self.setup(0, 50, 100, 1, self.default_cb)

	def default_cb(self, val):
		print("val %s" % val)

	def setup(self, minimum, initial, maximum, turns, callback):
		print("Setting up wheel encoder: minimum %s initial %s maximum %s turns %s" % ( minimum, initial, maximum, turns))
		# raw_max - raw_min = turns * steps_per_turn
		# ? = 1
		self.raw_min = minimum * (turns * self.steps_per_turn) / (maximum - minimum)
		self.raw = initial * (turns * self.steps_per_turn) / (maximum - minimum)
		self.raw_max = maximum * (turns * self.steps_per_turn) / (maximum - minimum)
		self.max = maximum
		self.min = minimum
		self.turns = turns
		self.cb = callback

	def pin_a_changed(self, gpio_id, val):
		if self.state_b != RPIO.input(self.pin_b):
			return

		if self.state_a == val:
			return
		self.state_a = val

		if self.state_b == 1:
			if val == 0:
				direction = Wheel.CW
			else:
				direction = Wheel.CCW
		else:
			if val == 0:
				direction = Wheel.CCW
			else:
				direction = Wheel.CW

		if direction == Wheel.CW:
			self.raw = self.raw + 1
			if self.raw > self.raw_max:
				self.raw = self.raw_max
		else:
			self.raw = self.raw - 1
			if self.raw < self.raw_min:
				self.raw = self.raw_min

		self.cb(int(self.raw * (self.max - self.min) / (self.turns * self.steps_per_turn)))


	def pin_b_changed(self, gpio_id, val):
		if self.state_a != RPIO.input(self.pin_a):
			return

		if self.state_b == val:
			return
		self.state_b = val

		if self.state_a == 1:
			if val == 0:
				direction = Wheel.CCW
			else:
				direction = Wheel.CW
		else:
			if val == 0:
				direction = Wheel.CW
			else:
				direction = Wheel.CCW

		if direction == Wheel.CW:
			self.raw = self.raw + 1
			if self.raw > self.raw_max:
				self.raw = self.raw_max
		else:
			self.raw = self.raw - 1
			if self.raw < self.raw_min:
				self.raw = self.raw_min

		self.cb(int(self.raw * (self.max - self.min) / (self.turns * self.steps_per_turn)))


if __name__ == "__main__":
	from time import sleep

	ui = UI()

	try:
		while True:
			sleep(20)
	except (KeyboardInterrupt, SystemExit):
		sleep(1)
