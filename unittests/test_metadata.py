# -*- coding: utf-8 -*-
#
# test_metadata.py
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
import os

from flent import metadata
from flent import util


class TestMetadataFunctions(unittest.TestCase):

    def setUp(self):
        sysctl = util.which("sysctl")
        if sysctl is None:
            self.skipTest("Could not find sysctl utility")

    def test_get_sysctls(self):
        sysctls = metadata.get_sysctls()

        for sysctl in metadata.INTERESTING_SYSCTLS:
            sysctl_path = os.path.join('/proc/sys', *sysctl.split('.'))
            if os.path.exists(sysctl_path):
                self.assertIn(sysctl, sysctls)
                with open(sysctl_path, 'r') as fp:
                    sysctl_value = fp.read().strip()
                    try:
                        sysctl_value = int(sysctl_value)
                    except ValueError:
                        pass
                self.assertEqual(sysctl_value, sysctls[sysctl])


test_suite = unittest.TestLoader().loadTestsFromTestCase(TestMetadataFunctions)
