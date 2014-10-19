## -*- coding: utf-8 -*-
##
## formatters.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     16 October 2012
## Copyright (c) 2012, Toke Høiland-Jørgensen
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

import json, sys, csv, math, inspect, os, re

from .util import cum_prob, frange, classname, long_substr
from .resultset import ResultSet
from .build_info import DATA_DIR, VERSION
from functools import reduce
from itertools import product,cycle,islice
try:
    from itertools import izip_longest as zip_longest
except ImportError:
    from itertools import zip_longest
try:
    from collections import OrderedDict
except ImportError:
    from netperf_wrapper.ordereddict import OrderedDict

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

def new(settings):
    formatter_name = classname(settings.FORMAT, 'Formatter')
    if not formatter_name in globals():
        raise RuntimeError("Formatter not found: '%s'." % settings.FORMAT)
    try:
        return globals()[formatter_name](settings)
    except Exception as e:
        raise RuntimeError("Error loading %s: %r." % (formatter_name, e))


class Formatter(object):

    open_mode = "w"

    def __init__(self, settings):
        self.settings = settings
        self.check_output(self.settings.OUTPUT)

    def check_output(self, output):
        if hasattr(output, 'read') or output == "-":
            self.output = output
        else:
            # This logic is there to ensure that:
            # 1. If there is no write access, fail before running the tests.
            # 2. If the file exists, do not open (and hence overwrite it) until after the
            #    tests have run.
            if os.path.exists(output):
                # os.access doesn't work on non-existant files on FreeBSD; so only do the
                # access check on existing files (to avoid overwriting them before the tests
                # have completed).
                if not os.access(output, os.W_OK):
                    raise RuntimeError("No write permission for output file '%s'" % output)
                else:
                    self.output = output
            else:
                # If the file doesn't exist, just try to open it immediately; that'll error out
                # if access is denied.
                try:
                    self.output = open(output, self.open_mode)
                except IOError as e:
                    raise RuntimeError("Unable to open output file: '%s'" % e)

    def open_output(self):
        output = self.output
        if hasattr(output, 'read'):
            return
        if output == "-":
            self.output = sys.stdout
        else:
            try:
                self.output = open(output, self.open_mode)
            except IOError as e:
                raise RuntimeError("Unable to output data: %s" % e)

    def format(self, results):
        if results[0].dump_file is not None:
            sys.stderr.write("No output formatter selected.\nTest data is in %s (use with -i to format).\n" % results[0].dump_file)

class NullFormatter(Formatter):
    def check_output(self, output):
        pass
    def format(self, results):
        pass

DefaultFormatter = Formatter

class TableFormatter(Formatter):

    def get_header(self, results):
        name = results[0].meta("NAME")
        keys = list(set(reduce(lambda x,y:x+y, [r.series_names for r in results])))
        header_row = [name]

        if len(results) > 1:
            for r in results:
                header_row += [k + ' - ' + r.label() for k in keys]
        else:
            header_row += keys
        return header_row

    def combine_results(self, results):
        """Generator to combine several result sets into one list of rows, by
        concatenating them."""
        keys = list(set(reduce(lambda x,y:x+y, [r.series_names for r in results])))
        for row in list(zip(*[list(r.zipped(keys)) for r in results])):
            out_row = [row[0][0]]
            for r in row:
                if r[0] != out_row[0]:
                    raise RuntimeError("x-value mismatch: %s/%s. Incompatible data sets?" % (out_row[0], r[0]))
                out_row += r[1:]
            yield out_row


class OrgTableFormatter(TableFormatter):
    """Format the output for an Org mode table. The formatter is pretty crude
    and does not align the table properly, but it should be sufficient to create
    something that Org mode can correctly realign."""

    def format(self, results):
        self.open_output()
        name = results[0].meta("NAME")

        if not results[0]:
            self.output.write(str(name) + " -- empty\n")
            return
        header_row = self.get_header(results)
        self.output.write("| " + " | ".join(header_row) + " |\n")
        self.output.write("|-" + "-+-".join(["-"*len(i) for i in header_row]) + "-|\n")

        def format_item(item):
            if isinstance(item, float):
                return "%.2f" % item
            return str(item)

        for row in self.combine_results(results):
            self.output.write("| ")
            self.output.write(" | ".join(map(format_item, row)))
            self.output.write(" |\n")



class CsvFormatter(TableFormatter):
    """Format the output as csv."""

    def format(self, results):
        self.open_output()
        if not results[0]:
            return

        writer = csv.writer(self.output)
        header_row = self.get_header(results)
        writer.writerow(header_row)

        def format_item(item):
            if item is None:
                return ""
            return str(item)

        for row in self.combine_results(results):
            writer.writerow(list(map(format_item, row)))

class StatsFormatter(Formatter):

    def __init__(self, settings):
        Formatter.__init__(self, settings)
        try:
            import numpy
            self.np = numpy
        except ImportError:
            raise RuntimeError("Stats formatter requires numpy, which seems to be missing. Please install it and try again.")

    def format(self, results):
        self.open_output()
        self.output.write("Warning: Totals are computed as cumulative sum * step size,\n"
                          "so spurious values wreck havoc with the results.\n")
        for r in results:
            self.output.write("Results %s" % r.meta('TIME'))
            if r.meta('TITLE'):
                self.output.write(" - %s" % r.meta('TITLE'))
            self.output.write(":\n")

            for s in sorted(r.series_names):
                self.output.write(" %s:\n" % s)
                d = [i for i in r.series(s) if i]
                if not d:
                    self.output.write("  No data.\n")
                    continue
                cs = self.np.cumsum(d)
                units = self.settings.DATA_SETS[s]['units']
                self.output.write("  Data points: %d\n" % len(d))
                if units != "ms":
                    self.output.write("  Total:       %f %s\n" % (cs[-1]*r.meta('STEP_SIZE'),
                                                               units.replace("/s", "")))
                self.output.write("  Mean:        %f %s\n" % (self.np.mean(d), units))
                self.output.write("  Median:      %f %s\n" % (self.np.median(d), units))
                self.output.write("  Min:         %f %s\n" % (self.np.min(d), units))
                self.output.write("  Max:         %f %s\n" % (self.np.max(d), units))
                self.output.write("  Std dev:     %f\n" % (self.np.std(d)))
                self.output.write("  Variance:    %f\n" % (self.np.var(d)))


class PlotFormatter(Formatter):

    open_mode = "wb"
    inverted_units = ('ms')

    linestyles = ['-', '--', ':']
    markers = ['o', '^', 's', 'v', 'D', '*', '<', '>', 'x', '+']
    colours = ["#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e", "#e6ab02", "#a6761d", "#666666"]
    dashes = [[8,4,2,4],
              ]

    def __init__(self, settings):
        Formatter.__init__(self, settings)
        self.subplot_combine_disabled = False
        self.disable_cleanup = False
        self.title = None
        try:
            import matplotlib, numpy
            # If saving to file, try our best to set a proper backend for
            # matplotlib according to the output file name. This helps with
            # running matplotlib without an X server.
            output = self.settings.OUTPUT
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
                    raise RuntimeError("Unrecognised file format for output '%s'" % output)
            import matplotlib.pyplot as plt
            self.mpl = matplotlib
            self.plt = plt
            self.np = numpy
            self.figure = self.plt.figure()
            self.build_styles()
            self.init_plots()
        except ImportError:
            raise RuntimeError("Unable to plot -- matplotlib is missing! Please install it if you want plots.")

    def __del__(self):
        if not self.disable_cleanup:
            try:
                self.plt.close(self.figure)
            except Exception:
                pass

    def _load_plotconfig(self, plot):
        if not plot in self.settings.PLOTS:
            raise RuntimeError("Unable to find plot configuration '%s'." % plot)
        config = self.settings.PLOTS[plot].copy()
        if 'parent' in config:
            parent_config = self.settings.PLOTS[config['parent']].copy()
            parent_config.update(config)
            return parent_config
        return config

    def build_styles(self):
        self.styles = []
        for ls in self.linestyles:
            self.styles.append(dict(linestyle=ls))
        for d in self.dashes:
            self.styles.append(dict(dashes=d))
        if self.settings.USE_MARKERS:
            for m in self.markers:
                self.styles.append(dict(marker=m))

    def init_plots(self):
        # Try to detect if a custom matplotlibrc is installed, and if so don't
        # load our own values.
        if self.settings.LOAD_MATPLOTLIBRC \
          and not os.environ['HOME'] in self.mpl.matplotlib_fname() \
          and not 'MATPLOTLIBRC' in os.environ:
            self.mpl.rc_file(os.path.join(DATA_DIR, 'matplotlibrc.dist'))
        self.colours = self.mpl.rcParams['axes.color_cycle']

        self.figure.clear()
        if self.settings.FIG_WIDTH is not None:
            self.figure.set_figwidth(self.settings.FIG_WIDTH)
        if self.settings.FIG_HEIGHT is not None:
            self.figure.set_figheight(self.settings.FIG_HEIGHT)
        self.config = self._load_plotconfig(self.settings.PLOT)
        self.configs = [self.config]
        getattr(self, '_init_%s_plot' % self.config['type'])()

    def _init_timeseries_combine_plot(self, config=None, axis=None):
        self._init_timeseries_plot(config, axis)

    def _init_timeseries_plot(self, config=None, axis=None):
        if axis is None:
            axis = self.figure.gca()
        if config is None:
            config = self.config

        if 'dual_axes' in config and config['dual_axes']:
            second_axis = self.figure.add_axes(axis.get_position(), sharex=axis, frameon=False)
            second_axis.yaxis.tick_right()
            axis.yaxis.tick_left()
            second_axis.yaxis.set_label_position('right')
            second_axis.yaxis.set_offset_position('right')
            second_axis.xaxis.set_visible(False)
            axis.grid(False)
            second_axis.grid(False)
            config['axes'] = [axis,second_axis]
        else:
            config['axes'] = [axis]

        for a in config['axes']:
            a.minorticks_on()

        unit = [None]*len(config['axes'])
        for s in config['series']:
            if 'axis' in s and s['axis'] == 2:
                a = 1
            else:
                a = 0
            s_unit = self.settings.DATA_SETS[s['data']]['units']
            if unit[a] is not None and s_unit != unit[a]:
                raise RuntimeError("Plot axis unit mismatch: %s/%s" % (unit[a], s_unit))
            unit[a] = s_unit

        axis.set_xlabel('Time (s)')
        for i,u in enumerate(unit):
            if 'axis_labels' in config and config['axis_labels'][i]:
                l = config['axis_labels'][i]
            else:
                l = unit[i]

            if self.settings.NORM_FACTORS:
                l = l[0].lower() + l[1:]
                l = "Normalised %s" % l
            config['axes'][i].set_ylabel(l)


        config['units'] =  unit

    def _init_box_plot(self, config=None, axis=None):
        if axis is None:
            axis = self.figure.gca()
        if config is None:
            config = self.config

        self._init_timeseries_plot(config, axis)
        axis.set_xlabel('')

        for a in config['axes']:
            a.grid(False, axis='x')

        self.start_position = 1

    def _init_bar_plot(self, config=None, axis=None):
        self._init_box_plot(config, axis)

    def _init_bar_combine_plot(self, config=None, axis=None):
        self._init_bar_plot(config, axis)

    def _init_box_combine_plot(self, config=None, axis=None):
        self._init_box_plot(config, axis)

    def _init_ellipsis_combine_plot(self, config=None, axis=None):
        self._init_ellipsis_plot(config, axis)

    def _init_cdf_combine_plot(self, config=None, axis=None):
        self._init_cdf_plot(config, axis)

    def _init_cdf_plot(self, config=None, axis=None):
        if axis is None:
            axis = self.figure.gca()
        if config is None:
            config = self.config

        unit = None
        for s in config['series']:
            s_unit = self.settings.DATA_SETS[s['data']]['units']
            if unit is not None and s_unit != unit:
                raise RuntimeError("Plot axis unit mismatch: %s/%s" % (unit, s_unit))
            unit = s_unit

        if 'axis_labels' in config and config['axis_labels'][0]:
            axis.set_xlabel(config['axis_labels'][0])
        else:
            axis.set_xlabel(unit)
        axis.set_ylabel('Cumulative probability')
        axis.set_ylim(0,1)
        axis.minorticks_on()
        config['axes'] = [axis]
        self.medians = []
        self.min_vals = []


    def _init_qq_plot(self, config=None, axis=None):
        if axis is None:
            axis = self.figure.gca()
        if config is None:
            config = self.config

        axis.minorticks_on()
        config['axes'] = [axis]

        if len(config['series']) > 1:
            raise RuntimeError("Can't do Q-Q plot with more than one series.")


    def _init_ellipsis_plot(self, config=None, axis=None):
        try:
            from netperf_wrapper.error_ellipse import plot_point_cov
            self.plot_point_cov = plot_point_cov
        except ImportError:
            raise RuntimeError("Unable to load error_ellipse plotting functions.")

        if axis is None:
            axis = self.figure.gca()
        if config is None:
            config = self.config

        axis.minorticks_on()
        config['axes'] = [axis]

        for i,a in enumerate(['x','y']):
            unit = self.settings.DATA_SETS[config['series'][i]['data']]['units']
            if self.settings.INVERT_Y and unit in self.inverted_units:
                config['invert_'+a] = True
            else:
                config['invert_'+a] = False
            if 'axis_labels' in config and config['axis_labels'][i]:
                getattr(axis, 'set_'+a+'label')(config['axis_labels'][i])
            else:
                getattr(axis, 'set_'+a+'label')(self.settings.DATA_SETS[config['series'][i]['data']]['units'])


    def _init_meta_plot(self, config=None):
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
            sharex=ax
        else:
            sharex = None
        for i,subplot in enumerate(config['subplots']):
            if config.get('orientation', 'vertical') == 'vertical':
                rows = len(config['subplots'])
                cols = 1
            else:
                cols = len(config['subplots'])
                rows = 1
            axis = self.figure.add_subplot(rows, cols,i+1, sharex=sharex, **subplot_params[i])
            cfg = self._load_plotconfig(subplot)
            self.configs.append(cfg)
            getattr(self, '_init_%s_plot' % cfg['type'])(config=cfg, axis=axis)
            if i < len(config['subplots'])-1:
                axis.set_xlabel("")

    def subplot_combine(self, callback, results):
        config = {'subplots': [self.settings.PLOT] * len(results),
                  'subplot_params': [{'title': r.meta('TITLE')} for r in results],}
        self.figure.clear()
        self._init_meta_plot(config=config)
        for c,r in zip(self.configs,results):
            callback(r, config=c, extra_scale_data=results)

    def dataseries_combine(self, callback, results, always_colour, config=None, axis=None):
        styles = cycle(self.styles)
        colours = cycle(self.colours)
        labels = self._filter_labels([r.label() for r in results])
        for l,r in zip(labels,results):
            style = next(styles).copy()
            if (config and 'series' in config and len(config['series']) == 1) or \
                ('series' in self.config and len(self.config['series']) == 1) or always_colour:
                style['color'] = next(colours)
            callback(r, config=config, axis=axis, postfix=" - "+l, extra_kwargs=style, extra_scale_data=results)

    def combine(self, callback, results, config=None, axis=None, always_colour = False):
        if self.settings.SUBPLOT_COMBINE and not self.subplot_combine_disabled:
            return self.subplot_combine(callback, results)
        else:
            return self.dataseries_combine(callback, results, always_colour, config, axis)


    def do_timeseries_combine_plot(self, results, config=None, axis=None):
        return self.do_combine_many_plot(self.do_timeseries_plot, results, config, axis)

    def do_timeseries_plot(self, results, config=None, axis=None):
        if len(results) > 1:
            self.combine(self._do_timeseries_plot, results, config, axis)
        else:
            self._do_timeseries_plot(results[0], config=config, axis=axis)

    def _do_timeseries_plot(self, results, config=None, axis=None, postfix="", extra_kwargs={}, extra_scale_data=[]):
        if axis is None:
            axis = self.figure.gca()
        if config is None:
            config = self.config

        xlim = axis.get_xlim()
        axis.set_xlim(
            min(results.x_values+[xlim[0]]) if xlim[0] > 0 else min(results.x_values),
            max(results.x_values+[self.settings.TOTAL_LENGTH, xlim[1]])
            )

        data = []
        for i in range(len(config['axes'])):
            data.append([])

        colours = cycle(self.colours)

        for s in config['series']:
            if not s['data'] in results.series_names:
                continue
            if 'smoothing' in s:
                smooth=s['smoothing']
            else:
                smooth = False
            kwargs = {}
            for k in PLOT_KWARGS:
                if k in s:
                    kwargs[k] = s[k]

            if 'label' in kwargs:
                kwargs['label']+=postfix

            if not 'color' in kwargs:
                kwargs['color'] = next(colours)

            kwargs.update(extra_kwargs)

            y_values = results.series(s['data'], smooth)
            if 'axis' in s and s['axis'] == 2:
                a = 1
            else:
                a = 0
            data[a] += y_values
            for r in self.settings.SCALE_DATA+extra_scale_data:
                data[a] += r.series(s['data'], smooth)
            config['axes'][a].plot(results.x_values,
                   y_values,
                   **kwargs)

        if 'scaling' in config:
            btm,top = config['scaling']
        else:
            btm,top = 0,100

        for a in range(len(config['axes'])):
            if data[a]:
                self._do_scaling(config['axes'][a], data[a], btm, top, config['units'][a])

        for a,b in zip(config['axes'], self.settings.BOUNDS_X):
            a.set_xbound(b)
        for a,b in zip(config['axes'], self.settings.BOUNDS_Y):
            a.set_ybound(b)

    def do_bar_plot(self, results, config=None, axis=None):
        if config is None:
            config = self.config
        axis = config['axes'][0]

        group_size = len(results)
        ticklabels = []
        ticks = []
        pos = 1
        all_data = []
        for a in config['axes']:
            all_data.append([])

        errcol = 'k'
        width = 1.0

        # The error bars lines are black, so filter out black from the list of colours
        colours = list(islice(cycle([c for c in self.colours if c != errcol]), len(config['series'])))

        labels = self._filter_labels([r.label() for r in results])
        texts = []

        if self.settings.NORM_FACTORS:
            norms = list(islice(cycle(self.settings.NORM_FACTORS), len(config['series'])))
        else:
            norms = None

        for i,s in enumerate(config['series']):
            if 'axis' in s and s['axis'] == 2:
                a = 1
            else:
                a = 0

            data = []
            errors = []
            for r in results:
                dp = [d for d in r.series(s['data']) if d is not None]
                if norms is not None:
                    dp = [d/norms[i] for d in dp]
                if not dp:
                    data.append(0.0)
                    errors.append(0.0)
                    all_data[a].append(0.0)
                else:
                    dp = self.np.array(dp)
                    data.append(dp.mean())
                    errors.append(dp.std())
                    all_data[a].append(data[-1]+errors[-1])
                    all_data[a].append(data[-1]-errors[-1])


            positions = [p-width/2.0 for p in range(pos,pos+group_size)]
            ticks.extend(list(range(pos,pos+group_size)))
            ticklabels.extend(labels)
            if config.get('colour_by', 'groups') == 'groups':
                colour = colours[i]
            else:
                colour = self.colours[:len(data)]

            bp = config['axes'][a].bar(positions, data, yerr=errors, ecolor=errcol, color=colour,
                                       alpha=0.75, width=width, align='edge')
            if len(config['series']) > 1 or self.settings.PRINT_TITLE:
                texts.append(config['axes'][0].text(pos+group_size/2.0-0.5, 14, s['label'], ha='center'))

            config['axes'][a].axvline(x=pos + group_size, color='black', linewidth=0.5, linestyle=':')
            pos += group_size+1

        for a,b in zip(config['axes'], self.settings.BOUNDS_Y):
            a.set_ybound(b)

        min_y,max_y = config['axes'][0].get_ylim()

        for t in texts:
            x,y = t.get_position()
            t.set_position((x, max_y+abs(max_y-min_y)*0.01))


        axis.set_xticks(ticks)
        axis.set_xticks([], minor=True)
        axis.set_xticklabels(ticklabels, rotation=90, ha='center')
        axis.set_xlim(0,pos-1)

        return texts


    def do_box_plot(self, results, config=None, axis=None):
        if config is None:
            config = self.config
        axis = config['axes'][0]

        group_size = len(results)
        ticklabels = []
        ticks = []
        pos = 1
        all_data = []
        for a in config['axes']:
            all_data.append([])

        # The median lines are red, so filter out red from the list of colours
        colours = list(islice(cycle([c for c in self.colours if c != 'r']), len(results)))

        for i,s in enumerate(config['series']):
            if 'axis' in s and s['axis'] == 2:
                a = 1
            else:
                a = 0

            data = []
            for r in results:
                d = [d for d in r.series(s['data']) if d is not None]
                all_data[a].extend(d)
                if not d:
                    data.append([0.0])
                else:
                    data.append(d)

            if 'label' in s:
                ticklabels.append(s['label'])
            else:
                ticklabels.append(i)

            positions = range(pos,pos+group_size)
            ticks.append(self.np.mean(positions))

            bp = config['axes'][a].boxplot(data,
                                           positions=positions)
            for j,r in enumerate(results):
                self.plt.setp(bp['boxes'][j], color=colours[j])
                if i == 0 and group_size > 1:
                    bp['caps'][j*2].set_label(r.label())
                if len(bp['fliers']) == len(results):
                    self.plt.setp([bp['fliers'][j]], markeredgecolor=colours[j])
                    keys = 'caps','whiskers'
                else:
                    keys = 'caps','whiskers','fliers'
                for k in keys:
                    if bp[k]:
                        self.plt.setp(bp[k][j*2], color=colours[j])
                        self.plt.setp(bp[k][j*2+1], color=colours[j])


            config['axes'][a].axvline(x=pos + group_size, color='black', linewidth=0.5, linestyle=':')
            pos += group_size+1
        for i,a in enumerate(config['axes']):
            self._do_scaling(a, all_data[i], 0, 100, config['units'][i], allow_log=False)

        for a,b in zip(config['axes'], self.settings.BOUNDS_Y):
            a.set_ybound(b)

        axis.set_xticks(ticks)
        axis.set_xticks([], minor=True)
        axis.set_xticklabels(ticklabels)
        axis.set_xlim(0,pos-1)


    def do_bar_combine_plot(self, results, config=None, axis=None):
        return self.do_combine_many_plot(self.do_bar_plot, results, config, axis)

    def do_box_combine_plot(self, results, config=None, axis=None):
        self.do_combine_many_plot(self.do_box_plot, results, config, axis)

    def do_ellipsis_combine_plot(self, results, config=None, axis=None):
        self.do_combine_many_plot(self.do_ellipsis_plot, results, config, axis)

    def do_cdf_combine_plot(self, results, config=None, axis=None):
        self.do_combine_many_plot(self.do_cdf_plot, results, config, axis)

    # Match a word of all digits, optionally with a non-alphanumeric character
    # preceding or succeeding it. For instance a series of files numbered as
    # -01, -02, etc.
    serial_regex = re.compile(r'\W?\b\d+\b\W?')
    def do_combine_many_plot(self, callback, results, config=None, axis=None):

        """Combines several result sets into one box plot by grouping them on
        unique data file name parts and then combining each group into a single
        data set."""

        if config is None:
            config = self.config

        # Group the result sets into the groups that will appear as new data
        # sets. This is done on the file name, by first removing the file
        # extension and the longest common prefix from all the loaded file
        # names, then removing the first word boundary-delimited sequence of
        # digits.
        #
        # The idea is that the data files will be named by a common prefix, with
        # the distinguishing attribute (for instance configured qdisc) at the
        # end, followed by a number signifying test iteration. So for instance
        # given the filenames:
        #
        # rrul-fq_codel-01.json.gz
        # rrul-fq_codel-02.json.gz
        # rrul-fq_codel-03.json.gz
        # rrul-pfifo_fast-01.json.gz
        # rrul-pfifo_fast-02.json.gz
        # rrul-pfifo_fast-03.json.gz
        #
        # two new data sets will be created ('fq_codel' and 'pfifo_fast'), each
        # with three data points created from each of the data files. The
        # function used to map the data points of each result set into a single
        # data point is specified in the test config, and can be one of:
        #
        # mean, median, min, max : resp value computed from all valid data points
        # span: max()-min() from all data points
        # mean_span: mean of all data points' difference from the min value
        # mean_zero: mean value with missing data points interpreted as 0 rather
        #            than being filtered out
        groups = OrderedDict()
        new_results = []
        filenames = [r.meta('DATA_FILENAME').replace(r.SUFFIX, '') for r in results]
        for r in self.settings.FILTER_REGEXP:
            filenames = [re.sub(r, "", f) for f in filenames]
        prefix = long_substr(filenames, prefix_only=True)
        names = map(lambda s: self.serial_regex.sub("", s.replace(prefix, ""), count=1), filenames)
        for i,n in enumerate(names):
            if n in groups:
                groups[n].append(results[i])
            else:
                groups[n] = [results[i]]


        group_by = config.get('group_by', 'groups')
        # group_by == 'groups' means preserve the data series and group the data
        # by the data groups identified above -- i.e. they become the items in
        # the legend.
        if group_by == 'groups':
            for k in groups.keys():
                title = "%s (n=%d)" % (k, len(groups[k])) if self.settings.COMBINE_PRINT_N else k
                res = ResultSet(TITLE=title, NAME=results[0].meta('NAME'))
                res.create_series([s['data'] for s in config['series']])
                x = 0
                for r in groups[k]:
                    data = {}
                    for s in config['series']:
                        data[s['data']] = self._combine_data(r, s['data'], s.get('combine_mode', 'mean'), config.get('cutoff', None))

                    res.append_datapoint(x, data)
                    x += 1
                new_results.append(res)

        # groups_points means group by groups, but do per-point combinations, to
        # e.g. create a data series that is the mean of several others
        elif group_by == 'groups_points':
            for k in groups.keys():
                title = "%s (n=%d)" % (k, len(groups[k])) if self.settings.COMBINE_PRINT_N else k
                res = ResultSet(TITLE=title, NAME=results[0].meta('NAME'))
                x_values = []
                for r in groups[k]:
                    if len(r.x_values) > len(x_values):
                        x_values = r.x_values
                cutoff = config.get('cutoff', None)
                if cutoff is not None:
                    res.x_values = [x for x in x_values if x >= cutoff[0] and x <= max(x_values)-cutoff[1]]
                else:
                    res.x_values = x_values
                for s in config['series']:
                    data = zip_longest(x_values, *[r[s['data']] for r in groups[k]])
                    new_data = []
                    for d in data:
                        if cutoff is None or (d[0] >= cutoff[0] and d[0] <= max(x_values)-cutoff[1]):
                            new_data.append(self._combine_data(res, s['data'], s.get('combine_mode', 'mean'), None, d=d[1:]))
                    res.add_result(s['data'], new_data)
                new_results.append(res)

        # groups_concat means group by groups, but do per-point combinations, to
        # e.g. create a data series that is the mean of several others
        elif group_by == 'groups_concat':
            for k in groups.keys():
                title = "%s (n=%d)" % (k, len(groups[k])) if self.settings.COMBINE_PRINT_N else k
                res = ResultSet(TITLE=title, NAME=results[0].meta('NAME'))
                res.create_series([s['data'] for s in config['series']])
                x = 0
                for r in groups[k]:
                    keys = [s['data'] for s in config['series']]
                    for p in r.zipped(keys):
                        res.append_datapoint(x, dict(zip(keys, p[1:])))
                        x += 1
                new_results.append(res)

        # group_by == 'series' means flip the group and series, so the groups
        # become the entries on the x axis, while the series become the new
        # groups (in the legend)
        elif group_by == 'series':
            for s in config['series']:
                res = ResultSet(TITLE=s['label'], NAME=results[0].meta('NAME'))
                res.create_series(groups.keys())
                x = 0
                for d in zip_longest(*groups.values()):
                    data = {}
                    for k,v in zip(groups.keys(), d):
                        data[k] = self._combine_data(v, s['data'], s.get('combine_mode', 'mean'), config.get('cutoff', None)) if v is not None else None
                    res.append_datapoint(x, data)
                    x += 1
                new_results.append(res)
            new_series = []
            for k in groups.keys():
                new_series.append({'data': k, 'label': k})
            config['series'] = new_series

        # group_by == 'both' means that the group names should be split by a
        # delimiter (currently '-') and the first part specifies the group, the
        # second the series. Currently only works if there's just one series
        # name configured in the plot config.
        elif group_by == 'both':
            assert len(config['series']) == 1
            series_names = []
            group_names = []
            old_s = config['series'][0]
            for k in groups.keys():
                s,g = k.rsplit("-",1)
                if not s in series_names:
                    series_names.append(s)
                if not g in group_names:
                    group_names.append(g)
            new_series = [{'data': s, 'label': s} for s in series_names]
            new_results = []
            for s in group_names:
                res = ResultSet(TITLE=s,NAME=results[0].meta('NAME'))
                res.create_series(series_names)
                x = 0
                for d in zip_longest(*[g[1] for g in groups.items() if g[0].endswith("-%s" % s)]):
                    data = {}
                    for k,v in zip([k.rsplit("-",1)[0] for k in groups.keys() if k.endswith("-%s" % s)], d):
                        data[k] = self._combine_data(v, old_s['data'], old_s.get('combine_mode', 'mean'), config.get('cutoff', None)) if v is not None else None
                    res.append_datapoint(x, data)
                    x += 1
                new_results.append(res)
            config['series'] = new_series

        config['cutoff'] = None

        return callback(new_results, config, axis)

    def _combine_data(self, resultset, key, combine_mode, cutoff=None, d=None):
        if d is None:
            d = resultset[key]
        if cutoff is not None:
            # cut off values from the beginning and end before doing the
            # plot; for e.g. pings that run long than the streams, we don't
            # want the unloaded ping values
            start,end = cutoff
            end = -int(end/self.settings.STEP_SIZE)
            if end == 0:
                end = None
            d = d[int(start/self.settings.STEP_SIZE):end]
        if combine_mode in ('mean', 'median', 'min', 'max'):
            d = [p for p in d if p is not None]
            return getattr(self.np, combine_mode)(d) if d else None
        elif combine_mode == 'span':
            d = [p for p in d if p is not None]
            return self.np.max(d)-self.np.min(d) if d else None
        elif combine_mode == 'mean_span':
            d = [p for p in d if p is not None]
            if not d:
                return None
            min_val = min(d)
            d = [i-min_val for i in d]
            return self.np.mean(d)
        elif combine_mode == 'mean_zero':
            d = [p if p is not None else 0 for p in d]
            return self.np.mean(d) if d else None
        elif combine_mode.startswith('meta:'):
            metakey = combine_mode.split(":", 1)[1]
            try:
                return resultset.meta('SERIES_META')[key][metakey]
            except KeyError:
                return None

    def do_cdf_plot(self, results, config=None, axis=None):
        if len(results) > 1:
            self.combine(self._do_cdf_plot, results, config, axis)
        else:
            self._do_cdf_plot(results[0], config=config, axis=axis)

    def _do_cdf_plot(self, results, config=None, axis=None, postfix="", extra_kwargs={}, extra_scale_data=[]):
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
                start,end = config['cutoff']
                end = -int(end/self.settings.STEP_SIZE)
                if end == 0:
                    end = None
                s_data = s_data[int(start/self.settings.STEP_SIZE):end]
            sizes.append(float(len(s_data)))
            d = sorted([x for x in s_data if x is not None])
            data.append(d)
            if d:
                self.medians.append(self.np.median(d))
                self.min_vals.append(min(d))
                max_value = max([max_value]+d)

                for r in self.settings.SCALE_DATA + extra_scale_data:
                    d_s = [x for x in r.series(s['data']) if x is not None]
                    if d_s:
                        max_value = max([max_value]+d_s)



        if max_value > 10:
            max_value += 10-(max_value%10) # round up to nearest value divisible by 10
        axis.set_xlim(right=max_value)

        for i,s in enumerate(config['series']):
            if not data[i]:
                continue
            max_val = max(data[i])
            min_val = min(data[i])
            step = (max_val-min_val)/1000.0 if min_val != max_val else 1.0
            x_values = list(frange(min_val-2*step, max_val+2*step, step))
            kwargs = {}
            for k in PLOT_KWARGS:
                if k in s:
                    kwargs[k] = s[k]
            if 'label' in kwargs:
                kwargs['label']+=postfix
            if not 'color' in kwargs:
                kwargs['color'] = next(colours)
            kwargs.update(extra_kwargs)
            y_values = [cum_prob(data[i], point, sizes[i]) for point in x_values]
            if 1.0 in y_values:
                idx_1 = y_values.index(1.0)+1
            else:
                idx_1 = len(y_values)
            idx_0 = 0
            while y_values[idx_0+1] == 0.0:
                idx_0 +=1

            x_vals, y_vals = self._filter_dup_vals(x_values[idx_0:idx_1], y_values[idx_0:idx_1])
            axis.plot(x_vals,
                      y_vals,
                      **kwargs)

        if self.settings.ZERO_Y:
            axis.set_xlim(left=0)
        elif self.min_vals:
            min_val = min(self.min_vals)
            if min_val > 10:
                min_val -= min_val%10 # nearest value divisible by 10
            if min_val > 100:
                min_val -= min_val%100
            axis.set_xlim(left=min_val)

        if self.medians and max(self.medians)/min(self.medians) > 10.0 and self.settings.LOG_SCALE:
            # More than an order of magnitude difference; switch to log scale
            axis.set_xscale('log')

        for a,b in zip(config['axes'], self.settings.BOUNDS_X):
            a.set_xbound(b)

    def _filter_dup_vals(self, x_vals, y_vals):
        """Filter out series of identical y-vals, also removing the corresponding x-vals.

        Lowers the amount of plotted points and avoids strings of markers on CDFs."""
        x_vals = list(x_vals)
        y_vals = list(y_vals)
        i = 0
        while i < len(x_vals)-2:
            while y_vals[i] == y_vals[i+1] and y_vals[i] == y_vals[i+2]:
                del x_vals[i+1]
                del y_vals[i+1]
            i +=1
        return x_vals,y_vals


    def do_qq_plot(self, results):
        if len(results) < 2:
            results *= 2
        self._do_qq_plot(results[:2])

    def _do_qq_plot(self, results):
        series = self.config['series'][0]
        axis = self.config['axes'][0]

        x_values,y_values = self._equal_length(results[0].series(series['data']), results[1].series(series['data']))

        axis.plot(x_values, y_values, 'r.', label=series['label'])

        max_val = max(x_values.max(), y_values.max())
        axis.plot([0,max_val], [0,max_val], 'b-', label="Ref (x=y)")

        axis.set_xlabel(results[0].label())
        axis.set_ylabel(results[1].label())

        axis.set_xlim(min(x_values)*0.99, max(x_values)*1.01)
        axis.set_ylim(min(y_values)*0.99, max(y_values)*1.01)

    def do_ellipsis_plot(self, results, config=None, axis=None):
        self.xvals = []
        self.yvals = []
        if len(results) > 1:
            self.combine(self._do_ellipsis_plot, results, config, axis, always_colour=True)
        else:
            self._do_ellipsis_plot(results[0], config=config, axis=axis)

    def _do_ellipsis_plot(self, results, config=None, axis=None, extra_kwargs={}, postfix="", **kwargs):
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
            data = [i for i in zip(x_values, results.series(s['data'])) if i[0] is not None and i[1] is not None]
            points = self.np.array(data)
            x_values,y_values = zip(*data)
            el = self.plot_point_cov(points, ax=axis, alpha=0.5, **carg)
            med = self.np.median(points, axis=0)
            self.xvals.append(el.center[0]-el.width/2)
            self.xvals.append(el.center[0]+el.width/2)
            self.yvals.append(el.center[1]-el.height/2)
            self.yvals.append(el.center[1]+el.height/2)
            self.xvals.append(med[0])
            self.yvals.append(med[1])
            axis.plot(*med, marker='o', linestyle=" ", **carg)
            axis.annotate(label, med, ha='center', annotation_clip=True, xytext=(0,8), textcoords='offset points')

        if self.settings.ZERO_Y:
            self.xvals.append(0.0)
            self.yvals.append(0.0)
        axis.set_xlim(max(min(self.xvals)*0.99,0), max(self.xvals)*1.1)
        axis.set_ylim(max(min(self.yvals)*0.99,0), max(self.yvals)*1.1)
        if config['invert_x']:
            axis.invert_xaxis()
        if config['invert_y']:
            axis.invert_yaxis()

        for a,b in zip(config['axes'], self.settings.BOUNDS_X):
            a.set_xbound(b)
        for a,b in zip(config['axes'], self.settings.BOUNDS_Y):
            a.set_ybound(b)


    def _equal_length(self, x, y):
        x_values = self.np.sort([r for r in x if r is not None])
        y_values = self.np.sort([r for r in y if r is not None])

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
            y_values = self.np.interp(self.np.linspace(0, len(y_values),
                                                       num=len(x_values), endpoint=False),
                                      range(len(y_values)), y_values)

        elif len(y_values) < len(x_values):
            x_values = self.np.interp(self.np.linspace(0, len(x_values),
                                                       num=len(y_values), endpoint=False),
                                      range(len(x_values)), x_values)

        return x_values, y_values


    def do_meta_plot(self, results):
        self.subplot_combine_disabled = True
        for i,config in enumerate(self.configs):
            getattr(self, 'do_%s_plot' % config['type'])(results, config=config)

    def format(self, results):
        if not results[0]:
            return

        self.subplot_combine_disabled = False

        artists = getattr(self, 'do_%s_plot' % self.config['type'])(results)
        skip_title = len(results) > 1

        if not artists:
            artists = []
        all_legends = []
        for c in self.configs:
            legends = self._do_legend(c)
            if legends:
                all_legends += legends

        artists += all_legends + self._annotate_plot(skip_title)
        self.legends = all_legends

        # Since outputting image data to stdout does not make sense, we launch
        # the interactive matplotlib viewer if stdout is set for output.
        # Otherwise, the filename is passed to matplotlib, which selects an
        # appropriate output format based on the file name.
        if self.output == "-":
            self.figure.canvas.mpl_connect('resize_event', self.size_legends)
            self.size_legends()
            if not self.settings.GUI:
                self.plt.show()
        else:
            try:
                if self.plt.get_backend() == 'pdf':
                    self.save_pdf(self.output, results[0].meta('DATA_FILENAME'), artists)
                else:
                    self.figure.savefig(self.output, bbox_extra_artists=artists, bbox_inches='tight',
                                    dpi=self.settings.FIG_DPI)
            except IOError as e:
                raise RuntimeError("Unable to save output plot: %s" % e)

    def save_pdf(self, filename, data_filename, artists):
        with self.mpl.backends.backend_pdf.PdfPages(filename) as pdf:
            pdf.infodict()['Producer'] = 'netperf-wrapper v%s' % VERSION
            pdf.infodict()['Subject'] = data_filename
            if self.title:
                pdf.infodict()['Title'] = self.title.replace("\n", "; ")
            self.figure.savefig(pdf, bbox_extra_artists=artists, bbox_inches='tight',
                                dpi=self.settings.FIG_DPI)

    def size_legends(self, event=None):
        # For the interactive viewer there's no bbox_extra_artists, so we
        # need to reduce the axis sizes to make room for the legend.
        if self.settings.PRINT_LEGEND and not self.settings.HORIZONTAL_LEGEND and self.legends:
            self.figure.canvas.draw() # Legend width is not set before it's drawn
            legend_width = max([l.get_window_extent().width for l in self.legends])
            canvas_width = self.figure.canvas.get_width_height()[0]
            for a in reduce(lambda x,y:x+y, [i['axes'] for i in self.configs]):
                # Save the original width of the (in the interval [0..1]) and
                # use that as a base to scale the axis on subsequent calls.
                # Otherwise, each call will shrink the axis.
                if not hasattr(a, 'orig_width'):
                    a.orig_width = a.get_position().width
                ax_width = a.get_window_extent().width
                box = a.get_position()
                a.set_position([box.x0, box.y0, (a.orig_width - legend_width/canvas_width), box.height])


    def _annotate_plot(self, skip_title=False):
        titles = []
        title_y=0.98
        if self.settings.OVERRIDE_TITLE:
            titles.append(self.figure.suptitle(self.settings.OVERRIDE_TITLE, fontsize=14, y=title_y))
            self.title = self.settings.OVERRIDE_TITLE
        elif self.settings.PRINT_TITLE:
            plot_title = self.settings.DESCRIPTION
            if 'description' in self.config:
                plot_title += "\n" + self.config['description']
            if self.settings.TITLE and not skip_title:
                plot_title += "\n" + self.settings.TITLE
            if 'description' in self.config and self.settings.TITLE and not skip_title:
                y=1.00
            titles.append(self.figure.suptitle(plot_title, fontsize=14, y=title_y))
            self.title = plot_title

        if self.settings.ANNOTATE:
            annotation_string = "Local/remote: %s/%s - Time: %s - Length/step: %ds/%.2fs" % (
                self.settings.LOCAL_HOST, self.settings.HOST,
                self.settings.TIME,
                self.settings.LENGTH, self.settings.STEP_SIZE)
            titles.append(self.figure.text(0.5, 0.0, annotation_string,
                                            horizontalalignment='center',
                                            verticalalignment='bottom',
                                            fontsize=8))
        return titles

    def _filter_labels(self, labels):
        for r in self.settings.FILTER_REGEXP:
            labels = [re.sub(r, "", l) for l in labels]
        if self.settings.FILTER_LEGEND and labels:
            substr = long_substr(labels)
            if len(substr) > 3 and substr != " - ":
                labels = [l.replace(substr, '') for l in labels]
            prefix = long_substr(labels, prefix_only=True)
            if prefix and len(prefix) < len(labels[0]):
                labels = [l.replace(prefix, '') for l in labels]
        return labels

    def _do_legend(self, config, postfix=""):
        if not self.settings.PRINT_LEGEND:
            return []

        axes = config['axes']

        # Each axis has a set of handles/labels for the legend; combine them
        # into one list of handles/labels for displaying one legend that holds
        # all plot lines
        handles, labels = reduce(lambda x,y:(x[0]+y[0], x[1]+y[1]),
                                 [a.get_legend_handles_labels() for a in axes])
        if not labels:
            return []

        labels = self._filter_labels(labels)

        kwargs = {}
        if 'legend_title' in config:
            kwargs['title'] = config['legend_title']


        if len(axes) > 1:
            offset_x = 1.11
        else:
            offset_x = 1.02

        legends = []
        if self.settings.HORIZONTAL_LEGEND:
            bbox = (0.5, -0.12)
            ncol = len(labels)
            loc = 'center'
        else:
            bbox = (offset_x, 1.0)
            ncol = 1
            loc = 'upper left'
        l = axes[0].legend(handles, labels,
                                bbox_to_anchor=bbox,
                                loc=loc, borderaxespad=0.,
                                prop={'size':'small'},
                                ncol=ncol,
                                **kwargs)

        # Work around a bug in older versions of matplotlib where the
        # legend.get_window_extent method does not take any arguments, leading
        # to a crash when using bbox_extra_artists when saving the figure
        #
        # Simply check for either the right number of args, or a vararg
        # specification, and if they are not present, attempt to monkey-patch
        # the method if it does not accept any arguments.
        a,v,_,_ = inspect.getargspec(l.get_window_extent)
        if len(a) < 2 or v is None:
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

        # Leave 1 percent of the axis range as extra space, so the outermost
        # points are not smudged by the axis lines.
        space = (top_percentile - btm_percentile)*0.01
        top_scale = top_percentile + space
        btm_scale = btm_percentile - space
        if self.settings.ZERO_Y:
            # When y is set at zero, set space at the top to be one percent room
            # of the *axis* range, not the data range (this may be a big
            # difference if the data range is small).
            top_scale = top_percentile*1.01
            axis.set_ylim(ymin=0, ymax=top_scale)
        else:
            if btm_percentile > 0 and top_percentile/btm_percentile > 20.0 and self.settings.LOG_SCALE and allow_log:
                axis.set_yscale('log')
                axis.set_ylim(ymin=max(0,btm_scale), ymax=top_scale)
            else:
                axis.set_ylim(ymin=btm_scale, ymax=top_scale)

        if self.settings.INVERT_Y and unit in self.inverted_units:
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
        idx = int(len(lst) * (q/100.0))
        return self.np.sort(lst)[idx]


class MetadataFormatter(Formatter):

    def format(self, results):
        self.open_output()
        self.output.write(json.dumps([r.serialise_metadata() for r in results], indent=4) + "\n")
