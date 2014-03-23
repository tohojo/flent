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
    unicode
except NameError:
    unicode = str

try:
    from PyQt4 import QtCore, QtGui, uic
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *
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
        self.viewArea.tabCloseRequested.connect(self.close_tab)
        self.viewArea.currentChanged.connect(self.activate_tab)

        self.plotDock.visibilityChanged.connect(self.plot_visibility)
        self.settingsDock.visibilityChanged.connect(self.settings_visibility)
        self.metadataDock.visibilityChanged.connect(self.metadata_visibility)
        self.metadataView.entered.connect(self.update_statusbar)

        self.checkZeroY.toggled.connect(self.zero_y_toggled)
        self.checkDisableLog.toggled.connect(self.disable_log_toggled)
        self.checkAnnotation.toggled.connect(self.annotation_toggled)
        self.checkLegend.toggled.connect(self.legend_toggled)
        self.checkTitle.toggled.connect(self.title_toggled)

        self.load_files(self.settings.INPUT)

    # Helper functions to update menubar actions when dock widgets are closed
    def plot_visibility(self):
        self.action_Plot_selector.setChecked(not self.plotDock.isHidden())
    def settings_visibility(self):
        self.action_Settings.setChecked(not self.settingsDock.isHidden())
    def metadata_visibility(self):
        self.action_Metadata.setChecked(not self.metadataDock.isHidden())

    def zero_y_toggled(self, val):
        widget = self.viewArea.currentWidget()
        if widget is not None:
            widget.zero_y(val)
    def disable_log_toggled(self, val):
        widget = self.viewArea.currentWidget()
        if widget is not None:
            widget.disable_log(val)
    def annotation_toggled(self, val):
        widget = self.viewArea.currentWidget()
        if widget is not None:
            widget.draw_annotation(val)
    def legend_toggled(self, val):
        widget = self.viewArea.currentWidget()
        if widget is not None:
            widget.draw_legend(val)
    def title_toggled(self, val):
        widget = self.viewArea.currentWidget()
        if widget is not None:
            widget.draw_title(val)

    def update_checkboxes(self):
        widget = self.viewArea.currentWidget()
        if widget is not None:
            self.checkZeroY.setChecked(widget.zero_y())
            self.checkDisableLog.setChecked(widget.disable_log())
            self.checkAnnotation.setChecked(widget.draw_annotation())
            self.checkLegend.setChecked(widget.draw_legend())
            self.checkTitle.setChecked(widget.draw_title())

    def update_statusbar(self, idx):
        self.statusBar().showMessage(
            self.metadataView.model().data(idx, Qt.StatusTipRole), 1000)

    def on_open(self):
        filenames = QFileDialog.getOpenFileNames(self,
                                                 "Select data file(s)",
                                                 os.getcwd(),
                                                 "Data files (*.json.gz)")
        self.load_files(filenames)

    def close_tab(self, idx=None):
        if idx is None:
            idx = self.viewArea.currentIndex()
        widget = self.viewArea.widget(idx)
        if widget is not None:
            self.viewArea.removeTab(idx)
            widget.setParent(None)
            widget.deleteLater()

    def activate_tab(self, idx=None):
        if idx is None:
            return

        widget = self.viewArea.widget(idx)
        self.plotView.setModel(widget.plotModel)
        self.plotView.setSelectionModel(widget.plotSelectionModel)
        self.metadataView.setModel(widget.metadataModel)
        self.metadataView.setSelectionModel(widget.metadataSelectionModel)
        self.update_checkboxes()

    def load_files(self, filenames):
        self.setCursor(Qt.WaitCursor)
        for f in filenames:
            widget = ResultWidget(self.viewArea, f, self.settings)
            self.viewArea.setCurrentIndex(self.viewArea.addTab(widget, widget.title))
        self.setCursor(Qt.ArrowCursor)


class PlotModel(QStringListModel):

    def __init__(self, parent, settings):
        QStringListModel.__init__(self, parent)
        self.settings = settings

        self.keys = list(self.settings.PLOTS.keys())

        strings = []
        for k,v in self.settings.PLOTS.items():
            strings.append("%s (%s)" % (k, v['description']))
        self.setStringList(strings)


    def index_of(self, plot):
        return self.index(self.keys.index(plot))

    def name_of(self, idx):
        return self.keys[idx.row()]


class TreeItem(object):

    def __init__(self, parent, name, value):
        self.parent = parent
        self.name = name
        self.children = []

        if isinstance(value, list):
            self.value = ""
            for v in value:
                self.children.append(TreeItem(self, "", v))
        elif isinstance(value, dict):
            self.value = ""
            for k,v in sorted(value.items()):
                self.children.append(TreeItem(self, k, v))
        else:
            self.value = value
            self.children = []

    def __len__(self):
        return len(self.children)


class MetadataModel(QAbstractItemModel):

    header_names = [u"Name", u"Value"]

    def __init__(self, parent, datadict):
        QAbstractItemModel.__init__(self, parent)
        self.root = TreeItem(None, "root", datadict)

    def columnCount(self, parent):
        return 2

    def rowCount(self, parent):
        if parent.isValid():
            return len(parent.internalPointer())
        return len(self.root)

    def headerData(self, section, orientation, role = Qt.DisplayRole):
        if orientation == Qt.Vertical or role != Qt.DisplayRole:
            return None
        return self.header_names[section]

    def data(self, idx, role = Qt.DisplayRole):
        if not role in (Qt.DisplayRole, Qt.StatusTipRole):
            return None

        item = idx.internalPointer()
        if role == Qt.StatusTipRole:
            if item.name:
                return "%s: %s" % (item.name, item.value)
            else:
                return item.value
        if idx.column() == 0:
            return item.name
        elif idx.column() == 1:
            return item.value

    def parent(self, idx):
        item = idx.internalPointer()
        if item is None:
            return QModelIndex()
        return self.createIndex(0, 0, item.parent)

    def index(self, row, column, parent):
        item = parent.internalPointer()
        if item is None:
            item = self.root
        return self.createIndex(row, column, item.children[row])


class ResultWidget(get_ui_class("resultwidget.ui")):
    def __init__(self, parent, filename, settings):
        super(ResultWidget, self).__init__(parent)
        self.filename = unicode(filename)
        self.settings = settings.copy()
        self.settings.OUTPUT = "-"

        self.results = ResultSet.load_file(self.filename)
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

        self.plotModel = PlotModel(self, self.settings)
        self.plotSelectionModel = QItemSelectionModel(self.plotModel)
        self.plotSelectionModel.setCurrentIndex(self.plotModel.index_of(self.settings.PLOT),
                                                QItemSelectionModel.SelectCurrent)
        self.plotSelectionModel.currentChanged.connect(self.change_plot)

        self.metadataModel = MetadataModel(self, self.results.meta())
        self.metadataSelectionModel = QItemSelectionModel(self.metadataModel)

        if self.settings.TITLE:
            self.title = "%s - %s - %s" % (self.settings.NAME, self.settings.TITLE,
                                           self.settings.TIME.strftime("%Y-%m-%d %H:%M:%S"))
        else:
            self.title = "%s - %s" % (self.settings.NAME, self.settings.TIME.strftime("%Y-%m-%d %H:%M:%S"))

        self.update()

    def zero_y(self, val=None):
        if val is not None:
            self.settings.ZERO_Y = val
            self.update()
        return self.settings.ZERO_Y

    def disable_log(self, val=None):
        if val is not None:
            self.settings.LOG_SCALE = not val
            self.update()
        return not self.settings.LOG_SCALE

    def draw_annotation(self, val=None):
        if val is not None:
            self.settings.ANNOTATE = val
            self.update()
        return self.settings.ANNOTATE

    def draw_legend(self, val=None):
        if val is not None:
            self.settings.PRINT_LEGEND = val
            self.update()
        return self.settings.PRINT_LEGEND

    def draw_title(self, val=None):
        if val is not None:
            self.settings.PRINT_TITLE = val
            self.update()
        return self.settings.PRINT_TITLE

    def change_plot(self, idx, prev):
        self.settings.PLOT = self.plotModel.name_of(idx)
        self.update()


    def update(self):
        self.formatter.init_plots()
        self.formatter.format([self.results])
        self.canvas.draw()
