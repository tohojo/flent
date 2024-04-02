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

from .test_helpers import ForkingTestCase, get_test_data_files

from flent import resultset, formatters
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

# Some flent test files intentionally lack plots. This list contains the empty
# plots to ensure that they do not fail. The lack of data is either because the
# test did not run with the required flag or because the file is simply older
# than the feature.
MISSING_PLOTS = {
    'test-http-1up.flent.gz': set((
        'tcp_cwnd',
        'tcp_delivery_rate',
        'tcp_pacing',
        'tcp_rtt',
        'tcp_rtt_bar_combine',
        'tcp_rtt_box_combine',
        'tcp_rtt_cdf',
    )),
    'test-http.flent.gz': set((
        'tcp_cwnd',
        'tcp_delivery_rate',
        'tcp_pacing',
        'tcp_rtt',
        'tcp_rtt_bar_combine',
        'tcp_rtt_box_combine',
        'tcp_rtt_cdf',
    )),
    'test-rrul-icmp.flent.gz': set((
        'tcp_cwnd',
        'tcp_delivery_rate',
        'tcp_pacing',
        'tcp_rtt',
        'tcp_rtt_bar_combine',
        'tcp_rtt_box_combine',
        'tcp_rtt_cdf',
    )),
    'test-rrul.flent.gz': set((
        'cpu_core',
        'cpu_core_bar',
        'cpu_core_box',
        'tcp_delivery_rate',
        'tcp_pacing',
        'tcp_rtt_bar_combine',
        'tcp_rtt_box_combine',
        'tcp_rtt_cdf',
    )),
    'test-rrul_be-socket_stats.flent.gz': set((
        'tcp_rtt_bar_combine',
        'tcp_rtt_box_combine',
        'tcp_rtt_cdf',
    )),
    'test-rtt-fair.flent.gz': set((
        'tcp_cwnd',
        'tcp_delivery_rate',
        'tcp_pacing',
        'tcp_rtt',
        'tcp_rtt_bar_combine',
        'tcp_rtt_box_combine',
        'tcp_rtt_cdf',
    )),
    'test-tcp_nup.flent.gz': set((
        'tcp_delivery_rate',
        'tcp_pacing',
        'tcp_rtt_bar_combine',
        'tcp_rtt_box_combine',
        'tcp_rtt_cdf',
    )),
    'test-tcp_1up_noping-cpu_stats.flent.gz': set((
        'tcp_cwnd',
        'tcp_pacing',
        'tcp_rtt',
        'tcp_rtt_cdf',
        'tcp_rtt_box_combine',
        'tcp_rtt_bar_combine',
    )),
    'test-voip-1up.flent.gz': set((
        'tcp_cwnd',
        'tcp_delivery_rate',
        'tcp_pacing',
        'tcp_rtt',
        'tcp_rtt_bar_combine',
        'tcp_rtt_box_combine',
        'tcp_rtt_cdf',
    )),
    'test-voip-rrul.flent.gz': set((
        'tcp_cwnd',
        'tcp_delivery_rate',
        'tcp_pacing',
        'tcp_rtt',
        'tcp_rtt_bar_combine',
        'tcp_rtt_box_combine',
        'tcp_rtt_cdf',
    )),
}


class PlottersTestCase(ForkingTestCase):

    def setUp(self):
        from flent import plotters
        if not plotters.HAS_MATPLOTLIB:
            self.skipTest('no matplotlib available')
        self.plotters = plotters

    def __getstate__(self):
        state = {}

        for k, v in self.__dict__.items():
            if k != 'plotters':
                state[k] = v

        return state


class TestPlottersInit(PlottersTestCase):

    def init_test_backend(self, filename):
        self.plotters.init_matplotlib(filename, False, False)
        return self.plotters.matplotlib.get_backend()

    def test_init_fail(self):
        self.plotters.HAS_MATPLOTLIB = False
        self.assertRaises(
            RuntimeError, self.plotters.init_matplotlib, None, None, None)

    def test_init_svg(self):
        self.assertEqual(self.init_test_backend('test.svg'), 'svg')

    def test_init_svgz(self):
        self.assertEqual(self.init_test_backend('test.svgz'), 'svg')

    def test_init_ps(self):
        self.assertEqual(self.init_test_backend('test.ps'), 'ps')

    def test_init_eps(self):
        self.assertEqual(self.init_test_backend('test.eps'), 'ps')

    def test_init_pdf(self):
        self.assertEqual(self.init_test_backend('test.pdf'), 'pdf')

    def test_init_png(self):
        self.assertEqual(self.init_test_backend('test.png'), 'agg')

    def test_init_styles(self):
        self.plotters.init_matplotlib('test.svg', True, False)
        self.assertEqual(len(self.plotters.STYLES), len(self.plotters.LINESTYLES) +
                         len(self.plotters.DASHES) + len(self.plotters.MARKERS))
        for ls in self.plotters.LINESTYLES:
            self.assertIn(dict(linestyle=ls), self.plotters.STYLES)
        for d in self.plotters.DASHES:
            self.assertIn(dict(dashes=d), self.plotters.STYLES)
        for m in self.plotters.MARKERS:
            self.assertIn(dict(marker=m, markevery=10), self.plotters.STYLES)

    def test_init_styles_nomarkers(self):
        self.plotters.init_matplotlib('test.svg', False, False)
        self.assertEqual(len(self.plotters.STYLES), len(self.plotters.LINESTYLES) +
                         len(self.plotters.DASHES))
        for ls in self.plotters.LINESTYLES:
            self.assertIn(dict(linestyle=ls), self.plotters.STYLES)
        for d in self.plotters.DASHES:
            self.assertIn(dict(dashes=d), self.plotters.STYLES)


class TestPlotters(PlottersTestCase):

    def setUp(self):
        super().setUp()
        self.plot_config = {'series': [{'data': 'Test 1'}]}
        self.data_config = {'Test 1': {'units': 'ms'}}
        self.plotters.init_matplotlib('test.svg', True, True)

    def create_plotter(self, plotter_class_name, init=True):
        plotter_class = getattr(self.plotters, plotter_class_name)
        p = plotter_class(self.plot_config, self.data_config)
        self.assertIsInstance(p, plotter_class)
        if init:
            p.init()
        return p

    def test_create_timeseries(self):
        self.create_plotter("TimeseriesPlotter")

    def test_create_timeseries_combine(self):
        self.create_plotter("TimeseriesCombinePlotter")

    def test_create_box(self):
        self.create_plotter("BoxPlotter")

    def test_create_box_combine(self):
        self.create_plotter("BoxCombinePlotter")

    def test_create_bar(self):
        self.create_plotter("BarPlotter")

    def test_create_bar_combine(self):
        self.create_plotter("BarCombinePlotter")

    def test_create_cdf(self):
        self.create_plotter("CdfPlotter")

    def test_create_cdf_combine(self):
        self.create_plotter("CdfCombinePlotter")

    def test_create_qq(self):
        # QQ plots only work with only 1 data series
        p = self.create_plotter("QqPlotter")
        self.plot_config['series'].append({'data': 'Test 1'})

        p = self.create_plotter("QqPlotter", init=False)
        self.assertRaises(RuntimeError, p.init)

    def test_create_ellipsis(self):
        # Ellipsis plots only work with >=2 data series
        p = self.create_plotter("EllipsisPlotter", init=False)
        self.assertRaises(RuntimeError, p.init)

        self.plot_config['series'].append({'data': 'Test 1'})
        p = self.create_plotter("EllipsisPlotter")

    def test_create_subplot_combine(self):
        self.create_plotter("SubplotCombinePlotter")


class TestPlotting(PlottersTestCase):

    def __init__(self, filename, fmt):
        self.filename = filename
        self.fmt = fmt
        unittest.TestCase.__init__(self)

    def setUp(self):
        super().setUp()
        self.output_dir = tempfile.mkdtemp()
        self.settings = settings.copy()

    def tearDown(self):
        shutil.rmtree(self.output_dir)

    def __str__(self):
        return "%s - %s (%s)" % (os.path.basename(self.filename), self.fmt,
                                 strclass(self.__class__))

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
                filename = os.path.basename(self.filename)
                if filename in MISSING_PLOTS and p in MISSING_PLOTS[filename]:
                    continue

                if not res:
                    raise self.failureException(
                        "Verification of plot '%s' failed: %s" % (p, plen))
            except self.failureException:
                raise
            except Exception as e:
                tb = traceback.format_exc()
                new_exc = Exception("Error creating plot '%s'" % p)
                new_exc.orig_tb = tb
                raise new_exc

def plot_one(settings, plot, results):
    from flent import plotters
    plotters.init_matplotlib("-", False, True)
    settings.PLOT = plot
    return plotters.draw_worker(settings, [results])

class TestGUIPlotting(PlottersTestCase):

    def __init__(self, filename):
        self.filename = filename
        unittest.TestCase.__init__(self)

    def setUp(self):
        super().setUp()
        self.output_dir = tempfile.mkdtemp()
        self.settings = settings.copy()

    def tearDown(self):
        shutil.rmtree(self.output_dir)

    def __str__(self):
        return "%s - GUI (%s)" % (os.path.basename(self.filename),
                                  strclass(self.__class__))

    def runTest(self):
        results = resultset.load(self.filename)
        self.settings.update(results.meta())
        self.settings.load_test(informational=True)

        with Pool() as pool:
            for p in self.settings.PLOTS.keys():
                plot = pool.apply(plot_one, (self.settings, p, results))
                res, plen = plot.verify()

                filename = os.path.basename(self.filename)
                if filename in MISSING_PLOTS and p in MISSING_PLOTS[filename]:
                    continue

                if not res:
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
