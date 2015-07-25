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

MATPLOTLIB_RC_VALUES = {
    'axes.axisbelow': True,
    'axes.color_cycle': ['#1b9e77', '#d95f02', '#7570b3', '#e7298a', '#66a61e', '#e6ab02', '#a6761d', '#666666'],
    'axes.edgecolor': 'white',
    'axes.facecolor': '#EAEAF2',
    'axes.grid': True,
    'axes.labelcolor': '.15',
    'axes.linewidth': 0,
    'figure.edgecolor': 'white',
    'figure.facecolor': 'white',
    'figure.frameon': False,
    'grid.color': 'white',
    'grid.linestyle': '-',
    'image.cmap': 'Greys',
    'legend.frameon': False,
    'legend.numpoints': 1,
    'legend.scatterpoints': 1,
    'lines.color': '.15',
    'lines.solid_capstyle': 'round',
    'pdf.fonttype': 42,
    'text.color': '.15',
    'xtick.color': '.15',
    'xtick.direction': 'out',
    'xtick.major.size': 0,
    'xtick.minor.size': 0,
    'ytick.color': '.15',
    'ytick.direction': 'out',
    'ytick.major.size': 0,
    'ytick.minor.size': 0,
}

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



class TestPlottersInit(unittest.TestCase):

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

    @prefork
    def test_init_styles(self):
        plotters.init_matplotlib('-', True, False)
        self.assertEqual(len(plotters.STYLES), len(plotters.LINESTYLES)+\
                         len(plotters.DASHES)+len(plotters.MARKERS))
        for ls in plotters.LINESTYLES:
            self.assertIn(dict(linestyle=ls), plotters.STYLES)
        for d in plotters.DASHES:
            self.assertIn(dict(dashes=d), plotters.STYLES)
        for m in plotters.MARKERS:
            self.assertIn(dict(marker=m, markevery=10), plotters.STYLES)

        self.assertEqual(plotters.matplotlib.rcParams['axes.color_cycle'],
                         plotters.COLOURS)

    @prefork
    def test_init_styles_nomarkers(self):
        plotters.init_matplotlib('-', False, False)
        self.assertEqual(len(plotters.STYLES), len(plotters.LINESTYLES)+\
                         len(plotters.DASHES))
        for ls in plotters.LINESTYLES:
            self.assertIn(dict(linestyle=ls), plotters.STYLES)
        for d in plotters.DASHES:
            self.assertIn(dict(dashes=d), plotters.STYLES)

    @prefork
    def test_init_rcfile(self):
        with mock.patch.object(plotters.matplotlib, 'matplotlib_fname') as mock_obj:
            mock_obj.return_value = ''
            if 'MATPLOTLIBRC' in os.environ:
                del os.environ['MATPLOTLIBRC']

            plotters.init_matplotlib('-', False, True)
            for k,v in MATPLOTLIB_RC_VALUES.items():
                self.assertEqual(v, plotters.matplotlib.rcParams[k],
                                 msg='rc param mismatch on %s' %k)
        self.assertEqual(plotters.matplotlib.rcParams['axes.color_cycle'],
                         plotters.COLOURS)

@unittest.skipUnless(plotters.HAS_MATPLOTLIB, 'no matplotlib available')
class TestPlotters(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        plotters.init_matplotlib('-', True, True)

    def setUp(self):
        self.plot_config = {'series': [{'data': 'Test 1'}]}
        self.data_config = {'Test 1': {'units': 'ms'}}

    def create_plotter(self, plotter_class):
        p = plotter_class(self.plot_config, self.data_config)
        p.init()
        self.assertIsInstance(p, plotter_class)

    def test_create_timeseries(self):
        self.create_plotter(plotters.TimeseriesPlotter)

    def test_create_timeseries_combine(self):
        self.create_plotter(plotters.TimeseriesCombinePlotter)

    def test_create_box(self):
        self.create_plotter(plotters.BoxPlotter)

    def test_create_box_combine(self):
        self.create_plotter(plotters.BoxCombinePlotter)

    def test_create_bar(self):
        self.create_plotter(plotters.BarPlotter)

    def test_create_bar_combine(self):
        self.create_plotter(plotters.BarCombinePlotter)

    def test_create_cdf(self):
        self.create_plotter(plotters.CdfPlotter)

    def test_create_cdf_combine(self):
        self.create_plotter(plotters.CdfCombinePlotter)

    def test_create_qq(self):
        # QQ plots only work with only 1 data series
        p = plotters.QqPlotter(self.plot_config, self.data_config)
        p.init()
        self.assertIsInstance(p, plotters.QqPlotter)
        self.plot_config['series'].append({'data': 'Test 1'})

        p = plotters.QqPlotter(self.plot_config, self.data_config)
        self.assertRaises(RuntimeError, p.init)

    def test_create_ellipsis(self):
        # Ellipsis plots only work with >=2 data series
        p = plotters.EllipsisPlotter(self.plot_config, self.data_config)
        self.assertRaises(RuntimeError, p.init)

        self.plot_config['series'].append({'data': 'Test 1'})
        p = plotters.EllipsisPlotter(self.plot_config, self.data_config)
        p.init()
        self.assertIsInstance(p, plotters.EllipsisPlotter)

    def test_create_subplot_combine(self):
        self.create_plotter(plotters.SubplotCombinePlotter)

test_suite = unittest.TestSuite([unittest.TestLoader().loadTestsFromTestCase(TestPlottersInit),
                                 unittest.TestLoader().loadTestsFromTestCase(TestPlotters)])
