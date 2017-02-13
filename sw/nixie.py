#! /usr/bin/python -u

import threading
import RPIO.PWM as PWM
import RPIO
from time import localtime, sleep, struct_time

# Dots GPIOs
dot_top = 23
dot_bot = 24

anode_a = 8
anode_b = 25
anode_c = 7

cathode_A = 10
cathode_B = 18
cathode_C = 11
cathode_D = 9


tube_gpios = (anode_a, anode_b, anode_c)
digit_gpios = (cathode_A, cathode_B, cathode_C, cathode_D)

tube_1 = (0, 0, 1)
tube_2 = (0, 1, 0)
tube_3 = (1, 0, 1)
tube_0 = (1, 1, 0)
blank_tube = (0, 0, 0)
tubes = [tube_0, tube_1, tube_2, tube_3]

d_0 = (0, 0, 0, 0) # 0
d_6 = (0, 0, 0, 1) # 1
d_7 = (0, 0, 1, 0) # 2
d_1 = (0, 1, 0, 0) # 4
d_5 = (0, 1, 1, 0) # 6
d_9 = (1, 0, 0, 0) # 8
d_2 = (1, 0, 0, 1) # 9
d_8 = (1, 0, 1, 0) # 10
d_3 = (1, 1, 0, 0) # 12
d_4 = (1, 1, 1, 0) # 14

digits = (d_0, d_1, d_2, d_3, d_4, d_5, d_6, d_7, d_8, d_9)

class Sequence:
	def __init__(self, channel = 0, gpios = (), gpio_sets = [()]):
		self.channel = channel
		self.gpios = gpios
		self.gpio_sets = gpio_sets

		print gpio_sets
		for gpio in gpios:
			RPIO.setup(gpio, RPIO.OUT)
			RPIO.output(gpio, False)
			PWM.add_channel_pulse(self.channel, gpio, 0, 1)
		self.reset()

	def set_channel(self, channel = 0):
		self.channel = channel

	def apply(self):
		for (gpio_set, start, width) in self.gpio_sets:
			#print gpio_set
			#print start
			#print width
			for i in range(0, len(self.gpios)):
				#print i
				if gpio_set[i] == 1:
					PWM.add_channel_pulse(self.channel, self.gpios[i], start, width)

	def reset(self):
		for gpio in self.gpios:
			PWM.clear_channel_gpio(self.channel, gpio)

class ClockSequence:
	def __init__(self, period = 10000):
		PWM.setup()
		PWM.init_channel(0, period)
		PWM.print_channel(0)

class StandardDisplay:
	TUBE_LENGTH = 170
	STRIDE = 250
	DIGIT_LENGTH = 240
	def __init__(self):
		self.tube_length = StandardDisplay.TUBE_LENGTH
		self.tube = Sequence(0, tube_gpios, [(tube_0, 1, self.tube_length),
											(tube_1, 1 + StandardDisplay.STRIDE, self.tube_length),
											(tube_2, 1 + 2 * StandardDisplay.STRIDE, self.tube_length),
											(tube_3, 1 + 3 * StandardDisplay.STRIDE, self.tube_length)])
		self.tube.channel = 0
		self.tube.apply()

		self.digit = Sequence(0, digit_gpios, [(digits[0], 0, StandardDisplay.DIGIT_LENGTH),
											(digits[0], StandardDisplay.STRIDE, StandardDisplay.DIGIT_LENGTH),
											(digits[0], 2 * StandardDisplay.STRIDE, StandardDisplay.DIGIT_LENGTH),
											(digits[0], 3 * StandardDisplay.STRIDE, StandardDisplay.DIGIT_LENGTH), ])
		self.digit.channel = 0
		self.digit.apply()

	def reset(self):
		self.tube.reset()
		self.digit.reset()

	def apply(self):
		self.digit.apply()
		self.tube.apply()

	def set_brightness(self, brightness):
		self.tube_length = (brightness * StandardDisplay.TUBE_LENGTH) / 100
		if self.tube_length > StandardDisplay.TUBE_LENGTH:
			self.tube_length = StandardDisplay.TUBE_LENGTH
		if self.tube_length < 0:
			self.tube_length = 0

		self.reset()
		self.apply()


	def set_tube(self, tube = 0, digit = 0):
		self.digit.gpio_sets[tube] = (digits[digit], tube * StandardDisplay.STRIDE, StandardDisplay.DIGIT_LENGTH)

	def blank_tube(self, tube):
		self.tube.gpio_sets[tube] =  (blank_tube, 1 + tube * StandardDisplay.STRIDE, self.tube_length)

	def unblank_tube(self, tube):
		self.tube.gpio_sets[tube] =  (tubes[tube], 1 + tube * StandardDisplay.STRIDE, self.tube_length)


class DisplayThread(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)
		self.daemon = True

		self.cs = ClockSequence()
		self.display = StandardDisplay()
		self.blanked = False
		self.custom = False
		self.custom_tubes = [ 0, 0, 0, 0 ]
		self.custom_event = threading.Event()

	def run(self):
		current_time = localtime()
		previous_time = localtime(0)
		event = False

		while True:
			timeout = None
			if self.custom:
				print("custom")
				timeout = 3
				previous_time = localtime(0)
				self.display.reset()

				if self.custom_tubes[0] == -1:
					self.display.blank_tube(0)
				else:
					self.display.unblank_tube(0)
					self.display.set_tube(0, self.custom_tubes[0])

				if self.custom_tubes[1] == -1:
					self.display.blank_tube(1)
				else:
					self.display.unblank_tube(1)
					self.display.set_tube(1, self.custom_tubes[1])

				if self.custom_tubes[2] == -1:
					self.display.blank_tube(2)
				else:
					self.display.unblank_tube(2)
					self.display.set_tube(2, self.custom_tubes[2])

				if self.custom_tubes[3] == -1:
					self.display.blank_tube(3)
				else:
					self.display.unblank_tube(3)
					self.display.set_tube(3, self.custom_tubes[3])

				self.display.apply()

			elif self.blanked:
				print("blanked")
				previous_time = localtime(0)
				self.display.reset()
				self.display.blank_tube(0)
				self.display.blank_tube(1)
				self.display.blank_tube(2)
				self.display.blank_tube(3)
				self.display.apply()

			else:
				print("time")
				current_time = localtime()
				if current_time.tm_hour != previous_time.tm_hour or current_time.tm_min != previous_time.tm_min:
					self.display.reset()

					if current_time.tm_hour >= 10:
						self.display.unblank_tube(0)
						self.display.set_tube(0, current_time.tm_hour / 10)
					else:
						self.display.blank_tube(0)

					self.display.unblank_tube(1)
					self.display.set_tube(1, current_time.tm_hour % 10)

					self.display.unblank_tube(2)
					self.display.set_tube(2, current_time.tm_min / 10)

					self.display.unblank_tube(3)
					self.display.set_tube(3, current_time.tm_min % 10)

					self.display.apply()

				previous_time = current_time
				timeout = 60 - current_time.tm_sec

			print("timeout %s" % timeout)
			event = self.custom_event.wait(timeout)
			if not event:
				self.custom = False	 # There is a race condition here
			self.custom_event.clear()

	def display_number(self, number = 0):
		if number >= 1000:
			self.custom_tubes[0] = number / 1000
		else:
			self.custom_tubes[0] = -1
		if number >= 100:
			self.custom_tubes[1] = (number % 1000) / 100
		else:
			self.custom_tubes[1] = -1
		if number >= 10:
			self.custom_tubes[2] = (number % 100) / 10
		else:
			self.custom_tubes[2] = -1

		self.custom_tubes[3] = number % 10

		self.custom = True
		self.custom_event.set()

	def blank(self):
		self.blanked = True
		self.custom = False

		self.custom_event.set()

	def unblank(self):
		self.blanked = False
		self.custom = False

		self.custom_event.set()


if __name__ == "__main__":
	try:

		RPIO.setup(dot_top, RPIO.OUT)
		RPIO.setup(dot_bot, RPIO.OUT)

		RPIO.output(dot_top, False)
		RPIO.output(dot_bot, True)

		# Setup PWM and DMA channel 0
		#PWM.set_loglevel(PWM.LOG_LEVEL_DEBUG)

		dt = DisplayThread()
		dt.start()
		i = 0
		while True:
			sleep(10)
			dt.display_number(i)
			i = i + 2

		"""
		cs = clock_sequence()

		display = StandardDisplay()

		sleep(1)
		display.set_tube(0, 1)
		sleep(1)
		display.blank_tube(0)
		sleep(1)
		display.unblank_tube(0)
		sleep(1)
		display.set_tube(1, 2)
		sleep(1)
		display.set_tube(2, 3)
		sleep(1)
		display.set_tube(3, 4)
		sleep(1)

		# Add some pulses to the subcycle
		tube = Sequence(0, tube_gpios, ((tube_0, 1, 170), (tube_1, 251, 170), (tube_2, 501, 170), (tube_3, 751, 170), ))
		tube.channel = 0
		tube.apply()

		digit = Sequence(0, digit_gpios, ((digits[0], 0, 240), (digits[1], 250, 240), (digits[2], 500, 240), (digits[3], 750, 240), ))
		digit.channel = 0
		digit.apply()

		sleep(1)

		for i in range(0, 10):
			digit.reset()
			# digit.gpio_sets = ((digits[i], 0, 240), )
			digit.gpio_sets = ((digits[(i + 0) % 10], 0, 240), (digits[(i + 1) % 10], 250, 240), (digits[(i + 2) % 10], 500, 240), (digits[(i + 3) % 10], 750, 240), )
			digit.apply()
			sleep(0.2)

		i = 0
		for i in range(0, 100):
			# digit.gpio_sets = ((digits[i], 0, 240), )
			digit.gpio_sets = ((digits[(i / 600) % 10], 0, 240), (digits[(i / 100) % 6], 250, 240), (digits[(i / 10) % 10], 500, 240), (digits[i % 10], 750, 240), )
			digit.reset()
			tube.reset()
			tube.apply()
			digit.apply()
			sleep(0.1)

		i = 0
		step = 40
		digit.reset()
		while (True):
			i = (i + step)
			PWM.clear_channel_gpio(0, cathode_D)
			PWM.add_channel_pulse(0, cathode_D, start=i, width=240-i)

			if (i == 240) or (i == 0):
				step = -step
				sleep(0.9)
			sleep(0.1)
		"""
	except KeyboardInterrupt:
		# Stop PWM for specific GPIO on channel 0
		PWM.clear_channel_gpio(0, anode_a)
		PWM.clear_channel_gpio(0, anode_c)

		# Shutdown all PWM and DMA activity
		PWM.cleanup()

		# reset every channel that has been set up by this program,
		# and unexport interrupt gpio interfaces
		RPIO.cleanup()
