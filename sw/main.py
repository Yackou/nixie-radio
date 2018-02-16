#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
# Starts the LightUpPi Alarm application.
#
# Copyright (c) 2015 carlosperate https://github.com/carlosperate/
# Licensed under The MIT License (MIT), a copy can be found in the LICENSE file
#
# Copyright (c) 2017 Yackou  https://github.com/Yackou/
#
# arguments to select the command line interface, the server only run, or to
# have both running at the same time.
#
from __future__ import unicode_literals, absolute_import, print_function
import sys
import getopt
import thread
import platform
import threading
import subprocess
from time import sleep
from LightUpAlarm import AlarmCli
from LightUpAlarm import AlarmManager
from LightUpServer import Server
from user_input import UI, Wheel
from nixie import DisplayThread
from gi import require_version
require_version('Gst', '1.0')
from gi.repository import GObject, Gst

WHEEL_STEPS = 100
STEPS_PER_TURN = 96
"""
from mplayer import Player

Player.introspect()

class MPlayer(object):
	def __init__(self):
		self.player = Player(args=["-ao", "alsa:noblock:device=hw=1.0", "-softvol", "-volume", "50"])

		if not self.player.paused:
			self.player.pause()

	def play(self, uri, volume):
		 self.player.loadfile(uri)
		 self.player.volume = volume

	def stop(self):
		self.player.stop()

	def set_volume(self, new_volume):
		self.player.volume = new_volume
"""

class CliThread(threading.Thread):
	"""
	Simple thread class for launching command line ui in its own process (to be
	able to run alongside the server, which needs to be in the main thread)
	"""
	def __init__(self):
		self.cli_instance = None
		threading.Thread.__init__(self, name = "cli")
		self.daemon = True

	def attach_alarm_mgr(self, alarm_mgr):
		self.cli_instance = AlarmCli.AlarmCli(alarm_mgr=alarm_mgr)

	def run(self):
		if self.cli_instance is None:
			print('ERROR: Need to attach an AlarmManager instance using the '
				  'attach_alarm_mgr method.', file=sys.stderr)
			return
		self.cli_instance.cmdloop()
		# Exit from cli returns here. User has requested the app to exit, and
		# this thread needs to request a keyboard interrupt to the main thread.
		print("Exiting from CLI...")
		thread.interrupt_main()

	def callback_event(self):
		""" Updates the cli data, to be used as a server callback. """
		self.cli_instance.onecmd('alarms')
		sys.stdout.flush()
		sys.stdout.write('\n%s' % self.cli_instance.prompt)


class GstPlayer(object):
	def __init__(self):
		self.player = Gst.ElementFactory.make('playbin', 'player')

	def play(self, uri, volume):
		self.player.set_property("uri", uri)
		#self.player.set_property("volume", volume/100.0)
		self.player.set_state(Gst.State.PLAYING)

	def stop(self):
		self.player.set_state(Gst.State.NULL)

	def set_volume(self, new_volume):
		self.player.set_property("volume", new_volume/100.0)


class Watchdog(threading.Thread):
	def __init__(self, online, offline):
		threading.Thread.__init__(self, name = "watchdog")
		self.daemon = True
		self.current_status = 1
		self.offline = offline
		self.online = online

	def run(self):
		timeout = 2
		dev_null = open("/dev/null")
		hostname = "gate"
		cmd_str =  "ping -c1 -w2 " + hostname

		while True:
			return_code = subprocess.call(cmd_str.split(), stderr= dev_null, stdout = dev_null)

			if return_code != 0 and self.current_status == 1:
				self.current_status = 0
				self.offline()
				subprocess.call('ifdown wlan0'.split())
				subprocess.call('rmmod mt7601u'.split())
				sleep(1)
				subprocess.call('modprobe mt7601u'.split())
				subprocess.call('ifup wlan0'.split())

			if return_code == 0 and self.current_status == 0:
				self.current_status = 1
				self.online()

			sleep(timeout)


class StateWheel:
	VOLUME = 0

class StateWheelSwitch:
	PLAY = 0

class RadioState:
	DEFAULT = 0
	VOLUME = 1
	BRIGHTNESS = 2
	NEXT = 3
	STATION = 4
	ALARM = 5
	SNOOZE = 6
	SLEEP = 7

class RadioEvent:
	TIMEOUT = 0
	T = 1
	M = 2
	B = 3
	WHEEL_MOVE = 4
	WHEEL_PRESSED = 5
	ALARM = 6
	TMB = 7

class Conductor(threading.Thread):
	def __init__(self, wheel_setup_cb):
		threading.Thread.__init__(self, name = "conductor")
		self.daemon = True

		GObject.threads_init()
		Gst.init(None)

		self.threading_event = threading.Event()

		self.player = GstPlayer()
		self.dt = DisplayThread()
		self.dt.start()

		self.wheel_setup_cb = wheel_setup_cb

		self.alarm_mgr = None

		self.offline_station = 'file:///home/yannick/Music/01 - Il Y A.mp3'
		self.stations = []
		#self.stations.append('file:///home/yannick/Music/01 - Il Y A.mp3')
		#self.stations.append('http://tsfjazz.ice.infomaniak.ch/tsfjazz-high.mp3')
		#self.stations.append('http://direct.fipradio.fr/live/fip-midfi.mp3')
		#self.stations.append('http://rivieraradio.ice.infomaniak.ch:80/rivieraradio-high')
		self.current_station = None

		self.state_offline = False
		self.state_playing = False
		self.state_wheel_switch = StateWheelSwitch.PLAY
		self.state_wheel = StateWheel.VOLUME
		self.wheel_value = 50
		self.state_brightness = 50
		self.state_volume = 0
		self.state_station = 1
		self.state_blanked = False

		self.state_volume_change(WHEEL_STEPS / 2)

	def attach_alarm_mgr(self, alarm_mgr):
		self.alarm_mgr = alarm_mgr
		self.stations = self.alarm_mgr.get_all_stations()
		if len(self.stations) > 0:
			self.current_station = self.stations[0]


	def state_station_change(self, new_station):
		self.dt.display_number(10000 + new_station.id_)
		if new_station == self.current_station:
			return

		self.current_station = new_station
		if self.state_playing == True:
			self.state_playing_change(False)
			self.state_playing_change(True)

	def state_playing_change(self, new_state):
		if new_state == self.state_playing:
			return

		if new_state == True:
			if self.state_offline:
				self.player.play(self.offline_station, self.state_volume)
			else:
				self.player.play(self.current_station.url, self.state_volume)
			self.player.set_volume(self.state_volume)
			print('Playing music')
		else:
			self.player.stop()
			print('Stopping music')

		self.state_playing = new_state


	def state_playing_toggle(self):
		self.state_playing_change(not self.state_playing)

	def state_blanking_toggle(self):
		self.state_blanked = not self.state_blanked
		if self.state_blanked:
			self.dt.blank()
		else:
			self.dt.unblank()


	def state_volume_change(self, new_volume):
		self.dt.display_number(new_volume)
		if new_volume == self.state_volume:
			return

		self.state_volume = new_volume * 100 / WHEEL_STEPS

		print("volume: %s" % self.state_volume)

		if self.state_playing:
			self.player.set_volume(self.state_volume)

	def state_brightness_change(self, new_brightness):
		self.dt.display_number(new_brightness)
		if new_brightness == self.state_brightness:
			return

		self.state_brightness = new_brightness * 100 / WHEEL_STEPS
		self.dt.display.set_brightness(self.state_brightness)
		self.dt.dots.set_brightness(self.state_brightness)

		print("brightness: %s" % self.state_brightness)


	def alert(self, alarm_item):
		station = self.alarm_mgr.get_station(alarm_item.station_id)
		# '\a' is a request to the terminal to beep
		print('\n\nRING RING RING ' + station.name + ' !!!!\a')
		sleep(0.8)
		print('\a')
		sleep(0.8)
		print('\a')

		self.state_volume_change(WHEEL_STEPS / 2)
		self.state_station_change(station)
		self.state_playing_change(True)


	def wheel_turned(self, val):
		if self.state_wheel == StateWheel.VOLUME:
			self.state_volume_change(val)


	def wheel_switch_pressed(self):
		if self.state_wheel_switch == StateWheelSwitch.PLAY:
			self.state_playing_toggle()

	def online(self):
		print("Back online")
		self.state_offline = False
		if self.state_playing:
			self.state_playing_change(False)
			self.state_playing_change(True)

	def offline(self):
		print("Went offline")
		self.state_offline = True
		if self.state_playing:
			self.state_playing_change(False)
			self.state_playing_change(True)

	def event_T(self):
		self.event = RadioEvent.T
		self.threading_event.set()

	def event_M(self):
		self.event = RadioEvent.M
		self.threading_event.set()

	def event_B(self):
		self.event = RadioEvent.B
		self.threading_event.set()

	def event_WHEEL_PRESSED(self):
		self.event = RadioEvent.WHEEL_PRESSED
		self.threading_event.set()

	def event_WHEEL_MOVE(self, new_val):
		self.wheel_value = new_val
		self.event = RadioEvent.WHEEL_MOVE
		self.threading_event.set()

	def to_state_DEFAULT(self):
		self.wheel_setup_cb(0, self.state_volume, WHEEL_STEPS, (WHEEL_STEPS + 23) / 24, STEPS_PER_TURN, self.event_WHEEL_MOVE)
		if self.state_blanked:
			self.dt.blank()
		self.dt.dots.steady(0, 1, 1)
		self.state = RadioState.DEFAULT
		self.timeout = None

	def to_state_BRIGHTNESS(self):
		self.wheel_setup_cb(0, self.state_brightness, WHEEL_STEPS, (WHEEL_STEPS + 23) / 24, STEPS_PER_TURN, self.event_WHEEL_MOVE)
		self.state_brightness_change(self.state_brightness)
		self.dt.dots.steady(1, 1, 1)
		self.state = RadioState.BRIGHTNESS
		self.timeout = 3

	def to_state_NEXT(self):
		alarm_item = self.alarm_mgr.get_next_alarm()
		self.dt.display_number(alarm_item.hour*100 + alarm_item.minute)
		self.dt.dots.altern()
		self.state = RadioState.NEXT
		self.timeout = 3

	def to_state_STATION(self):
		self.wheel_setup_cb(0, [s.id_ for s in self.stations].index(self.current_station.id_), len(self.stations) - 1, (len(self.stations) - 1 + 23) / 24, 8*(len(self.stations) - 1), self.event_WHEEL_MOVE)
		self.state_station_change(self.current_station)
		self.dt.dots.steady(0, 1, 1)
		self.state = RadioState.STATION
		self.timeout = 3

	def run(self):
		event_raised = False
		self.event = RadioEvent.TIMEOUT
		self.to_state_DEFAULT()

		while True:
			event_raised = self.threading_event.wait(self.timeout)
			if not event_raised:
				self.event = RadioEvent.TIMEOUT

			print("State: %s  Event: %s timeout %s" % (self.state, self.event, self.timeout))
			if self.state == RadioState.DEFAULT:
				if self.event == RadioEvent.T:
					self.to_state_BRIGHTNESS()

				elif self.event == RadioEvent.M:
					self.to_state_NEXT()

				elif self.event == RadioEvent.B:
					self.to_state_STATION()

				elif self.event == RadioEvent.WHEEL_MOVE:
					self.state_volume_change(self.wheel_value)
					self.state = RadioState.VOLUME
					self.timeout = 3

				elif self.event == RadioEvent.WHEEL_PRESSED:
					self.state_playing_toggle()


			elif self.state == RadioState.VOLUME:
				if self.event == RadioEvent.TIMEOUT:
					self.to_state_DEFAULT()

				elif self.event == RadioEvent.T:
					self.to_state_BRIGHTNESS()

				elif self.event == RadioEvent.M:
					self.to_state_NEXT()

				elif self.event == RadioEvent.B:
					self.to_state_STATION()

				elif self.event == RadioEvent.WHEEL_MOVE:
					self.state_volume_change(self.wheel_value)

				elif self.event == RadioEvent.WHEEL_PRESSED:
					self.state_playing_toggle()


			elif self.state == RadioState.BRIGHTNESS:
				if self.event == RadioEvent.TIMEOUT:
					self.to_state_DEFAULT()

				elif self.event == RadioEvent.T:
					self.state_blanking_toggle()
					self.to_state_DEFAULT()

				elif self.event == RadioEvent.M:
					self.to_state_NEXT()

				elif self.event == RadioEvent.B:
					self.to_state_STATION()

				elif self.event == RadioEvent.WHEEL_MOVE:
					self.state_brightness_change(self.wheel_value)

				elif self.event == RadioEvent.WHEEL_PRESSED:
					self.state_playing_toggle()


			elif self.state == RadioState.NEXT:
				if self.event == RadioEvent.TIMEOUT:
					self.to_state_DEFAULT()

				elif self.event == RadioEvent.T:
					self.to_state_BRIGHTNESS()

				elif self.event == RadioEvent.B:
					self.to_state_STATION()


			elif self.state == RadioState.STATION:
				if self.event == RadioEvent.TIMEOUT:
					self.to_state_DEFAULT()

				elif self.event == RadioEvent.T:
					self.to_state_BRIGHTNESS()

				elif self.event == RadioEvent.M:
					self.to_state_NEXT()

				elif self.event == RadioEvent.WHEEL_MOVE:
					self.state_station_change(self.stations[self.wheel_value])

				elif self.event == RadioEvent.WHEEL_PRESSED:
					self.state_playing_toggle()


			print("New state: %s  Timeout: %s" % (self.state, self.timeout))
			self.threading_event.clear()

def parsing_args(argv):
	"""
	Processes the command line arguments. Arguments supported:
	-h / --help
	-c / --cli
	-s / --server
	-b / --both
	:return: dictionary with available options(keys) and value(value)
	"""
	option_dict = {}
	try:
		opts, args = getopt.getopt(
			argv, 'hscb', ['help', 'server', 'cli', 'both'])
	except getopt.GetoptError as e:
		print('There was a problem parsing the command line arguments:')
		print('\t%s' % e)
		sys.exit(1)

	for opt, arg in opts:
		if opt in ('-h', '--help'):
			print('Choose between running the application in command line ' +
				  'interface, to launch the HTTP server, or both.\n' +
				  '\t-c Command Line Interface\n\t-s Launch HTTP server\n'
				  '\t-b Both command line and server')
			sys.exit(0)
		elif opt in ('-c', '--cli'):
				option_dict['cli'] = None
		elif opt in ('-s', '--server'):
				option_dict['server'] = None
		elif opt in ('-b', '--both'):
				option_dict['both'] = None
		else:
			print('Flag ' + opt + ' not recognised.')

		# It only takes the server or the cli flag, so check
		if 'server' in option_dict and 'cli' in option_dict:
			print('Both server and cli flags detected, you can use the flag '
				  '-b/--both for both.')
	return option_dict


def main(argv):
	"""
	Gets the argument flags and launches the server or command line interface.
	"""
	print('Running Python version ' + platform.python_version())

	# This variable is used to select between the different modes, defaults both
	start = 'both'

	# Checking command line arguments in order of priority
	print('\n======= Parsing Command line arguments =======')
	if len(argv) > 0:
		arguments = parsing_args(argv)
		if 'both' in arguments:
			print('Command line and server selected')
			start = 'both'
		elif 'cli' in arguments:
			print('Command line selected')
			start = 'cli'
		elif 'server' in arguments:
			print('Server selected')
			start = 'server'
	else:
		print('No flags defaults to the command line interface.')

	# Loading the settings
	print('\n=========== Launching Nixie Alarm Clock ==========')

	ui = UI()

	conductor = Conductor(ui.wheel.setup)

	watchdog = Watchdog(conductor.online, conductor.offline)

	ui.set_wheel_pressed_callback(conductor.event_WHEEL_PRESSED)
	ui.wheel.setup(0, WHEEL_STEPS / 2, WHEEL_STEPS, (WHEEL_STEPS + 23) / 24, STEPS_PER_TURN, conductor.state_volume_change)

	ui.set_top_pressed_callback(conductor.event_T)
	ui.set_middle_pressed_callback(conductor.event_M)
	ui.set_bottom_pressed_callback(conductor.event_B)

	if start == 'server':
		# For the server we only set the offset alarm, as it is meant to be run
		# headless and nothing else will be connected to ring/alert
		alarm_mgr = AlarmManager.AlarmManager(
			offset_alert_callback=None)
		Server.run(alarm_mgr_arg=alarm_mgr)
	else:
		# The command line interface running on its own thread is common to
		# the 'cli' and 'both' options.
		cli_thread = CliThread()
		alarm_mgr = AlarmManager.AlarmManager(
			alert_callback=conductor.alert,
			offset_alert_callback=None)
		conductor.attach_alarm_mgr(alarm_mgr)
		cli_thread.attach_alarm_mgr(alarm_mgr)
		conductor.start()
		watchdog.start()
		cli_thread.start()

		# Infinite loop can be the Flask server, or just a loop
		try:
			if start == 'both':
				Server.run(
					alarm_mgr_arg=alarm_mgr,
					silent=True,
					callback_arg=cli_thread.callback_event)
			else:
				while cli_thread.isAlive():
					sleep(0.2)
		except (KeyboardInterrupt, SystemExit):
			print("Exiting...")
			conductor.dt.blank()
			conductor.player.stop()
			# Allow the clean exit from the CLI interface to execute
			if cli_thread.isAlive():
				sleep(1)


if __name__ == '__main__':
	main(sys.argv[1:])
