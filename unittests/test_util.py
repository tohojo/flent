# -*- coding: utf-8 -*-
#
# test_utils.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     16 July 2015
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

import unittest

from flent import util


class TestSmallUtilFunctions(unittest.TestCase):

    def test_uscore_to_camel(self):
        self.assertEqual(util.uscore_to_camel('test_name'), 'TestName')

    def test_classname(self):
        self.assertEqual(util.classname('test_class'), 'TestClass')

        self.assertEqual(util.classname(
            'test_class', 'Suffix'), 'TestClassSuffix')


test_suite = unittest.TestLoader().loadTestsFromTestCase(TestSmallUtilFunctions)
