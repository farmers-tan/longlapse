#!/usr/bin/python3

# timelapse based on sunrise/sunset
# 11/13/16
# updated 12/18/16

import picamera
import ephem
import time
import datetime
import os
import shutil
import subprocess
import logging
import traceback
from fractions import Fraction
from longpaths import base_remote_path, host, scp_host

base_pi_path = '/home/pi/gitbucket/longlapse'
log_locate = os.path.join(base_pi_path, 'longlapse.log')


class Camera(object):

    def __init__(self):
        self.base_pi_path = base_pi_path
        self.base_remote_path = base_remote_path
        self.remote_copy_path = '/Volumes/RAGU/longlapse/dayze'
        self.copied = False
        self.pixels = (2592, 1944)
        self.framerate = 1
        self.led = False
        self.vflip = True
        self.hflip = True
        self.meter_mode = 'backlit'
        self.iso = 100
        self.awb_mode = 'off'
        self.awb_gains = (Fraction(447, 256), Fraction(255, 256))
        # self.exposure_mode = 'off'  # exposure_mode off disables picam.analog_gain & picam.digital_gain, which are not directly settable

    def _make_remote_dir(self, today):
        self.remote_dir = os.path.join(self.remote_copy_path, today)
        status = subprocess.call(['ssh', host, 'test -d {}'.format(self.remote_dir)], stdout=subprocess.DEVNULL)

        if status == 0:
            logging.info('remote directory already exists at {}'.format(self.remote_dir))
            return True
        elif status == 1:
            remote = subprocess.call(['ssh', host, 'mkdir {}'.format(self.remote_dir)])
            if remote == 0:
                logging.info('made remote directory at {}'.format(self.remote_dir))
                return True
            else:
                logging.warning('problem creating remote directory at {}, not copying anything'.format(self.remote_dir))
                logging.warning('exit status: {}'.format(status))
                return False
        else:
            logging.warning('problem encountered in _make_remote_dir()')
            logging.warning('exit status: {}'.format(status))

    def take_pics(self, today):
        with picamera.PiCamera(resolution=self.pixels, framerate=self.framerate) as picam:
            picam.iso = self.iso
            picam.led = self.led
            picam.vflip = self.vflip
            picam.hflip = self.hflip
            picam.meter_mode = self.meter_mode

            time.sleep(5)

            picam.awb_mode = self.awb_mode
            picam.awb_gains = self.awb_gains
            counter = 1

            for frame in range(self.total_frames_today):
                now = datetime.datetime.now()
                picam.capture(os.path.join(self.base_pi_path, today, '{}_frame{:03d}.jpg'.format(now.strftime("%Y-%m-%d_%H-%M"), counter)))
                logging.debug("awb_gains for frame{:03d}: {}".format(counter, picam.awb_gains))

                counter += 1
                self.wait()

    def wait(self):
        next_minute = (datetime.datetime.now() + datetime.timedelta(minutes=5)).replace(second=0, microsecond=0)
        delay = (next_minute - datetime.datetime.now()).total_seconds()
        time.sleep(delay)

    def calculate_frames(self, awake_interval):
        self.total_frames_today = int(abs(awake_interval / 300))
        logging.info('{} frames will be shot today over {} hours'.format(camera.total_frames_today, abs(light.awake_interval) / 3600))

    def sleep_til_sunrise(self, sleep_interval):
        logging.info('sleeping til sunrise {} hours from now'.format(light.sleep_interval / 3600))
        time.sleep(sleep_interval)
        logging.info("I'm awake!")

    def make_todays_dir(self, today):
        self.todays_dir = os.path.join(self.base_pi_path, today)
        if not os.path.isdir(self.todays_dir):
            os.mkdir(self.todays_dir)
            logging.info("made today's directory at {}".format(camera.todays_dir))

    def copy_todays_dir(self, today):
        '''
        to check if file exists on remote use:
        subprocess.call(['ssh', host, 'test -f {}'.format(shlex.quote(path))])
        '''
        remote = self._make_remote_dir(today)

        if remote:
            logging.info("copying today's directory to kestrel")
            # remove leading '/' so that os.path.join() will work
            remote_pic_path = os.path.join(scp_host, self.remote_dir[1:])
            status_dict = {}
            trouble = False
            pic_list = [pic for pic in os.listdir(self.todays_dir) if not pic.startswith('.')]
            pic_list.sort()

            for pic in pic_list:
                pic_path = os.path.join(self.todays_dir, pic)
                status = subprocess.call(['scp', '-p', pic_path, remote_pic_path], stdout=subprocess.DEVNULL)
                status_dict[pic] = status

            for key in status_dict.keys():
                if status_dict[key] == 1:
                    # TODO: add uncopied photos to a list, try again next day
                    #       or just have the script try to copy all folders it sees
                    logging.warning("trouble copying {}".format(key))
                    trouble = True

            if not trouble:
                logging.info("finished copying today's directory")
                self.copied = True

    def delete_todays_dir(self):
        if os.path.isdir(self.todays_dir) and self.copied:
            shutil.rmtree(self.todays_dir)
            logging.info("deleted today's directory")
        else:
            logging.warning("did not delete today's directory")

    def push_log(self):
        git_dir = os.path.join(base_pi_path, '.git')
        work_tree = base_pi_path

        logging.info("pushing today's log to github\n")
        subprocess.call(['git', '--git-dir', git_dir, '--work-tree', work_tree, 'add', log_locate])
        subprocess.call(['git', '--git-dir', git_dir, '--work-tree', work_tree, 'commit', '-m' 'update log'])
        subprocess.call(['git', '--git-dir', git_dir, '--work-tree', work_tree, 'push'])


class Light(object):

    def __init__(self):
        self.seattle = ephem.Observer()
        self.seattle.pressure = 0
        self.seattle.horizon = '-6'
        self.seattle.lon = '-122:21:19:5'
        self.seattle.lat = '47:44:03:9'
        self.seattle.elevation = 145

    def get_times(self):
        # self.prev_rise = ephem.localtime(self.seattle.previous_rising(ephem.Sun()))
        self.next_rise = ephem.localtime(self.seattle.next_rising(ephem.Sun()))
        self.next_set = ephem.localtime(self.seattle.next_setting(ephem.Sun()))
        self.sleep_interval = (self.next_rise - datetime.datetime.now()).total_seconds()
        self.awake_interval = (self.next_rise - self.next_set).total_seconds()
        self.today = light.next_rise.strftime("%Y-%m-%d")

        logging.info('----------------------- {} -----------------------'.format(self.today))
        logging.debug('light.next_rise = {}'.format(light.next_rise))
        logging.debug('light.next_set = {}'.format(light.next_set))
        logging.debug('light.sleep_interval = {}'.format(light.sleep_interval))
        logging.debug('light.awake_interval = {}'.format(light.awake_interval))
        logging.debug('light.today = {}'.format(light.today))


if __name__ == '__main__':
    logging.basicConfig(filename=log_locate, format='%(asctime)s %(message)s', datefmt='%Y/%m/%d %H:%M:%S', level=logging.INFO)

    camera = Camera()
    light = Light()

    try:
        light.get_times()

        camera.make_todays_dir(light.today)
        camera.calculate_frames(light.awake_interval)
        camera.sleep_til_sunrise(light.sleep_interval)

        camera.take_pics(light.today)

        # TODO: use rsync instead of these methods for file copying and directory deleting?
        camera.copy_todays_dir(light.today)
        camera.delete_todays_dir()
        camera.push_log()

    except Exception as e:
        logging.error(traceback.format_exc())
