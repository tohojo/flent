## -*- coding: utf-8 -*-
##
## __init__.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     16 July 2015
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
from . import test_util
from . import test_metadata
from . import test_plotters
from . import test_tests

test_suite = unittest.TestSuite([test_util.test_suite,
                                 test_metadata.test_suite,
                                 test_tests.test_suite,
                                 test_plotters.test_suite,
])

all_tests = unittest.TestSuite([test_suite, test_plotters.plot_suite])
