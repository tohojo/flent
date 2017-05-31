# -*- coding: utf-8 -*-
#
# test_tests.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     25 July 2015
# Copyright (c) 2015-2016, Toke Høiland-Jørgensen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import unittest

from flent.testenv import TEST_PATH
from flent.settings import parser, Settings, DEFAULT_SETTINGS
settings = parser.parse_args(args=[], namespace=Settings(DEFAULT_SETTINGS))


class TestTests(unittest.TestCase):

    def setUp(self):
        self.tests = sorted([os.path.splitext(i)[0]
                             for i in os.listdir(TEST_PATH)
                             if i.endswith('.conf')])
        self.settings = settings.copy()

    def test_load_tests(self):
        for t in self.tests:
            self.settings.load_test(t, informational=True)


test_suite = unittest.TestSuite(
    [unittest.TestLoader().loadTestsFromTestCase(TestTests)])
