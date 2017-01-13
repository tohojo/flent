# -*- coding: utf-8 -*-
#
# gui.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     22 March 2014
# Copyright (c) 2014-2016, Toke Høiland-Jørgensen
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

import base64
import logging
import os
import signal
import sys
import tempfile
import time

try:
    import cPickle as pickle
except ImportError:
    import pickle

from itertools import chain
from multiprocessing import Pool, Queue

from flent import util, batch, loggers, resultset, plotters
from flent.build_info import DATA_DIR, VERSION
from flent.loggers import get_logger, add_log_handler, remove_log_handler, \
    set_queue_handler
from flent.resultset import ResultSet
from flent.settings import ListTests, new as new_settings

logger = get_logger(__name__)

mswindows = (sys.platform == "win32")

# Python 2/3 compatibility
try:
    unicode
except NameError:
    unicode = str

try:
    from os import cpu_count
except ImportError:
    from multiprocessing import cpu_count

try:
    CPU_COUNT = cpu_count()
except NotImplementedError:
    CPU_COUNT = 1


FORCE_QT4 = False
try:
    import matplotlib
    ver = tuple([int(i) for i in matplotlib.__version__.split(".")[:2]])
    if ver < (1, 4):
        logger.debug("Forcing fallback to Qt4 because of matplotlib version %s.",
                     matplotlib.__version__)
        FORCE_QT4 = True
    matplotlib.use("Agg")
except ImportError:
    raise RuntimeError("The GUI requires matplotlib.")


try:
    if FORCE_QT4:
        raise ImportError("Force fallback to Qt4")

    from PyQt5 import QtCore, QtGui, uic

    from PyQt5.QtWidgets import QMessageBox, QFileDialog, QTreeView, \
        QAbstractItemView, QMenu, QAction, QTableView, QHeaderView, \
        QVBoxLayout, QApplication, QPlainTextEdit

    from PyQt5.QtGui import QFont, QCursor, QMouseEvent, QKeySequence, \
        QResizeEvent

    from PyQt5.QtCore import Qt, QIODevice, QByteArray, \
        QDataStream, QSettings, QTimer, QEvent, pyqtSignal, \
        QAbstractItemModel, QAbstractTableModel, QModelIndex, \
        QItemSelectionModel, QStringListModel

    from PyQt5.QtNetwork import QLocalSocket, QLocalServer

    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg \
        as FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT \
        as NavigationToolbar
    QTVER = 5
except ImportError:
    try:
        from PyQt4 import QtCore, QtGui, uic

        from PyQt4.QtGui import QMessageBox, QFileDialog, QTreeView, \
            QAbstractItemView, QMenu, QAction, QFont, QTableView, QCursor, \
            QHeaderView, QVBoxLayout, QItemSelectionModel, QMouseEvent, \
            QApplication, QStringListModel, QKeySequence, QResizeEvent, \
            QPlainTextEdit

        from PyQt4.QtCore import Qt, QIODevice, QByteArray, \
            QDataStream, QSettings, QTimer, QEvent, pyqtSignal, \
            QAbstractItemModel, QAbstractTableModel, QModelIndex

        from PyQt4.QtNetwork import QLocalSocket, QLocalServer

        from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg \
            as FigureCanvas
        from matplotlib.backends.backend_qt4agg import NavigationToolbar2QT \
            as NavigationToolbar

        QTVER = 4

        logger.warning("Falling back to Qt4 for the GUI. "
                       "Please consider installing PyQt5.\n")
    except ImportError:
        raise RuntimeError("PyQt must be installed to use the GUI.")


# The file selector dialog on OSX is buggy, so switching allowed file extensions
# doesn't work with double extensions. So just include the deprecated extensions
# in the default ones on Mac.
if hasattr(QtGui, "qt_mac_set_native_menubar"):
    FILE_SELECTOR_STRING = "Flent data files " \
                           "(*.flent *.flnt *.flent.gz *.flent.bz2 *.json.gz)"
    osx = True
else:
    FILE_SELECTOR_STRING = "Flent data files (*.flent *.flent.gz *.flent.bz2);;" \
                           "Flent data files - " \
                           "deprecated extensions (*.flnt *.json.gz)"
    osx = False
FILE_SELECTOR_STRING += ";;All files (*.*)"


# IPC socket parameters
SOCKET_NAME_PREFIX = "flent-socket-"
SOCKET_DIR = tempfile.gettempdir()

__all__ = ['run_gui']


def run_gui(settings):
    if check_running(settings):
        return 0

    plotters.init_matplotlib("-", settings.USE_MARKERS,
                             settings.LOAD_MATPLOTLIBRC)

    # Python does not get a chance to process SIGINT while in the Qt event loop,
    # so reset to the default signal handler which just kills the application.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Start up the Qt application and exit when it does
    app = QApplication(sys.argv[:1])
    mainwindow = MainWindow(settings)
    mainwindow.show()
    return app.exec_()


def pool_init_func(settings, queue):
    plotters.init_matplotlib("-", settings.USE_MARKERS,
                             settings.LOAD_MATPLOTLIBRC)
    set_queue_handler(queue)


def check_running(settings):
    """Check for a valid socket of an already running instance, and if so,
    connect to it and send the input file names."""
    if settings.NEW_GUI_INSTANCE or mswindows:
        return False

    files = os.listdir(SOCKET_DIR)
    for f in files:
        if f.startswith(SOCKET_NAME_PREFIX):
            try:
                pid = int(f.split("-")[-1])
                os.kill(pid, 0)
                logger.info(
                    "Found a running instance with pid %d. "
                    "Trying to connect... ", pid)
                # Signal handler did not raise an error, so the pid is running.
                # Try to connect
                sock = QLocalSocket()
                sock.connectToServer(os.path.join(
                    SOCKET_DIR, f), QIODevice.WriteOnly)
                if not sock.waitForConnected(1000):
                    continue

                # Encode the filenames as a QStringList and pass them over the
                # socket
                block = QByteArray()
                stream = QDataStream(block, QIODevice.WriteOnly)
                stream.setVersion(QDataStream.Qt_4_0)
                stream.writeQStringList([os.path.abspath(f)
                                         for f in settings.INPUT])
                sock.write(block)
                ret = sock.waitForBytesWritten(1000)
                sock.disconnectFromServer()

                # If we succeeded in sending stuff, we're done. Otherwise, if
                # there's another possibly valid socket in the list we'll try
                # again the next time round in the loop.
                if ret:
                    logger.info("Success!\n")
                    return True
                else:
                    logger.info("Error!\n")
            except (OSError, ValueError):
                # os.kill raises OSError if the pid does not exist
                # int() returns a ValueError if the pid is not an integer
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


class LoadedResultset(dict):
    pass


def results_load_helper(filename):
    try:
        r = ResultSet.load_file(filename)
        s = new_settings()
        s.update(r.meta())
        s.load_test(informational=True)
        s.compute_missing_results(r)
        return LoadedResultset(results=r,
                               plots=s.PLOTS,
                               data_sets=s.DATA_SETS,
                               defaults=s.DEFAULTS,
                               description=s.DESCRIPTION,
                               title=r.title)
    except Exception as e:
        logger.exception(unicode(e))
        logger.warning("Unable to load file '%s'.", filename)
        return None


class MainWindow(get_ui_class("mainwindow.ui")):

    def __init__(self, settings):
        super(MainWindow, self).__init__()
        self.settings = settings
        self.last_dir = os.getcwd()

        self.defer_load = self.settings.INPUT
        self.load_queue = []
        self.load_timer = QTimer(self)
        self.load_timer.timeout.connect(self.load_one)
        self.focus_new = False

        if self.settings.HOVER_HIGHLIGHT is None:
            self.settings.HOVER_HIGHLIGHT = True

        self.setWindowTitle("Flent GUI v%s" % VERSION)

        self.actionNewTab.triggered.connect(self.add_tab)
        self.actionOpen.triggered.connect(self.on_open)
        self.actionCloseTab.triggered.connect(self.close_tab)
        self.actionCloseAll.triggered.connect(self.close_all)
        self.actionSavePlot.triggered.connect(self.save_plot)
        self.actionLoadExtra.triggered.connect(self.load_extra)
        self.actionOtherExtra.triggered.connect(self.other_extra)
        self.actionClearExtra.triggered.connect(self.clear_extra)
        self.actionScaleOpen.triggered.connect(self.scale_open)
        self.actionNextTab.triggered.connect(self.next_tab)
        self.actionNextTab.setShortcuts([QKeySequence("Ctrl+Tab"),
                                         QKeySequence("Ctrl+Right")])
        self.actionPrevTab.triggered.connect(self.prev_tab)
        self.actionPrevTab.setShortcuts([QKeySequence("Ctrl+Shift+Backtab"),
                                         QKeySequence("Ctrl+Left")])
        self.actionRefresh.triggered.connect(self.refresh_plot)
        self.actionNewTest.triggered.connect(self.run_test)

        self.viewArea.tabCloseRequested.connect(self.close_tab)
        self.viewArea.currentChanged.connect(self.activate_tab)

        self.plotDock.visibilityChanged.connect(self.plot_visibility)
        self.metadataDock.visibilityChanged.connect(self.metadata_visibility)
        self.openFilesDock.visibilityChanged.connect(self.open_files_visibility)
        self.logEntriesDock.visibilityChanged.connect(self.log_entries_visibility)
        self.expandButton.clicked.connect(self.metadata_column_resize)

        # Set initial value of checkboxes from settings
        self.checkZeroY.setChecked(self.settings.ZERO_Y)
        self.checkInvertY.setChecked(self.settings.INVERT_Y)
        self.checkLogScale.setChecked(self.settings.LOG_SCALE)
        self.checkScaleMode.setChecked(self.settings.SCALE_MODE)
        self.checkSubplotCombine.setChecked(self.settings.SUBPLOT_COMBINE)
        self.checkAnnotation.setChecked(self.settings.ANNOTATE)
        self.checkLegend.setChecked(self.settings.PRINT_LEGEND)
        self.checkTitle.setChecked(self.settings.PRINT_TITLE)
        self.checkFilterLegend.setChecked(self.settings.FILTER_LEGEND)
        self.checkHighlight.setChecked(self.settings.HOVER_HIGHLIGHT)
        self.checkDebugLog.setChecked(loggers.out_handler.level == loggers.DEBUG)
        self.checkExceptionLog.setChecked(self.settings.DEBUG_ERROR)

        self.checkZeroY.toggled.connect(self.update_checkboxes)
        self.checkInvertY.toggled.connect(self.update_checkboxes)
        self.checkLogScale.toggled.connect(self.update_checkboxes)
        self.checkScaleMode.toggled.connect(self.update_checkboxes)
        self.checkSubplotCombine.toggled.connect(self.update_checkboxes)
        self.checkAnnotation.toggled.connect(self.update_checkboxes)
        self.checkLegend.toggled.connect(self.update_checkboxes)
        self.checkTitle.toggled.connect(self.update_checkboxes)
        self.checkFilterLegend.toggled.connect(self.update_checkboxes)
        self.checkHighlight.toggled.connect(self.update_checkboxes)
        self.checkDebugLog.toggled.connect(self.update_checkboxes)
        self.checkExceptionLog.toggled.connect(self.update_checkboxes)

        self.tabifyDockWidget(self.openFilesDock, self.metadataDock)
        self.tabifyDockWidget(self.openFilesDock, self.logEntriesDock)
        self.openFilesDock.raise_()
        self.open_files = OpenFilesModel(self)
        self.openFilesView = OpenFilesView(self.openFilesDock)
        self.openFilesDock.setWidget(self.openFilesView)
        self.openFilesView.setModel(self.open_files)
        self.openFilesView.clicked.connect(self.open_files.on_click)

        self.metadataView = MetadataView(self, self.openFilesView)
        self.metadataView.entered.connect(self.update_statusbar)
        self.metadataLayout.insertWidget(0, self.metadataView)
        self.expandButton.clicked.connect(self.metadataView.expandAll)

        self.logEntries = QPlainTextLogger(self, logging.DEBUG,
                                           statusbar=self.statusBar())
        add_log_handler(self.logEntries)
        self.logEntriesDock.setWidget(self.logEntries.widget)
        self.log_queue = Queue()
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self.read_log_queue)
        self.log_timer.setInterval(100)
        self.log_timer.start()

        # Start IPC socket server on name corresponding to pid
        self.server = QLocalServer()
        self.sockets = []
        self.server.newConnection.connect(self.new_connection)
        self.server.listen(os.path.join(SOCKET_DIR, "%s%d" %
                                        (SOCKET_NAME_PREFIX, os.getpid())))

        self.read_settings()

        self.worker_pool = Pool(initializer=pool_init_func,
                                initargs=(self.settings, self.log_queue))

        logger.info("GUI loaded. Running on PyQt v%s.", QtCore.PYQT_VERSION_STR)

    def read_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            logging.getLogger().handle(msg)

    def get_last_dir(self):
        if 'savefig.directory' in matplotlib.rcParams:
            return matplotlib.rcParams['savefig.directory']
        return self._last_dir

    def set_last_dir(self, value):
        if 'savefig.directory' in matplotlib.rcParams:
            matplotlib.rcParams['savefig.directory'] = value
        else:
            self._last_dir = value
    last_dir = property(get_last_dir, set_last_dir)

    def read_settings(self):
        settings = QSettings("Flent", "GUI")
        if settings.contains("mainwindow/geometry"):
            geom = settings.value("mainwindow/geometry")
            if hasattr(geom, 'toByteArray'):
                geom = geom.toByteArray()
            self.restoreGeometry(geom)
        if settings.contains("mainwindow/windowState"):
            winstate = settings.value("mainwindow/windowState")
            if hasattr(winstate, 'toByteArray'):
                winstate = winstate.toByteArray()
            self.restoreState(winstate)
            self.metadata_visibility()
            self.plot_visibility()
            self.open_files_visibility()
        if settings.contains("open_files/columns"):
            value = settings.value("open_files/columns")
            if hasattr(value, 'toString'):
                value = value.toString()
            self.open_files.restore_columns(value)
        if settings.contains("open_files/column_order"):
            value = settings.value("open_files/column_order")
            if hasattr(value, 'toByteArray'):
                value = value.toByteArray()
            self.openFilesView.horizontalHeader().restoreState(value)
            self.openFilesView.setSortingEnabled(True)

    def closeEvent(self, event):
        # Cleaning up matplotlib figures can take a long time; disable it when
        # the application is exiting.
        for i in range(self.viewArea.count()):
            widget = self.viewArea.widget(i)
            widget.setUpdatesEnabled(False)
            widget.disable_cleanup()
        settings = QSettings("Flent", "GUI")
        settings.setValue("mainwindow/geometry", self.saveGeometry())
        settings.setValue("mainwindow/windowState", self.saveState())
        settings.setValue("open_files/columns", self.open_files.save_columns())
        settings.setValue("open_files/column_order",
                          self.openFilesView.horizontalHeader().saveState())

        self.worker_pool.terminate()

        event.accept()

    # Helper functions to update menubar actions when dock widgets are closed
    def plot_visibility(self):
        self.actionPlotSelector.setChecked(not self.plotDock.isHidden())

    def metadata_visibility(self):
        self.actionMetadata.setChecked(not self.metadataDock.isHidden())

    def open_files_visibility(self):
        self.actionOpenFiles.setChecked(not self.openFilesDock.isHidden())

    def log_entries_visibility(self):
        self.actionLogEntries.setChecked(not self.logEntriesDock.isHidden())

    def metadata_column_resize(self):
        self.metadataView.resizeColumnToContents(0)

    def update_checkboxes(self):
        for i in range(self.viewArea.count()):
            widget = self.viewArea.widget(i)
            if widget is not None:
                widget.zero_y(self.checkZeroY.isChecked())
                widget.invert_y(self.checkInvertY.isChecked())
                widget.log_scale(self.checkLogScale.isChecked())
                widget.scale_mode(self.checkScaleMode.isChecked())
                widget.subplot_combine(self.checkSubplotCombine.isChecked())
                widget.draw_annotation(self.checkAnnotation.isChecked())
                widget.draw_legend(self.checkLegend.isChecked())
                widget.draw_title(self.checkTitle.isChecked())
                widget.filter_legend(self.checkFilterLegend.isChecked())
                widget.highlight(self.checkHighlight.isChecked())

        self.log_settings(self.checkDebugLog.isChecked(),
                          self.checkExceptionLog.isChecked())

        idx = self.viewArea.currentIndex()
        if idx >= 0:
            self.redraw_near(idx)

    def log_settings(self, debug=False, exceptions=False):
        self.logEntries.setLevel(loggers.DEBUG if debug else loggers.INFO)
        self.logEntries.format_exceptions = exceptions

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
                                                 FILE_SELECTOR_STRING)

        if isinstance(filenames, tuple):
            filenames = filenames[0]
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
        else:
            for r in widget.extra_results[-added:]:
                self.open_files.add_file(r)

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
        self.open_files.update()

    def clear_extra(self):
        widget = self.viewArea.currentWidget()
        if widget is not None:
            widget.clear_extra()
            self.open_files.update()

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
        self.open_files.update()

    def save_plot(self):
        widget = self.viewArea.currentWidget()
        if widget is not None:
            widget.save_plot()

    def refresh_plot(self):
        widget = self.viewArea.currentWidget()
        if widget is not None:
            widget.update()

    def warn_nomatch(self):
        logger.warning("Could not find any datasets with a "
                       "matching test name to add.")

    def show(self):
        super(MainWindow, self).show()

        # Deferring loading until here means the window has been created and a
        # busy cursor can be shown.
        if self.defer_load:
            self.load_files(self.defer_load)
            self.defer_load = None

    def shorten_titles(self, titles):
        new_titles = []
        substr = util.long_substr(titles)
        prefix = util.long_substr(titles, prefix_only=True)

        for t in titles:
            if len(substr) > 0:
                text = t.replace(substr, "...")
            if len(prefix) > 0 and prefix != substr:
                text = text.replace(prefix, "...").replace("......", "...")
            if len(substr) == 0 or text == "...":
                text = t
            new_titles.append(text)

        return new_titles

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
        indexes = []
        for i in range(self.viewArea.count()):
            if self.viewArea.widget(i).title == ResultWidget.default_title:
                continue
            titles.append(self.viewArea.widget(i).title)
            long_titles.append(self.viewArea.widget(i).long_title)
            indexes.append(i)

        titles = self.shorten_titles(titles)

        for i, t, lt in zip(indexes, titles, long_titles):
            self.viewArea.setTabText(i, t)
            self.viewArea.setTabToolTip(i, lt)

    def close_tab(self, idx=None):
        self.busy_start()
        if idx in (None, False):
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
            self.open_files.set_active_widget(None)
            return

        self.redraw_near(idx)

        self.plotView.setModel(widget.plotModel)
        if widget.plotSelectionModel is not None:
            self.plotView.setSelectionModel(widget.plotSelectionModel)
        self.metadataView.setModel(widget.metadataModel)
        if widget.metadataSelectionModel is not None:
            self.metadataView.setSelectionModel(widget.metadataSelectionModel)
        self.update_checkboxes()
        self.update_save(widget)
        widget.activate()
        self.open_files.set_active_widget(widget)

    def update_save(self, widget=None):
        if widget is None:
            widget = self.viewArea.currentWidget()
        if widget:
            self.actionSavePlot.setEnabled(widget.can_save)

    def update_plots(self, testname, plotname):
        for i in range(self.viewArea.count()):
            widget = self.viewArea.widget(i)
            if widget and widget.settings.NAME == testname:
                widget.change_plot(plotname)

        idx = self.viewArea.currentIndex()
        if idx >= 0:
            self.redraw_near(idx)

    def redraw_near(self, idx=None):
        if idx is None:
            idx = self.viewArea.currentIndex()

        rng = (CPU_COUNT + 1) // 2
        # Start a middle, go rng steps in either direction (will duplicate the
        # middle idx, but that doesn't matter, since multiple redraw()
        # operations are no-op.
        for i in chain(*[(idx+i, idx-i) for i in range(rng + 1)]):
            while i < 0:
                i += self.viewArea.count()
            w = self.viewArea.widget(i)
            if w:
                w.redraw()

    def add_tab(self, results=None, title=None, plot=None, focus=True):
        widget = ResultWidget(self.viewArea, self.settings, self.worker_pool)
        widget.update_start.connect(self.busy_start)
        widget.update_end.connect(self.busy_end)
        widget.update_end.connect(self.update_save)
        widget.plot_changed.connect(self.update_plots)
        if results:
            widget.load_results(results, plot)
        if title is None:
            title = widget.title
        idx = self.viewArea.addTab(widget, title)
        if hasattr(widget, "long_title"):
            self.viewArea.setTabToolTip(idx, widget.long_title)
        if focus or self.focus_new:
            self.viewArea.setCurrentWidget(widget)
            self.focus_new = False

        return widget

    def load_files(self, filenames, set_last_dir=True):
        if not filenames:
            return

        self.update_tabs = self.viewArea.currentWidget() is not None

        self.busy_start()

        if isinstance(filenames[0], ResultSet):
            results = filenames
        else:
            results = list(filter(None, self.worker_pool.map(results_load_helper,
                                                             map(unicode,
                                                                 filenames))))

        titles = self.shorten_titles([r['title'] for r in results])
        self.focus_new = True

        self.load_queue.extend(zip(results, titles))
        self.load_timer.start()

        if set_last_dir:
            self.last_dir = os.path.dirname(unicode(filenames[-1]))

    def load_one(self):
        if not self.load_queue:
            self.load_timer.stop()
            return

        r, t = self.load_queue.pop(0)

        widget = self.viewArea.currentWidget()
        if widget is not None:
            current_plot = widget.current_plot
        else:
            current_plot = None

        try:
            if widget is None or widget.is_active:
                widget = self.add_tab(r, t, current_plot, focus=False)
            else:
                widget.load_results(r, plot=current_plot)
            self.open_files.add_file(widget.results)
        except Exception as e:
            logger.exception(str(e))
            logger.warning("Error while loading data file. Skipping.")

        if not self.load_queue:
            self.openFilesView.resizeColumnsToContents()
            self.metadata_column_resize()
            if self.update_tabs:
                self.shorten_tabs()
            self.load_timer.stop()
            self.redraw_near()
            self.busy_end()

    def run_test(self):
        dialog = NewTestDialog(self, self.settings, self.log_queue)
        dialog.exec_()


class NewTestDialog(get_ui_class("newtestdialog.ui")):

    def __init__(self, parent, settings, log_queue):
        super(NewTestDialog, self).__init__(parent)
        self.settings = settings.copy()
        self.settings.INPUT = []
        self.settings.GUI = False
        self.log_queue = log_queue

        tests = ListTests.get_tests(settings)
        max_len = max([len(t[0]) for t in tests])
        for t, desc in tests:
            desc = desc.replace("\n", " ")
            self.testName.addItem(
                ("%-" + str(max_len) + "s :  %s") % (t, desc), t)
        self.testName.setCurrentIndex(self.testName.findData(self.settings.NAME))
        self.hostName.setText(self.settings.HOST or "")
        self.testTitle.setText(self.settings.TITLE or "")
        self.outputDir.setText(os.path.realpath(
            self.settings.DATA_DIR or os.getcwd()))
        self.testLength.setValue(self.settings.LENGTH)
        self.extendedMetadata.setChecked(self.settings.EXTENDED_METADATA)

        self.selectOutputDir.clicked.connect(self.select_output_dir)
        self.runButton.clicked.connect(self.run_test)

        self.monitor_timer = QTimer()
        self.monitor_timer.setInterval(500)
        self.monitor_timer.setSingleShot(False)
        self.monitor_timer.timeout.connect(self.update_progress)

        self.logEntries = QPlainTextLogger(self,
                                           level=logging.DEBUG,
                                           widget=self.logTextEdit)
        add_log_handler(self.logEntries)

    def select_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self,
                                                     "Select output directory",
                                                     self.outputDir.text())
        if directory:
            self.outputDir.setText(directory)

    def closeEvent(self, event):
        remove_log_handler(self.logEntries)

        event.accept()

    def run_test(self):
        test = self.testName.itemData(self.testName.currentIndex())
        host = self.hostName.text()
        path = self.outputDir.text()
        if not test or not host:
            QMessageBox.critical(self, "Error running test",
                                 "You must select a test to run and a "
                                 "hostname to connect to.")
            return
        if not os.path.isdir(path):
            QMessageBox.critical(self, "Error running test",
                                 "Output dir does not exist.")
            return

        self.settings.HOSTS = [host]
        self.settings.NAME = test
        self.settings.TITLE = self.testTitle.text()
        self.settings.LENGTH = self.testLength.value()
        self.settings.DATA_DIR = path
        self.settings.EXTENDED_METADATA = self.extendedMetadata.isChecked()
        self.settings.load_test(informational=True)
        self.settings.FORMATTER = "null"

        self.settings.DATA_FILENAME = None
        res = resultset.new(self.settings)
        self.settings.DATA_FILENAME = res.dump_filename

        self.total_time = self.settings.TOTAL_LENGTH
        self.start_time = time.time()

        self.testConfig.setEnabled(False)
        self.runButton.setEnabled(False)

        b = batch.new(self.settings)
        self.pid = b.fork_and_run(self.log_queue)
        self.monitor_timer.start()

    def update_progress(self):

        p, s = os.waitpid(self.pid, os.WNOHANG)
        if (p, s) == (0, 0):
            elapsed = time.time() - self.start_time
            self.progressBar.setValue(100 * elapsed / self.total_time)
        else:
            self.testConfig.setEnabled(True)
            self.runButton.setEnabled(True)
            self.progressBar.setValue(0)
            self.monitor_timer.stop()
            self.pid = None
            self.parent().load_files(
                [os.path.join(self.settings.DATA_DIR,
                              self.settings.DATA_FILENAME)])


class QPlainTextLogger(loggers.Handler):

    def __init__(self, parent, level=logging.NOTSET, widget=None,
                 statusbar=None, timeout=5000):

        super(QPlainTextLogger, self).__init__(level=level)

        font = QFont("Monospace")
        font.setStyleHint(QFont.TypeWriter)

        self.widget = widget or QPlainTextEdit(parent)
        self.widget.setFont(font)
        self.widget.setReadOnly(True)

        self.statusbar = statusbar
        self.timeout = timeout

    def emit(self, record):
        msg = self.format(record)
        self.widget.appendPlainText(msg)

        if self.statusbar:
            self.statusbar.showMessage(record.message, self.timeout)

    def write(self, p):
        pass


class PlotModel(QStringListModel):

    def __init__(self, parent, plots):
        QStringListModel.__init__(self, parent)

        self.keys = list(plots.keys())

        strings = []
        for k, v in plots.items():
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
            for k, v in sorted(value.items()):
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

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Vertical or role != Qt.DisplayRole:
            return None
        return self.header_names[section]

    def data(self, idx, role=Qt.DisplayRole):
        if role not in (Qt.DisplayRole, Qt.StatusTipRole, Qt.ToolTipRole):
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
        if item is None or item.parent in (None, self.root):
            return QModelIndex()
        parent = item.parent
        row = parent.parent.children.index(parent)
        return self.createIndex(row, 0, parent)

    def index(self, row, column, parent):
        item = parent.internalPointer()
        if item is None:
            item = self.root
        return self.createIndex(row, column, item.children[row])


class MetadataView(QTreeView):

    def __init__(self, parent, openFilesView):
        super(MetadataView, self).__init__(parent)
        self.setAlternatingRowColors(True)
        self.setMouseTracking(True)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.pinned_entries = set()
        self.openFilesView = openFilesView

    def contextMenuEvent(self, event):
        idx = self.indexAt(event.pos())
        menu = QMenu()

        def pin():
            self.add_pin(idx)
        act_pin = QAction("&Pin expanded", menu, triggered=pin)

        def col():
            self.add_open_files_col(idx)
        act_col = QAction("&Add open files column", menu, triggered=col)
        menu.addActions([act_pin, act_col])
        menu.exec_(event.globalPos())
        event.accept()

    def get_metadata_path(self, idx):
        path = []
        while idx.isValid():
            name = self.model().data(self.model().index(idx.row(),
                                                        0,
                                                        idx.parent()),
                                     Qt.DisplayRole)
            path.insert(0, name or idx.row())
            idx = idx.parent()

        return tuple(path)

    def add_pin(self, idx):
        pin = self.get_metadata_path(idx)
        if pin in self.pinned_entries:
            self.pinned_entries.remove(pin)
        else:
            self.pinned_entries.add(pin)

    def add_open_files_col(self, idx):
        path = self.get_metadata_path(idx)
        self.openFilesView.horizontalHeader().add_column(None,
                                                         ":".join(map(str, path)))

    def setModel(self, model):
        super(MetadataView, self).setModel(model)
        self.restore_pinned()

    def restore_pinned(self):
        if not self.model():
            return
        for pin in self.pinned_entries:
            parent = QModelIndex()
            for n in pin:
                try:
                    if isinstance(n, int):
                        idx = self.model().index(n, 0, parent)
                    else:
                        idx = self.model().match(self.model().index(
                            0, 0, parent), Qt.DisplayRole, n)[0]
                    self.setExpanded(idx, True)
                    parent = idx
                except IndexError:
                    logger.warning("Could not find pinned entry '%s'.",
                                   ":".join(map(str, pin)))
                    break
                except Exception as e:
                    logger.warning("Restoring pin '%s' failed: %s.",
                                   ":".join(map(str, pin)), e)
                    break


class ResultsetStore(object):

    def __init__(self):
        self._store = {}
        self._order = []
        self._sort_key = 'DATA_FILENAME'
        self._sort_rev = False

    def __len__(self):
        return sum([len(i) for i in self._store.values()])

    def __contains__(self, itm):
        for v in self._store.values():
            if itm in v:
                return True
        return False

    def __getitem__(self, idx):
        offset = 0
        for k in self._order:
            v = self._store[k]
            if idx < len(v) + offset:
                return v[idx - offset]
            offset += len(v)
        raise IndexError()

    def sort(self, key=None, reverse=False, only=None):
        if key is None:
            key = self._sort_key
            reverse = self._sort_rev

        def get_key(itm):
            try:
                return unicode(itm.meta(key))
            except KeyError:
                return ''
        if only:
            only.sort(key=get_key, reverse=reverse)
        else:
            self._sort_key, self._sort_rev = key, reverse
            for v in self._store.values():
                v.sort(key=get_key, reverse=reverse)

    def update_order(self, active):
        self._order = [active] + sorted([i for i in self._order if i != active])

    def append(self, itm):
        k = itm.meta('NAME')
        if k in self._store:
            self._store[k].append(itm)
            self.sort(only=self._store[k])
        else:
            self._store[k] = [itm]
            self._order.append(k)


class OpenFilesModel(QAbstractTableModel):
    test_name_role = Qt.UserRole

    def __init__(self, parent):
        QAbstractTableModel.__init__(self, parent)
        self._parent = parent
        self.open_files = ResultsetStore()
        self.columns = [(None, 'Act'),
                        ('DATA_FILENAME', 'Filename'),
                        ('TITLE', 'Title')]
        self.active_widget = None

    @property
    def ctrl_pressed(self):
        return bool(QApplication.keyboardModifiers() & Qt.ControlModifier)

    def save_columns(self):
        return base64.b64encode(pickle.dumps(self.columns, protocol=0)).decode()

    def restore_columns(self, data):
        try:
            cols = pickle.loads(base64.b64decode(data))
        except:
            return
        if len(cols) > len(self.columns):
            self.beginInsertColumns(
                QModelIndex(), len(self.columns), len(cols) - 1)
            self.columns = cols
            self.endInsertColumns()
        elif len(cols) < len(self.columns):
            self.beginRemoveColumns(
                QModelIndex(), len(cols), len(self.columns) - 1)
            self.columns = cols
            self.endRemoveColumns()
        else:
            self.columns = cols
        self.update()

    @property
    def has_widget(self):
        return self.active_widget is not None and self.active_widget.is_active

    def is_active(self, idx):
        if not self.has_widget:
            return False
        return self.active_widget.has(self.open_files[idx])

    def update_order(self):
        if self.has_widget:
            self.open_files.update_order(self.active_widget.results.meta("NAME"))

    def set_active_widget(self, widget):
        self.active_widget = widget
        self.update()

    def on_click(self, idx):
        if not self.is_active(idx.row()) or self.ctrl_pressed:
            self.activate(idx.row())
        else:
            self.deactivate(idx.row())

    def update(self):
        self.update_order()
        self.dataChanged.emit(self.index(0, 0), self.index(len(self.open_files),
                                                           len(self.columns)))

    def activate(self, idx, new_tab=False):
        if new_tab or not self.has_widget or self.ctrl_pressed:
            self._parent.load_files([self.open_files[idx]])
            return True
        ret = self.active_widget.add_extra(self.open_files[idx])
        self.update()
        return ret

    def deactivate(self, idx):
        if not self.has_widget:
            return False
        ret = self.active_widget.remove_extra(self.open_files[idx])
        self.update()
        return ret

    def is_primary(self, idx):
        if not self.has_widget:
            return False
        return self.active_widget.results == self.open_files[idx]

    def add_file(self, r):
        if r in self.open_files:
            return
        self.beginInsertRows(QModelIndex(), len(
            self.open_files), len(self.open_files))
        self.open_files.append(r)
        self.endInsertRows()
        self.update()

    def rowCount(self, parent):
        if parent.isValid():
            return 0
        return len(self.open_files)

    def columnCount(self, parent):
        if parent.isValid():
            return 0
        return len(self.columns)

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columns[section][1]
        if role == Qt.DisplayRole and orientation == Qt.Vertical:
            return section + 1
        if role == Qt.ToolTipRole and \
           orientation == Qt.Horizontal and \
           section > 0:
            return "Metadata path: %s.\nRight click to add or remove columns." \
                % self.columns[section][0]
        if role == Qt.TextAlignmentRole:
            return Qt.AlignLeft | Qt.AlignVCenter

    def flags(self, idx):
        flags = super(OpenFilesModel, self).flags(idx)
        if idx.column() == 0:
            flags |= Qt.ItemIsUserCheckable
        if (self.has_widget and
            self.active_widget.results.meta("NAME") !=
            self.open_files[idx.row()].meta("NAME"))\
           or (self.is_primary(idx.row()) and
               len(self.active_widget.extra_results) == 0):
            flags &= ~Qt.ItemIsEnabled
        return flags

    def get_metadata(self, idx, name):
        try:
            return unicode(self.open_files[idx].meta(name))
        except KeyError:
            return None

    def removeColumn(self, col, parent):
        if col == 0:
            return False
        self.beginRemoveColumns(parent, col, col)
        self.columns[col:col + 1] = []
        self.endRemoveColumns()

    def add_column(self, pos, path, name):
        self.beginInsertColumns(QModelIndex(), pos, pos)
        self.columns.insert(pos, (path, name))
        self.endInsertColumns()

    def data(self, idx, role=Qt.DisplayRole):
        if role == self.test_name_role:
            return self.open_files[idx.row()].meta('NAME')
        if idx.column() == 0:
            value = self.is_active(idx.row())
            if role == Qt.CheckStateRole:
                return Qt.Checked if value else Qt.Unchecked
            else:
                return None
        if role == Qt.ToolTipRole:
            if not self.has_widget:
                return "Click to open in new tab."
            elif self.is_primary(idx.row()) and len(
                    self.active_widget.extra_results) == 0:
                return "Can't deselect last item. Ctrl+click to open in new tab."
            elif self.flags(idx) & Qt.ItemIsEnabled:
                return "Click to select/deselect. Ctrl+click to open in new tab."
            else:
                return "Ctrl+click to open in new tab."
        if role == Qt.TextAlignmentRole:
            return Qt.AlignLeft | Qt.AlignVCenter
        if role == Qt.DisplayRole:
            return self.get_metadata(idx.row(), self.columns[idx.column()][0])
        if role == Qt.FontRole:
            font = QFont()
            if self.is_primary(idx.row()) and font is not None:
                font.setBold(True)
            return font

    def sort(self, column, order):
        if column == 0:
            return
        key = self.columns[column][0]
        self.open_files.sort(key, (order == Qt.DescendingOrder))
        self.update()


class OpenFilesView(QTableView):

    def __init__(self, parent):
        super(OpenFilesView, self).__init__(parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setAlternatingRowColors(True)

        self.setSortingEnabled(True)
        self.sortByColumn(1, Qt.AscendingOrder)

        self.setHorizontalHeader(OpenFilesHeader(self))

        self.setContextMenuPolicy(Qt.DefaultContextMenu)

    def remove_column(self, col):
        self.model().removeColumn(col, QModelIndex())

    def close_file(self, row):
        self.model().removeRow(row, QModelIndex())

    def mouseReleaseEvent(self, event):
        # Prevent clicked() from being emitted on right click
        if event.button() == Qt.LeftButton:
            super(OpenFilesView, self).mouseReleaseEvent(event)
        else:
            event.ignore()

    def contextMenuEvent(self, event):
        idx = self.indexAt(event.pos())
        menu = QMenu()

        def opn():
            self.model().activate(idx.row(), True)
        act_opn = QAction("&Open in new tab", menu, triggered=opn)

        sep = QAction(menu)
        sep.setSeparator(True)
        menu.addActions([act_opn, sep])
        menu.addActions(self.horizontalHeader(
        ).column_actions(idx.column(), menu))
        menu.exec_(event.globalPos())
        event.accept()


class OpenFilesHeader(QHeaderView):

    def __init__(self, parent):
        super(OpenFilesHeader, self).__init__(Qt.Horizontal, parent)
        self._parent = parent
        try:
            self.setSectionsMovable(True)
        except AttributeError:
            self.setMovable(True)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

    def column_actions(self, col, parent):
        actions = []
        if col > 0:
            def rem():
                self._parent.remove_column(col)
            name = self.model().headerData(col, Qt.Horizontal, Qt.DisplayRole)
            actions.append(QAction("&Remove column '%s'" %
                                   name, parent, triggered=rem))

        def add():
            self.add_column(col)
        actions.append(QAction("&Add new column", parent, triggered=add))

        return actions

    def add_column(self, col=None, path=None):
        if col is None:
            col = self.model().columnCount(QModelIndex())
        dialog = AddColumnDialog(self, path)
        if not dialog.exec_() or not dialog.get_path():
            return
        vis_old = self.visualIndex(col)
        self.model().add_column(col + 1, dialog.get_path(), dialog.get_name())
        vis_new = self.visualIndex(col + 1)
        self.moveSection(vis_new, vis_old + 1)
        self._parent.resizeColumnToContents(col + 1)

    def contextMenuEvent(self, event):
        idx = self.logicalIndexAt(event.pos())
        menu = QMenu()
        menu.addActions(self.column_actions(idx, menu))
        menu.exec_(event.globalPos())
        event.accept()


class AddColumnDialog(get_ui_class("addcolumn.ui")):

    def __init__(self, parent, path=None):
        super(AddColumnDialog, self).__init__(parent)

        self.metadataPathEdit.textChanged.connect(self.update_name)
        self.columnNameEdit.textEdited.connect(self.name_entered)
        self.name_entered = False

        if path is not None:
            self.metadataPathEdit.setText(path)

    def name_entered(self):
        self.name_entered = True

    def update_name(self, text):
        if self.name_entered:
            return
        parts = text.split(":")
        self.columnNameEdit.setText(parts[-1])

    def get_path(self):
        return unicode(self.metadataPathEdit.text())

    def get_name(self):
        return unicode(self.columnNameEdit.text())


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
    new_plot = pyqtSignal()
    default_title = "New tab"

    def __init__(self, parent, settings, worker_pool):
        super(ResultWidget, self).__init__(parent)
        self.results = None
        self.settings = settings.copy()
        self.dirty = True
        self.settings.OUTPUT = "-"

        self.extra_results = []
        self.title = self.default_title

        self.plotModel = None
        self.plotSelectionModel = None
        self.metadataModel = None
        self.metadataSelectionModel = None
        self.toolbar = None
        self.plotter = None
        self.canvas = None
        self.needs_resize = False

        self.new_plot.connect(self.get_plotter)
        self.async_fig = None
        self.async_timer = QTimer(self)
        self.async_timer.setInterval(100)
        self.async_timer.timeout.connect(self.get_plotter)

        self.worker_pool = worker_pool

    @property
    def is_active(self):
        return self.results is not None

    def init_plotter(self):

        if not self.results:
            return

        try:
            self.plotter = plotters.new(self.settings)
        except Exception as e:
            logger.exception(str(e))
            logger.warning("Error while loading plot '%s'. "
                           "Falling back to default plot.",
                           self.settings.PLOT)

            self.settings.PLOT = self.settings.DEFAULTS['PLOT']
            self.plotter = plotters.new(self.settings)

        if self.settings.GUI_NO_DEFER:
            self.redraw()

    def init_canvas(self):

        self.canvas = FigureCanvas(self.plotter.figure)
        self.canvas.setParent(self.graphDisplay)
        self.toolbar = NavigationToolbar(self.canvas, self.graphDisplay)

        vbl = QVBoxLayout()
        vbl.addWidget(self.canvas)
        vbl.addWidget(self.toolbar)
        self.graphDisplay.setLayout(vbl)

    def has(self, resultset):
        return resultset in chain([self.results], self.extra_results)

    def load_results(self, results, plot=None):
        if isinstance(results, LoadedResultset):
            self.results = results['results']
            self.settings.DEFAULTS = results['defaults']
            self.settings.DATA_SETS = results['data_sets']
            self.settings.PLOTS = results['plots']
            self.settings.DESCRIPTION = results['description']
            self.settings.update_defaults()
        elif isinstance(results, ResultSet):
            self.results = results
        else:
            self.results = ResultSet.load_file(unicode(results))
            self.settings.compute_missing_results(self.results)

        if plot and plot in self.settings.PLOTS:
            self.settings.PLOT = plot

        self.settings.update(self.results.meta())

        if not self.settings.PLOTS:
            self.settings.load_test(informational=True)

        self.title = self.results.title
        self.long_title = self.results.long_title

        self.init_plotter()

        self.plotModel = PlotModel(self, self.settings.PLOTS)
        self.plotSelectionModel = QItemSelectionModel(self.plotModel)
        self.plotSelectionModel.setCurrentIndex(
            self.plotModel.index_of(self.settings.PLOT),
            QItemSelectionModel.SelectCurrent)
        self.plotSelectionModel.currentChanged.connect(self.change_plot)

        self.metadataModel = MetadataModel(self, self.results.meta())
        self.metadataSelectionModel = QItemSelectionModel(self.metadataModel)

        return True

    def disconnect_all(self):
        for s in (self.update_start, self.update_end, self.plot_changed):
            s.disconnect()

    def disable_cleanup(self):
        if self.plotter is not None:
            self.plotter.disable_cleanup = True

    def load_files(self, filenames):
        added = 0
        for f in filenames:
            if self.add_extra(ResultSet.load_file(unicode(f))):
                self.update(False)
                added += 1
        self.redraw()
        return added

    def add_extra(self, resultset):
        if self.results is None:
            return self.load_results(resultset)
        if resultset in self.extra_results:
            return False
        if resultset.meta('NAME') == self.settings.NAME:
            self.extra_results.append(resultset)
            self.update()
            return True
        return False

    def remove_extra(self, resultset):
        if resultset not in self.extra_results:
            if resultset == self.results and self.extra_results:
                self.results = self.extra_results.pop(0)
                self.update()
                return True
            return False
        self.extra_results.remove(resultset)
        self.update()
        return True

    def clear_extra(self):
        self.extra_results = []
        self.update()

    @property
    def can_save(self):
        # Check for attribute to not crash on a matplotlib version that does not
        # have the save action.
        return hasattr(self.toolbar, 'save_figure')

    def save_plot(self):
        if self.can_save:
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

    def log_scale(self, val=None):
        if val is not None and val != self.settings.LOG_SCALE:
            self.settings.LOG_SCALE = val
            self.update()
        return self.settings.LOG_SCALE

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

    def highlight(self, val=None):
        if val is not None and val != self.settings.HOVER_HIGHLIGHT:
            self.settings.HOVER_HIGHLIGHT = val
            self.update()
        return self.settings.HOVER_HIGHLIGHT

    def change_plot(self, plot_name):
        if not self.plotter:
            return
        if isinstance(plot_name, QModelIndex):
            plot_name = self.plotModel.name_of(plot_name)
        plot_name = unicode(plot_name)
        if plot_name != self.settings.PLOT and plot_name in self.settings.PLOTS:
            self.settings.PLOT = plot_name
            self.plotSelectionModel.setCurrentIndex(
                self.plotModel.index_of(self.settings.PLOT),
                QItemSelectionModel.SelectCurrent)
            self.plot_changed.emit(self.settings.NAME, self.settings.PLOT)
            self.update()
            return True
        return False

    @property
    def current_plot(self):
        if not self.is_active:
            return None
        return self.settings.PLOT

    def updates_disabled(self):
        return UpdateDisabler(self)

    def update(self, redraw=True):
        self.dirty = True
        if redraw and ((self.isVisible() and self.updatesEnabled()) or
                       self.settings.GUI_NO_DEFER):
            self.redraw()

    def activate(self):
        self.get_plotter()

        if self.async_fig:
            self.async_timer.start()

        if not self.canvas:
            return

        if self.needs_resize:
            self.canvas.resizeEvent(QResizeEvent(self.canvas.size(),
                                                 self.canvas.size()))
            self.needs_resize = False

        try:
            self.canvas.blit(self.canvas.figure.bbox)
        except AttributeError:
            pass

        # Simulate a mouse move event when the widget is activated. This ensures
        # that the interactive plot highlight will get updated correctly.
        pt = self.canvas.mapFromGlobal(QCursor.pos())
        evt = QMouseEvent(QEvent.MouseMove, pt, Qt.NoButton,
                          Qt.NoButton, Qt.NoModifier)
        self.canvas.mouseMoveEvent(evt)

    def redraw(self):
        if not self.dirty or not self.is_active:
            return

        if self.settings.SCALE_MODE:
            self.settings.SCALE_DATA = self.extra_results
            res = [self.results]
        else:
            self.settings.SCALE_DATA = []
            res = [self.results] + self.extra_results

        self.async_fig = self.worker_pool.apply_async(
            plotters.draw_worker,
            (self.settings, res),
            callback=self.recv_plot)

        if self.isVisible():
            self.async_timer.start()

        self.plotter.disconnect_callbacks()

        self.dirty = False
        self.setCursor(Qt.WaitCursor)

    def recv_plot(self, fig):
        self.new_plot.emit()

    def get_plotter(self):
        if not self.async_fig or not self.async_fig.ready():
            return

        try:
            fig = self.async_fig.get()

            self.plotter = fig

            if not self.canvas:
                self.init_canvas()
            else:
                self.canvas.figure = self.plotter.figure
                self.plotter.figure.set_canvas(self.canvas)

            self.plotter.connect_interactive()

            if self.isVisible():
                self.canvas.resizeEvent(QResizeEvent(self.canvas.size(),
                                                     self.canvas.size()))
            else:
                self.needs_resize = True

        except Exception as e:
            logger.exception(str(e))
            logger.warning("Unhandled exception while plotting. Aborting.")
        finally:
            self.async_fig = None
            self.async_timer.stop()
            self.setCursor(Qt.ArrowCursor)
            self.update_end.emit()

    def setCursor(self, cursor):
        super(ResultWidget, self).setCursor(cursor)
        if self.canvas:
            self.canvas.setCursor(cursor)
        if self.toolbar:
            self.toolbar.setCursor(cursor)
