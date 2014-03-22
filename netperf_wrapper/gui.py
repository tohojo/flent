## -*- coding: utf-8 -*-
##
## gui.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     22 March 2014
## Copyright (c) 2014, Toke Høiland-Jørgensen
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

import sys, os

try:
    from PyQt4 import QtCore, QtGui, uic
    from PyQt4.QtGui import *
except ImportError:
    raise RuntimeError("PyQt4 must be installed to use the GUI.")

try:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt4agg import NavigationToolbar2QTAgg as NavigationToolbar
except ImportError:
    raise RuntimeError("The GUI requires matplotlib with the QtAgg backend.")

from netperf_wrapper.build_info import DATA_DIR
from netperf_wrapper.resultset import ResultSet
from netperf_wrapper.formatters import PlotFormatter

__all__ = ['run_gui']

def run_gui(settings):
    app = QApplication(sys.argv[:1])
    mainwindow = MainWindow(settings)
    mainwindow.show()
    sys.exit(app.exec_())

def get_ui_class(filename):
    """Helper method to dynamically load a .ui file, construct a class
    inheriting from the ui class and the associated base class, and return
    that constructed class.

    This allows subclasses to inherit from the output of this function."""

    try:
        ui, base = uic.loadUiType(os.path.join(DATA_DIR, 'ui', filename))
    except Exception as e:
        raise RuntimeError("While loading ui file '%s': %s" % (filename, e))

    class C(ui, base):
        def __init__(self, *args):
            base.__init__(self, *args)
            self.setupUi(self)
    return C


class MainWindow(get_ui_class("mainwindow.ui")):

    def __init__(self, settings):
        super(MainWindow, self).__init__()
        self.settings = settings

        self.action_Open.activated.connect(self.on_open)
        self.action_Close_tab.activated.connect(self.close_tab)
        self.tabWidget.tabCloseRequested.connect(self.close_tab)

        self.load_files(self.settings.INPUT)

    def on_open(self):
        filenames = QFileDialog.getOpenFileNames(self,
                                                 "Select data file(s)",
                                                 os.getcwd(),
                                                 "Data files (*.json.gz)")
        self.load_files(filenames)

    def close_tab(self, idx=None):
        if idx is None:
            idx = self.tabWidget.currentIndex()
        widget = self.tabWidget.widget(idx)
        if widget is not None:
            self.tabWidget.removeTab(idx)
            widget.setParent(None)
            widget.deleteLater()

    def load_files(self, filenames):
        self.tabWidget.setUpdatesEnabled(False)
        for f in filenames:
            self.tabWidget.setCurrentIndex(
                self.tabWidget.addTab(ResultWidget(self.tabWidget, f, self.settings),
                                  os.path.basename(unicode(f))))
        self.tabWidget.setUpdatesEnabled(True)

class ResultWidget(get_ui_class("resultwidget.ui")):
    def __init__(self, parent, filename, settings):
        super(ResultWidget, self).__init__(parent)
        self.filename = filename
        self.settings = settings.copy()
        self.settings.OUTPUT = "-"

        self.results = ResultSet.load_file(unicode(filename))
        self.settings.update(self.results.meta())
        self.settings.load_test()

        self.formatter = PlotFormatter(self.settings)

        self.canvas = FigureCanvas(self.formatter.figure)
        self.canvas.setParent(self.graphDisplay)
        self.toolbar = NavigationToolbar(self.canvas, self.graphDisplay)

        vbl = QVBoxLayout()
        vbl.addWidget(self.canvas)
        vbl.addWidget(self.toolbar)
        self.graphDisplay.setLayout(vbl)

        self.formatter.format([self.results])
