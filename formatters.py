## -*- coding: utf-8 -*-
##
## formatters.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     16 oktober 2012
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

import pprint, sys, csv

from settings import settings

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

    def __init__(self, output):
        if isinstance(output, basestring):
            if output == "-":
                self.output = sys.stdout
            else:
                self.output = open(output, "w")
        else:
            self.output = output

    def format(self, name, results):
        self.output.write(name+"\n")
        self.output.write(results+"\n")



class OrgTableFormatter(Formatter):
    """Format the output for an Org mode table. The formatter is pretty crude
    and does not align the table properly, but it should be sufficient to create
    something that Org mode can correctly realign."""

    def format(self, name, results):

        if not results:
            self.output.write(unicode(name) + u" -- empty\n")
        keys = settings.DATA_SETS.keys()
        header_row = [name] + keys
        self.output.write(u"| " + u" | ".join(header_row) + u" |\n")
        self.output.write(u"|-" + u"-+-".join([u"-"*len(i) for i in header_row]) + u"-|\n")

        def format_item(item):
            if isinstance(item, float):
                return "%.2f" % item
            return unicode(item)

        for row in results.zipped(keys):
            self.output.write(u"| ")
            self.output.write(u" | ".join(map(format_item, row)))
            self.output.write(u" |\n")


DefaultFormatter = OrgTableFormatter

class CsvFormatter(Formatter):
    """Format the output as csv."""

    def format(self, name, results):

        if not results:
            return

        writer = csv.writer(self.output)
        keys = settings.DATA_SETS.keys()
        header_row = [name] + keys
        writer.writerow(header_row)

        def format_item(item):
            if item is None:
                return ""
            return unicode(item)

        for row in results.zipped(keys):
            writer.writerow(map(format_item, row))

class PlotFormatter(Formatter):

    def __init__(self, output):
        self.output = output
        try:
            import matplotlib, numpy
            # If saving to file, try our best to set a proper backend for
            # matplotlib according to the output file name. This helps with
            # running matplotlib without an X server.
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
            self.plt = plt
            self.np = numpy
            self._init_plots()
        except ImportError:
            raise RuntimeError(u"Unable to plot -- matplotlib is missing! Please install it if you want plots.")


    def _load_plotconfig(self, plot):
        if not plot in settings.PLOTS:
            raise RuntimeError(u"Unable to find plot configuration '%s'" % plot)
        config = settings.PLOTS[plot]
        if 'parent' in config:
            parent_config = settings.PLOTS[config['parent']]
            parent_config.update(config)
            return parent_config
        return config

    def _init_plots(self):

        self.config = self._load_plotconfig(settings.PLOT)
        getattr(self, '_init_%s_plot' % self.config['type'])()


        return

        series_names = [i for i in self.config.sections() if i != 'global']
        plots = sorted(set([self.config.getint(s, 'subplot', 1) for s in series_names]))
        num_plots = len(plots)
        if plots != range(1, num_plots+1):
            raise RuntimeError(u"Plots are not numbered sequentially")

        self.fig, self.axs = self.plt.subplots(num_plots, 2, sharex=True, sharey=False, squeeze=False)


        # Hide all axes (they are then shown when used below)
        for a in self.axs.flatten():
            a.yaxis.set_visible(False)

        for s in series_names:
            # Each series is plotted on the appropriate axis with the series
            # name as label. The line parameters are optionally set in the
            # config file; if no value is set, matplotlib selects default
            # colours for the lines.
            subfig = self.config.getint(s, 'subplot', 1)-1
            axis = self.config.getint(s, 'plot_axis', 1)-1
            a = self.axs[subfig,axis]
            a.yaxis.set_visible(True)

            limits = self.config.get(s, 'limits', None)
            if limits is not None:
                l_min,l_max = [float(i) for i in limits.split(",")]
                y_min,y_max = a.get_ylim()
                a.set_ylim(min(y_min,l_min), max(y_max,l_max))

            # Scales start out with a scale of 'linear', change it if a scale is set
            scale = self.config.get(s, 'scale', None)
            if scale is not None:
                a.set_yscale(scale)

            # Set plot axis labels to the unit of the series, if set. Detect
            # multiple incompatibly set units and abort if found.
            units = self.config.get(s, 'units', '')
            label = a.get_ylabel()
            if label == '':
                a.set_ylabel(units)
            elif units and label != units:
                raise RuntimeError(u"Axis units mismatch: %s and %s for subplot %d" % (units,label,subfig))


        self.axs[-1,0].set_xlabel(self.config.get('global', 'x_label', ''))
        xlimits = self.config.get('global', 'x_limits', None)
        if xlimits is not None:
            l_min,l_max = [float(i) for i in xlimits.split(",")]
            self.axs[0,0].set_xlim(l_min,l_max)


        self.fig.suptitle(self.config.get('global', 'plot_title', ''), fontsize=16)

        self.fig.subplots_adjust(left=0.1, right=0.9)

        # Duplicate the twinx() function of axes for having the second set of
        # axes be on top of the others, for dual-axis view
        for axs in self.axs:
            box = axs[0].get_position()
            axs[0].set_position([box.x0, box.y0, box.width * 2.0, box.height])
            axs[1].set_position(axs[0].get_position())
            axs[1].set_frame_on(False)
            axs[1].yaxis.tick_right()
            axs[1].yaxis.set_label_position('right')
            axs[1].yaxis.set_offset_position('right')
            axs[1].xaxis.set_visible(False)

    def _init_timeseries_plot(self, config=None, axis=None):
        if axis is None:
            axis = self.plt.gca()
        if config is None:
            config = self.config

        if 'dual_axes' in config and config['dual_axes']:
            second_axis = self.plt.axes(axis.get_position(), sharex=axis, frameon=False)
            second_axis.yaxis.tick_right()
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
            s_unit = settings.DATA_SETS[s['data']]['units']
            if unit[a] is not None and s_unit != unit[a]:
                raise RuntimeError("Plot axis unit mismatch: %s/%s" % (unit[a], s_unit))
            unit[a] = s_unit

        axis.set_xlabel('Time')
        for i,u in enumerate(unit):
            config['axes'][i].set_ylabel(unit[i])


    def _do_timeseries_plot(self, results, config=None, axis=None):
        if axis is None:
            axis = self.plt.gca()
        if config is None:
            config = self.config

        axis.set_xlim(0, settings.TOTAL_LENGTH)
        data = []
        for i in range(len(self.config['axes'])):
            data.append([])

        for s in config['series']:
            if 'smoothing' in s:
                smooth=s['smoothing']
            else:
                smooth = False
            kwargs = {}
            for k in PLOT_KWARGS:
                if k in s:
                    kwargs[k] = s[k]

            y_values = results.series(s['data'], smooth)
            if 'axis' in s and s['axis'] == 2:
                a = 1
            else:
                a = 0
            data[a] += y_values
            config['axes'][a].plot(results.x_values,
                   y_values,
                   **kwargs)

        if 'scaling' in config:
            for a in range(len(config['axes'])):
                self._do_scaling(config['axes'][a], data[a], *config['scaling'])

        self._do_legend(config)

    def format(self, name, results):
        if not results:
            return

        getattr(self, '_do_%s_plot' % self.config['type'])(results)

        # Since outputting image data to stdout does not make sense, we launch
        # the interactive matplotlib viewer if stdout is set for output.
        # Otherwise, the filename is passed to matplotlib, which selects an
        # appropriate output format based on the file name.
        if self.output == "-":
            self.plt.show()
        else:
            self.plt.savefig(self.output)
        return
        # Unzip the data into time series and data dicts to allow for plotting.
        series_names = [i for i in self.config.sections() if i != 'global']

        # The config file can set plot_axis to 1 or 2 for each test depending on
        # which axis the results should be plotted. The second axis is only
        # created if it is selected in one of the data sets selects it. The
        # matplotlib .twinx() function creates a second axis on the right-hand
        # side of the plot in the obvious way.

        all_data = self.np.empty_like(self.axs, dtype=object)
        for i in range(len(all_data.flat)):
            all_data.flat[i] = []

        for s in series_names:
            # Each series is plotted on the appropriate axis with the series
            # name as label. The line parameters are optionally set in the
            # config file; if no value is set, matplotlib selects default
            # colours for the lines.
            subfig = self.config.getint(s, 'subplot', 1)-1
            axis = self.config.getint(s, 'plot_axis', 1)-1
            a = self.axs[subfig,axis]

            # Set optional kwargs from config file
            kwargs = {}
            linewidth=self.config.get(s,'plot_linewidth', None)
            if linewidth is not None:
                kwargs['linewidth'] = float(linewidth)
            color=self.config.get(s, 'plot_linecolor', None)
            if color is not None:
                kwargs['color'] = color

            if self.config.has_option(s, 'limits'):
                all_data[subfig,axis] = None

            if all_data[subfig,axis] is not None:
                all_data[subfig,axis] += [d for d in results.series(s) if d is not None]


            a.plot(results.x_values,
                   results.series(s),
                   self.config.get(s, 'plot_line', ''),
                   label=self.config.get(s, 'plot_label', s),
                   **kwargs
                )

    def _do_legend(self, config):
        axes = config['axes']

        # Each axis has a set of handles/labels for the legend; combine them
        # into one list of handles/labels for displaying one legend that holds
        # all plot lines
        handles, labels = reduce(lambda x,y:(x[0]+y[0], x[1]+y[1]),
                                 [a.get_legend_handles_labels() for a in axes])

        # Shrink the current subplot by 20% in the horizontal direction, and
        # place the legend on the right of the plot.
        for a in axes:
            box = a.get_position()
            a.set_position([box.x0, box.y0, box.width * 0.8, box.height])


            kwargs = {}
            if 'legend_title' in config:
                kwargs['title'] = config['legend_title']

            a.legend(handles, labels,
                     bbox_to_anchor=(1.05, 1.0),
                     loc='upper left', borderaxespad=0.,
                     prop={'size':'small'},
                     **kwargs)

    def _do_scaling(self, axis, data, btm, top):
        """Scale the axis to the selected bottom/top percentile"""
        data = filter(lambda x: x is not None, data)
        top_percentile = self.np.percentile(data, top)*1.05
        btm_percentile = self.np.percentile(data, btm)*0.95
        axis.set_ylim(ymin=btm_percentile, ymax=top_percentile)
