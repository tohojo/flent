# -*- coding: utf-8 -*-
#
# plotters.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:      4 March 2015
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

import io
import math
import os
import re
import warnings

from flent import combiners
from flent.util import classname, long_substr, format_date, diff_parts, \
    Glob, Update, float_pair, float_pair_noomit, keyval, comma_list, ArgParam, \
    ArgParser
from flent.build_info import VERSION
from flent.loggers import get_logger

from argparse import SUPPRESS
from functools import reduce
from itertools import cycle, islice, chain
from collections import OrderedDict
from distutils.version import LooseVersion

logger = get_logger(__name__)

try:
    import matplotlib
    import numpy as np
    HAS_MATPLOTLIB = True
    MPL_VER = LooseVersion(matplotlib.__version__)
    if MPL_VER < LooseVersion("1.5"):
        logger.warning("Cannot use old matplotlib version %s, please upgrade!",
                       matplotlib.__version__)
        raise ImportError("Matplotlib %s too old" % matplotlib.__version__)
except ImportError as e:
    logger.debug("Unable to import matplotlib: %s", e)
    HAS_MATPLOTLIB = False
    MPL_VER = LooseVersion("0")

PLOT_KWARGS = (
    'alpha',
    'antialiased',
    'color',
    'dash_capstyle',
    'dash_joinstyle',
    'drawstyle',
    'fillstyle',
    'label',
    'linestyle',
    'linewidth',
    'lod',
    'marker',
    'markeredgecolor',
    'markeredgewidth',
    'markerfacecolor',
    'markerfacecoloralt',
    'markersize',
    'markevery',
    'pickradius',
    'solid_capstyle',
    'solid_joinstyle',
    'visible',
    'zorder'
)

LINESTYLES = ['-', '--']
MARKERS = ['o', '^', 's', 'v', 'D', '*', '<', '>', 'x', '+']
COLOURS = ["#1b9e77", "#d95f02", "#7570b3", "#e7298a",
           "#66a61e", "#e6ab02", "#a6761d", "#666666"]
DASHES = [[2, 4],
          [8, 4, 2, 4],
          ]
STYLES = []

MATPLOTLIB_STYLES = {'axes.axisbelow': True,
                     'axes.edgecolor': 'white',
                     'axes.facecolor': '#E6E6E6',
                     'axes.formatter.useoffset': False,
                     'axes.grid': True,
                     'axes.labelcolor': 'black',
                     'axes.linewidth': 0.0,
                     'figure.edgecolor': 'white',
                     'figure.facecolor': 'white',
                     'figure.frameon': False,
                     'grid.color': 'white',
                     'grid.linestyle': '-',
                     'grid.linewidth': 1,
                     'image.cmap': 'Greys',
                     'legend.frameon': False,
                     'legend.numpoints': 1,
                     'legend.scatterpoints': 1,
                     'lines.color': 'black',
                     'lines.linewidth': 1,
                     'lines.solid_capstyle': 'round',
                     'pdf.fonttype': 42,
                     'text.color': 'black',
                     'xtick.color': 'black',
                     'xtick.direction': 'out',
                     'xtick.major.size': 0.0,
                     'xtick.minor.size': 0.0,
                     'ytick.color': 'black',
                     'ytick.direction': 'out',
                     'ytick.major.size': 0.0,
                     'ytick.minor.size': 0.0}

MATPLOTLIB_INIT = False


def init_matplotlib(output, use_markers, load_rc):
    if not HAS_MATPLOTLIB:
        raise RuntimeError(
            "Unable to plot -- matplotlib is missing! "
            "Please install it if you want plots.")
    global pyplot, COLOURS, MATPLOTLIB_INIT

    if MATPLOTLIB_INIT:
        return

    # Old versions of matplotlib will trigger this
    warnings.filterwarnings('ignore', message="elementwise == comparison failed")

    if output != "-":
        if output.endswith('.svg') or output.endswith('.svgz'):
            matplotlib.use('svg')
        elif output.endswith('.ps') or output.endswith('.eps'):
            matplotlib.use('ps')
        elif output.endswith('.pdf'):
            matplotlib.use('pdf')
        elif output.endswith('.png'):
            matplotlib.use('agg')
        else:
            raise RuntimeError(
                "Unrecognised file format for output '%s'" % output)

    elif not os.getenv("DISPLAY"):
        matplotlib.use("agg")

    from matplotlib import pyplot

    for ls in LINESTYLES:
        STYLES.append(dict(linestyle=ls))
    for d in DASHES:
        STYLES.append(dict(dashes=d))
    if use_markers:
        for m in MARKERS:
            STYLES.append(dict(marker=m, markevery=10))

    # Try to detect if a custom matplotlibrc is installed, and if so don't
    # load our own values.
    try:
        matplotlib.rcParams['figure.max_open_warning'] = 0
    except KeyError:
        pass
    if load_rc:
        matplotlib.rcParams.update(MATPLOTLIB_STYLES)
    elif 'axes.prop_cycle' in matplotlib.rcParams:
        c = matplotlib.rcParams['axes.prop_cycle']
        if 'color' in c.keys and hasattr(c, 'by_key'):
            COLOURS = c.by_key()['color']
    else:
        COLOURS = matplotlib.rcParams['axes.color_cycle']

    MATPLOTLIB_INIT = True
    logger.info("Initialised matplotlib v%s on numpy v%s.",
                matplotlib.__version__, np.__version__)


def get_plotconfig(settings, plot=None):
    if plot is None:
        plot = settings.PLOT
    if plot not in settings.PLOTS:
        raise RuntimeError("Unable to find plot configuration '%s'" % plot)
    config = settings.PLOTS[plot].copy()
    config['plot_name'] = plot
    if 'parent' in config:
        parent_config = settings.PLOTS[config['parent']].copy()
        parent_config.update(config)
        config = parent_config

    if 'subplots' in config:
        subplots = OrderedDict()
        for s in config['subplots']:
            cfg = settings.PLOTS[s].copy()
            if 'parent' in cfg:
                parent = settings.PLOTS[cfg['parent']].copy()
                parent.update(cfg)
                cfg = parent
            subplots[s] = cfg
        config['subplots'] = subplots
    return config


def get_plotter(plot_type):
    cname = classname(plot_type, "Plotter")
    if cname not in globals():
        raise RuntimeError("Plotter not found: '%s'" % plot_type)
    return globals()[cname]


def add_plotting_args(parser):
    # Convenience helper functions to modify actions after they are defined.
    # Prevents us from having to assign the return value of the add_argument
    # calls below and modify it afterwards.
    def hide_gui(a):
        "Prevents action from being shown in the GUI option editor."
        a.hide_gui = True
        return a

    def gui_help(a, gui_help):
        "Adds a second help text that takes precedence in the GUI editor."
        a.gui_help = gui_help
        return a

    parser.add_argument(
        "--label-x",
        action="append", dest="LABEL_X", type=str, default=[],
        help="Override X axis labels. "
        "Can be specified twice, corresponding to figures with multiple axes.")

    parser.add_argument(
        "--label-y",
        action="append", dest="LABEL_Y", type=str, default=[],
        help="Override Y axis labels. "
        "Can be specified twice, corresponding to figures with multiple axes.")

    parser.add_argument(
        "-I", "--invert-latency-y",
        action="store_true", dest="INVERT_Y",
        help="Invert latency data axis. This inverts the latency data axis "
        "(typically the Y axis), which makes plots show 'better' values upwards.")

    parser.add_argument(
        "-z", "--zero-y",
        action="store_true", dest="ZERO_Y",
        help="Zero Y axis. Always start y axis of plot at zero, instead of "
        "auto-scaling the axis. Auto-scaling is still enabled for the "
        "upper bound. This also disables log scale.")

    # --log-scale is old boolean option, kept for compatibility
    parser.add_argument("--log-scale", action="store_const", dest="LOG_SCALE",
                        const="log10", help=SUPPRESS)
    parser.add_argument(
        "--log-scale-y",
        action="store", type=str, dest="LOG_SCALE", choices=("log2", "log10"),
        help="Use logarithmic scale.")

    parser.add_argument(
        "--norm-factor",
        action="append", type=float, dest="NORM_FACTORS", metavar="FACTOR",
        default=[], help="Data normalisation factor. Divide all data "
        "points by this value. Can be specified multiple times, in which case "
        "each value corresponds to a data series.")

    parser.add_argument(
        "--data-cutoff",
        action="store", type=float_pair_noomit, dest="DATA_CUTOFF",
        help="Data cutoff interval. Cut off all data points outside this "
        "interval before plotting. For aggregate plots, this will happen "
        "*before* aggregation, so for instance mean values will be affected.")

    parser.add_argument(
        "--bounds-x",
        action="append", dest="BOUNDS_X", type=float_pair, default=[],
        help="X axis bounds. If specifying one number, "
        "that will become the upper bound. Specify two numbers separated by "
        "a comma to specify both upper and lower bounds. To specify just the "
        "lower bound, add a comma afterwards. Can be specified twice, "
        "corresponding to figures with multiple axes.")

    parser.add_argument(
        "--bounds-y",
        action="append", dest="BOUNDS_Y", type=float_pair, default=[],
        help="Y axis bounds. If specifying one number, "
        "that will become the upper bound. Specify two numbers separated by "
        "comma to specify both upper and lower bounds. To specify just the "
        "lower bound, add a comma afterwards. Can be specified twice, "
        "corresponding to figures with multiple axes.")

    parser.add_argument(
        "-S", "--scale-mode",
        action="store_true", dest="SCALE_MODE",
        help="Scale mode. If enabled, secondary data sets are not plotted, but "
        "are still taken into account when calculating axis bounds. Use this to "
        "plot several datasets with the same axis scales.")

    parser.add_argument(
        "--concatenate",
        action="store_true", dest="CONCATENATE",
        help="Concatenate datasets. Concatenates multiple result sets into a "
        "single data series.")

    parser.add_argument(
        "--absolute-time",
        action="store_true", dest="ABSOLUTE_TIME",
        help="Plot absolute times. Shows absolute Unix time on the x-axis instead"
        " of relative time from the test start.")

    parser.add_argument(
        "--subplot-combine",
        action="store_true", dest="SUBPLOT_COMBINE",
        help="Combine as subplots. When plotting multiple data series, plot "
        "each one on a separate "
        "subplot instead of combining them into one plot (not supported for all "
        "plot types).")

    parser.add_argument(
        "--skip-missing-series",
        action="store_true", dest="SKIP_MISSING",
        help="Skip missing on bar plots. If a series is missing, this option "
        "skips it entirely from bar plots instead of having an empty slot for "
        "it.")

    gui_help(parser.add_argument(
        "--no-print-n",
        action="store_false", dest="COMBINE_PRINT_N",
        help="No N values. Do not print the number of data points on "
        "combined plots."),
             gui_help="Print N values. Whether to print the number of data "
             "points used for combination plots.")

    gui_help(parser.add_argument(
        "--no-annotation",
        action="store_false", dest="ANNOTATE",
        help="Hide annotation. Exclude annotation with hostnames, time and test "
        "length from plots."),
             gui_help="Show annotation. Show annotation with hostnames, time "
             "and test length on plots.")

    parser.add_argument(
        "--figure-note", "--fig-note",
        action="store", type=str, dest="FIG_NOTE",
        help="Figure note. Will be added to the bottom-left corner of the "
        "figure.")

    gui_help(parser.add_argument(
        "--no-title",
        action="store_false", dest="PRINT_TITLE",
        help="Hide plot title."), gui_help="Show plot title.")

    parser.add_argument(
        "--override-title",
        action="store", type=str, dest="OVERRIDE_TITLE", metavar="TITLE",
        help="Override plot title. This parameter takes "
        "precedence over --no-title.")

    gui_help(parser.add_argument(
        "--no-labels",
        action="store_false", dest="PRINT_LABELS",
        help="Hide tick labels. Hides tick labels from box and bar plots."),
             gui_help="Show tick labels. Whether to show tick labels on "
             "box and bar plots.")

    gui_help(parser.add_argument(
        "--no-markers",
        action="store_false", dest="USE_MARKERS",
        help="No line markers. Don't use line markers to differentiate data "
        "series on plots."), gui_help="Use line markers. Whether to use line "
             "markers (in addition to line style) to differentiate data series "
             "on plots")

    gui_help(parser.add_argument(
        "--no-legend",
        action="store_false", dest="PRINT_LEGEND",
        help="Hide plot legend."), "Show plot legend.")

    parser.add_argument(
        "--horizontal-legend",
        action="store_true", dest="HORIZONTAL_LEGEND",
        help="Horizontal legend mode. Places a horizontal legend below the plot "
        "instead of a vertical one "
        "next to it. Doesn't work well if there are too many items in the "
        "legend.")

    parser.add_argument(
        "--legend-title",
        action="store", type=str, dest="LEGEND_TITLE",
        help="Override legend title.")

    parser.add_argument(
        "--legend-placement",
        action="store", type=str, dest="LEGEND_PLACEMENT",
        choices=('best',
                 'upper right',
                 'upper left',
                 'lower left',
                 'lower right',
                 'right',
                 'center left',
                 'center right',
                 'lower center',
                 'upper center',
                 'center'),
        help="Legend placement. Enabling this option will place the "
        "legend inside the plot at the specified location. Use 'best' to let "
        "matplotlib decide.")

    parser.add_argument(
        "--legend-columns",
        action="store", type=int, dest="LEGEND_COLUMNS", default=None,
        help="Legend columns. Set the number of columns in the legend.")

    parser.add_argument(
        "--reverse-legend",
        action="store_true", dest="LEGEND_REVERSE",
        help="Reverse legend order. Reverses the order of data series in "
        "the legend.")

    parser.add_argument(
        "--filter-legend",
        action="store_true", dest="FILTER_LEGEND",
        help="Auto-filter legend text. Filters labels by removing the longest "
        "common substring from all entries.")

    parser.add_argument(
        "--replace-legend",
        action=Update, type=keyval, dest="REPLACE_LEGEND", metavar="src=dest",
        default=OrderedDict(),
        help="Replace legend text. Replaces 'src' with 'dst' in legends. Can be "
        "specified multiple times.")

    parser.add_argument(
        "--filter-regexp",
        action="append", type=str, dest="FILTER_REGEXP", metavar="REGEXP",
        default=[], help="Filter labels (regex). Filter out supplied regular "
        "expression from label names. Can be specified multiple times, in which "
        "case the regular expressions will be filtered in the order specified.")

    parser.add_argument(
        "--override-label",
        action="append", type=str, dest="OVERRIDE_LABELS", metavar="LABEL",
        default=[],
        help="Override dataset labels. Must be specified multiple times "
        "corresponding to the datasets being overridden.")

    parser.add_argument(
        "--filter-series",
        action="append", type=str, dest="FILTER_SERIES", metavar="SERIES",
        default=[], help="Filter (hide) data series. Filters out specified "
        "series names from the plot. Can be specified multiple times.")

    parser.add_argument(
        "--split-group",
        action="append", type=str, dest="SPLIT_GROUPS", default=[],
        metavar="LABEL",
        help="New groups for box and bar plots. Specify this option multiple "
        "times to define the new groups that data sets should be split into on "
        "box and bar plots. The value of each option is the group name "
        "(displayed at the top of the plot).")

    parser.add_argument(
        "--colours",
        action="store", dest="COLOURS", type=comma_list, default=COLOURS,
        help="Override plot colours. Specify a comma-separated list of colours "
        "to be used for the plot colour cycle.")

    parser.add_argument(
        "--override-colour-mode",
        action="store", type=str, dest="OVERRIDE_COLOUR_MODE", metavar="MODE",
        help="Override colour_mode attribute. This changes the way colours "
        "are assigned to bar plots. The default is 'groups' which assigns a "
        "separate colour to each group of data series. The alternative is "
        "'series' which assigns a separate colour to each series, repeating them"
        "for each data group.")

    parser.add_argument(
        "--override-group-by",
        action="store", type=str, dest="OVERRIDE_GROUP_BY", metavar="GROUP",
        help="Override group_by attribute. This changes the way combination "
        "plots are created by overriding the function that is used to combine "
        "several data series into one.")

    hide_gui(parser.add_argument(
        "--combine-save-dir",
        action="store", type=str, dest="COMBINE_SAVE_DIR",
        metavar="DIRNAME",
        help="Save intermediate combination data. When doing a combination plot "
        "save the intermediate data to DIRNAME. This can then be used for "
        "subsequent plotting to avoid having to load all the source data files "
        "again on each plot."))

    hide_gui(parser.add_argument(
        "--figure-width", "--fig-width",
        action="store", type=float, dest="FIG_WIDTH", default=6.4,
        help="Figure width in inches. Used when saving plots to file and for "
        "default size of the interactive plot window."))

    hide_gui(parser.add_argument(
        "--figure-height", "--fig-height",
        action="store", type=float, dest="FIG_HEIGHT", default=4.8,
        help="Figure height in inches. Used when saving plots to file and for "
        "default size of the interactive plot window."))

    hide_gui(parser.add_argument(
        "--figure-dpi", "--fig-dpi",
        action="store", type=float, dest="FIG_DPI", default=100,
        help="Figure DPI. Used when saving plots to raster format files."))

    hide_gui(parser.add_argument(
        "--fallback-layout",
        action="store_true", dest="FALLBACK_LAYOUT",
        help="Use the fallback layout engine. Use the tight_layout engine built "
        "in to matplotlib for laying out figures. Enable this option if text is "
        "cut off on saved figures. The downside to the fallback engine is that "
        "the size of the figure (as specified by --figure-width and "
        "--figure-height) is no longer kept constant."))

    hide_gui(parser.add_argument(
        "--no-matplotlibrc",
        action="store_false", dest="LOAD_MATPLOTLIBRC",
        help="Don't use included matplotlib styles. Use this if you have "
        "configured custom matplotlib styles that you want Flent to use."))

    hide_gui(parser.add_argument(
        "--no-hover-highlight",
        action="store_false", dest="HOVER_HIGHLIGHT", default=None,
        help="Don't highlight on hover. This disables highlighting of hovered "
        "data series in interactive plot views. "
        "Use this if redrawing is too slow, or the highlighting is undesired "
        "for other reasons."))

    hide_gui(parser.add_argument(
        "--scale-data",
        action="append", type=str, dest="SCALE_DATA", default=[],
        help="Extra scale data. Additional data files to consider when scaling "
        "the plot axes "
        "(for plotting several plots with identical axes). Note, this displays "
        "only the first data set, but with axis scaling taking into account the "
        "additional data sets. Can be supplied multiple times; see also "
        "--scale-mode."))

    return parser


def new(settings, plotter=None, in_worker=False, **kwargs):
    try:
        if plotter is None:
            plotter = get_plotter(get_plotconfig(settings)['type'])
        kwargs.update(vars(settings))
        return plotter(
            plot_config=get_plotconfig(settings),
            data_config=settings.DATA_SETS,
            output=settings.OUTPUT,
            gui=settings.GUI,
            absolute_time=settings.ABSOLUTE_TIME,
            description=settings.DESCRIPTION,
            in_worker=in_worker,

            **kwargs)
    except Exception as e:
        raise RuntimeError("Error loading plotter: %s" % e)


def draw_worker(settings, results):
    plotter = new(settings, in_worker=True, results=results)
    plotter.init()
    plotter.plot(results)
    plotter.save(results)
    plotter.disconnect_callbacks()
    return plotter


def lines_equal(a, b):
    """Compare two matplotlib line segments by line style, marker, colour and label.
    Used to match legend items to data items on the axes."""
    # A null marker can be the string 'None' for some reason, to check for
    # this condition when comparing markers.
    return a.get_label() == b.get_label() and \
        a.get_linestyle() == b.get_linestyle() and \
        a.get_color() == b.get_color()


class Plotter(ArgParam):
    open_mode = "wb"
    inverted_units = ('ms')
    can_subplot_combine = False
    can_highlight = False

    params = add_plotting_args(ArgParser())

    def __init__(self,
                 plot_config,
                 data_config,
                 output="-",
                 gui=False,
                 description='',
                 figure=None,
                 results=None,
                 in_worker=False,
                 absolute_time=False,
                 **kwargs):
        super(Plotter, self).__init__(**kwargs)

        self.disable_cleanup = False
        self.title = None
        self.output = output
        self.styles = STYLES
        self.legends = []
        self.artists = []
        self.data_artists = []
        self.top_art = []
        self.btm_art = []
        self.right_art = []
        self.metadata = None
        self.callbacks = []
        self.in_worker = in_worker
        self.combined = False
        self.absolute_time = absolute_time

        self.gui = gui
        self.description = description

        self.interactive_callback = self.resize_callback = None
        if self.hover_highlight is not None:
            self.can_highlight = self.hover_highlight

        if self.log_scale and self.log_scale.startswith("log"):
            self.log_base = int(self.log_scale.replace("log", ""))
        else:
            self.log_base = None

        self.config = self.expand_plot_config(plot_config, data_config, results)
        self.configs = [self.config]
        self.data_config = data_config

        if figure is None:
            self.figure = pyplot.figure(dpi=self.fig_dpi)
            if self.fig_width is not None:
                self.figure.set_figwidth(self.fig_width)
            if self.fig_height is not None:
                self.figure.set_figheight(self.fig_height)
        else:
            self.figure = figure

        # Some versions of matplotlib will crash if this is not set
        if not hasattr(self.figure, '_original_dpi'):
            self.figure._original_dpi = self.figure.dpi

    def __del__(self):
        if not self.disable_cleanup:
            try:
                pyplot.close(self.figure)
            except Exception:
                pass

    def __getstate__(self):
        state = self.__dict__.copy()
        return state

    def init(self, config=None, axis=None):
        if config is not None:
            self.config = config
        self.configs = [self.config]

    def verify(self):
        lengths = [len(a.get_lines()) for a in self.figure.axes]
        return any(lengths), lengths

    def axes_iter(self):
        return iter(reduce(lambda x, y: x + y, [i['axes'] for i in self.configs]))

    def expand_plot_config(self, config, data, results=None):
        if 'series' not in config:
            return config
        new_series = []
        for s in config['series']:
            ns = []
            if isinstance(s['data'], Glob):
                for d in Glob.expand_list(s['data'], data.keys()):
                    if 'label' in s:
                        d_id = data[d]['id'] if 'id' in data[d] else d
                        if s['label']:
                            lbl = '%s -- %s' % (s['label'], d_id)
                        else:
                            lbl = d_id
                        ns.append(dict(s, data=d, id=d_id, label=lbl))
                        if 'parent_id' in data[d]:
                            ns[-1]['parent_id'] = data[d]['parent_id']
                    else:
                        ns.append(dict(s, data=d))

            else:
                ns.append(s)

            if results and 'raw_key' in s and isinstance(s['raw_key'], Glob):
                nns = []

                def all_keys(k):
                    return lambda x, y: x.union(y.get(k, set()))

                for s in ns:
                    all_rks = sorted(reduce(all_keys(s['data']),
                                            (r.raw_keys for r in results),
                                            set()))
                    rks = Glob.expand_list(s['raw_key'], all_rks)
                    for k, n in zip(rks, diff_parts(rks, "::")):
                        if k in self.filter_series:
                            continue
                        if 'label' in s:
                            nns.append(dict(s, raw_key=k,
                                            label="%s -- %s" % (s['label'], n)))
                        else:
                            nns.append(dict(s, raw_key=k))

                ns = nns

            new_series.extend(ns)

        if self.filter_series:
            new_series = [s for s in new_series if not s[
                'data'] in self.filter_series]

        if self.norm_factors:
            for n, s in zip(cycle(self.norm_factors), new_series):
                s['norm_factor'] = n

        if self.override_labels:
            for l, s in zip(self.override_labels, new_series):
                if l is not None:
                    s['label'] = l
                    s['label_override'] = True

        return dict(config, series=new_series)

    def plot(self, results, config=None, axis=None, connect_interactive=True):
        if self.metadata is None:
            self.metadata = results[0].meta()
        if len(results) > 1:
            self.combine(results, config, axis)
        else:
            self._plot(results[0], config=config, axis=axis)

        if connect_interactive:
            self.connect_interactive()

    def combine(self, results, config=None, axis=None, always_colour=False):
        styles = cycle(self.styles)
        colours = cycle(self.colours)
        labels = self._filter_labels([r.label() for r in results])
        for l, r in zip(labels, results):
            style = next(styles).copy()
            if (config and 'series' in config and len(config['series']) == 1) or \
               ('series' in self.config and len(self.config['series']) == 1) or \
               always_colour:
                style['color'] = next(colours)
            self._plot(r, config=config, axis=axis, postfix=" - " + l,
                       extra_kwargs=style, extra_scale_data=results)

    def save(self, results):

        skip_title = len(results) > 1

        artists = self.artists
        all_legends = self.legends
        if not all_legends:
            for c in self.configs:
                legends = self._do_legend(c)
                if legends:
                    all_legends += legends

        artists += all_legends + self._annotate_plot(skip_title)

        # Since outputting image data to stdout does not make sense, we launch
        # the interactive matplotlib viewer if stdout is set for output.
        # Otherwise, the filename is passed to matplotlib, which selects an
        # appropriate output format based on the file name.
        if self.output == "-":
            self.size_legends()
            if not self.gui and not self.in_worker:
                logger.debug("Showing matplotlib pyplot viewer")
                pyplot.show()
        else:
            logger.debug("Saving plot to %s", self.output)
            try:
                # PDFs have fixed DPI
                if pyplot.get_backend() == 'pdf':
                    self.figure.set_dpi(72)
                save_args = self.build_tight_layout(artists)
                if pyplot.get_backend() == 'pdf':
                    self.save_pdf(self.output, results[0].meta(
                        'DATA_FILENAME'), save_args)
                else:
                    self.figure.savefig(
                        self.output, dpi=self.fig_dpi, **save_args)
            except IOError as e:
                raise RuntimeError("Unable to save output plot: %s" % e)

    def init_interactive(self):
        self.clear_bg_cache()
        self.highlight_widths = {}
        self.hovered = set()
        for a in self.data_artists:
            self.highlight_widths[a] = (a.get_linewidth(), a.get_linewidth() * 2)

    def connect_interactive(self):
        if not self.resize_callback:
            self.resize_callback = self.figure.canvas.mpl_connect(
                'resize_event', self.size_legends)
            self.callbacks.append(self.resize_callback)

        try:
            if self.interactive_callback \
               or not self.can_highlight \
               or not self.figure.canvas.supports_blit \
               or not hasattr(self.figure.canvas, "copy_from_bbox"):
                return
        except AttributeError:
            # Old versions of matplotlib doesn't have the supports_blit attribute
            return
        self.init_interactive()
        self.interactive_callback = self.figure.canvas.mpl_connect(
            "motion_notify_event", self.on_move)
        self.callbacks.append(self.interactive_callback)
        self.callbacks.append(self.figure.canvas.mpl_connect(
            "draw_event", self.clear_bg_cache))
        self.callbacks.append(self.figure.canvas.mpl_connect(
            "button_press_event", self.on_click))
        self.callbacks.append(self.figure.canvas.mpl_connect(
            "key_press_event", self.on_keypress))

    def disconnect_callbacks(self):
        for c in self.callbacks:
            self.figure.canvas.mpl_disconnect(c)
        self.callbacks = []
        self.interactive_callback = self.resize_callback = None

    def on_move(self, event):
        hovered = set()
        for leg in self.legends:
            for l, t in zip(leg.get_lines(), leg.get_texts()):
                if l.contains(event)[0] or t.contains(event)[0]:
                    for a in self.data_artists:
                        if lines_equal(a, l):
                            hovered.add(a)
        if not hovered:
            for a in self.data_artists:
                if a.contains(event)[0]:
                    hovered.add(a)

        if hovered and self.figure.canvas.toolbar:
            s = []

            for a in hovered:
                ax = a.axes
                try:
                    trans = ax.transData.inverted()
                    xdata, ydata = trans.transform_point((event.x, event.y))
                except ValueError:
                    continue

                s.append("%s [%.2f, %.2f]" % (a.get_label(), xdata, ydata))

            self.figure.canvas.toolbar.set_message(", ".join(s))

        self.update_axes(hovered)

    def on_click(self, event):
        if event.dblclick:
            for t in chain(*[(t for t in leg.get_texts())
                             for leg in self.legends]):
                if t.contains(event)[0]:
                    return

    def on_keypress(self, event):
        if event.key in ('x', 'X', 'y', 'Y'):
            a = event.key.lower()
            d = 'in' if a == event.key else 'out'
            self.zoom(a, d)

    def zoom(self, axis, direction='in'):
        factor = 0.9 if direction == 'in' else 1.1
        for ax in self.axes_iter():
            setter = getattr(ax, "set_"+axis+"lim")
            getter = getattr(ax, "get_"+axis+"lim")

            l, u = getter()
            mid = l + (u-l) / 2

            nl = mid - (mid-l)*factor
            nu = mid + (u-mid)*factor
            setter(nl, nu)

        self.figure.canvas.draw()
        self.figure.canvas.toolbar.push_current()

    def update_axes(self, hovered):
        bboxes = set()

        for ax in self.axes_iter():

            # If the bbox has negative width or height abort rather than crash
            # when trying to copy its content below
            if ax.bbox.width < 0 or ax.bbox.height < 0:
                return

            # If we don't have a background cache this is the first time we are
            # called after a redraw, so no modifications to artists have been
            # made. Hence, we just cache the background now.
            bboxes.add(ax.bbox)
            if ax not in self.bg_cache:
                self.bg_cache[ax] = self.figure.canvas.copy_from_bbox(ax.bbox)
            else:
                self.figure.canvas.restore_region(self.bg_cache[ax])

        for a in hovered:
            a.set_linewidth(self.highlight_widths[a][1])
            a.set_markeredgewidth(self.highlight_widths[a][1])
            try:
                a.axes.draw_artist(a)
            except AttributeError:
                pass
            a.set_linewidth(self.highlight_widths[a][0])
            a.set_markeredgewidth(self.highlight_widths[a][0])

        for bbox in bboxes:
            self.figure.canvas.blit(bbox)

    def clear_bg_cache(self, evt=None):
        self.bg_cache = {}

    def save_pdf(self, filename, data_filename, save_args):
        pdf = matplotlib.backends.backend_pdf.PdfPages(filename)
        try:
            pdf.infodict()['Producer'] = 'Flent v%s' % VERSION
            pdf.infodict()['Subject'] = data_filename
            if self.title:
                pdf.infodict()['Title'] = self.title.replace("\n", "; ")
            self.figure.savefig(pdf, **save_args)
        finally:
            pdf.close()

    def build_tight_layout(self, artists):
        args = None
        if self.fallback_layout:
            return {'bbox_extra_artists': artists, 'bbox_inches': 'tight'}
        try:
            self.figure.savefig(io.BytesIO())

            renderer = self.figure._cachedRenderer
            right = x_max = self.figure.get_figwidth() * self.figure.dpi
            top = y_max = self.figure.get_figheight() * self.figure.dpi
            vsp = 0.02 * self.figure.dpi
            hsp = 0.08 * self.figure.dpi

            left = btm = offset_x = right_ax = 0

            # these move with the subplots, so use .width/.height
            for ax in self.axes_iter():
                w = ax.yaxis.get_tightbbox(renderer).width
                if ax.yaxis.get_label_position() == 'right':
                    right_ax = max(w, right_ax)
                else:
                    left = max(left, w)

                bbx = ax.xaxis.get_tightbbox(renderer)
                if bbx:
                    btm = max(btm, bbx.height)

            if self.right_art:
                right -= max((a.get_window_extent(renderer).width
                             for a in self.right_art))
                offset_x = max((a.offset_x for a in self.right_art
                                if hasattr(a, "offset_x")))
            else:
                # This only seems to be necessary if there's no legend to the right
                right -= right_ax

            # these are fixed in place, so use .y0/.y1
            bsp = 0
            if self.btm_art:
                for a in self.btm_art:
                    bb = a.get_window_extent(renderer)
                    bsp = max(bsp, bb.y1)
                    if bb.y1 < 0:
                        btm += bb.height - bb.y1
            btm += bsp

            if self.top_art:
                top = y_max - sum((a.get_window_extent(renderer).height
                                   for a in self.top_art))

            # The offset is a percentage of the final subplot bounding box, so
            # adjust by that
            if offset_x:
                right -= (right - left) * (offset_x - 1)

            left = (hsp + left)/x_max
            top = (top - vsp)/y_max
            right = (right - hsp)/x_max
            bottom = (vsp + btm)/y_max

            self.figure.subplots_adjust(left=left, right=right,
                                        top=top, bottom=bottom)
            args = {}
        except (AttributeError, ImportError, ValueError) as e:
            logger.warning("Unable to build our own tight layout: %s", e)

        # Fall back to the regular bbox_extra_artists output feature
        if args is None:
            logger.debug("Falling back to bbox_inches=tight layout")
            args = {'bbox_extra_artists': artists, 'bbox_inches': 'tight'}
        return args

    def size_legends(self, event=None):
        # For the interactive viewer there's no bbox_extra_artists, so we
        # need to reduce the axis sizes to make room for the legend.

        if not self.resize_callback:
            self.resize_callback = self.figure.canvas.mpl_connect(
                'resize_event', self.size_legends)
            self.callbacks.append(self.resize_callback)

        if self.print_legend \
           and not self.horizontal_legend \
           and not self.legend_placement \
           and self.legends:

            # Make sure we have a renderer to get size from
            renderer = getattr(self.figure, '_cachedRenderer', None)
            if not renderer:
                self.figure.canvas.draw()
                renderer = getattr(self.figure, '_cachedRenderer', None)

            try:
                legend_width = max(
                    [l.get_window_extent(renderer).width for l in self.legends])
            except Exception as e:
                logger.debug("Error getting legend sizes: %s", e)
                return

            canvas_width = self.figure.canvas.get_width_height()[0]
            for a in self.axes_iter():
                # Save the original width of the axis (in the interval [0..1])
                # and use that as a base to scale the axis on subsequent calls.
                # Otherwise, each call will shrink the axis.
                if not hasattr(a, 'orig_width'):
                    a.orig_width = a.get_position().width
                box = a.get_position()
                a.set_position(
                    [box.x0,
                     box.y0,
                     (a.orig_width - legend_width / canvas_width),
                     box.height])
            self.figure.canvas.draw_idle()

    def _annotate_plot(self, skip_title=False):
        titles = []
        title_y = 1 - 0.04 / self.figure.get_figheight()
        if self.override_title:
            art = self.figure.suptitle(self.override_title,
                                       fontsize=14, y=title_y)
            titles.append(art)
            self.top_art.append(art)
            self.title = self.override_title
        elif self.print_title:
            plot_title = self.description
            if 'description' in self.config:
                plot_title += "\n" + self.config['description']
            if self.metadata['TITLE'] and not skip_title:
                plot_title += "\n" + self.metadata['TITLE']
            art = self.figure.suptitle(
                plot_title, fontsize=14, y=title_y)
            titles.append(art)
            self.top_art.append(art)
            self.title = plot_title

        if self.annotate:
            annotation_string = "Local/remote: %s/%s - " \
                                "Time: %s - Length/step: %ds/%.2fs" % (
                                    self.metadata['LOCAL_HOST'],
                                    self.metadata['HOST'],
                                    format_date(self.metadata['TIME']),
                                    self.metadata['LENGTH'],
                                    self.metadata['STEP_SIZE'])
            self.btm_art.append(
                self.figure.text(0.5,
                                 0.04 / self.figure.get_figheight(),
                                 annotation_string,
                                 horizontalalignment='center',
                                 verticalalignment='bottom',
                                 fontsize=8))
        if self.fig_note:
            self.btm_art.append(
                self.figure.text(0.0,
                                 0.04 / self.figure.get_figheight(),
                                 self.fig_note,
                                 horizontalalignment='left',
                                 verticalalignment='bottom',
                                 fontsize=8))

        return titles

    def _filter_labels(self, labels):
        for s, d in self.replace_legend.items():
            labels = [l.replace(s, d) for l in labels]
        for r in self.filter_regexp:
            labels = [re.sub(r, "", l) for l in labels]
        if self.filter_legend and labels:
            if 'Avg' in labels:
                filt = labels[:]
                filt.remove('Avg')
                substr = long_substr(filt)
            else:
                substr = long_substr(labels)

            if len(substr) > 3 and substr != " - ":
                labels = [l.replace(substr, '') for l in labels]
            prefix = long_substr(labels, prefix_only=True)
            if prefix and len(prefix) < len(labels[0]):
                labels = [l.replace(prefix, '') for l in labels]

        labels = [l.strip() for l in labels]
        return labels

    def do_legend(self):
        legends = []
        for c in self.configs:
            legends.extend(self._do_legend(c))
        return legends

    def _do_legend(self, config, postfix=""):
        if not self.print_legend:
            return []

        axes = config['axes']

        # Each axis has a set of handles/labels for the legend; combine them
        # into one list of handles/labels for displaying one legend that holds
        # all plot lines
        handles, labels = reduce(lambda x, y: (x[0] + y[0], x[1] + y[1]),
                                 [a.get_legend_handles_labels() for a in axes])
        if not labels:
            return []

        if self.legend_reverse:
            handles, labels = reversed(handles), reversed(labels)

        labels = self._filter_labels(labels)

        kwargs = {}
        if self.legend_title is not None:
            kwargs['title'] = self.legend_title
        elif 'legend_title' in config:
            kwargs['title'] = config['legend_title']

        legends = []
        offset_x = None
        if self.horizontal_legend:
            bbox = (0.5, -0.15)
            ncol = len(labels)
            loc = 'upper center'
        elif self.legend_placement:
            bbox = None
            ncol = 1
            loc = self.legend_placement
        else:
            if len(axes) > 1:
                offset_x = 1.11
            else:
                offset_x = 1.02

            bbox = (offset_x, 1.0)
            ncol = 1
            loc = 'upper left'
        l = axes[0].legend(handles, labels,
                           bbox_to_anchor=bbox,
                           loc=loc, borderaxespad=0.,
                           prop={'size': 'small'},
                           ncol=self.legend_columns or ncol,
                           **kwargs)

        if offset_x is not None:
            self.right_art.append(l)
            l.offset_x = offset_x  # We use this in build_tight_layout

        if self.horizontal_legend:
            self.btm_art.append(l)

        legends.append(l)
        return legends

    def _do_scaling(self, axis, data, btm, top, unit=None, allow_log=True):
        """Scale the axis to the selected bottom/top percentile"""
        if data is None or not data.any():
            return

        top_percentile = self._percentile(data, top)
        btm_percentile = self._percentile(data, btm)

        if top_percentile == btm_percentile or \
           math.isnan(top_percentile) or math.isnan(btm_percentile):
            return

        # Leave 1 percent of the axis range as extra space, so the outermost
        # points are not smudged by the axis lines.
        space = (top_percentile - btm_percentile) * 0.01
        top_scale = top_percentile + space
        btm_scale = btm_percentile - space

        if self.zero_y:
            # When y is set at zero, set space at the top to be one percent room
            # of the *axis* range, not the data range (this may be a big
            # difference if the data range is small).
            top_scale = top_percentile * 1.01
            axis.set_ylim(0, top_scale)
        else:
            if self.log_base:
                axis.set_yscale('log', basey=self.log_base)
                axis.set_ylim(max(0, btm_scale), top_scale)
            else:
                axis.set_ylim(btm_scale, top_scale)

        if self.invert_y and unit in self.inverted_units:
            axis.invert_yaxis()

    def _percentile(self, arr, q):
        try:
            # nanpercentile was only introduced in numpy 1.9.0
            return np.nanpercentile(arr, q)
        except AttributeError:
            ma = np.ma.masked_invalid(arr)
            return np.percentile(ma.compressed(), q)

    def get_series(self, series, results, config,
                   no_invalid=False, aligned=False):

        if aligned or self.combined:
            data = np.array((results.x_values,
                             results.series(series['data'])),
                            dtype=float)
        else:
            raw_key = series.get('raw_key')
            try:

                data = np.array(
                    list(results.raw_series(series['data'], raw_key=raw_key,
                                            absolute=self.absolute_time)),
                    dtype=float).transpose()

                if not len(data):
                    raise KeyError()

            except KeyError:
                if raw_key:
                    # No point in using synthesised results since those won't be
                    # correct when raw_key is set
                    return np.array([], dtype=float)
                logger.debug("No raw data found for series %s, "
                             "falling back to computed values", series['data'])
                data = np.array((results.x_values,
                                 results.series(series['data'])),
                                dtype=float)

        if data.any() and (self.data_cutoff or config.get('cutoff')):
            start, end = self.data_cutoff or config['cutoff']
            if self.absolute_time:
                start += results.t0

            if end <= 0:
                end += results.meta("TOTAL_LENGTH")

            min_idx = data[0].searchsorted(start, side='left')
            max_idx = data[0].searchsorted(end, side='right')

            data = data[:, min_idx:max_idx]

        if len(data) == 0:
            return data

        if no_invalid:
            data = np.ma.compress_cols(np.ma.masked_invalid(data))

        if 'norm_factor' in series:
            data[1] /= series['norm_factor']

        if 'smoothing' in series and series['smoothing'] and data.any():
            l = series['smoothing']
            if l % 2 != 1:
                l += 1

            if l <= len(data[1]):
                kern = np.ones(l, dtype=float)
                kern /= l
                data[1] = np.convolve(data[1], kern, mode=str('same'))
            else:
                logger.warn("Smoothing length longer than data series %s; "
                            "not smoothing", series['data'])

        return data


class CombineManyPlotter(object):

    def __init__(self, *args, **kwargs):
        super(CombineManyPlotter, self).__init__(*args, **kwargs)
        self.combined = True

    def plot(self, results, config=None, axis=None, connect_interactive=True):
        if self.metadata is None:
            self.metadata = results[0].meta()
        if config is None:
            config = self.config

        combine_mode = self.override_group_by or config.get('group_by', 'groups')
        combiner = combiners.new(combine_mode, print_n=self.combine_print_n,
                                 filter_regexps=self.filter_regexp,
                                 filter_series=self.filter_series,
                                 save_dir=self.combine_save_dir,
                                 data_cutoff=self.data_cutoff)
        super(CombineManyPlotter, self).plot(
            combiner(results, config),
            config,
            axis,
            connect_interactive=connect_interactive)


class TimeseriesPlotter(Plotter):
    can_subplot_combine = True
    can_highlight = True

    def init(self, config=None, axis=None):
        Plotter.init(self, config, axis)

        if axis is None:
            axis = self.figure.gca()
        if config is None:
            config = self.config

        if 'dual_axes' in config and config['dual_axes']:
            second_axis = self.figure.add_axes(
                axis.get_position(), sharex=axis, frameon=False)
            second_axis.yaxis.tick_right()
            axis.yaxis.tick_left()
            second_axis.yaxis.set_label_position('right')
            second_axis.yaxis.set_offset_position('right')
            second_axis.xaxis.set_visible(False)
            axis.grid(False)
            second_axis.grid(False)
            config['axes'] = [axis, second_axis]
        else:
            config['axes'] = [axis]

        for a in config['axes']:
            a.minorticks_on()

        unit = [None] * len(config['axes'])
        for s in config['series']:
            if 'axis' in s and s['axis'] == 2:
                a = 1
            else:
                a = 0
            s_unit = self.data_config[s['data']]['units']
            if unit[a] is not None and s_unit != unit[a] and 'raw_key' not in s:
                raise RuntimeError(
                    "Plot axis unit mismatch: %s/%s" % (unit[a], s_unit))
            unit[a] = s_unit

        axis.set_xlabel(self.label_x[0] if self.label_x else 'Time (s)')
        for i, u in enumerate(unit):
            if 'axis_labels' in config and config['axis_labels'][i]:
                l = config['axis_labels'][i]
            else:
                l = unit[i]

            if self.norm_factors:
                l = l[0].lower() + l[1:]
                l = "Normalised %s" % l

            if self.label_y:
                l = self.label_y[min(i, len(self.label_y) - 1)]

            config['axes'][i].set_ylabel(l)

        config['units'] = unit

    def _plot(self, results, config=None, axis=None, postfix="",
              extra_kwargs={}, extra_scale_data=[]):
        if axis is None:
            axis = self.figure.gca()
        if config is None:
            config = self.config

        stack = 'stacked' in config and config['stacked']

        x_min = 2**63
        x_max = 0

        colours = cycle(self.colours)

        if stack:
            sums = np.zeros(len(results.x_values))

        all_data = [None] * len(config['axes'])

        for i, s in enumerate(config['series']):
            data = self.get_series(s, results, config, aligned=stack)
            if not data.any():
                continue

            x_min = min(data[0].min(), x_min)
            x_max = max(data[0].max(), x_max)

            kwargs = {}
            for k in PLOT_KWARGS:
                if k in s:
                    kwargs[k] = s[k]

            if 'label' in kwargs:
                kwargs['label'] += postfix

            if 'color' not in kwargs:
                kwargs['color'] = next(colours)

            kwargs.update(extra_kwargs)

            if 'axis' in s and s['axis'] == 2:
                a = 1
            else:
                a = 0

            if stack:
                kwargs['facecolor'] = kwargs['color']
                kwargs['edgecolor'] = 'none'
                del kwargs['color']

                config['axes'][a].fill_between(
                    data[0], sums, data[1] + sums, **kwargs)
                sums += data[1]
            else:
                if all_data[a] is None:
                    all_data[a] = data[1].copy()
                else:
                    all_data[a] = np.append(all_data[a], data[1])
                for r in self.scale_data + extra_scale_data:
                    d = self.get_series(s, r, config)
                    if d.any():
                        all_data[a] = np.append(all_data[a], d[1])
                self.data_artists.extend(config['axes'][a].plot(data[0], data[1],
                                                                **kwargs))

        xlim = axis.get_xlim()
        axis.set_xlim(
            min(x_min, xlim[0]) if xlim[0] > 0 else x_min,
            max(x_max, self.metadata['TOTAL_LENGTH'], xlim[1]))

        if 'scaling' in config:
            btm, top = config['scaling']
        else:
            btm, top = 0, 100

        for a in range(len(config['axes'])):
            if all_data[a] is not None:
                self._do_scaling(config['axes'][a], all_data[a], btm, top,
                                 config['units'][a])

            # Handle cut-off data sets. If the x-axis difference between the
            # largest data point and the TOTAL_LENGTH from settings, scale to
            # the data values, but round to nearest 10 above that value.
            try:
                max_xdata = max([l.get_xdata()[-1]
                                 for l in config['axes'][a].get_lines()
                                 if l.get_xdata()])
                if abs(self.metadata['TOTAL_LENGTH'] - max_xdata) > 10:
                    config['axes'][a].set_xlim(
                        right=(max_xdata + (10 - max_xdata % 10)))
            except ValueError:
                pass

        for a, b in zip(config['axes'], self.bounds_x):
            a.set_xbound(b)
        for a, b in zip(config['axes'], self.bounds_y):
            a.set_ybound(b)


class TimeseriesCombinePlotter(CombineManyPlotter, TimeseriesPlotter):
    pass


class BoxPlotter(TimeseriesPlotter):
    # Since labels are printed vertically at the bottom, they tend to break
    # matplotlib's layout logic if they're too long.
    _max_label_length = 30

    def init(self, config=None, axis=None):
        if axis is None:
            axis = self.figure.gca()

        TimeseriesPlotter.init(self, config, axis)

        if config is None:
            config = self.config

        axis.set_xlabel('')

        for a in config['axes']:
            a.grid(False, axis='x')

        self.start_position = 1

    def plot(self, results, config=None, axis=None, connect_interactive=True):
        if self.metadata is None:
            self.metadata = results[0].meta()
        return self._plot(results, config, axis)

    def _get_split_groups(self, results, config):
        if self.split_groups:
            if len(results) % len(self.split_groups) > 0:
                raise RuntimeError(
                    "Split groups only works when the number of results "
                    "is divisible by the number of groups")
            split_results = []
            series = []
            group_size = len(results) // len(self.split_groups)
            for i, g in enumerate(self.split_groups):
                split_results.append(results[i * group_size:(i + 1) * group_size])
                for s in config['series']:
                    ns = s.copy()
                    ns['label'] = g
                    series.append(ns)
        else:
            group_size = len(results)
            split_results = []
            series = config['series']

        return group_size, split_results, series

    def _plot(self, results, config=None, axis=None):
        if config is None:
            config = self.config
        axis = config['axes'][0]

        ticklabels = []
        ticks = []
        texts = []
        pos = 1
        all_data = [None] * len(config['axes'])

        group_size, split_results, series = self._get_split_groups(results,
                                                                   config)

        # The median lines are red, so filter out red from the list of colours
        colours = list(
            islice(cycle([c for c in self.colours if c != 'r']), group_size))
        series_labels = [s.get('label', '') for s in series]
        if not any([s.get('label_override', False) for s in series]):
            series_labels = self._filter_labels(series_labels)
        ticklabel_override = False
        for i, s in enumerate(series):
            if split_results:
                results = split_results[i]
            if 'axis' in s and s['axis'] == 2:
                a = 1
            else:
                a = 0

            data = []
            group_size = len(results)
            for r in results:
                d = self.get_series(s, r, config, no_invalid=True)

                if not d.any():
                    continue

                if all_data[a] is None:
                    all_data[a] = d[1].copy()
                else:
                    all_data[a] = np.append(all_data[a], d[1])

                data.append(d[1])

            if not data:
                continue

            group_size = len(data)

            if len(series) > 1 or self.print_title:
                texts.append(config['axes'][0].text(
                    pos + group_size / 2.0 - 0.5,
                    14,
                    series_labels[i],
                    ha='center'))

            positions = range(pos, pos + group_size)
            ticks.extend(list(range(pos, pos + group_size)))

            bp = config['axes'][a].boxplot(data,
                                           positions=positions, sym="b+")
            for j, r in zip(range(group_size), results):
                pyplot.setp(bp['boxes'][j], color=colours[j])
                if i == 0 and group_size > 1:
                    bp['caps'][j * 2].set_label(r.label())
                if len(results) > 1:
                    ticklabels.append(r.label())
                    ticklabel_override = (ticklabel_override or
                                          r.metadata.get('label_override',
                                                         False))
                if len(bp['fliers']) == group_size:
                    pyplot.setp([bp['fliers'][j]], markeredgecolor=colours[j])
                    keys = 'caps', 'whiskers'
                else:
                    keys = 'caps', 'whiskers', 'fliers'
                for k in keys:
                    if bp[k]:
                        pyplot.setp(bp[k][j * 2], color=colours[j])
                        pyplot.setp(bp[k][j * 2 + 1], color=colours[j])

                if bp['whiskers']:
                    for art in bp['whiskers']:
                        art.set_linestyle("-")

            config['axes'][a].axvline(
                x=pos + group_size, color='black', linewidth=0.5, linestyle=':')
            pos += group_size + 1

        if not ticks:
            return  # no data

        for i, a in enumerate(config['axes']):
            if all_data[i] is not None:
                self._do_scaling(a, all_data[i], 0, 100,
                                 config['units'][i], allow_log=False)

        for a, b in zip(config['axes'], self.bounds_y):
            a.set_ybound(b)

        if not ticklabel_override:
            ticklabels = self._filter_labels(ticklabels)
        for i, l in enumerate(ticklabels):
            if len(l) > self._max_label_length:
                ticklabels[i] = l[:self._max_label_length] + "..."

        for t in texts:
            min_y, max_y = t.axes.get_ylim()
            x, y = t.get_position()
            mult = 0.1 if self.log_base else 0.01
            t.set_position((x, max_y + abs(max_y - min_y) * mult))

        self.artists.extend(texts)
        if texts:
            self.top_art.append(texts[0])

        axis.set_xlim(0, pos - 1)
        axis.set_xticks(ticks)
        axis.set_xticks([], minor=True)
        if self.print_labels:
            axis.set_xticklabels(ticklabels, rotation=90, ha='center')
        else:
            axis.set_xticklabels([])


class BoxCombinePlotter(CombineManyPlotter, BoxPlotter):
    pass


class BarPlotter(BoxPlotter):

    def init(self, config=None, axis=None):
        BoxPlotter.init(self, config, axis)

    def _plot(self, results, config=None, axis=None):
        if config is None:
            config = self.config
        axis = config['axes'][0]

        ticklabels = []
        ticks = []
        pos = 1
        all_data = []
        for a in config['axes']:
            all_data.append([])

        errcol = 'k'
        width = 1.0

        group_size, split_results, series = self._get_split_groups(results,
                                                                   config)
        # The error bars lines are black, so filter out black from the list of
        # colours
        colours = list(
            islice(cycle([c for c in self.colours if c != errcol]),
                   max(group_size, len(series))))

        colour_mode = (self.override_colour_mode or
                       config.get('colour_mode', 'groups'))

        series_labels = self._filter_labels(
            [s['label'] for s in series])
        texts = []

        for i, s in enumerate(series):
            if split_results:
                results = split_results[i]
            if 'axis' in s and s['axis'] == 2:
                a = 1
            else:
                a = 0

            data = []
            errors = []
            for r in results:
                dp = self.get_series(s, r, config, no_invalid=True)
                if not dp.any() and not self.skip_missing:
                    data.append(0.0)
                    errors.append(0.0)
                    all_data[a].append(0.0)
                elif dp.any():
                    dp = np.array(dp[1])
                    data.append(dp.mean())
                    errors.append(dp.std())
                    all_data[a].append(data[-1] + errors[-1])
                    all_data[a].append(data[-1] - errors[-1])

            # may have skipped series, recalculate
            group_size = len(data)

            positions = [p - width / 2.0 for p in range(pos, pos + group_size)]
            ticks.extend(list(range(pos, pos + group_size)))
            ticklabels.extend(self._filter_labels([r.label() for r in results]))
            if colour_mode == 'groups':
                colour = colours[i]
            else:
                colour = self.colours[:len(data)]

            config['axes'][a].bar(positions, data, yerr=errors, ecolor=errcol,
                                  color=colour, alpha=0.75, width=width,
                                  align='edge', capsize=2)
            if len(config['series']) > 1 or self.print_title:
                texts.append(config['axes'][0].text(
                    pos + group_size / 2.0 - 0.5,
                    14,
                    series_labels[i],
                    ha='center'))

            config['axes'][a].axvline(
                x=pos + group_size, color='black', linewidth=0.5, linestyle=':')
            pos += group_size + 1

        if not ticks:
            return  # no data

        for a, b in zip(config['axes'], self.bounds_y):
            a.set_ybound(b)

        min_y, max_y = config['axes'][0].get_ylim()

        for t in texts:
            x, y = t.get_position()
            t.set_position((x, max_y + abs(max_y - min_y) * 0.01))

        for i, l in enumerate(ticklabels):
            if len(l) > self._max_label_length:
                ticklabels[i] = l[:self._max_label_length] + "..."

        axis.set_xlim(0, pos - 1)
        axis.set_xticks(ticks)
        axis.set_xticks([], minor=True)
        if self.print_labels:
            axis.set_xticklabels(ticklabels, rotation=90, ha='center')
        else:
            axis.set_xticklabels([])

        self.artists.extend(texts)
        if texts:
            self.top_art.append(texts[0])


class BarCombinePlotter(CombineManyPlotter, BarPlotter):
    pass


class CdfPlotter(Plotter):
    can_subplot_combine = True
    can_highlight = True

    def init(self, config=None, axis=None):
        Plotter.init(self, config, axis)
        if axis is None:
            axis = self.figure.gca()
        if config is None:
            config = self.config

        unit = None
        for s in config['series']:
            s_unit = self.data_config[s['data']]['units']
            if unit is not None and s_unit != unit:
                raise RuntimeError(
                    "Plot axis unit mismatch: %s/%s" % (unit, s_unit))
            unit = s_unit

        if 'axis_labels' in config and config['axis_labels'][0]:
            axis.set_xlabel(config['axis_labels'][0])
        else:
            axis.set_xlabel(unit)
        axis.set_ylabel('Cumulative probability')
        axis.set_ylim(0, 1)
        axis.minorticks_on()
        config['axes'] = [axis]

    def _plot(self, results, config=None, axis=None, postfix="",
              extra_kwargs={}, extra_scale_data=[]):
        if config is None:
            config = self.config
        if axis is None:
            axis = config['axes'][0]

        colours = cycle(self.colours)
        max_value = 0.0
        min_value = float('inf')

        for i, s in enumerate(config['series']):

            data = self.get_series(s, results, config, no_invalid=True)
            if not data.any():
                continue

            # ECDF that avoids bias due to binning. See discussion at
            # http://stackoverflow.com/a/11692365
            x_values = np.sort(data[1])
            y_values = np.arange(1, len(x_values)+1)/float(len(x_values))

            max_value = max(max_value, x_values[-1])
            min_value = min(min_value, x_values[0])

            kwargs = {}
            for k in PLOT_KWARGS:
                if k in s:
                    kwargs[k] = s[k]
            if 'label' in kwargs:
                kwargs['label'] += postfix
            if 'color' not in kwargs:
                kwargs['color'] = next(colours)
            kwargs.update(extra_kwargs)
            self.data_artists.extend(axis.plot(x_values,
                                               y_values,
                                               **kwargs))

        if max_value > 10:
            # round up to nearest value divisible by 10
            max_value += 10 - (max_value % 10)

        if max_value > 0:
            axis.set_xlim(right=max(max_value, axis.get_xlim()[1]))

        if self.zero_y:
            axis.set_xlim(left=0)
        elif min_value < max_value:
            if min_value > 10:
                min_value -= min_value % 10  # nearest value divisible by 10
            if min_value > 100:
                min_value -= min_value % 100
            axis.set_xlim(left=min(min_value, axis.get_xlim()[0]))

        if self.log_base:
            axis.set_xscale('log', basex=self.log_base)

        for a, b in zip(config['axes'], self.bounds_x):
            a.set_xbound(b)


class CdfCombinePlotter(CombineManyPlotter, CdfPlotter):
    pass


class QqPlotter(Plotter):

    def init(self, config=None, axis=None):
        Plotter.init(self, config, axis)
        if axis is None:
            axis = self.figure.gca()
        if config is None:
            config = self.config

        axis.minorticks_on()
        config['axes'] = [axis]

        if len(config['series']) > 1:
            raise RuntimeError("Can't do Q-Q plot with more than one series")

    def plot(self, results, connect_interactive=True):
        if self.metadata is None:
            self.metadata = results[0].meta()
        if len(results) < 2:
            results *= 2
        self._plot(results[:2])

    def _plot(self, results):
        series = self.config['series'][0]
        axis = self.config['axes'][0]

        x_values, y_values = self._equal_length(results[0].series(
            series['data']), results[1].series(series['data']))

        axis.plot(x_values, y_values, 'r.', label=series['label'])

        max_val = max(x_values.max(), y_values.max())
        axis.plot([0, max_val], [0, max_val], 'b-', label="Ref (x=y)")

        axis.set_xlabel(results[0].label())
        axis.set_ylabel(results[1].label())

        axis.set_xlim(min(x_values) * 0.99, max(x_values) * 1.01)
        axis.set_ylim(min(y_values) * 0.99, max(y_values) * 1.01)

    def _equal_length(self, x, y):
        x_values = np.sort([r for r in x if r is not None])
        y_values = np.sort([r for r in y if r is not None])

        # If data sets are not of equal sample size, the larger one is shrunk by
        # interpolating values into the length of the smallest data set.
        #
        # Translated from the R implementation:
        # http://svn.r-project.org/R/trunk/src/library/stats/R/qqplot.R and
        # http://svn.r-project.org/R/trunk/src/library/stats/R/approx.R
        #
        # np.linspace returns a number of equally spaced points between a
        # maximum and a minimum (like range() but specifying number of steps
        # rather than interval). These are the x values of used for
        # interpolation.
        #
        # np.interp does linear interpolation of a dataset. I.e. for each x
        # value in the first argument it returns the linear interpolation
        # between the two neighbouring y values of the source data set. The
        # source x values are simply numbered up to the length of the longer
        # data set, and the source y values are the actual values of the
        # longer data set. The destination x values are equally spaced in the
        # length of the longer data set, with n being equal to the number of
        # data points in the shorter data set.
        if len(x_values) < len(y_values):
            y_values = np.interp(np.linspace(0, len(y_values),
                                             num=len(x_values),
                                             endpoint=False),
                                 range(len(y_values)), y_values)

        elif len(y_values) < len(x_values):
            x_values = np.interp(np.linspace(0, len(x_values),
                                             num=len(y_values),
                                             endpoint=False),
                                 range(len(x_values)), x_values)

        return x_values, y_values


class EllipsisPlotter(Plotter):
    can_subplot_combine = True

    def init(self, config=None, axis=None):
        Plotter.init(self, config, axis)
        try:
            from flent.error_ellipse import plot_point_cov
            self.plot_point_cov = plot_point_cov
        except ImportError:
            raise RuntimeError("Unable to load error_ellipse plotting functions")

        if axis is None:
            axis = self.figure.gca()
        if config is None:
            config = self.config

        if len(config['series']) < 2:
            raise RuntimeError(
                "Can't do ellipsis plots with fewer than two series")

        axis.minorticks_on()
        config['axes'] = [axis]

        for i, a in enumerate(['x', 'y']):
            unit = self.data_config[config['series'][i]['data']]['units']
            if self.invert_y and unit in self.inverted_units:
                config['invert_' + a] = True
            else:
                config['invert_' + a] = False
            if 'axis_labels' in config and config['axis_labels'][i]:
                getattr(axis, 'set_' + a + 'label')(config['axis_labels'][i])
            else:
                getattr(
                    axis, 'set_' + a + 'label')(
                        self.data_config[config['series'][i]['data']]['units'])

    def _plot(self, results, config=None, axis=None, extra_kwargs={},
              postfix="", **kwargs):
        self.xvals, self.yvals = [], []
        if config is None:
            config = self.config
        if axis is None:
            axis = config['axes'][0]

        series = config['series']

        label = postfix.replace(" - ", "") if postfix else results.label()

        carg = {}
        if 'color' in extra_kwargs:
            carg['color'] = extra_kwargs['color']

        x_values = self.get_series(series[0], results, config, aligned=True)[1]

        for s in series[1:]:
            y_values = self.get_series(s, results, config, aligned=True)[1]

            points = np.vstack((x_values, y_values))
            points = np.transpose(
                np.ma.compress_cols(np.ma.masked_invalid(points)))

            if len(points) == 1:
                points = np.vstack((points, points))

            el = self.plot_point_cov(points, ax=axis, alpha=0.5, **carg)
            med = np.median(points, axis=0)
            self.xvals.append(el.center[0] - el.width / 2)
            self.xvals.append(el.center[0] + el.width / 2)
            self.yvals.append(el.center[1] - el.height / 2)
            self.yvals.append(el.center[1] + el.height / 2)
            self.xvals.append(med[0])
            self.yvals.append(med[1])
            axis.plot(*med, marker='o', linestyle=" ", **carg)
            axis.annotate(label, med, ha='center', annotation_clip=True,
                          xytext=(0, 8), textcoords='offset points')

        if len(self.yvals) == 0:
            return

        if self.zero_y:
            self.xvals.append(0.0)
            self.yvals.append(0.0)
        axis.set_xlim(max(min(self.xvals) * 0.99, 0), max(self.xvals) * 1.1)
        axis.set_ylim(max(min(self.yvals) * 0.99, 0), max(self.yvals) * 1.1)
        if config['invert_x']:
            axis.invert_xaxis()
        if config['invert_y']:
            axis.invert_yaxis()

        for a, b in zip(config['axes'], self.bounds_x):
            a.set_xbound(b)
        for a, b in zip(config['axes'], self.bounds_y):
            a.set_ybound(b)


class EllipsisCombinePlotter(CombineManyPlotter, EllipsisPlotter):
    pass


class MetaPlotter(Plotter):

    def __init__(self, plot_config, data_config, figure=None, **kwargs):
        self._kwargs = kwargs
        self._can_highlight = True
        self.subplots = []
        Plotter.__init__(self, plot_config, data_config, figure=figure, **kwargs)

    def init(self, config=None):
        Plotter.init(self, config)
        self.subplots = []

        if config is None:
            config = self.config
        self.configs = []
        ax = self.figure.gca()
        ax.set_axis_off()
        if 'subplot_params' in config:
            subplot_params = config['subplot_params']
        else:
            subplot_params = [{}] * len(config['subplots'])

        if config.get('share_axis', True):
            sharex = ax
        else:
            sharex = None
        for i, (subplot, cfg) in enumerate(config['subplots'].items()):
            if config.get('orientation', 'vertical') == 'vertical':
                rows = len(config['subplots'])
                cols = 1
            else:
                cols = len(config['subplots'])
                rows = 1
            axis = self.figure.add_subplot(
                rows, cols, i + 1, sharex=sharex, **subplot_params[i])
            cfg['axes'] = [axis]
            cfg = self.expand_plot_config(cfg, self.data_config,
                                          results=self._kwargs.get("results"))
            self.configs.append(cfg)
            plotter = get_plotter(cfg['type'])(cfg, self.data_config,
                                               figure=self.figure, **self._kwargs)
            plotter.init(cfg, axis)
            self.subplots.append((plotter, axis))
            if i < len(config['subplots']) - 1:
                axis.set_xlabel("")

    def plot(self, results):
        if self.metadata is None:
            self.metadata = results[0].meta()
        for s, ax in self.subplots:
            s.plot(results, connect_interactive=False)
            s.legends.extend(s.do_legend())
            self.legends.extend(s.legends)
            self.right_art.extend(s.right_art)
            s.init_interactive()
        self.connect_interactive()

    def get_can_highlight(self):
        return self._can_highlight and all([s.can_highlight
                                            for s, ax in self.subplots])

    def set_can_highlight(self, v):
        self._can_highlight = v
    can_highlight = property(get_can_highlight, set_can_highlight)

    def on_move(self, event):
        for s, ax in self.subplots:
            if ax.in_axes(event) or any([l.contains(event)[0]
                                         for l in s.legends]):
                s.on_move(event)
            else:
                # If the event did not fit this axes, we may have just left it,
                # so update with no hovered elements to make sure we clear any
                # highlights.
                s.update_axes(set())

    def clear_bg_cache(self, evt=None):
        for s, ax in self.subplots:
            s.clear_bg_cache()

    def disconnect_callbacks(self):
        Plotter.disconnect_callbacks(self)
        for s, ax in self.subplots:
            s.disconnect_callbacks()


class SubplotCombinePlotter(MetaPlotter):

    def init(self, config=None):
        pass

    def _init(self, number):
        config = self.config
        config['subplots'] = OrderedDict()
        for i in range(number):
            config['subplots'][str(i)] = config.copy()
        if not get_plotter(config['type']).can_subplot_combine:
            raise RuntimeError(
                "This plot type does not work with --subplot-combine")
        MetaPlotter.init(self, config)

    def plot(self, results, connect_interactive=True):
        if self.metadata is None:
            self.metadata = results[0].meta()
        self._init(len(results))
        for (p, a), r in zip(self.subplots, results):
            p.plot([r])
            self.legends.extend(p.do_legend())
