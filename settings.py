## -*- coding: utf-8 -*-
##
## settings.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     25 november 2012
## Copyright (c) 2012, Toke Høiland-Jørgensen
##
## This program is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os, runpy, optparse

from ordereddict import OrderedDict

DEFAULT_SETTINGS = {
    'HOST': 'localhost',
    'STEP_SIZE': 0.1,
    'LENGTH': 60,
    'OUTPUT': '-',
    'FORMAT': 'default',
    'TITLE': '',
    'LOG_FILE': None,
    'INPUT': None,
    }

TEST_PATH = os.path.join(os.path.dirname(__file__), 'tests')
DICT_SETTINGS = ('DATA_SETS', 'PLOTS')

parser = optparse.OptionParser(description='Wrapper to run concurrent netperf-style tests',
                               usage="usage: %prog [options] test")

parser.add_option("-o", "--output", action="store", type="string", dest="OUTPUT",
                  help="file to write output to (default standard out)")
parser.add_option("-i", "--input", action="store", type="string", dest="INPUT",
                  help="file to read input from (instead of running tests)")
parser.add_option("-f", "--format", action="store", type="string", dest="FORMAT",
                  help="override config file output format")
parser.add_option("-H", "--host", action="store", type="string", dest="HOST",
                  help="host to connect to for tests")
parser.add_option("-t", "--title-extra", action="store", type="string", dest="TITLE",
                  help="text to add to plot title")
parser.add_option("-l", "--log-file", action="store", type="string", dest="LOG_FILE",
                  help="write debug log (test program output) to log file")
parser.add_option("-L", "--length", action="store", type="int", dest="LENGTH",
                  help="base test length (some tests may add some time to this)")
parser.add_option("-s", "--step-size", action="store", type="float", dest="STEP_SIZE",
                  help="measurement data point step size")

class Settings(optparse.Values, object):

    def load_test(self, test_name):
        self.NAME = test_name
        settings = runpy.run_path(os.path.join(TEST_PATH, test_name + ".conf"),
                                  self.__dict__,
                                  test_name)

        for k,v in settings.items():
            if k == k.upper():
                setattr(self, k, v)

        if not 'TOTAL_LENGTH' in settings:
            self.TOTAL_LENGTH = self.LENGTH

    def __setattr__(self, k, v):
        if k in DICT_SETTINGS and isinstance(v, list):
            v = OrderedDict(v)
        object.__setattr__(self, k, v)

settings = Settings(DEFAULT_SETTINGS)

def load():
    (dummy,args) = parser.parse_args(values=settings)

    if len(args) < 1:
        parser.error("Missing test name.")

    test_name = args[0]

    if os.path.exists(test_name):
        test_name = os.path.splitext(os.path.basename(test_file))[0]

    settings.load_test(test_name)

    return settings
