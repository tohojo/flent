# -*- coding: utf-8 -*-
#
# test_plotters.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     24 July 2015
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
import shutil
import tempfile
import unittest
import traceback

from multiprocessing import Pool
from unittest.util import strclass

from .test_helpers import prefork, get_test_data_files

try:
    from unittest import mock
except ImportError:
    try:
        import mock
    except ImportError:
        raise RuntimeError("Needs 'mock' library for these tests.")

from flent import plotters, resultset, formatters
from flent.settings import parser, Settings, DEFAULT_SETTINGS
settings = parser.parse_args(args=[], namespace=Settings(DEFAULT_SETTINGS))

MATPLOTLIB_RC_VALUES = {
    'axes.axisbelow': True,
    'axes.color_cycle': ['#1b9e77', '#d95f02', '#7570b3', '#e7298a',
                         '#66a61e', '#e6ab02', '#a6761d', '#666666'],
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

# Plots that may fail validation
PLOTS_MAY_FAIL = set(('tcp_cwnd', 'tcp_rtt', 'tcp_rtt_cdf',
                      'tcp_rtt_box_combine', 'tcp_rtt_bar_combine', 'tcp_pacing',
                      'all_scaled_delivery', 'tcp_delivery_rate', 'tcp_delivery_with_rtt'))


class TestPlottersInit(unittest.TestCase):

    def init_test_backend(self, filename):
        plotters.init_matplotlib(filename, False, False)
        return plotters.matplotlib.get_backend()

    def setUp(self):
        if not plotters.HAS_MATPLOTLIB:
            self.skipTest('no matplotlib available')

    @mock.patch.object(plotters, 'HAS_MATPLOTLIB', False)
    def test_init_fail(self):
        self.assertRaises(
            RuntimeError, plotters.init_matplotlib, None, None, None)

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
        plotters.init_matplotlib('test.svg', True, False)
        self.assertEqual(len(plotters.STYLES), len(plotters.LINESTYLES) +
                         len(plotters.DASHES) + len(plotters.MARKERS))
        for ls in plotters.LINESTYLES:
            self.assertIn(dict(linestyle=ls), plotters.STYLES)
        for d in plotters.DASHES:
            self.assertIn(dict(dashes=d), plotters.STYLES)
        for m in plotters.MARKERS:
            self.assertIn(dict(marker=m, markevery=10), plotters.STYLES)

    @prefork
    def test_init_styles_nomarkers(self):
        plotters.init_matplotlib('test.svg', False, False)
        self.assertEqual(len(plotters.STYLES), len(plotters.LINESTYLES) +
                         len(plotters.DASHES))
        for ls in plotters.LINESTYLES:
            self.assertIn(dict(linestyle=ls), plotters.STYLES)
        for d in plotters.DASHES:
            self.assertIn(dict(dashes=d), plotters.STYLES)


@unittest.skipUnless(plotters.HAS_MATPLOTLIB, 'no matplotlib available')
class TestPlotters(unittest.TestCase):

    def setUp(self):
        self.plot_config = {'series': [{'data': 'Test 1'}]}
        self.data_config = {'Test 1': {'units': 'ms'}}

    def create_plotter(self, plotter_class):
        p = plotter_class(self.plot_config, self.data_config)
        p.init()
        self.assertIsInstance(p, plotter_class)

    @prefork
    def test_create_timeseries(self):
        plotters.init_matplotlib('test.svg', True, True)
        self.create_plotter(plotters.TimeseriesPlotter)

    @prefork
    def test_create_timeseries_combine(self):
        plotters.init_matplotlib('test.svg', True, True)
        self.create_plotter(plotters.TimeseriesCombinePlotter)

    @prefork
    def test_create_box(self):
        plotters.init_matplotlib('test.svg', True, True)
        self.create_plotter(plotters.BoxPlotter)

    @prefork
    def test_create_box_combine(self):
        plotters.init_matplotlib('test.svg', True, True)
        self.create_plotter(plotters.BoxCombinePlotter)

    @prefork
    def test_create_bar(self):
        plotters.init_matplotlib('test.svg', True, True)
        self.create_plotter(plotters.BarPlotter)

    @prefork
    def test_create_bar_combine(self):
        plotters.init_matplotlib('test.svg', True, True)
        self.create_plotter(plotters.BarCombinePlotter)

    @prefork
    def test_create_cdf(self):
        plotters.init_matplotlib('test.svg', True, True)
        self.create_plotter(plotters.CdfPlotter)

    @prefork
    def test_create_cdf_combine(self):
        plotters.init_matplotlib('test.svg', True, True)
        self.create_plotter(plotters.CdfCombinePlotter)

    @prefork
    def test_create_qq(self):
        plotters.init_matplotlib('test.svg', True, True)
        # QQ plots only work with only 1 data series
        p = plotters.QqPlotter(self.plot_config, self.data_config)
        p.init()
        self.assertIsInstance(p, plotters.QqPlotter)
        self.plot_config['series'].append({'data': 'Test 1'})

        p = plotters.QqPlotter(self.plot_config, self.data_config)
        self.assertRaises(RuntimeError, p.init)

    @prefork
    def test_create_ellipsis(self):
        plotters.init_matplotlib('test.svg', True, True)
        # Ellipsis plots only work with >=2 data series
        p = plotters.EllipsisPlotter(self.plot_config, self.data_config)
        self.assertRaises(RuntimeError, p.init)

        self.plot_config['series'].append({'data': 'Test 1'})
        p = plotters.EllipsisPlotter(self.plot_config, self.data_config)
        p.init()
        self.assertIsInstance(p, plotters.EllipsisPlotter)

    @prefork
    def test_create_subplot_combine(self):
        plotters.init_matplotlib('test.svg', True, True)
        self.create_plotter(plotters.SubplotCombinePlotter)


class TestPlotting(unittest.TestCase):

    def __init__(self, filename, fmt):
        self.filename = filename
        self.fmt = fmt
        unittest.TestCase.__init__(self)

    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.settings = settings.copy()

    def tearDown(self):
        shutil.rmtree(self.output_dir)

    def __str__(self):
        return "%s - %s (%s)" % (os.path.basename(self.filename), self.fmt,
                                 strclass(self.__class__))

    @prefork
    def runTest(self):
        r = resultset.load(self.filename)
        self.settings.update(r.meta())
        self.settings.load_test(informational=True)
        self.settings.compute_missing_results(r)
        self.settings.FORMAT = 'plot'

        for p in self.settings.PLOTS.keys():
            try:
                self.settings.PLOT = p
                self.settings.OUTPUT = os.path.join(
                    self.output_dir, "%s.%s" % (p, self.fmt))
                formatter = formatters.new(self.settings)
                formatter.format([r])
                res, plen = formatter.verify()
                if not res and p not in PLOTS_MAY_FAIL:
                    raise self.failureException(
                        "Verification of plot '%s' failed: %s" % (p, plen))
            except self.failureException:
                raise
            except Exception as e:
                tb = traceback.format_exc()
                new_exc = Exception("Error creating plot '%s'" % p)
                new_exc.orig_tb = tb
                raise new_exc


def initfunc():
    plotters.init_matplotlib("-", False, True)


def plot_one(settings, plot, results):
    settings.PLOT = plot
    return plotters.draw_worker(settings, [results])


@unittest.skipUnless(plotters.HAS_MATPLOTLIB, 'no matplotlib available')
class TestGUIPlotting(unittest.TestCase):

    def __init__(self, filename):
        self.filename = filename
        unittest.TestCase.__init__(self)

    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.settings = settings.copy()

    def tearDown(self):
        shutil.rmtree(self.output_dir)

    def __str__(self):
        return "%s - GUI (%s)" % (os.path.basename(self.filename),
                                  strclass(self.__class__))

    @prefork
    def runTest(self):
        pool = Pool(initializer=initfunc)
        results = resultset.load(self.filename)
        self.settings.update(results.meta())
        self.settings.load_test(informational=True)
        plotters.init_matplotlib("-", False, True)
        for p in self.settings.PLOTS.keys():
            plot = pool.apply(plot_one, (self.settings, p, results))
            res, plen = plot.verify()
            if not res and p not in PLOTS_MAY_FAIL:
                raise self.failureException(
                    "Verification of plot '%s' failed: %s" % (p, plen))


dirname = os.path.join(os.path.dirname(__file__), "test_data")
output_formats = ['svg', 'pdf', 'png']
plot_suite = unittest.TestSuite()
for fname in get_test_data_files():
    plot_suite.addTest(TestGUIPlotting(fname))
    for fmt in output_formats:
        plot_suite.addTest(TestPlotting(fname, fmt))


test_suite = unittest.TestSuite(
    [unittest.TestLoader().loadTestsFromTestCase(TestPlottersInit),
     unittest.TestLoader().loadTestsFromTestCase(TestPlotters)])
