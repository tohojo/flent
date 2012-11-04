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

import pprint, sys



class Formatter(object):

    def __init__(self, output, config):
        self.config = config
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


class PprintFormatter(Formatter):

    def format(self, name, results):
        """Use the pprint pretty-printing module to just print out the contents of
        the results list."""

        self.output.write(name+"\n")
        pprint.pprint(results, self.output)

DefaultFormatter = PprintFormatter

class OrgTableFormatter(Formatter):
    """Format the output for an Org mode table. The formatter is pretty crude
    and does not align the table properly, but it should be sufficient to create
    something that Org mode can correctly realign."""

    def format(self, name, results):

        if not results:
            self.output.write(unicode(name) + u" -- empty\n")
        first_row = results[0][1]
        header_row = [name] + sorted(first_row.keys())
        self.output.write(u"| " + u" | ".join(header_row) + u" |\n")
        self.output.write(u"|-" + u"-+-".join([u"-"*len(i) for i in header_row]) + u"-|\n")
        for i,row in results:
            self.output.write(u"| %s | " % i)
            for c in header_row[1:]:
                if isinstance(row[c], float):
                    self.output.write(u"%.2f | " % row[c])
                else:
                    self.output.write(unicode(row[c]) + u" | ")
            self.output.write(u"\n")

class PlotFormatter(Formatter):

    def __init__(self, output, config):
        self.output = output
        self.config = config
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
            self._init_subplots()
        except ImportError:
            raise RuntimeError(u"Unable to plot -- matplotlib is missing! Please install it if you want plots.")


    def _init_subplots(self):
        series_names = [i for i in self.config.sections() if i != 'global']
        plots = sorted(set([self.config.getint(s, 'subplot', 1) for s in series_names]))
        num_plots = len(plots)
        if plots != range(1, num_plots+1):
            raise RuntimeError(u"Plots are not numbered sequentially")

        self.fig, self.axs = self.plt.subplots(num_plots, 1, sharex=True, sharey=False, squeeze=False)


        ## The following dual-axis stuff seems to confuse the plot layout code,
        ## so disable multiple axes on the same plot for now.

        # Turn the axs array into a two-dimensional array with the second
        # dimension holding twinx() axes if selected.
        #        self.axs = self.np.empty([num_plots, 2], dtype=object)
        #        for i in range(num_plots):
        #            a = axs[i,0]
        #            self.axs[i,0] = a
        # Find any plots that have output selected on the second axis.
        #        for s in series_names:
        #            axis = self.config.getint(s, 'plot_axis', 1)-1
        #            subplot = self.config.getint(s, 'subplot', 1)-1
        #            if axis == 1 and self.axs[subplot,1] is None:
        #                self.axs[subplot,1] = self.axs[subplot-1,0].twinx()

        for s in series_names:
            # Each series is plotted on the appropriate axis with the series
            # name as label. The line parameters are optionally set in the
            # config file; if no value is set, matplotlib selects default
            # colours for the lines.
            subfig = self.config.getint(s, 'subplot', 1)-1
            axis = 0

            limits = self.config.get(s, 'limits', None)
            if limits is not None:
                l_min,l_max = [float(i) for i in limits.split(",")]
                y_min,y_max = self.axs[subfig,axis].get_ylim()
                self.axs[subfig,axis].set_ylim(min(y_min,l_min), max(y_max,l_max))

            # Scales start out with a scale of 'linear', change it if a scale is set
            scale = self.config.get(s, 'scale', None)
            if scale is not None:
                self.axs[subfig,axis].set_yscale(scale)

            # Set plot axis labels to the unit of the series, if set. Detect
            # multiple incompatibly set units and abort if found.
            units = self.config.get(s, 'units', '')
            label = self.axs[subfig,axis].get_ylabel()
            if label == '':
                self.axs[subfig,0].set_ylabel(units)
            elif units and label != units:
                raise RuntimeError(u"Axis units mismatch: %s and %s for subplot %d" % (units,label,subfig))


        self.axs[-1,0].set_xlabel(self.config.get('global', 'x_label', ''))


        self.fig.suptitle(self.config.get('global', 'plot_title', ''), fontsize=16)


    def format(self, name, results):
        if not results:
            return

        # Unzip the data into time series and data dicts to allow for plotting.
        t,data = zip(*results)
        series_names = data[0].keys()

        # The config file can set plot_axis to 1 or 2 for each test depending on
        # which axis the results should be plotted. The second axis is only
        # created if it is selected in one of the data sets selects it. The
        # matplotlib .twinx() function creates a second axis on the right-hand
        # side of the plot in the obvious way.

        for s in series_names:
            # Each series is plotted on the appropriate axis with the series
            # name as label. The line parameters are optionally set in the
            # config file; if no value is set, matplotlib selects default
            # colours for the lines.
            subfig = self.config.getint(s, 'subplot', 1)-1
            axis = 0 #self.config.getint(s, 'plot_axis', 1)-1

            # Set optional kwargs from config file
            kwargs = {}
            linewidth=self.config.get(s,'plot_linewidth', None)
            if linewidth is not None:
                kwargs['linewidth'] = float(linewidth)
            color=self.config.get(s, 'plot_linecolor', None)
            if color is not None:
                kwargs['color'] = color


            self.axs[subfig,axis].plot(t,
                           [(d[s] or 0.0) for d in data], # Non-existant datapoints are plotted as 0.0
                           self.config.get(s, 'plot_line', ''),
                           label=s,
                           **kwargs
                )


        for axs in self.axs:
            # Each axis has a set of handles/labels for the legend; combine them
            # into one list of handles/labels for displaying one legend that holds
            # all plot lines
            handles, labels = reduce(lambda x,y:(x[0]+y[0], x[1]+y[1]),
                                     [a.get_legend_handles_labels() for a in axs if a is not None])
            axs[0].legend(handles, labels,
                          bbox_to_anchor=(0., 1.02, 1., .102),
                          loc=3, ncol=2, mode='expand', borderaxespad=0.)

        # Since outputting image data to stdout does not make sense, we launch
        # the interactive matplotlib viewer if stdout is set for output.
        # Otherwise, the filename is passed to matplotlib, which selects an
        # appropriate output format based on the file name.
        if self.output == "-":
            self.plt.show()
        else:
            self.plt.savefig(self.output)
