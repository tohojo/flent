## -*- coding: utf-8 -*-
##
## test_plotters.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     24 July 2015
## Copyright (c) 2015, Toke Høiland-Jørgensen
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

from __future__ import absolute_import, division, print_function, unicode_literals

import unittest
import os
import sys

try:
    from unittest import mock
except ImportError:
    try:
        import mock
    except ImportError:
        raise RuntimeError("Needs 'mock' library for these tests.")

from flent import plotters

class TestPlotters(unittest.TestCase):

    @mock.patch.object(plotters, 'HAS_MATPLOTLIB', False)
    def test_init_fail(self):
        self.assertRaises(RuntimeError, plotters.init_matplotlib, None, None, None)

    @unittest.skipIf(not plotters.HAS_MATPLOTLIB, 'no matplotlib available')
    def test_init_success(self):
        pass



test_suite = unittest.TestLoader().loadTestsFromTestCase(TestPlotters)
