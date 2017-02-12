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
from time import sleep
from LightUpAlarm import AlarmCli
from LightUpAlarm import AlarmManager
from LightUpServer import Server
from user_input import UI, Wheel
from nixie import DisplayThread
from gi import require_version
require_version('Gst', '1.0')
from gi.repository import GObject, Gst

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
        threading.Thread.__init__(self)
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



class StateWheel:
    VOLUME = 0

class StateWheelSwitch:
    PLAY = 0

class Conductor(object):
    def __init__(self):
        GObject.threads_init()
        Gst.init(None)

        self.player = GstPlayer()
        self.dt = DisplayThread()
        self.dt.start()

        self.stations = []
        self.stations.append('http://direct.fipradio.fr/live/fip-midfi.mp3')
        self.stations.append('http://rivieraradio.ice.infomaniak.ch:80/rivieraradio-high')

        self.state_playing = False
        self.state_wheel_switch = StateWheelSwitch.PLAY
        self.state_wheel = StateWheel.VOLUME
        self.state_volume = 0
        self.state_station = 0
        self.state_blanked = False

        self.state_volume_change(50)


    def state_playing_change(self, new_state):
        if new_state == self.state_playing:
            return

        if new_state == True:
            self.player.play(self.stations[self.state_station], self.state_volume)
            self.player.set_volume(self.state_volume)
            self.dt.display_number(self.state_volume)
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
        if new_volume == self.state_volume:
            return

        self.state_volume = new_volume
        self.dt.display_number(new_volume)

        print("volume: %s" % self.state_volume)

        if self.state_playing:
            self.player.set_volume(new_volume)


    def alert(self):
        # '\a' is a request to the terminal to beep
        print('\n\nRING RING RING!!!!\a')
        sleep(0.8)
        print('\a')
        sleep(0.8)
        print('\a')

        self.state_playing_change(True)


    def wheel_turned(self, val):
        if self.state_wheel == StateWheel.VOLUME:
            self.state_volume_change(val)


    def wheel_switch_pressed(self):
        if self.state_wheel_switch == StateWheelSwitch.PLAY:
            self.state_playing_toggle()



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

    conductor = Conductor()
    ui = UI()

    ui.set_wheel_pressed_callback(conductor.state_playing_toggle)
    ui.wheel.setup(0, 50, 100, 0.5, conductor.state_volume_change)

    ui.set_top_pressed_callback(conductor.state_blanking_toggle)

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
        cli_thread.attach_alarm_mgr(alarm_mgr)
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
            # Allow the clean exit from the CLI interface to execute
            if cli_thread.isAlive():
                sleep(1)


if __name__ == '__main__':
    main(sys.argv[1:])
