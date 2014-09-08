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

import sys, os, signal, traceback

# Python 2/3 compatibility
try:
    unicode
except NameError:
    unicode = str

try:
    from PyQt4 import QtCore, QtGui, QtNetwork, uic
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *
except ImportError:
    raise RuntimeError("PyQt4 must be installed to use the GUI.")

try:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt4agg import NavigationToolbar2QT as NavigationToolbar
except ImportError:
    raise RuntimeError("The GUI requires matplotlib with the QtAgg backend.")

from netperf_wrapper.build_info import DATA_DIR
from netperf_wrapper.resultset import ResultSet
from netperf_wrapper.formatters import PlotFormatter
from netperf_wrapper import util

# IPC socket parameters
SOCKET_NAME_PREFIX = "netperf-wrapper-socket-"
SOCKET_DIR = "/tmp"

__all__ = ['run_gui']

def run_gui(settings):
    if check_running(settings):
        sys.exit(0)

    # Python does not get a chance to process SIGINT while in the Qt event loop,
    # so reset to the default signal handler which just kills the application.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Start up the Qt application and exit when it does
    app = QApplication(sys.argv[:1])
    mainwindow = MainWindow(settings)
    mainwindow.show()
    sys.exit(app.exec_())

def check_running(settings):
    """Check for a valid socket of an already running instance, and if so,
    connect to it and send the input file names."""
    if settings.NEW_GUI_INSTANCE:
        return False

    files = os.listdir(SOCKET_DIR)
    for f in files:
        if f.startswith(SOCKET_NAME_PREFIX):
            pid = int(f.split("-")[-1])
            try:
                os.kill(pid, 0)
                sys.stderr.write("Found a running instance with pid %d. Trying to connect... " % pid)
                # Signal handler did not raise an error, so the pid is running. Try to connect
                sock = QtNetwork.QLocalSocket()
                sock.connectToServer(os.path.join(SOCKET_DIR, f), QIODevice.WriteOnly)
                if not sock.waitForConnected(1000):
                    continue

                # Encode the filenames as a QStringList and pass them over the socket
                block = QByteArray()
                stream = QDataStream(block, QIODevice.WriteOnly)
                stream.setVersion(QDataStream.Qt_4_0)
                stream.writeQStringList([os.path.abspath(f) for f in settings.INPUT])
                sock.write(block)
                ret = sock.waitForBytesWritten(1000)
                sock.disconnectFromServer()

                # If we succeeded in sending stuff, we're done. Otherwise, if
                # there's another possibly valid socket in the list we'll try
                # again the next time round in the loop.
                if ret:
                    sys.stderr.write("Success!\n")
                    return True
                else:
                    sys.stderr.write("Error!\n")
            except OSError:
                # os.kill raises OSError if the pid does not exist
                pass
    return False

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
        self.last_dir = os.getcwd()
        self.defer_load = self.settings.INPUT

        self.actionOpen.activated.connect(self.on_open)
        self.actionCloseTab.activated.connect(self.close_tab)
        self.actionCloseAll.activated.connect(self.close_all)
        self.actionSavePlot.activated.connect(self.save_plot)
        self.actionLoadExtra.activated.connect(self.load_extra)
        self.actionOtherExtra.activated.connect(self.other_extra)
        self.actionClearExtra.activated.connect(self.clear_extra)
        self.actionScaleOpen.activated.connect(self.scale_open)
        self.actionNextTab.activated.connect(self.next_tab)
        self.actionPrevTab.activated.connect(self.prev_tab)
        self.actionRefresh.activated.connect(self.refresh_plot)

        self.viewArea.tabCloseRequested.connect(self.close_tab)
        self.viewArea.currentChanged.connect(self.activate_tab)

        self.plotDock.visibilityChanged.connect(self.plot_visibility)
        self.settingsDock.visibilityChanged.connect(self.settings_visibility)
        self.metadataDock.visibilityChanged.connect(self.metadata_visibility)
        self.metadataView.entered.connect(self.update_statusbar)

        # Set initial value of checkboxes from settings
        self.checkZeroY.setChecked(self.settings.ZERO_Y)
        self.checkInvertY.setChecked(self.settings.INVERT_Y)
        self.checkDisableLog.setChecked(not self.settings.LOG_SCALE)
        self.checkScaleMode.setChecked(self.settings.SCALE_MODE)
        self.checkSubplotCombine.setChecked(self.settings.SUBPLOT_COMBINE)
        self.checkAnnotation.setChecked(self.settings.ANNOTATE)
        self.checkLegend.setChecked(self.settings.PRINT_LEGEND)
        self.checkTitle.setChecked(self.settings.PRINT_TITLE)
        self.checkFilterLegend.setChecked(self.settings.FILTER_LEGEND)

        self.checkZeroY.toggled.connect(self.update_checkboxes)
        self.checkInvertY.toggled.connect(self.update_checkboxes)
        self.checkDisableLog.toggled.connect(self.update_checkboxes)
        self.checkScaleMode.toggled.connect(self.update_checkboxes)
        self.checkSubplotCombine.toggled.connect(self.update_checkboxes)
        self.checkAnnotation.toggled.connect(self.update_checkboxes)
        self.checkLegend.toggled.connect(self.update_checkboxes)
        self.checkTitle.toggled.connect(self.update_checkboxes)
        self.checkFilterLegend.toggled.connect(self.update_checkboxes)

        # Start IPC socket server on name corresponding to pid
        self.server = QtNetwork.QLocalServer()
        self.sockets = []
        self.server.newConnection.connect(self.new_connection)
        self.server.listen(os.path.join(SOCKET_DIR, "%s%d" %(SOCKET_NAME_PREFIX, os.getpid())))

    def closeEvent(self, event):
        # Cleaning up matplotlib figures can take a long time; disable it when
        # the application is exiting.
        for i in range(self.viewArea.count()):
            widget = self.viewArea.widget(i)
            widget.setUpdatesEnabled(False)
            widget.disable_cleanup()
        event.accept()

    # Helper functions to update menubar actions when dock widgets are closed
    def plot_visibility(self):
        self.actionPlotSelector.setChecked(not self.plotDock.isHidden())
    def settings_visibility(self):
        self.actionSettings.setChecked(not self.settingsDock.isHidden())
    def metadata_visibility(self):
        self.actionMetadata.setChecked(not self.metadataDock.isHidden())

    def update_checkboxes(self):
        widget = self.viewArea.currentWidget()
        if widget is not None:
            widget.zero_y(self.checkZeroY.isChecked())
            widget.invert_y(self.checkInvertY.isChecked())
            widget.disable_log(self.checkDisableLog.isChecked())
            widget.scale_mode(self.checkScaleMode.isChecked())
            widget.subplot_combine(self.checkSubplotCombine.isChecked())
            widget.draw_annotation(self.checkAnnotation.isChecked())
            widget.draw_legend(self.checkLegend.isChecked())
            widget.draw_title(self.checkTitle.isChecked())
            widget.filter_legend(self.checkFilterLegend.isChecked())

    def new_connection(self):
        sock = self.server.nextPendingConnection()
        self.sockets.append(sock)
        sock.readyRead.connect(self.data_ready)

    def data_ready(self):
        for s in self.sockets:
            if s.isReadable():
                stream = QDataStream(s)
                filenames = stream.readQStringList()
                self.load_files(filenames)
                self.sockets.remove(s)
                self.raise_()
                self.activateWindow()

    def update_statusbar(self, idx):
        self.statusBar().showMessage(
            self.metadataView.model().data(idx, Qt.StatusTipRole), 1000)

    def get_opennames(self):
        filenames = QFileDialog.getOpenFileNames(self,
                                                 "Select data file(s)",
                                                 self.last_dir,
                                                 "Data files (*.json.gz)")
        if filenames:
            self.last_dir = os.path.dirname(unicode(filenames[0]))

        return filenames

    def on_open(self):
        filenames = self.get_opennames()
        self.load_files(filenames)

    def load_extra(self):
        widget = self.viewArea.currentWidget()
        if widget is None:
            return

        filenames = self.get_opennames()
        if not filenames:
            return
        with widget.updates_disabled():
            added = widget.load_files(filenames)

        if added == 0:
            self.warn_nomatch()

    def other_extra(self):
        idx = self.viewArea.currentIndex()
        widget = self.viewArea.currentWidget()
        if widget is None:
            return

        added = 0
        with widget.updates_disabled():
            for i in range(self.viewArea.count()):
                if i != idx and widget.add_extra(self.viewArea.widget(i).results):
                    added += 1

        if not added:
            self.warn_nomatch()

    def clear_extra(self):
        widget = self.viewArea.currentWidget()
        if widget is not None:
            widget.clear_extra()

    def scale_open(self):
        self.checkScaleMode.setChecked(True)
        self.update_checkboxes()
        if self.viewArea.count() < 2:
            return
        all_results = []
        for i in range(self.viewArea.count()):
            all_results.append(self.viewArea.widget(i).results)
        for i in range(self.viewArea.count()):
            widget = self.viewArea.widget(i)
            with widget.updates_disabled():
                for r in [j[1] for j in enumerate(all_results) if j != i]:
                    widget.add_extra(r)

        self.viewArea.currentWidget().update()

    def save_plot(self):
        widget = self.viewArea.currentWidget()
        if widget is not None:
            widget.save_plot()

    def refresh_plot(self):
        widget = self.viewArea.currentWidget()
        if widget is not None:
            widget.update()

    def warn_nomatch(self):
        QMessageBox.warning(self, "No matching datasets found",
                           "Could not find any datasets with a matching test name to add.")


    def show(self):
        super(MainWindow, self).show()

        # Deferring loading until here means the window has been created and a busy
        # cursor can be shown.
        if self.defer_load:
            self.load_files(self.defer_load)
            self.defer_load = None

    def shorten_tabs(self):
        """Try to shorten tab labels by filtering out common substrings.

        Approach: Find longest common substring and replace that with ellipses
        in the name. Also, find longest common *prefix* and filter that out as
        well.

        Since tab titles start with the test name, and several tests are
        commonly loaded as well, this double substring search helps cut off the
        (common) test name in the case where the longest substring is in the
        middle of the tab name."""

        titles = []
        long_titles = []
        for i in range(self.viewArea.count()):
            titles.append(self.viewArea.widget(i).title)
            long_titles.append(self.viewArea.widget(i).long_title)

        substr = util.long_substr(titles)
        prefix = util.long_substr(titles, prefix_only=True)
        for i,t in enumerate(titles):
            if len(substr) > 0:
                text = t.replace(substr, "...")
            if len(prefix) > 0 and prefix != substr:
                text = text.replace(prefix, "...").replace("......", "...")
            if len(substr) == 0 or text == "...":
                text = t
            self.viewArea.setTabText(i, text)
            self.viewArea.setTabToolTip(i, long_titles[i])


    def close_tab(self, idx=None):
        self.busy_start()
        if idx is None:
            idx = self.viewArea.currentIndex()
        widget = self.viewArea.widget(idx)
        if widget is not None:
            widget.setUpdatesEnabled(False)
            widget.disconnect_all()
            self.viewArea.removeTab(idx)
            widget.setParent(None)
            widget.deleteLater()
            self.shorten_tabs()
        self.busy_end()

    def close_all(self):
        self.busy_start()
        widgets = []
        for i in range(self.viewArea.count()):
            widgets.append(self.viewArea.widget(i))
        self.viewArea.clear()
        for w in widgets:
            w.setUpdatesEnabled(False)
            w.disconnect_all()
            w.setParent(None)
            w.deleteLater()
        self.busy_end()

    def move_tab(self, move_by):
        count = self.viewArea.count()
        if count:
            idx = self.viewArea.currentIndex()
            self.viewArea.setCurrentIndex((idx + move_by) % count)

    def next_tab(self):
        self.move_tab(1)

    def prev_tab(self):
        self.move_tab(-1)

    def busy_start(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)

    def busy_end(self):
        QApplication.restoreOverrideCursor()

    def activate_tab(self, idx=None):
        if idx is None:
            return
        widget = self.viewArea.widget(idx)
        if widget is None:
            return

        self.plotView.setModel(widget.plotModel)
        self.plotView.setSelectionModel(widget.plotSelectionModel)
        self.metadataView.setModel(widget.metadataModel)
        self.metadataView.setSelectionModel(widget.metadataSelectionModel)
        self.update_checkboxes()
        self.actionSavePlot.setEnabled(widget.can_save())
        widget.redraw()

    def update_plots(self, testname, plotname):
        for i in range(self.viewArea.count()):
            widget = self.viewArea.widget(i)
            if widget and widget.settings.NAME == testname:
                widget.change_plot(plotname)

    def load_files(self, filenames):
        self.busy_start()
        widget = self.viewArea.currentWidget()
        if widget is not None:
            current_plot = widget.current_plot()
        else:
            current_plot = None
        widget = None
        for f in filenames:
            try:
                widget = ResultWidget(self.viewArea, f, self.settings)
            except Exception as e:
                traceback.print_exc()
                if isinstance(e, RuntimeError):
                    err = "%s" % e
                else:
                    typ,val,tra = sys.exc_info()
                    err = "".join(traceback.format_exception_only(typ,val))
                QMessageBox.warning(self, "Error loading file",
                                    "Error while loading data file:\n\n%s\n\nSkipping. Full traceback output to console." % err)
                continue

            widget.update_start.connect(self.busy_start)
            widget.update_end.connect(self.busy_end)
            widget.plot_changed.connect(self.update_plots)
            widget.change_plot(current_plot)
            self.viewArea.addTab(widget, widget.title)
            self.last_dir = os.path.dirname(unicode(f))
        if widget is not None:
            self.viewArea.setCurrentWidget(widget)
        self.shorten_tabs()
        self.busy_end()

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
        if not role in (Qt.DisplayRole, Qt.StatusTipRole, Qt.ToolTipRole):
            return None

        item = idx.internalPointer()
        if role in (Qt.StatusTipRole, Qt.ToolTipRole):
            if item.name:
                return "%s: %s" % (item.name, item.value)
            else:
                return item.value
        if idx.column() == 0:
            return item.name
        elif idx.column() == 1:
            return unicode(item.value)

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


class UpdateDisabler(object):
    def __init__(self, widget):
        self.widget = widget
    def __enter__(self):
        self.widget.setUpdatesEnabled(False)
    def __exit__(self, *ignored):
        self.widget.setUpdatesEnabled(True)
        self.widget.update()

class ResultWidget(get_ui_class("resultwidget.ui")):

    update_start = pyqtSignal()
    update_end = pyqtSignal()
    plot_changed = pyqtSignal('QString', 'QString')

    def __init__(self, parent, filename, settings):
        super(ResultWidget, self).__init__(parent)
        self.filename = unicode(filename)
        self.settings = settings.copy()
        self.dirty = True
        self.settings.OUTPUT = "-"

        self.results = ResultSet.load_file(self.filename)
        self.extra_results = []
        self.settings.update(self.results.meta())
        self.settings.load_test(informational=True)
        self.settings.compute_missing_results(self.results)

        try:
            self.formatter = PlotFormatter(self.settings)
        except Exception as e:
            traceback.print_exc()
            if isinstance(e, RuntimeError):
                err = "%s" % e
            else:
                typ,val,tra = sys.exc_info()
                err = "".join(traceback.format_exception_only(typ,val))
            QMessageBox.warning(self, "Error loading plot",
                                "Error while loading plot:\n\n%s\nFalling back to default plot. Full traceback output to console." % err)

            self.settings.PLOT = self.settings.DEFAULTS['PLOT']
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
            self.title = "%s - %s" % (self.settings.NAME, self.settings.TITLE)
            self.long_title = "%s - %s" % (self.title, self.settings.TIME.strftime("%Y-%m-%d %H:%M:%S"))
        else:
            self.title = "%s - %s" % (self.settings.NAME,
                                      self.settings.TIME.strftime("%Y-%m-%d %H:%M:%S"))
            self.long_title = self.title

        if self.settings.GUI_NO_DEFER:
            self.redraw()

    def disconnect_all(self):
        for s in (self.update_start, self.update_end, self.plot_changed):
            s.disconnect()

    def disable_cleanup(self):
        self.formatter.disable_cleanup = True

    def load_files(self, filenames):
        added = 0
        for f in filenames:
            if self.add_extra(ResultSet.load_file(unicode(f))):
                self.update(False)
                added += 1
        self.redraw()
        return added

    def add_extra(self, resultset):
        if resultset.meta('NAME') == self.settings.NAME:
            self.extra_results.append(resultset)
            self.update()
            return True
        return False

    def clear_extra(self):
        self.extra_results = []
        self.update()

    def can_save(self):
        # Check for attribute to not crash on a matplotlib version that does not
        # have the save action.
        return hasattr(self.toolbar, 'save_figure')
    def save_plot(self):
        if self.can_save():
            self.toolbar.save_figure()

    def zero_y(self, val=None):
        if val is not None and val != self.settings.ZERO_Y:
            self.settings.ZERO_Y = val
            self.update()
        return self.settings.ZERO_Y

    def invert_y(self, val=None):
        if val is not None and val != self.settings.INVERT_Y:
            self.settings.INVERT_Y = val
            self.update()
        return self.settings.INVERT_Y

    def disable_log(self, val=None):
        if val is not None and val == self.settings.LOG_SCALE:
            self.settings.LOG_SCALE = not val
            self.update()
        return not self.settings.LOG_SCALE

    def scale_mode(self, val=None):
        if val is not None and val != self.settings.SCALE_MODE:
            self.settings.SCALE_MODE = val
            self.update()
        return self.settings.SCALE_MODE

    def subplot_combine(self, val=None):
        if val is not None and val != self.settings.SUBPLOT_COMBINE:
            self.settings.SUBPLOT_COMBINE = val
            self.update()
        return self.settings.SUBPLOT_COMBINE

    def draw_annotation(self, val=None):
        if val is not None and val != self.settings.ANNOTATE:
            self.settings.ANNOTATE = val
            self.update()
        return self.settings.ANNOTATE

    def draw_legend(self, val=None):
        if val is not None and val != self.settings.PRINT_LEGEND:
            self.settings.PRINT_LEGEND = val
            self.update()
        return self.settings.PRINT_LEGEND

    def draw_title(self, val=None):
        if val is not None and val != self.settings.PRINT_TITLE:
            self.settings.PRINT_TITLE = val
            self.update()
        return self.settings.PRINT_TITLE

    def filter_legend(self, val=None):
        if val is not None and val != self.settings.FILTER_LEGEND:
            self.settings.FILTER_LEGEND = val
            self.update()
        return self.settings.FILTER_LEGEND

    def change_plot(self, plot_name):
        if isinstance(plot_name, QModelIndex):
            plot_name = self.plotModel.name_of(plot_name)
        plot_name = unicode(plot_name)
        if plot_name != self.settings.PLOT and plot_name in self.settings.PLOTS:
            self.settings.PLOT = plot_name
            self.plotSelectionModel.setCurrentIndex(self.plotModel.index_of(self.settings.PLOT),
                                                    QItemSelectionModel.SelectCurrent)
            self.plot_changed.emit(self.settings.NAME, self.settings.PLOT)
            self.update()
            return True
        return False

    def current_plot(self):
        return self.settings.PLOT

    def updates_disabled(self):
        return UpdateDisabler(self)

    def update(self, redraw=True):
        self.dirty = True
        if redraw and ((self.isVisible() and self.updatesEnabled()) or self.settings.GUI_NO_DEFER):
            self.redraw()

    def redraw(self):
        if not self.dirty:
            return
        self.update_start.emit()
        try:
            self.formatter.init_plots()
            if self.settings.SCALE_MODE:
                self.settings.SCALE_DATA = self.extra_results
                self.formatter.format([self.results])
            else:
                self.settings.SCALE_DATA = []
                self.formatter.format([self.results] + self.extra_results)
            self.canvas.draw()
            self.dirty = False
        except Exception as e:
            traceback.print_exc()
            typ,val,tra = sys.exc_info()
            err = "".join(traceback.format_exception_only(typ,val))
            QMessageBox.warning(self, "Error plotting",
                                "Unhandled exception while plotting:\n\n%s\nAborting. Full traceback output to console." % err)
        finally:
            self.update_end.emit()
