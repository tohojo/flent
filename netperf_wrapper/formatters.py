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

import json, sys, csv, math, inspect, os

from .util import cum_prob, frange
from functools import reduce

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

DefaultFormatter = Formatter

class TableFormatter(Formatter):

    def get_header(self, results):
        name = results[0].meta("NAME")
        keys = list(self.settings.DATA_SETS.keys())
        header_row = [name]

        if len(results) > 1:
            for r in results:
                header_row += [k + ' - ' + r.meta("TITLE") for k in keys]
        else:
            header_row += keys
        return header_row

    def combine_results(self, results):
        """Generator to combine several result sets into one list of rows, by
        concatenating them."""
        keys = list(self.settings.DATA_SETS.keys())
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

    def __init__(self, settings):
        Formatter.__init__(self, settings)
        try:
            import matplotlib, numpy
            # If saving to file, try our best to set a proper backend for
            # matplotlib according to the output file name. This helps with
            # running matplotlib without an X server.
            if self.output != "-":
                if self.output.endswith('.svg') or self.output.endswith('.svgz'):
                    matplotlib.use('svg')
                elif self.output.endswith('.ps') or self.output.endswith('.eps'):
                    matplotlib.use('ps')
                elif self.output.endswith('.pdf'):
                    matplotlib.use('pdf')
                elif self.output.endswith('.png'):
                    matplotlib.use('agg')
                else:
                    raise RuntimeError("Unrecognised file format for output '%s'" % output)
            import matplotlib.pyplot as plt
            self.plt = plt
            self.np = numpy
            self.figure = self.plt.gcf()
            self.init_plots()
        except ImportError:
            raise RuntimeError("Unable to plot -- matplotlib is missing! Please install it if you want plots.")


    def _load_plotconfig(self, plot):
        if not plot in self.settings.PLOTS:
            raise RuntimeError("Unable to find plot configuration '%s'" % plot)
        config = self.settings.PLOTS[plot].copy()
        if 'parent' in config:
            parent_config = self.settings.PLOTS[config['parent']].copy()
            parent_config.update(config)
            return parent_config
        return config

    def init_plots(self):
        self.figure.clear()
        self.config = self._load_plotconfig(self.settings.PLOT)
        self.configs = [self.config]
        getattr(self, '_init_%s_plot' % self.config['type'])()

    def _init_timeseries_plot(self, config=None, axis=None):
        if axis is None:
            axis = self.plt.gca()
        if config is None:
            config = self.config

        if 'dual_axes' in config and config['dual_axes']:
            second_axis = self.plt.axes(axis.get_position(), sharex=axis, frameon=False)
            second_axis.yaxis.tick_right()
            axis.yaxis.tick_left()
            second_axis.yaxis.set_label_position('right')
            second_axis.yaxis.set_offset_position('right')
            second_axis.xaxis.set_visible(False)
            config['axes'] = [axis,second_axis]
        else:
            config['axes'] = [axis]


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

        axis.set_xlabel('Time')
        for i,u in enumerate(unit):
            config['axes'][i].set_ylabel(unit[i])

    def _init_cdf_plot(self, config=None, axis=None):
        if axis is None:
            axis = self.plt.gca()
        if config is None:
            config = self.config

        unit = None
        for s in config['series']:
            s_unit = self.settings.DATA_SETS[s['data']]['units']
            if unit is not None and s_unit != unit:
                raise RuntimeError("Plot axis unit mismatch: %s/%s" % (unit, s_unit))
            unit = s_unit

        axis.set_xlabel(unit)
        axis.set_ylabel('Cumulative probability')
        axis.set_ylim(0,1)
        config['axes'] = [axis]
        self.medians = []
        self.min_vals = []


    def _init_meta_plot(self):
        self.configs = []
        for i,subplot in enumerate(self.config['subplots']):
            axis = self.plt.subplot(len(self.config['subplots']),1,i+1, sharex=self.plt.gca())
            config = self._load_plotconfig(subplot)
            self.configs.append(config)
            getattr(self, '_init_%s_plot' % config['type'])(config=config, axis=axis)
            if i < len(self.config['subplots'])-1:
                axis.set_xlabel("")


    def _do_timeseries_plot(self, results, config=None, axis=None, postfix=""):
        if axis is None:
            axis = self.plt.gca()
        if config is None:
            config = self.config

        axis.set_xlim(0, max(results.x_values+[self.settings.TOTAL_LENGTH]))
        data = []
        for i in range(len(config['axes'])):
            data.append([])

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

            y_values = results.series(s['data'], smooth)
            if 'axis' in s and s['axis'] == 2:
                a = 1
            else:
                a = 0
            data[a] += y_values
            for r in self.settings.SCALE_DATA:
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
                self._do_scaling(config['axes'][a], data[a], btm, top)

    def _do_cdf_plot(self, results, config=None, axis=None, postfix=""):
        if axis is None:
            axis = self.plt.gca()
        if config is None:
            config = self.config

        data = []
        sizes = []
        max_value = 0.0
        for s in config['series']:
            if not s['data'] in results.series_names:
                data.append([])
                continue
            s_data = results.series(s['data'])
            if 'cutoff' in config:
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

                for r in self.settings.SCALE_DATA:
                    d_s = [x for x in r.series(s['data']) if x is not None]
                    if d_s:
                        max_value = max([max_value]+d_s)


        x_values = list(frange(0, max_value, 0.1))


        for i,s in enumerate(config['series']):
            kwargs = {}
            for k in PLOT_KWARGS:
                if k in s:
                    kwargs[k] = s[k]
            if 'label' in kwargs:
                kwargs['label']+=postfix
            axis.plot(x_values,
                      [cum_prob(data[i], point, sizes[i]) for point in x_values],
                      **kwargs)

        if self.medians and max(self.medians)/min(self.medians) > 10.0:
            # More than an order of magnitude difference; switch to log scale
            axis.set_xscale('log')
            min_val = min(self.min_vals)
            if min_val > 10:
                min_val -= min_val%10 # nearest value divisible by 10
            axis.set_xlim(left=min_val)

    def _do_meta_plot(self, results, postfix=""):
        for i,config in enumerate(self.configs):
            getattr(self, '_do_%s_plot' % config['type'])(results, config=config, postfix=postfix)

    def format(self, results):
        if not results[0]:
            return

        if len(results) > 1:
            for r in results:
                getattr(self, '_do_%s_plot' % self.config['type'])(r, postfix=" - "+r.meta("TITLE"))
            skip_title = True
        else:
            getattr(self, '_do_%s_plot' % self.config['type'])(results[0])
            skip_title = False

        artists = []
        for c in self.configs:
            artists += self._do_legend(c)

        artists += self._annotate_plot(skip_title)

        # Since outputting image data to stdout does not make sense, we launch
        # the interactive matplotlib viewer if stdout is set for output.
        # Otherwise, the filename is passed to matplotlib, which selects an
        # appropriate output format based on the file name.
        if self.output == "-":
            # For the interactive viewer there's no bbox_extra_artists, so we
            # need to reduce the axis sizes to make room for the legend (which
            # might still be slightly cut off).
            if self.settings.PRINT_LEGEND:
                for a in reduce(lambda x,y:x+y, [i['axes'] for i in self.configs]):
                    box = a.get_position()
                    a.set_position([box.x0, box.y0, box.width * 0.8, box.height])
            if not self.settings.GUI:
                self.plt.show()
        else:
            try:
                self.plt.savefig(self.output, bbox_extra_artists=artists, bbox_inches='tight')
            except IOError as e:
                raise RuntimeError("Unable to save output plot: %s" % e)


    def _annotate_plot(self, skip_title=False):
        titles = []
        if self.settings.PRINT_TITLE:
            plot_title = self.settings.DESCRIPTION
            y=0.98
            if 'description' in self.config:
                plot_title += "\n" + self.config['description']
            if self.settings.TITLE and not skip_title:
                plot_title += "\n" + self.settings.TITLE
            if 'description' in self.config and self.settings.TITLE and not skip_title:
                y=1.01
            titles.append(self.plt.suptitle(plot_title, fontsize=14, y=y))

        if self.settings.ANNOTATE:
            annotation_string = "Local/remote: %s/%s - Time: %s - Length/step: %ds/%.2fs" % (
                self.settings.LOCAL_HOST, self.settings.HOST,
                self.settings.TIME,
                self.settings.LENGTH, self.settings.STEP_SIZE)
            titles.append(self.plt.gcf().text(0.5, -0.01, annotation_string,
                                            horizontalalignment='center',
                                            verticalalignment='bottom',
                                            fontsize=8))
        return titles

    def _do_legend(self, config, postfix=""):
        if not self.settings.PRINT_LEGEND:
            return []

        axes = config['axes']

        # Each axis has a set of handles/labels for the legend; combine them
        # into one list of handles/labels for displaying one legend that holds
        # all plot lines
        handles, labels = reduce(lambda x,y:(x[0]+y[0], x[1]+y[1]),
                                 [a.get_legend_handles_labels() for a in axes])

        kwargs = {}
        if 'legend_title' in config:
            kwargs['title'] = config['legend_title']


        if len(axes) > 1:
            offset_x = 1.09
        else:
            offset_x = 1.02

        legends = []
        l = axes[0].legend(handles, labels,
                                bbox_to_anchor=(offset_x, 1.0),
                                loc='upper left', borderaxespad=0.,
                                prop={'size':'small'},
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

    def _do_scaling(self, axis, data, btm, top):
        """Scale the axis to the selected bottom/top percentile"""
        data = [x for x in data if x is not None]
        if not data:
            return
        top_percentile = self.np.percentile(data, top)*1.05
        btm_percentile = self.np.percentile(data, btm)*0.95
        if self.settings.ZERO_Y:
            axis.set_ylim(ymin=0, ymax=top_percentile)
        else:
            axis.set_ylim(ymin=btm_percentile, ymax=top_percentile)
            if top_percentile/btm_percentile > 20.0 and self.settings.LOG_SCALE:
                axis.set_yscale('log')


class MetadataFormatter(Formatter):

    def format(self, results):
        self.open_output()
        self.output.write(json.dumps([r.serialise_metadata() for r in results], indent=4) + "\n")
