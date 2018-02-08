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

nixie_channel = 7
dots_channel = 6

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

digit_sets = map(lambda (a,b,c,d): (a << digit_gpios[0]) | (b << digit_gpios[1]) | (c << digit_gpios[2]) | (d << digit_gpios[3]), digits)
digit_mask = (1 << digit_gpios[0]) | (1 << digit_gpios[1]) | (1 << digit_gpios[2]) | (1 << digit_gpios[3])

tube_sets = map(lambda (a,b,c): (a << tube_gpios[0]) | (b << tube_gpios[1]) | (c << tube_gpios[2]), tubes)
tube_mask = (1 << tube_gpios[0]) | (1 << tube_gpios[1]) | (1 << tube_gpios[2])


class DMAChannel:
	def __init__(self, channel = 0, period = 10000, gpios = ()):
		self.channel = channel
		self.gpios = gpios

		PWM.init_channel(channel, period)
		PWM.print_channel(channel)

		# Calling clear channel on a gpio that was not used with add_channel_pulse triggers an error,
		# so avoid it by adding/removing all gpios at channel init time
		for gpio in gpios:
			PWM.add_channel_pulse(self.channel, gpio, 0, 1)
		self.reset()

	def apply(self, gpio_sets, gpios = None):
		if gpios == None:
			gpios = self.gpios
		for (gpio_set, start, width) in gpio_sets:
			#print gpio_set
			#print start
			#print width
			for i in range(0, len(gpios)):
				#print i
				if gpio_set[i] == 1:
					PWM.add_channel_pulse(self.channel, gpios[i], start, width)

	def set_on(self, position):
		PWM.buffer_set_on(self.channel, position)

	def set_off(self, position):
		PWM.buffer_set_off(self.channel, position)

	def assign(self, gpios, position):
		for gpio in gpios:
			PWM.buffer_assign(self.channel, gpio, position)

	def set_mask(self, set, mask, position):
		PWM.buffer_set_mask(self.channel, set, mask, position)

	def reset(self):
		for gpio in reversed(self.gpios):
			PWM.clear_channel_gpio(self.channel, gpio)


class Dots:
	PERIOD = 1000000
	DOT_LENGTH = 49000
	STRIDE = 0
	def __init__(self):
		self.dot_length = Dots.DOT_LENGTH
		self.channel = DMAChannel(channel = dots_channel, period = Dots.PERIOD, gpios = (dot_top, dot_bot))

		self.channel.apply([((1, 0), 1, self.dot_length),
							((0, 1), 1 + Dots.STRIDE, self.dot_length)])

	def reset(self):
		self.channel.reset()


class Tube:
	TUBE_LENGTH = 170
	DIGIT_LENGTH = 240
	def __init__(self, channel, tube = 0, offset = 0):
		self.start = offset
		self.tube_length = Tube.TUBE_LENGTH
		self.channel = channel
		self.dual_pos = -1
		# Digits
		channel.set_on(self.start)

		channel.assign(digit_gpios, self.start + self.DIGIT_LENGTH)
		channel.set_off(self.start + self.DIGIT_LENGTH)

		# Tubes
		channel.set_mask(tube_sets[tube], tube_mask, self.start + 1)
		channel.set_on(self.start + 1)

		channel.set_mask(tube_mask, tube_mask, self.start + 1 + self.tube_length)
		channel.set_off(self.start + 1 + self.tube_length)

	def set_digit(self, digit = 0):
		self.clear_dual()
		self.channel.set_mask(digit_sets[digit], digit_mask, self.start)
		self.channel.set_on(self.start)

	def blank(self):
		# TODO: implement set_none and use it rather than clearing the GPIOs, since they should already be clear
		self.channel.set_off(self.start + 1)

	def unblank(self):
		self.channel.set_on(self.start + 1)

	def set_brightness(self, percentage):
		tube_length = (min(max(percentage, 0), 100) * Tube.TUBE_LENGTH) / 100
		tube_length = max(tube_length, 1)

		if tube_length != self.tube_length:
			self.channel.set_mask(tube_mask, tube_mask, self.start + 1 + tube_length)
			self.channel.set_off(self.start + 1 + tube_length)

			self.channel.set_mask(0, tube_mask, self.start + 1 + self.tube_length)
			self.channel.set_off(self.start + 1 + self.tube_length) #TODO implement set_none

			self.tube_length = tube_length

	def set_dual(self, i, j, percentage):
		self.clear_dual()
		self.set_digit(i)
		self.dual_pos = self.start + (self.tube_length * min(max(percentage, 0), 100)) / 100

		self.channel.set_mask(digit_mask, digit_mask, self.dual_pos)
		self.channel.set_on(self.dual_pos)

		self.channel.set_mask(~digit_sets[j], digit_mask, self.dual_pos + 1)
		self.channel.set_off(self.dual_pos + 1)

	def clear_dual(self):
		if self.dual_pos != -1:
			self.channel.set_mask(0, digit_mask, self.dual_pos)
			self.channel.set_off(self.dual_pos)	#TODO implement set_none

			self.channel.set_mask(0, digit_mask, self.dual_pos + 1)
			self.channel.set_off(self.dual_pos + 1)	#TODO implement set_none

			self.dual_pos = -1


class Display:
	PERIOD = 10000
	STRIDE = 250
	def __init__(self):
		self.channel = DMAChannel(channel = nixie_channel, period = Display.PERIOD, gpios = tube_gpios + digit_gpios)
		self.tubes = []
		for i in range(0,4):
			self.tubes.append(Tube(self.channel, i, i * Display.STRIDE))

	def set_brightness(self, brightness):
		for i in range(0,4):
			self.tubes[i].set_brightness(brightness)

	def set_tube(self, tube = 0, digit = 0):
		self.tubes[tube].set_digit(digit)

	def blank_tube(self, tube):
		self.tubes[tube].blank()

	def unblank_tube(self, tube):
		self.tubes[tube].unblank()


class DisplayThread(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)
		self.daemon = True

		PWM.setup(pulse_incr_us=10)

		self.display = Display()
		self.blanked = False
		self.custom = False
		self.custom_tubes = [ 0, 0, 0, 0 ]
		self.custom_event = threading.Event()

		self.dots = Dots()


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

				if self.custom_tubes[0] == -1:
					self.display.blank_tube(0)
				elif self.custom_tubes[0] == 18:
					self.display.unblank_tube(0)
					self.display.tubes[0].set_dual(1, 8, 50)
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

			elif self.blanked:
				print("blanked")
				previous_time = localtime(0)
				self.dots.reset()

				self.display.blank_tube(0)
				self.display.blank_tube(1)
				self.display.blank_tube(2)
				self.display.blank_tube(3)

			else:
				print("time")
				current_time = localtime()
				if current_time.tm_hour != previous_time.tm_hour or current_time.tm_min != previous_time.tm_min:

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

				previous_time = current_time
				timeout = 60 - current_time.tm_sec

			print("timeout %s" % timeout)
			event = self.custom_event.wait(timeout)
			if not event:
				self.custom = False	 # There is a race condition here
			self.custom_event.clear()


	def display_number(self, number = 0):
		if number >= 10000:
			self.custom_tubes[0] = 18
			number -= 10000
		elif number >= 1000:
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

		display = Display()

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
		tube = Sequence(nixie_channel, tube_gpios, ((tube_0, 1, 170), (tube_1, 251, 170), (tube_2, 501, 170), (tube_3, 751, 170), ))
		tube.apply()

		digit = Sequence(nixie_channel, digit_gpios, ((digits[0], 0, 240), (digits[1], 250, 240), (digits[2], 500, 240), (digits[3], 750, 240), ))
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
			PWM.clear_channel_gpio(nixie_channel, cathode_D)
			PWM.add_channel_pulse(nixie_channel, cathode_D, start=i, width=240-i)

			if (i == 240) or (i == 0):
				step = -step
				sleep(0.9)
			sleep(0.1)
		"""
	except (KeyboardInterrupt, SystemExit):
		# Stop PWM for specific GPIO on channel 0
		PWM.clear_channel_gpio(nixie_channel, anode_a)
		PWM.clear_channel_gpio(nixie_channel, anode_c)

		# Shutdown all PWM and DMA activity
		PWM.cleanup()

		# reset every channel that has been set up by this program,
		# and unexport interrupt gpio interfaces
		RPIO.cleanup()