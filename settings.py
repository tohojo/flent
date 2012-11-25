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

import sys, os, runpy, optparse

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
    'DESCRIPTION': 'No description',
    'PLOTS': {},
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
parser.add_option("-p", "--plot", action="store", type="string", dest="PLOT",
                  help="select which plot to output for the given test")
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

parser.add_option('--list-tests', action='store_true', dest="LIST_TESTS",
                  help="list available tests")
parser.add_option('--list-plots', action='store_true', dest="LIST_PLOTS",
                  help="list available tests")

class Settings(optparse.Values, object):

    def load_test(self, test_name):
        self.NAME = test_name
        settings = runpy.run_path(os.path.join(TEST_PATH, test_name + ".conf"),
                                  self.__dict__,
                                  test_name)

        for k,v in settings.items():
            if k == k.upper():
                setattr(self, k, v)

        if 'DEFAULTS' in settings:
            for k,v in settings['DEFAULTS'].items():
                if not hasattr(self, k):
                    setattr(self, k, v)

        if not 'TOTAL_LENGTH' in settings:
            self.TOTAL_LENGTH = self.LENGTH

    def __setattr__(self, k, v):
        if k in DICT_SETTINGS and isinstance(v, list):
            v = OrderedDict(v)
        object.__setattr__(self, k, v)

    def update(self, values):
        for k,v in values.items():
            setattr(self, k, v)

settings = Settings(DEFAULT_SETTINGS)


def load():
    (dummy,args) = parser.parse_args(values=settings)

    if hasattr(settings, 'LIST_TESTS') and settings.LIST_TESTS:
        list_tests()

    if len(args) < 1:
        parser.error("Missing test name.")

    test_name = args[0]

    if os.path.exists(test_name):
        test_name = os.path.splitext(os.path.basename(test_file))[0]

    settings.load_test(test_name)

    if hasattr(settings, 'LIST_PLOTS') and settings.LIST_PLOTS:
        list_plots()

    return settings

def list_tests():
    tests = sorted([os.path.splitext(i)[0] for i in os.listdir(TEST_PATH) if i.endswith('.conf')])
    sys.stderr.write('Available tests:\n')
    max_len = unicode(max([len(t) for t in tests]))
    for t in tests:
        settings.update(DEFAULT_SETTINGS)
        settings.load_test(t)
        sys.stderr.write((u"  %-"+max_len+u"s :  %s\n") % (t, settings.DESCRIPTION))
    sys.exit(0)

def list_plots():
    plots = settings.PLOTS.keys()
    if not plots:
        sys.stderr.write("No plots available for test '%s'.\n" % settings.NAME)
        sys.exit(0)

    sys.stderr.write("Available plots for test '%s':\n" % settings.NAME)
    max_len = unicode(max([len(p) for p in plots]))
    for p in plots:
        sys.stderr.write((u"  %-"+max_len+u"s :  %s\n") % (p, settings.PLOTS[p]['description']))
    sys.exit(0)
