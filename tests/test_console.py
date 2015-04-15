from unittest import TestCase
import sys
from atavism.command_line import main


class TestConsole(TestCase):
    def test_basic(self):
        # argv[1] will be test...
        sys.argv = ['', '--find-devices', '/home/david/Pictures/timelapse/steps_day1_1.mp4']
#        main()

