# -*- coding: utf-8 -*-
#
# test_gui.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:      4 July 2019
# Copyright (c) 2019, Toke Høiland-Jørgensen
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

import unittest
import os

from flent.settings import parser, Settings, DEFAULT_SETTINGS
settings = parser.parse_args(args=[], namespace=Settings(DEFAULT_SETTINGS))


class TestGui(unittest.TestCase):

    def setUp(self):
        self.settings = settings.copy()

        try:
            from qtpy import QtCore
        except ImportError:
            self.skipTest("No usable Qt module found")

    def test_start_gui(self):
        from flent import gui
        gui.run_gui(self.settings, test_mode=True)


test_suite = unittest.TestSuite(
    [unittest.TestLoader().loadTestsFromTestCase(TestGui)])
