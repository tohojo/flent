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

import inspect
import io
import re

from flent import combiners
from flent.util import cum_prob, frange, classname, long_substr, format_date, \
    Glob, Update, float_pair, keyval, comma_list, ArgParam, ArgParser
from flent.build_info import VERSION
from flent.loggers import get_logger

from functools import reduce
from itertools import cycle, islice
from collections import OrderedDict

try:
    import matplotlib
    import numpy
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# Python 2/3 compatibility
try:
    unicode
    PY2 = True
except NameError:
    unicode = str
    PY2 = False

logger = get_logger(__name__)

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

if PY2:
    # Matplotlib will tend to pass the values directly to backends where they
    # will be converted into native types. This breaks on some versions of
    # matplotlib running on Python 2 if the values are unicode objects (which
    # can't always be automatically converted). To work around this, encode
    # everything if we are running on Python 2.

    def filt(x):
        try:
            return x.encode()
        except AttributeError:
            return x

    LINESTYLES = list(map(filt, LINESTYLES))
    MARKERS = list(map(filt, LINESTYLES))
    COLOURS = list(map(filt, COLOURS))

    for k, v in MATPLOTLIB_STYLES.items():
        MATPLOTLIB_STYLES[k] = filt(v)

    del filt


def init_matplotlib(output, use_markers, load_rc):
    if not HAS_MATPLOTLIB:
        raise RuntimeError(
            "Unable to plot -- matplotlib is missing! "
            "Please install it if you want plots.")
    global pyplot, COLOURS, MATPLOTLIB_INIT

    if MATPLOTLIB_INIT:
        return

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
    matplotlib.rcParams['figure.max_open_warning'] = 0
    if load_rc:
        matplotlib.rcParams.update(MATPLOTLIB_STYLES)
    elif 'axes.prop_cycle' in matplotlib.rcParams:
        c = matplotlib.rcParams['axes.prop_cycle']
        if 'color' in c.keys:
            COLOURS = c.by_key()['color']
    else:
        COLOURS = matplotlib.rcParams['axes.color_cycle']

    MATPLOTLIB_INIT = True
    logger.debug("Initialised matplotlib v%s on numpy v%s.",
                 matplotlib.__version__, numpy.__version__)


def get_plotconfig(settings, plot=None):
    if plot is None:
        plot = settings.PLOT
    if plot not in settings.PLOTS:
        raise RuntimeError("Unable to find plot configuration '%s'." % plot)
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
    parser.add_argument(
        "-z", "--zero-y",
        action="store_true", dest="ZERO_Y",
        help="Always start y axis of plot at zero, instead of auto-scaling the "
        "axis (also disables log scales). Auto-scaling is still enabled for the "
        "upper bound.")

    parser.add_argument(
        "--bounds-x",
        action="append", dest="BOUNDS_X", type=float_pair, default=[],
        help="Specify bounds of the plot X axis. If specifying one number, "
        "that will become the upper bound. Specify two numbers separated by "
        "a comma to specify both upper and lower bounds. To specify just the "
        "lower bound, add a comma afterwards. Can be specified twice, "
        "corresponding to figures with multiple axes.")

    parser.add_argument(
        "--bounds-y",
        action="append", dest="BOUNDS_Y", type=float_pair, default=[],
        help="Specify bounds of the plot Y axis. If specifying one number, "
        "that will become the upper bound. Specify two numbers separated by "
        "comma to specify both upper and lower bounds. To specify just the "
        "lower bound, add a comma afterwards. Can be specified twice, "
        "corresponding to figures with multiple axes.")

    parser.add_argument(
        "--label-x",
        action="append", dest="LABEL_X", default=[],
        help="Override the X axis label. "
        "Can be specified twice, corresponding to figures with multiple axes.")

    parser.add_argument(
        "--label-y",
        action="append", dest="LABEL_Y", default=[],
        help="Override the Y axis label. "
        "Can be specified twice, corresponding to figures with multiple axes.")

    parser.add_argument(
        "--colours",
        action="store", dest="COLOURS", type=comma_list, default=COLOURS,
        help="Comma-separated list of colours to be used for the plot colour "
        "cycle.")

    parser.add_argument(
        "-I", "--invert-latency-y",
        action="store_true", dest="INVERT_Y",
        help="Invert the y-axis for latency data series (making plots show "
        "'better' values upwards).")

    parser.add_argument(
        "--log-scale",
        action="store_true", dest="LOG_SCALE",
        help="Use logarithmic scale on plots.")

    parser.add_argument(
        "--norm-factor",
        action="append", type=float, dest="NORM_FACTORS", metavar="FACTOR",
        default=[], help="Factor to normalise data by. I.e. divide all data "
        "points by this value. Can be specified multiple times, in which case "
        "each value corresponds to a data series.")

    parser.add_argument(
        "--scale-data",
        action="append", type=unicode, dest="SCALE_DATA", default=[],
        help="Additional data files to consider when scaling the plot axes "
        "(for plotting several plots with identical axes). Note, this displays "
        "only the first data set, but with axis scaling taking into account the "
        "additional data sets. Can be supplied multiple times; see also "
        "--scale-mode.")

    parser.add_argument(
        "-S", "--scale-mode",
        action="store_true", dest="SCALE_MODE",
        help="Treat file names (except for the first one) passed as unqualified "
        "arguments as if passed as --scale-data (default as if passed as "
        "--input).")

    parser.add_argument(
        "--concatenate",
        action="store_true", dest="CONCATENATE",
        help="Concatenate multiple result sets into one data series.")

    parser.add_argument(
        "--absolute-time",
        action="store_true", dest="ABSOLUTE_TIME",
        help="Plot data points with absolute Unix time on the x-axis.")

    parser.add_argument(
        "--subplot-combine",
        action="store_true", dest="SUBPLOT_COMBINE",
        help="When plotting multiple data series, plot each one on a separate "
        "subplot instead of combining them into one plot (not supported for all "
        "plot types).")

    parser.add_argument(
        "--no-print-n",
        action="store_false", dest="COMBINE_PRINT_N",
        help="Do not print the number of data points on combined plots.")

    parser.add_argument(
        "--no-annotation",
        action="store_false", dest="ANNOTATE",
        help="Exclude annotation with hostnames, time and test length from "
        "plots.")

    parser.add_argument(
        "--no-title",
        action="store_false", dest="PRINT_TITLE",
        help="Exclude title from plots.")

    parser.add_argument(
        "--override-title",
        action="store", type=unicode, dest="OVERRIDE_TITLE", metavar="TITLE",
        help="Override plot title with this string. This parameter takes "
        "precedence over --no-title.")

    parser.add_argument(
        "--override-label",
        action="append", type=unicode, dest="OVERRIDE_LABELS", metavar="LABEL",
        default=[],
        help="Override dataset label. Must be specified multiple times "
        "corresponding to the datasets being overridden.")

    parser.add_argument(
        "--override-group-by",
        action="store", type=unicode, dest="OVERRIDE_GROUP_BY", metavar="GROUP",
        help="Override plot group_by attribute for combination plots.")

    parser.add_argument(
        "--combine-save-dir",
        action="store", type=unicode, dest="COMBINE_SAVE_DIR",
        metavar="DIRNAME",
        help="When doing a combination plot save the intermediate data "
        "to DIRNAME. This can then be used for subsequent plotting to "
        "avoid having to load all the source data files again on each plot.")

    parser.add_argument(
        "--split-group",
        action="append", type=unicode, dest="SPLIT_GROUPS", default=[],
        metavar="LABEL",
        help="Split data sets into groups. Specify this option multiple "
        "times to define the new groups. The value of each option is the "
        "group name. This only works for box plots.")

    parser.add_argument(
        "--no-markers",
        action="store_false", dest="USE_MARKERS",
        help="Don't use line markers to differentiate data series on plots.")

    parser.add_argument(
        "--no-legend",
        action="store_false", dest="PRINT_LEGEND",
        help="Exclude legend from plots.")

    parser.add_argument(
        "--horizontal-legend",
        action="store_true", dest="HORIZONTAL_LEGEND",
        help="Place a horizontal legend below the plot instead of a vertical one "
        "next to it. Doesn't work well if there are too many items in the "
        "legend.")

    parser.add_argument(
        "--legend-title",
        action="store", dest="LEGEND_TITLE",
        help="Override legend title on plot.")

    parser.add_argument(
        "--legend-placement",
        action="store", dest="LEGEND_PLACEMENT",
        help="Control legend placement. Enabling this option will place the "
        "legend inside the plot at the specified location. Use 'best' to let "
        "matplotlib decide.")

    parser.add_argument(
        "--legend-columns",
        action="store", type=int, dest="LEGEND_COLUMNS",
        help="Set the number of columns in the legend.")

    parser.add_argument(
        "--filter-legend",
        action="store_true", dest="FILTER_LEGEND",
        help="Filter legend labels by removing the longest common substring from "
        "all entries.")

    parser.add_argument(
        "--filter-regexp",
        action="append", dest="FILTER_REGEXP", metavar="REGEXP", default=[],
        help="Filter out supplied regular expression from legend names. Can be "
        "specified multiple times, in which case the regular expressions will be "
        "filtered in the order specified.")

    parser.add_argument(
        "--filter-series",
        action="append", dest="FILTER_SERIES", metavar="SERIES", default=[],
        help="Filter out specified series from plot. Can be specified multiple "
        "times.")

    parser.add_argument(
        "--skip-missing-series",
        action="store_true", dest="SKIP_MISSING",
        help="Skip missing series entirely from plots. Only works for bar plots.")

    parser.add_argument(
        "--replace-legend",
        action=Update, type=keyval, dest="REPLACE_LEGEND", metavar="src=dest",
        default=OrderedDict(),
        help="Replace 'src' with 'dst' in legends. Can be specified multiple "
        "times.")

    parser.add_argument(
        "--figure-width", "--fig-width",
        action="store", type=float, dest="FIG_WIDTH",
        help="Figure width in inches. Used when saving plots to file and for "
        "default size of the interactive plot window.")

    parser.add_argument(
        "--figure-height", "--fig-height",
        action="store", type=float, dest="FIG_HEIGHT",
        help="Figure height in inches. Used when saving plots to file and for "
        "default size of the interactive plot window.")

    parser.add_argument(
        "--figure-dpi", "--fig-dpi",
        action="store", type=float, dest="FIG_DPI",
        help="Figure DPI. Used when saving plots to raster format files.")

    parser.add_argument(
        "--figure-note", "--fig-note",
        action="store", type=unicode, dest="FIG_NOTE",
        help="Figure note. Will be added to the bottom-left corner of the "
        "figure.")

    parser.add_argument(
        "--no-matplotlibrc",
        action="store_false", dest="LOAD_MATPLOTLIBRC",
        help="Don't use included matplotlib styles. Use this if you have "
        "configured custom matplotlib styles that you want Flent to use.")

    parser.add_argument(
        "--no-hover-highlight",
        action="store_false", dest="HOVER_HIGHLIGHT", default=None,
        help="Don't highlight data series on hover in interactive plot views. "
        "Use this if redrawing is too slow, or the highlighting is undesired "
        "for other reasons.")

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
            description=settings.DESCRIPTION,
            in_worker=in_worker,

            **kwargs)
    except Exception as e:
        raise RuntimeError("Error loading plotter: %s" % e)


def draw_worker(settings, results):
    plotter = new(settings, in_worker=True)
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
                 in_worker=False,
                 **kwargs):
        super(Plotter, self).__init__(**kwargs)

        self.disable_cleanup = False
        self.title = None
        self.output = output
        self.styles = STYLES
        self.legends = []
        self.artists = []
        self.data_artists = []
        self.metadata = None
        self.callbacks = []
        self.in_worker = in_worker

        self.gui = gui
        self.description = description

        self.interactive_callback = self.resize_callback = None
        if self.hover_highlight is not None:
            self.can_highlight = self.hover_highlight

        self.config = self.expand_plot_config(plot_config, data_config)
        self.configs = [self.config]
        self.data_config = data_config

        if figure is None:
            self.figure = pyplot.figure()
            if self.fig_width is not None:
                self.figure.set_figwidth(self.fig_width)
            if self.fig_height is not None:
                self.figure.set_figheight(self.fig_height)
        else:
            self.figure = figure

    def __del__(self):
        if not self.disable_cleanup:
            try:
                pyplot.close(self.figure)
            except Exception:
                pass

    def init(self, config=None, axis=None):
        if config is not None:
            self.config = config
        self.configs = [self.config]

    def expand_plot_config(self, config, data):
        if 'series' not in config:
            return config
        new_series = []
        for s in config['series']:
            if isinstance(s['data'], Glob):
                for d in Glob.expand_list(s['data'], data.keys()):
                    if 'label' in s and 'id' in data[d]:
                        ns = dict(s, data=d, id=data[d]['id'],
                                  label='%s -- %s' % (s['label'], data[d]['id']))
                        if 'parent_id' in data[d]:
                            ns['parent_id'] = data[d]['parent_id']
                        new_series.append(ns)
                    else:
                        new_series.append(dict(s, data=d))
            else:
                new_series.append(s)
        if self.filter_series:
            new_series = [s for s in new_series if not s[
                'data'] in self.filter_series]
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
        all_legends = []
        if not self.legends:
            for c in self.configs:
                legends = self._do_legend(c)
                if legends:
                    all_legends += legends

        artists += all_legends + self._annotate_plot(skip_title)
        self.legends.extend(all_legends)

        # Since outputting image data to stdout does not make sense, we launch
        # the interactive matplotlib viewer if stdout is set for output.
        # Otherwise, the filename is passed to matplotlib, which selects an
        # appropriate output format based on the file name.
        if self.output == "-":
            self.size_legends()
            if not self.gui:
                pyplot.show()
        else:
            try:
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

        self.update_axes(hovered)

    def update_axes(self, hovered):
        bboxes = set()

        for ax in reduce(lambda x, y: x + y, [i['axes'] for i in self.configs]):
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
            try:
                a.axes.draw_artist(a)
            except AttributeError:
                pass
            a.set_linewidth(self.highlight_widths[a][0])

        for bbox in bboxes:
            self.figure.canvas.blit(bbox)

    def clear_bg_cache(self, evt=None):
        self.bg_cache = {}

    def save_pdf(self, filename, data_filename, save_args):
        with matplotlib.backends.backend_pdf.PdfPages(filename) as pdf:
            pdf.infodict()['Producer'] = 'Flent v%s' % VERSION
            pdf.infodict()['Subject'] = data_filename
            if self.title:
                pdf.infodict()['Title'] = self.title.replace("\n", "; ")
            self.figure.savefig(pdf, dpi=self.fig_dpi, **save_args)

    def build_tight_layout(self, artists):
        rect = [0, 0, 1, 1]
        args = None
        try:
            # Some plot configurations are incompatible with tight_layout; this
            # test is from matplotlib's tight_layout() in figure.py
            from matplotlib.tight_layout import get_subplotspec_list
            if None not in get_subplotspec_list(self.figure.axes):
                self.figure.savefig(io.BytesIO())
                renderer = self.figure._cachedRenderer
                fig_bbox = self.figure.get_tightbbox(renderer)
                if self.legends and not self.legend_placement:
                    if self.horizontal_legend:
                        legend_height = max(
                            [l.get_window_extent().height
                             for l in self.legends]) / self.figure.dpi
                        rect[1] = legend_height / fig_bbox.height
                    else:
                        legend_width = max(
                            [l.get_window_extent().width
                             for l in self.legends]) / self.figure.dpi
                        rect[2] = max(0.5, 1 - legend_width / fig_bbox.width)

                if self.annotation_obj:
                    annotation_height = self.annotation_obj.get_window_extent(
                        renderer).height / self.figure.dpi
                    rect[1] = max(rect[1], annotation_height / fig_bbox.height)

                if self.note_obj:
                    note_height = self.note_obj.get_window_extent(
                        renderer).height / self.figure.dpi
                    rect[1] = max(rect[1], note_height / fig_bbox.height)

                if self.title_obj:
                    title_height = self.title_obj.get_window_extent(
                        renderer).height / self.figure.dpi
                    rect[3] = 1 - title_height / fig_bbox.height

                self.figure.tight_layout(pad=0.5, rect=rect)
                args = {}
        except (AttributeError, ImportError):
            pass
        # Fall back to the regular bbox_extra_artists output feature
        if args is None:
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
            legend_width = max(
                [l.get_window_extent().width for l in self.legends])

            if not legend_width:  # Legend width is not set before it's drawn
                self.figure.canvas.draw()
                legend_width = max(
                    [l.get_window_extent().width for l in self.legends])

            canvas_width = self.figure.canvas.get_width_height()[0]
            for a in reduce(lambda x, y: x + y,
                            [i['axes'] for i in self.configs]):
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
        title_y = 1
        if self.override_title:
            self.title_obj = self.figure.suptitle(self.override_title,
                                                  fontsize=14, y=title_y)
            titles.append(self.title_obj)
            self.title = self.override_title
        elif self.print_title:
            plot_title = self.description
            if 'description' in self.config:
                plot_title += "\n" + self.config['description']
            if self.metadata['TITLE'] and not skip_title:
                plot_title += "\n" + self.metadata['TITLE']
            if 'description' in self.config \
               and self.metadata['TITLE'] \
               and not skip_title:
                title_y = 1.00
            self.title_obj = self.figure.suptitle(
                plot_title, fontsize=14, y=title_y)
            titles.append(self.title_obj)
            self.title = plot_title
        else:
            self.title_obj = None

        if self.annotate:
            annotation_string = "Local/remote: %s/%s - " \
                                "Time: %s - Length/step: %ds/%.2fs" % (
                                    self.metadata['LOCAL_HOST'],
                                    self.metadata['HOST'],
                                    format_date(self.metadata['TIME']),
                                    self.metadata['LENGTH'],
                                    self.metadata['STEP_SIZE'])
            self.annotation_obj = self.figure.text(0.5, 0.0, annotation_string,
                                                   horizontalalignment='center',
                                                   verticalalignment='bottom',
                                                   fontsize=8)
        else:
            self.annotation_obj = None

        if self.fig_note:
            self.note_obj = self.figure.text(0.0, 0.0, self.fig_note,
                                             horizontalalignment='left',
                                             verticalalignment='bottom',
                                             fontsize=8)
            titles.append(self.note_obj)
        else:
            self.note_obj = None
        return titles

    def _filter_labels(self, labels):
        for s, d in self.replace_legend.items():
            labels = [l.replace(s, d) for l in labels]
        for r in self.filter_regexp:
            labels = [re.sub(r, "", l) for l in labels]
        if self.filter_legend and labels:
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

        labels = self._filter_labels(labels)

        kwargs = {}
        if self.legend_title is not None:
            kwargs['title'] = self.legend_title
        elif 'legend_title' in config:
            kwargs['title'] = config['legend_title']

        if len(axes) > 1:
            offset_x = 1.11
        else:
            offset_x = 1.02

        legends = []
        if self.horizontal_legend:
            bbox = (0.5, -0.15)
            ncol = len(labels)
            loc = 'upper center'
        elif self.legend_placement:
            bbox = None
            ncol = 1
            loc = self.legend_placement
        else:
            bbox = (offset_x, 1.0)
            ncol = 1
            loc = 'upper left'
        l = axes[0].legend(handles, labels,
                           bbox_to_anchor=bbox,
                           loc=loc, borderaxespad=0.,
                           prop={'size': 'small'},
                           ncol=self.legend_columns or ncol,
                           **kwargs)

        # Work around a bug in older versions of matplotlib where the
        # legend.get_window_extent method does not take any arguments, leading
        # to a crash when using bbox_extra_artists when saving the figure
        #
        # Simply check for either the right number of args, or a vararg
        # specification, and if they are not present, attempt to monkey-patch
        # the method if it does not accept any arguments.
        a, v, _, _ = inspect.getargspec(l.get_window_extent)
        if not self.in_worker and len(a) < 2 or v is None:
            def get_window_extent(*args, **kwargs):
                return l.legendPatch.get_window_extent(*args, **kwargs)
            l.get_window_extent = get_window_extent
        legends.append(l)
        return legends

    def _do_scaling(self, axis, data, btm, top, unit=None, allow_log=True):
        """Scale the axis to the selected bottom/top percentile"""
        data = [x for x in data if x is not None]
        if not data:
            return

        top_percentile = self._percentile(data, top)
        btm_percentile = self._percentile(data, btm)

        if top_percentile == btm_percentile:
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
            axis.set_ylim(ymin=0, ymax=top_scale)
        else:
            if self.log_scale:
                axis.set_yscale('log')
                axis.set_ylim(ymin=max(0, btm_scale), ymax=top_scale)
            else:
                axis.set_ylim(ymin=btm_scale, ymax=top_scale)

        if self.invert_y and unit in self.inverted_units:
            axis.invert_yaxis()

    def _percentile(self, lst, q):
        """Primitive percentile calculation for axis scaling.

        Implemented here since old versions of numpy don't include
        the percentile function."""
        q = int(q)
        if q == 0:
            return min(lst)
        elif q == 100:
            return max(lst)
        elif q < 0 or q > 100:
            raise ValueError("Invalid percentile: %s" % q)
        idx = int(len(lst) * (q / 100.0))
        return numpy.sort(lst)[idx]


class CombineManyPlotter(object):

    def plot(self, results, config=None, axis=None, connect_interactive=True):
        if self.metadata is None:
            self.metadata = results[0].meta()
        if config is None:
            config = self.config

        combine_mode = self.override_group_by or config.get('group_by', 'groups')
        combiner = combiners.new(combine_mode, print_n=self.combine_print_n,
                                 filter_regexps=self.filter_regexp,
                                 filter_series=self.filter_series,
                                 save_dir=self.combine_save_dir)
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
            if unit[a] is not None and s_unit != unit[a]:
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

        xlim = axis.get_xlim()
        axis.set_xlim(
            min(results.x_values + [xlim[0]]
                ) if xlim[0] > 0 else min(results.x_values),
            max(results.x_values + [self.metadata['TOTAL_LENGTH'], xlim[1]])
        )

        if self.norm_factors:
            norms = list(islice(cycle(self.norm_factors), len(config['series'])))
        else:
            norms = None

        data = []
        for i in range(len(config['axes'])):
            data.append([])

        colours = cycle(self.colours)

        if stack:
            sums = numpy.zeros(len(results.x_values))

        for i, s in enumerate(config['series']):
            if not s['data'] in results.series_names:
                continue
            if 'smoothing' in s:
                smooth = s['smoothing']
            else:
                smooth = False
            kwargs = {}
            for k in PLOT_KWARGS:
                if k in s:
                    kwargs[k] = s[k]

            if 'label' in kwargs:
                kwargs['label'] += postfix

            if 'color' not in kwargs:
                kwargs['color'] = next(colours)

            kwargs.update(extra_kwargs)

            y_values = results.series(s['data'], smooth)
            if norms is not None:
                y_values = [y / norms[i] if y is not None else None
                            for y in y_values]
            if 'axis' in s and s['axis'] == 2:
                a = 1
            else:
                a = 0

            if stack:
                kwargs['facecolor'] = kwargs['color']
                del kwargs['color']
                y_values = numpy.array(y_values, dtype=float)

                config['axes'][a].fill_between(
                    results.x_values, sums, y_values + sums, **kwargs)
                sums += y_values
            else:
                data[a] += y_values
                for r in self.scale_data + extra_scale_data:
                    data[a] += r.series(s['data'], smooth)
                self.data_artists.extend(config['axes'][a].plot(results.x_values,
                                                                y_values,
                                                                **kwargs))

        if 'scaling' in config:
            btm, top = config['scaling']
        else:
            btm, top = 0, 100

        for a in range(len(config['axes'])):
            if data[a]:
                self._do_scaling(config['axes'][a], data[
                                 a], btm, top, config['units'][a])

            # Handle cut-off data sets. If the x-axis difference between the
            # largest data point and the TOTAL_LENGTH from settings, scale to
            # the data values, but round to nearest 10 above that value.
            try:
                max_xdata = max([l.get_xdata()[-1]
                                 for l in config['axes'][a].get_lines()])
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

        if self.split_groups:
            if len(results) % len(self.split_groups) > 0:
                raise RuntimeError(
                    "Split groups only works when the number of results "
                    "is divisible by the number of groups.")
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

        # The median lines are red, so filter out red from the list of colours
        colours = list(
            islice(cycle([c for c in self.colours if c != 'r']), group_size))

        if self.norm_factors:
            norms = list(islice(cycle(self.norm_factors), len(config['series'])))
        else:
            norms = None

        for i, s in enumerate(series):
            if split_results:
                results = split_results[i]
            if 'axis' in s and s['axis'] == 2:
                a = 1
            else:
                a = 0

            data = []
            for r in results:
                d = [d for d in r.series(s['data']) if d is not None]
                if norms is not None:
                    d = [di / norms[i] for di in d]
                all_data[a].extend(d)
                if not d:
                    data.append([0.0])
                else:
                    data.append(d)

            if 'label' in s:
                ticklabels.append(s['label'])
            else:
                ticklabels.append(i)

            positions = range(pos, pos + group_size)
            ticks.append(numpy.mean(positions))

            bp = config['axes'][a].boxplot(data,
                                           positions=positions)
            for j, r in enumerate(results):
                pyplot.setp(bp['boxes'][j], color=colours[j])
                if i == 0 and group_size > 1:
                    bp['caps'][j * 2].set_label(r.label())
                if len(bp['fliers']) == group_size:
                    pyplot.setp([bp['fliers'][j]], markeredgecolor=colours[j])
                    keys = 'caps', 'whiskers'
                else:
                    keys = 'caps', 'whiskers', 'fliers'
                for k in keys:
                    if bp[k]:
                        pyplot.setp(bp[k][j * 2], color=colours[j])
                        pyplot.setp(bp[k][j * 2 + 1], color=colours[j])

            config['axes'][a].axvline(
                x=pos + group_size, color='black', linewidth=0.5, linestyle=':')
            pos += group_size + 1
        for i, a in enumerate(config['axes']):
            self._do_scaling(a, all_data[i], 0, 100, config[
                             'units'][i], allow_log=False)

        for a, b in zip(config['axes'], self.bounds_y):
            a.set_ybound(b)

        axis.set_xticks(ticks)
        axis.set_xticks([], minor=True)
        axis.set_xticklabels(self._filter_labels(ticklabels))
        axis.set_xlim(0, pos - 1)


class BoxCombinePlotter(CombineManyPlotter, BoxPlotter):
    pass


class BarPlotter(BoxPlotter):
    # Since labels are printed vertically at the bottom, they tend to break
    # matplotlib's layout logic if they're too long.
    _max_label_length = 30

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

        # The error bars lines are black, so filter out black from the list of
        # colours
        colours = list(
            islice(cycle([c for c in self.colours if c != errcol]),
                   len(config['series'])))

        labels = self._filter_labels([r.label() for r in results])
        series_labels = self._filter_labels(
            [s['label'] for s in config['series']])
        texts = []

        if self.norm_factors:
            norms = list(islice(cycle(self.norm_factors), len(config['series'])))
        else:
            norms = None

        for i, s in enumerate(config['series']):
            if 'axis' in s and s['axis'] == 2:
                a = 1
            else:
                a = 0

            data = []
            errors = []
            for r in results:
                dp = [d for d in r.series(s['data']) if d is not None]
                if norms is not None:
                    dp = [d / norms[i] for d in dp]
                if not dp and not self.skip_missing:
                    data.append(0.0)
                    errors.append(0.0)
                    all_data[a].append(0.0)
                elif dp:
                    dp = numpy.array(dp)
                    data.append(dp.mean())
                    errors.append(dp.std())
                    all_data[a].append(data[-1] + errors[-1])
                    all_data[a].append(data[-1] - errors[-1])

            group_size = len(data)

            positions = [p - width / 2.0 for p in range(pos, pos + group_size)]
            ticks.extend(list(range(pos, pos + group_size)))
            ticklabels.extend(labels)
            if config.get('colour_by', 'groups') == 'groups':
                colour = colours[i]
            else:
                colour = self.colours[:len(data)]

            config['axes'][a].bar(positions, data, yerr=errors, ecolor=errcol,
                                  color=colour, alpha=0.75, width=width,
                                  align='edge')
            if len(config['series']) > 1 or self.print_title:
                texts.append(config['axes'][0].text(
                    pos + group_size / 2.0 - 0.5,
                    14,
                    series_labels[i],
                    ha='center'))

            config['axes'][a].axvline(
                x=pos + group_size, color='black', linewidth=0.5, linestyle=':')
            pos += group_size + 1

        for a, b in zip(config['axes'], self.bounds_y):
            a.set_ybound(b)

        min_y, max_y = config['axes'][0].get_ylim()

        for t in texts:
            x, y = t.get_position()
            t.set_position((x, max_y + abs(max_y - min_y) * 0.01))

        for i, l in enumerate(ticklabels):
            if len(l) > self._max_label_length:
                ticklabels[i] = l[:self._max_label_length] + "..."

        axis.set_xticks(ticks)
        axis.set_xticks([], minor=True)
        axis.set_xticklabels(ticklabels, rotation=90, ha='center')
        axis.set_xlim(0, pos - 1)

        self.artists.extend(texts)


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
        self.medians = []
        self.min_vals = []

    def _plot(self, results, config=None, axis=None, postfix="",
              extra_kwargs={}, extra_scale_data=[]):
        if config is None:
            config = self.config
        if axis is None:
            axis = config['axes'][0]

        colours = cycle(self.colours)
        data = []
        sizes = []
        max_value = 0.0
        for s in config['series']:
            if not s['data'] in results.series_names:
                data.append([])
                continue
            s_data = results.series(s['data'])
            if 'cutoff' in config and config['cutoff']:
                # cut off values from the beginning and end before doing the
                # plot; for e.g. pings that run long than the streams, we don't
                # want the unloaded ping values
                start, end = config['cutoff']
                end = int((self.metadata['TOTAL_LENGTH'] -
                           end) / self.metadata['STEP_SIZE'])
                start = int(start / self.metadata['STEP_SIZE'])
                if end == 0:
                    end = None
                s_data = s_data[start:end]
            sizes.append(float(len(s_data)))
            d = sorted([x for x in s_data if x is not None])
            data.append(d)
            if d:
                self.medians.append(numpy.median(d))
                self.min_vals.append(min(d))
                max_value = max([max_value] + d)

                for r in self.scale_data + extra_scale_data:
                    d_s = [x for x in r.series(s['data']) if x is not None]
                    if d_s:
                        max_value = max([max_value] + d_s)

        if max_value > 10:
            # round up to nearest value divisible by 10
            max_value += 10 - (max_value % 10)
        axis.set_xlim(right=max_value)

        for i, s in enumerate(config['series']):
            if not data[i]:
                continue
            max_val = max(data[i])
            min_val = min(data[i])
            step = (max_val - min_val) / 1000.0 if min_val != max_val else 1.0
            x_values = list(frange(min_val - 2 * step, max_val + 2 * step, step))
            kwargs = {}
            for k in PLOT_KWARGS:
                if k in s:
                    kwargs[k] = s[k]
            if 'label' in kwargs:
                kwargs['label'] += postfix
            if 'color' not in kwargs:
                kwargs['color'] = next(colours)
            kwargs.update(extra_kwargs)
            y_values = [cum_prob(data[i], point, sizes[i]) for point in x_values]
            if 1.0 in y_values:
                idx_1 = y_values.index(1.0) + 1
            else:
                idx_1 = len(y_values)
            idx_0 = 0
            while y_values[idx_0 + 1] == 0.0:
                idx_0 += 1

            x_vals, y_vals = self._filter_dup_vals(
                x_values[idx_0:idx_1], y_values[idx_0:idx_1])
            self.data_artists.extend(axis.plot(x_vals,
                                               y_vals,
                                               **kwargs))

        if self.zero_y:
            axis.set_xlim(left=0)
        elif self.min_vals:
            min_val = min(self.min_vals)
            if min_val > 10:
                min_val -= min_val % 10  # nearest value divisible by 10
            if min_val > 100:
                min_val -= min_val % 100
            axis.set_xlim(left=min_val)

        if self.log_scale:
            # More than an order of magnitude difference; switch to log scale
            axis.set_xscale('log')

        for a, b in zip(config['axes'], self.bounds_x):
            a.set_xbound(b)

    def _filter_dup_vals(self, x_vals, y_vals):
        """Filter out series of identical y-vals, also removing the corresponding
        x-vals.

        Lowers the amount of plotted points and avoids strings of markers on
        CDFs.

        """
        x_vals = list(x_vals)
        y_vals = list(y_vals)
        i = 0
        while i < len(x_vals) - 2:
            while (i < len(y_vals) - 2 and
                   y_vals[i] == y_vals[i + 1] and
                   y_vals[i] == y_vals[i + 2]):
                del x_vals[i + 1]
                del y_vals[i + 1]
            i += 1
        return x_vals, y_vals


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
            raise RuntimeError("Can't do Q-Q plot with more than one series.")

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
        x_values = numpy.sort([r for r in x if r is not None])
        y_values = numpy.sort([r for r in y if r is not None])

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
            y_values = numpy.interp(numpy.linspace(0, len(y_values),
                                                   num=len(x_values),
                                                   endpoint=False),
                                    range(len(y_values)), y_values)

        elif len(y_values) < len(x_values):
            x_values = numpy.interp(numpy.linspace(0, len(x_values),
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
            raise RuntimeError("Unable to load error_ellipse plotting functions.")

        if axis is None:
            axis = self.figure.gca()
        if config is None:
            config = self.config

        if len(config['series']) < 2:
            raise RuntimeError(
                "Can't do ellipsis plots with less than two series.")

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

        x_values = results.series(series[0]['data'])

        for s in series[1:]:
            data = [i for i in zip(x_values, results.series(s['data'])) if i[
                0] is not None and i[1] is not None]
            if len(data) < 2:
                points = numpy.array(data * 2)
            else:
                points = numpy.array(data)
            x_values, y_values = zip(*data)
            el = self.plot_point_cov(points, ax=axis, alpha=0.5, **carg)
            med = numpy.median(points, axis=0)
            self.xvals.append(el.center[0] - el.width / 2)
            self.xvals.append(el.center[0] + el.width / 2)
            self.yvals.append(el.center[1] - el.height / 2)
            self.yvals.append(el.center[1] + el.height / 2)
            self.xvals.append(med[0])
            self.yvals.append(med[1])
            axis.plot(*med, marker='o', linestyle=" ", **carg)
            axis.annotate(label, med, ha='center', annotation_clip=True,
                          xytext=(0, 8), textcoords='offset points')

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
            cfg = self.expand_plot_config(cfg, self.data_config)
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
                "This plot type does not work with --subplot-combine.")
        MetaPlotter.init(self, config)

    def plot(self, results, connect_interactive=True):
        if self.metadata is None:
            self.metadata = results[0].meta()
        self._init(len(results))
        for s, r in zip(self.subplots, results):
            s.plot([r])
            self.legends.extend(s.do_legend())
