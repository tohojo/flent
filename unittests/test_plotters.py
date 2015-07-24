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
    import cPickle as pickle
except ImportError:
    import pickle

try:
    from unittest import mock
except ImportError:
    try:
        import mock
    except ImportError:
        raise RuntimeError("Needs 'mock' library for these tests.")

from flent import plotters

def prefork(method):
    def new_method(*args, **kwargs):
        pipe_r, pipe_w = os.pipe()
        pid = os.fork()
        if pid:
            os.close(pipe_w)
            os.waitpid(pid, 0)
            res = pickle.loads(os.read(pipe_r, 65535))
            if isinstance(res, Exception):
                raise res
            return res
        else:
            os.close(pipe_r)
            try:
                res = method(*args, **kwargs)
                os.write(pipe_w, pickle.dumps(res))
            except Exception as e:
                os.write(pipe_w, pickle.dumps(e))
            finally:
                os._exit(0)
    return new_method



class TestPlotters(unittest.TestCase):

    def init_test_backend(self, filename):
        plotters.init_matplotlib(filename, False, False)
        return plotters.matplotlib.get_backend()

    def setUp(self):
        if not plotters.HAS_MATPLOTLIB:
            self.skipTest('no matplotlib available')


    @mock.patch.object(plotters, 'HAS_MATPLOTLIB', False)
    def test_init_fail(self):
        self.assertRaises(RuntimeError, plotters.init_matplotlib, None, None, None)

    @prefork
    def test_init_svg(self):
        self.assertEqual(self.init_test_backend('test.svg'), 'svg')

    @prefork
    def test_init_svgz(self):
        self.assertEqual(self.init_test_backend('test.svgz'), 'svg')

    @prefork
    def test_init_ps(self):
        self.assertEqual(self.init_test_backend('test.ps'), 'ps')

    @prefork
    def test_init_eps(self):
        self.assertEqual(self.init_test_backend('test.eps'), 'ps')

    @prefork
    def test_init_pdf(self):
        self.assertEqual(self.init_test_backend('test.pdf'), 'pdf')

    @prefork
    def test_init_png(self):
        self.assertEqual(self.init_test_backend('test.png'), 'agg')


test_suite = unittest.TestLoader().loadTestsFromTestCase(TestPlotters)
