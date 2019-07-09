# -*- coding: utf-8 -*-
#
# test_formatters.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:      9 July 2019
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

import os
import shutil
import tempfile
import unittest
import traceback

from unittest.util import strclass

from .test_helpers import get_test_data_files

from flent import resultset, formatters, combiners
from flent.settings import parser, Settings, DEFAULT_SETTINGS
settings = parser.parse_args(args=[], namespace=Settings(DEFAULT_SETTINGS))

TEST_FORMATTERS = ['table', 'org_table', 'csv', 'summary', 'metadata']
if combiners.HAS_NUMPY:
    TEST_FORMATTERS.append('stats')


class TestFormatters(unittest.TestCase):

    def __init__(self, filename):
        self.filename = filename
        unittest.TestCase.__init__(self)

    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.settings = settings.copy()

    def tearDown(self):
        shutil.rmtree(self.output_dir)

    def __str__(self):
        return "format %s (%s)" % (os.path.basename(self.filename),
                                   strclass(self.__class__))

    def runTest(self):
        r = resultset.load(self.filename)
        self.settings.update(r.meta())
        self.settings.load_test(informational=True)
        self.settings.compute_missing_results(r)
        self.settings.FORMAT = 'metadata'

        for f in TEST_FORMATTERS:
            try:
                self.settings.FORMAT = f
                self.settings.OUTPUT = os.path.join(
                    self.output_dir, "%s.txt" % f)
                formatter = formatters.new(self.settings)
                formatter.format([r])
                res, _ = formatter.verify()
                if not res:
                    raise self.failureException(
                        "Verification of formatter '%s' failed" % f)
            except self.failureException:
                raise
            except Exception:
                tb = traceback.format_exc()
                new_exc = Exception("Error creating formatter '%s'" % f)
                new_exc.orig_tb = tb
                raise new_exc


test_suite = unittest.TestSuite()
for fname in get_test_data_files():
    test_suite.addTest(TestFormatters(fname))
