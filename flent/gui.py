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

from argparse import SUPPRESS
from datetime import datetime
from itertools import chain
from multiprocessing import Pool, Queue

from flent import util, batch, loggers, resultset, plotters
from flent.build_info import DATA_DIR, VERSION
from flent.loggers import get_logger, add_log_handler, remove_log_handler, \
    set_queue_handler
from flent.resultset import ResultSet
from flent.settings import ListTests, new as new_settings, plot_group

import matplotlib
matplotlib.use("Agg")

logger = get_logger(__name__)

mswindows = (sys.platform == "win32")

try:
    from os import cpu_count
except ImportError:
    from multiprocessing import cpu_count

try:
    CPU_COUNT = cpu_count()
except NotImplementedError:
    CPU_COUNT = 1


try:
    import qtpy
    from qtpy import QtCore, QtGui, uic

    from qtpy.QtWidgets import QMessageBox, QFileDialog, QTreeView, \
        QAbstractItemView, QMenu, QAction, QTableView, QHeaderView, \
        QFormLayout, QHBoxLayout, QVBoxLayout, QApplication, QPlainTextEdit, \
        QWidget, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QScrollArea, \
        QPushButton, QShortcut, QMainWindow, QDialog

    from qtpy.QtGui import QFont, QCursor, QMouseEvent, QKeySequence, \
        QResizeEvent, QDesktopServices, QValidator, QGuiApplication

    from qtpy.QtCore import Qt, QIODevice, QByteArray, \
        QDataStream, QSettings, QTimer, QEvent, Signal, \
        QAbstractItemModel, QAbstractTableModel, QModelIndex, \
        QItemSelectionModel, QStringListModel, QUrl

    from qtpy.QtNetwork import QLocalSocket, QLocalServer

    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg \
        as FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT \
        as NavigationToolbar

except ImportError:
    raise RuntimeError("Unable to find a usable Qt version.")


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
WINDOW_STATE_VERSION = 1

# Hack to propagate the --absolute-time option to multi-process helpers
USE_ABSOLUTE_TIME = False

ABOUT_TEXT = """<p>Flent version {version}.<br>
Copyright &copy; 2017 Toke Høiland-Jørgensen and contributors.<br>
Released under the GNU GPLv3.</p>

<p><a href="https://flent.org">https://flent.org</a></p>

<p>To report a bug, please <a href="https://github.com/tohojo/flent/issues">
file an issue on Github<a>.</p>"""

__all__ = ['run_gui']


def run_gui(settings, test_mode=False):
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
    if test_mode:
        mainwindow.defer_close()
    return app.exec_()


def pool_init_func(settings, queue):
    global USE_ABSOLUTE_TIME
    USE_ABSOLUTE_TIME = settings.ABSOLUTE_TIME

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


def get_ui_file(filename):
    return os.path.join(DATA_DIR, 'ui', filename)


class LoadedResultset(dict):
    pass


def results_load_helper(filename):
    try:
        r = ResultSet.load_file(filename, USE_ABSOLUTE_TIME)
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
        logger.exception("Unable to load file '%s': '%s'", filename, e)
        return None


class MainWindow(QMainWindow):

    def __init__(self, settings):
        super(MainWindow, self).__init__()
        uic.loadUi(get_ui_file("mainwindow.ui"), self)
        self.settings = settings
        self.last_dir = os.getcwd()

        self.defer_load = self.settings.INPUT
        self.load_queue = []
        self.load_timer = QTimer(self)
        self.load_timer.timeout.connect(self.load_one)
        self.focus_new = False
        self.new_test_dialog = None

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
        self.actionPrevTab.triggered.connect(self.prev_tab)
        self.actionRefresh.triggered.connect(self.refresh_plot)
        self.actionNewTest.triggered.connect(self.run_test)

        self.actionHelpGUI.triggered.connect(self.help_gui)
        self.actionHelpRunning.triggered.connect(self.help_running)
        self.actionHelpTests.triggered.connect(self.help_tests)
        self.actionHelpBug.triggered.connect(self.help_bug)
        self.actionHelpAbout.triggered.connect(self.help_about)

        self.viewArea.tabCloseRequested.connect(self.close_tab)
        self.viewArea.currentChanged.connect(self.activate_tab)

        self.plotDock.visibilityChanged.connect(self.plot_visibility)
        self.metadataDock.visibilityChanged.connect(self.metadata_visibility)
        self.plotSettingsDock.visibilityChanged.connect(self.plot_settings_visibility)
        self.openFilesDock.visibilityChanged.connect(self.open_files_visibility)
        self.logEntriesDock.visibilityChanged.connect(self.log_entries_visibility)
        self.expandButton.clicked.connect(self.metadata_column_resize)

        self.checkHighlight.setChecked(self.settings.HOVER_HIGHLIGHT)
        self.checkExceptionLog.setChecked(self.settings.DEBUG_ERROR)

        if loggers.out_handler:
            self.checkDebugLog.setChecked(loggers.out_handler.level == loggers.DEBUG)

        self.checkHighlight.toggled.connect(self.update_checkboxes)
        self.checkDebugLog.toggled.connect(self.update_checkboxes)
        self.checkExceptionLog.toggled.connect(self.update_checkboxes)

        self.tabifyDockWidget(self.openFilesDock, self.metadataDock)
        self.tabifyDockWidget(self.openFilesDock, self.logEntriesDock)
        self.openFilesDock.raise_()
        self.tabifyDockWidget(self.plotDock, self.plotSettingsDock)
        self.plotDock.raise_()
        self.open_files = OpenFilesModel(self)
        self.openFilesView = OpenFilesView(self.openFilesDock)
        self.openFilesDock.setWidget(self.openFilesView)
        self.openFilesView.setModel(self.open_files)
        self.openFilesView.clicked.connect(self.open_files.on_click)

        self.metadataView = MetadataView(self, self.openFilesView)
        self.metadataView.entered.connect(self.update_statusbar)
        self.metadataLayout.insertWidget(0, self.metadataView)
        self.expandButton.clicked.connect(self.metadataView.expandAll)

        self.plotSettingsWidget = SettingsWidget(self, plot_group, settings,
                                                 compact=True)
        self.plotSettingsDock.setWidget(self.plotSettingsWidget)
        self.plotSettingsWidget.values_changed.connect(self.update_settings)

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
        self.update_checkboxes()

        self.worker_pool = Pool(initializer=pool_init_func,
                                initargs=(self.settings, self.log_queue))

        QShortcut(QKeySequence("Ctrl+Right"),
                  self).activated.connect(self.next_tab)
        QShortcut(QKeySequence("Ctrl+Left"),
                  self).activated.connect(self.prev_tab)
        QShortcut(QKeySequence("Ctrl+Down"),
                  self).activated.connect(self.next_plot)
        QShortcut(QKeySequence("Ctrl+Up"),
                  self).activated.connect(self.prev_plot)

        logger.info("GUI loaded. Using Qt through %s v%s.", qtpy.API,
                    QtCore.__version__)

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

            version = settings.value("mainwindow/windowStateVersion", 0)
            if hasattr(version, "toInt"):
                version = version.toInt()[0]
            version = int(version)

            if version == WINDOW_STATE_VERSION:
                self.restoreState(winstate)
                self.metadata_visibility()
                self.plot_visibility()
                self.plot_settings_visibility()
                self.open_files_visibility()
            else:
                logger.debug("Discarding old window state (version %d!=%d)",
                             version, WINDOW_STATE_VERSION)

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
        settings.setValue("mainwindow/windowStateVersion", WINDOW_STATE_VERSION)
        settings.setValue("open_files/columns", self.open_files.save_columns())
        settings.setValue("open_files/column_order",
                          self.openFilesView.horizontalHeader().saveState())

        self.worker_pool.terminate()

        event.accept()

    def keyPressEvent(self, event):
        widget = self.viewArea.currentWidget()
        text = str(event.text())
        if widget and text in ('x', 'X', 'y', 'Y'):
            a = text.lower()
            d = 'in' if a == text else 'out'
            widget.zoom(a, d)
            event.accept()
        else:
            super(MainWindow, self).keyPressEvent(event)

    # Helper functions to update menubar actions when dock widgets are closed
    def plot_visibility(self):
        self.actionPlotSelector.setChecked(not self.plotDock.isHidden())

    def plot_settings_visibility(self):
        self.actionPlotSettings.setChecked(not self.plotSettingsDock.isHidden())

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
                widget.highlight(self.checkHighlight.isChecked())

        self.log_settings(self.checkDebugLog.isChecked(),
                          self.checkExceptionLog.isChecked())

        idx = self.viewArea.currentIndex()
        if idx >= 0:
            self.redraw_near(idx)

    def log_settings(self, debug=False, exceptions=False):
        self.logEntries.setLevel(loggers.DEBUG if debug else loggers.INFO)
        self.logEntries.format_exceptions = exceptions

        if self.new_test_dialog is not None:
            self.new_test_dialog.log_settings(debug, exceptions)

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
            self.last_dir = os.path.dirname(str(filenames[0]))

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

    def defer_close(self):
        self.close_timer = QTimer(self)
        self.close_timer.timeout.connect(self.close)
        self.close_timer.start()

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

    def move_plot(self, move_by):
        model = self.plotView.model()
        if not model:
            return

        count = model.rowCount()
        if count:
            idx = self.plotView.currentIndex()
            row = idx.row()
            self.plotView.setCurrentIndex(model.index((row + move_by) % count))

    def next_plot(self):
        self.move_plot(1)

    def prev_plot(self):
        self.move_plot(-1)

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
        self.update_settings(widget)
        self.update_save(widget)
        widget.activate()
        self.open_files.set_active_widget(widget)

    def update_save(self, widget=None):
        if widget is None:
            widget = self.viewArea.currentWidget()
        if widget:
            self.actionSavePlot.setEnabled(widget.can_save)

    def update_settings(self, widget=None):
        if widget is None:
            widget = self.viewArea.currentWidget()
        if widget:
            widget.update_settings(self.plotSettingsWidget.values())

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
        widget.name_changed.connect(self.shorten_tabs)
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
            titles = self.shorten_titles([r.title for r in results])
        else:
            results = list(filter(None, self.worker_pool.map(results_load_helper,
                                                             map(str,
                                                                 filenames))))

            titles = self.shorten_titles([r['title'] for r in results])

        self.focus_new = True

        self.load_queue.extend(zip(results, titles))
        self.load_timer.start()

        if set_last_dir:
            self.last_dir = os.path.dirname(str(filenames[-1]))

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
            logger.exception("Error while loading data file: '%s'. Skipping.",
                             str(e))

        if not self.load_queue:
            self.openFilesView.resizeColumnsToContents()
            self.metadata_column_resize()
            if self.update_tabs:
                self.shorten_tabs()
            self.load_timer.stop()
            self.redraw_near()
            self.busy_end()

    def run_test(self):
        if mswindows:
            QMessageBox.critical(self, "Can't run new test",
                                 "Running new tests is currently not "
                                 "supported on Windows.")
            return

        if self.new_test_dialog is None:
            self.busy_start()
            self.new_test_dialog = NewTestDialog(self, self.settings,
                                                 self.log_queue)
            self.busy_end()

        self.new_test_dialog.show()
        self.new_test_dialog.log_settings(self.checkDebugLog.isChecked(),
                                          self.checkExceptionLog.isChecked())

    def help_gui(self):
        QDesktopServices.openUrl(QUrl("https://flent.org/gui.html"))

    def help_running(self):
        QDesktopServices.openUrl(QUrl("https://flent.org/options.html"))

    def help_tests(self):
        QDesktopServices.openUrl(QUrl("https://flent.org/tests.html"))

    def help_bug(self):
        QDesktopServices.openUrl(QUrl("https://github.com/tohojo/flent/issues"))

    def help_about(self):
        dlg = AboutDialog(self)
        dlg.setModal(True)
        dlg.exec_()


class AboutDialog(QDialog):

    def __init__(self, parent):
        super(AboutDialog, self).__init__(parent)
        uic.loadUi(get_ui_file("aboutdialog.ui"), self)

        self.aboutText.setText(ABOUT_TEXT.format(version=VERSION))


class NewTestDialog(QDialog):

    def __init__(self, parent, settings, log_queue):
        super(NewTestDialog, self).__init__(parent)
        uic.loadUi(get_ui_file("newtestdialog.ui"), self)
        self.orig_settings = settings.copy()
        self.orig_settings.INPUT = []
        self.orig_settings.GUI = False
        self.settings = self.orig_settings.copy()
        self.log_queue = log_queue
        self.pid = None
        self.aborted = False

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
        self.runButton.clicked.connect(self.run_or_abort)

        self.monitor_timer = QTimer()
        self.monitor_timer.setInterval(500)
        self.monitor_timer.setSingleShot(False)
        self.monitor_timer.timeout.connect(self.update_progress)

        self.logEntries = QPlainTextLogger(self,
                                           level=logging.DEBUG,
                                           widget=self.logTextEdit)

    def show(self):
        super(NewTestDialog, self).show()
        add_log_handler(self.logEntries, replay=False)

    def log_settings(self, debug=False, exceptions=False):
        self.logEntries.setLevel(loggers.DEBUG if debug else loggers.INFO)
        self.logEntries.format_exceptions = exceptions

    def select_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self,
                                                     "Select output directory",
                                                     self.outputDir.text())
        if directory:
            self.outputDir.setText(directory)

    def closeEvent(self, event):
        remove_log_handler(self.logEntries)

        event.accept()

    def run_or_abort(self):
        if self.pid is None:
            self.run_test()
        else:
            self.abort_test()

    def run_test(self):
        test = self.testName.itemData(self.testName.currentIndex())
        if hasattr(test, 'toString'):
            test = test.toString()
        host = self.hostName.text()
        path = self.outputDir.text()
        if not test or not host:
            logger.error("You must select a test to run and a "
                         "hostname to connect to.")
            return
        if not os.path.isdir(path):
            logger.error("Output directory does not exist.")
            return

        test = str(test)
        host = str(host)
        path = str(path)

        self.settings.HOSTS = util.token_split(host)
        self.settings.NAME = test
        self.settings.TITLE = str(self.testTitle.text())
        self.settings.LENGTH = self.testLength.value()
        self.settings.DATA_DIR = path
        self.settings.EXTENDED_METADATA = self.extendedMetadata.isChecked()
        self.settings.load_test(informational=True)
        self.settings.FORMATTER = "null"
        self.settings.TIME = datetime.utcnow()

        self.settings.DATA_FILENAME = None
        res = resultset.new(self.settings)
        self.settings.DATA_FILENAME = res.dump_filename

        self.total_time = self.settings.TOTAL_LENGTH
        self.start_time = time.time()

        self.testConfig.setEnabled(False)
        self.runButton.setText("&Abort test")
        self.runButton.setDefault(False)

        b = batch.new(self.settings)
        self.pid = b.fork_and_run(self.log_queue)
        self.monitor_timer.start()

    def abort_test(self):
        if QMessageBox.question(self, "Abort test?",
                                "Are you sure you want to abort "
                                "the current test?",
                                QMessageBox.Yes | QMessageBox.No) \
           != QMessageBox.Yes:
            return

        logger.info("Aborting test.")
        os.kill(self.pid, signal.SIGTERM)
        self.runButton.setEnabled(False)
        self.aborted = True
        logger.debug("Waiting for child process with PID %d to exit.", self.pid)

    def reset(self):
        self.testConfig.setEnabled(True)
        self.runButton.setText("&Run test")
        self.runButton.setDefault(True)
        self.runButton.setEnabled(True)
        self.progressBar.setValue(0)
        self.monitor_timer.stop()
        self.pid = None
        self.aborted = False
        self.settings = self.orig_settings.copy()

    def keyPressEvent(self, evt):
        if evt.key() == Qt.Key_Escape:
            evt.accept()
            if self.pid is not None:
                self.abort_test()
            else:
                self.close()
        else:
            super(NewTestDialog, self).keyPressEvent(evt)

    def update_progress(self):

        p, s = os.waitpid(self.pid, os.WNOHANG)
        if (p, s) == (0, 0):
            if not self.aborted:
                elapsed = time.time() - self.start_time
                self.progressBar.setValue(100 * elapsed / self.total_time)
        else:
            fn = os.path.join(self.settings.DATA_DIR,
                              self.settings.DATA_FILENAME)
            if os.path.exists(fn):
                self.parent().load_files([fn])
            self.reset()


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
            return str(item.value)

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

        def col():
            self.add_open_files_col(idx)

        def copy():
            self.copy_value(idx)

        menu.addActions([
            QAction("&Pin expanded", menu, triggered=pin),
            QAction("&Add open files column", menu, triggered=col),
            QAction("&Copy value to clipboard", menu, triggered=copy)
        ])
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

    def copy_value(self, idx):
        val = self.model().data(self.model().index(idx.row(),
                                                   1,
                                                   idx.parent()),
                                Qt.DisplayRole)
        QGuiApplication.clipboard().setText(val)

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
                    logger.exception("Restoring pin '%s' failed: %s.",
                                     ":".join(map(str, pin)), e)
                    break


class ActionWidget(object):

    def __init__(self, parent, action, default=None):
        super(ActionWidget, self).__init__(parent)

        self.action = action
        self.default = default

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.value_changed)
        self.value_changed.connect(self.timer.stop)
        self.connect_timer(self)

        help = getattr(action, "gui_help", getattr(action, "help", ""))
        if "." in help:
            self.setToolTip(help.split(".", 1)[1].strip())

    def key(self):
        return self.action.dest

    def connect_timer(self, widget):
        for p in "valueChanged", "textChanged":
            if hasattr(widget, p):
                getattr(widget, p).connect(self.timer.start)


class BooleanActionWidget(ActionWidget, QComboBox):

    value_changed = Signal()

    def __init__(self, *args, **kwargs):
        super(BooleanActionWidget, self).__init__(*args, **kwargs)

        self.addItems(["Disabled", "Enabled"])
        self.currentIndexChanged.connect(self.value_changed)
        self.clear()

    def value(self):
        # This always shows boolean options (store_true and store_false) as
        # their actual boolean values, not the possible reversed ones. Only
        # works right if store_false options has a gui_help that fits to this
        # usage (or the help text will not make sense).
        return bool(self.currentIndex())

    def clear(self):
        if self.default is not None:
            self.setCurrentIndex(int(self.default))
        else:
            self.setCurrentIndex(int(not self.action.const))


class ChoicesActionWidget(ActionWidget, QComboBox):

    value_changed = Signal()

    def __init__(self, *args, **kwargs):
        super(ChoicesActionWidget, self).__init__(*args, **kwargs)

        self.addItem("Unset")
        self.addItems(self.action.choices)

        self.currentIndexChanged.connect(self.value_changed)
        self.clear()

    def value(self):
        idx = self.currentIndex()
        if idx == 0:
            return None
        return self.action.choices[idx-1]

    def clear(self):
        if self.default:
            self.setCurrentIndex(self.action.choices.index(self.default)+1)
        else:
            self.setCurrentIndex(0)


class NoneSpinBoxMixin(object):

    def __init__(self, *args, **kwargs):
        super(NoneSpinBoxMixin, self).__init__(*args, **kwargs)
        self.setSpecialValueText("Unset")

    def value(self):
        v = super(NoneSpinBoxMixin, self).value()
        if v == self.minimum():
            return None
        return v

    def valueFromText(self, text):
        if not text:
            return self.minimum()
        return super(NoneSpinBoxMixin, self).valueFromText(text)

    def validate(self, text, pos):
        if not text:
            return QValidator.Acceptable, text, pos
        return super(NoneSpinBoxMixin, self).validate(text, pos)


class NoneDoubleSpinBox(NoneSpinBoxMixin, QDoubleSpinBox):
    value_changed = Signal()


class IntActionWidget(ActionWidget, NoneSpinBoxMixin, QSpinBox):

    value_changed = Signal()

    def __init__(self, *args, **kwargs):
        super(IntActionWidget, self).__init__(*args, **kwargs)

        self.setRange(0, 1000)
        self.clear()

        self.setSpecialValueText("Unset")
        self.editingFinished.connect(self.value_changed)

    def clear(self):
        if self.default:
            self.setValue(self.default)
        else:
            self.setValue(self.minimum())


class FloatActionWidget(ActionWidget, NoneSpinBoxMixin, QDoubleSpinBox):

    value_changed = Signal()

    def __init__(self, *args, **kwargs):
        super(FloatActionWidget, self).__init__(*args, **kwargs)

        self.setRange(0, 1000)
        self.clear()

        self.editingFinished.connect(self.value_changed)

    def clear(self):
        if self.default:
            self.setValue(self.default)
        else:
            self.setValue(self.minimum())


class PairActionWidget(ActionWidget, QWidget):

    value_changed = Signal()

    def __init__(self, parent, action, widget=QLineEdit, **kwargs):
        super(PairActionWidget, self).__init__(parent, action, **kwargs)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self._left = widget()
        self._right = widget()
        layout.addWidget(self._left)
        layout.addWidget(self._right)
        self.setLayout(layout)
        self.clear()

        self._left.editingFinished.connect(self.value_changed)
        self._right.editingFinished.connect(self.value_changed)

        self.connect_timer(self._left)
        self.connect_timer(self._right)

    def value(self):
        if self._left.text() or self._right.text():
            return (self._left.text(), self._right.text())
        return None

    def clear(self):
        self._left.setText("")
        self._right.setText("")


class FloatPairActionWidget(PairActionWidget):

    value_changed = Signal()

    def __init__(self, *args, **kwargs):
        kwargs["widget"] = NoneDoubleSpinBox
        super(FloatPairActionWidget, self).__init__(*args, **kwargs)
        self._left.setSpecialValueText("Unset")
        self._left.setRange(-1000, 100000)
        self._right.setSpecialValueText("Unset")
        self._right.setRange(-1000, 100000)
        self.clear()

    def value(self):
        v = (self._left.value(), self._right.value())
        if v == (None, None):
            return None
        return v

    def clear(self):
        if self.default:
            self._left.setValue(self.default[0] or self._left.minimum())
            self._right.setValue(self.default[1] or self._left.minimum())
        else:
            self._left.setValue(self._left.minimum())
            self._right.setValue(self._left.minimum())


class TextActionWidget(ActionWidget, QLineEdit):

    value_changed = Signal()

    def __init__(self, *args, **kwargs):
        super(TextActionWidget, self).__init__(*args, **kwargs)

        self.clear()
        self.editingFinished.connect(self.value_changed)

        self.setMinimumSize(self.sizeHint())

    def value(self):
        if not self.text():
            return None
        return self.text()

    def clear(self):
        self.setText(self.default or "")


class AddRemoveWidget(QWidget):

    add_pressed = Signal()
    remove_pressed = Signal('QWidget')
    value_changed = Signal()

    def __init__(self, parent, subwidget):
        super(AddRemoveWidget, self).__init__(parent)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(subwidget)
        self._subwidget = subwidget
        self._add_button = QPushButton("+", self)
        self._add_button.setFixedSize(20, 20)
        self._remove_button = QPushButton("-", self)
        self._remove_button.setFixedSize(20, 20)

        self._remove_button.clicked.connect(self.remove)
        self._add_button.clicked.connect(self.add_pressed)

        layout.addWidget(self._add_button)
        layout.addWidget(self._remove_button)
        self.setLayout(layout)

    def set_add_button(self, visible):
        self._add_button.setVisible(visible)

    def remove(self):
        self.remove_pressed.emit(self)

    def clear(self):
        self._subwidget.clear()

    def value(self):
        return self._subwidget.value()


class MultiValWidget(ActionWidget, QWidget):

    value_changed = Signal()

    def __init__(self, *args, **kwargs):
        widget = kwargs.get("widget", TextActionWidget)
        combiner_func = kwargs.get("combiner_func", list)

        for k in 'widget', 'combiner_func':
            if k in kwargs:
                del kwargs[k]

        super(MultiValWidget, self).__init__(*args, **kwargs)

        self._widget_class = widget
        self._combiner_func = combiner_func
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        for i in range(max(len(self.default or []), 1)):
            self.create_widget()

    def create_widget(self):

        count = self.layout().count()
        if count > 0:
            self.layout().itemAt(count - 1).widget().set_add_button(False)

        if count < len(self.default):
            default = self.default[count]
        else:
            default = None

        sw = self._widget_class(self, self.action, default=default)
        sw.value_changed.connect(self.value_changed)

        wdgt = AddRemoveWidget(self, sw)
        wdgt.remove_pressed.connect(self.destroy_widget)
        wdgt.add_pressed.connect(self.create_widget)

        self.layout().addWidget(wdgt)

        self.value_changed.emit()

    def find_widget(self, widget):
        for i in range(self.layout().count()):
            itm = self.layout().itemAt(i)
            if itm and itm.widget() == widget:
                return i

        return None

    def destroy_widget(self, widget):
        count = self.layout().count()
        if count > 1:
            if self.find_widget(widget) == count - 1:
                self.layout().itemAt(count - 2).widget().set_add_button(True)
            self.layout().removeWidget(widget)
            widget.deleteLater()
        else:
            self.layout().itemAt(0).widget().clear()

        self.value_changed.emit()

    def value_iter(self):
        for i in range(self.layout().count()):
            itm = self.layout().itemAt(i)
            if itm and itm.widget():
                yield itm.widget().value()

    def value(self):
        if not any(self.value_iter()):
            return self._combiner_func()
        return self._combiner_func(self.value_iter())


class SettingsWidget(QScrollArea):

    values_changed = Signal()

    _widget_type_map = {int: IntActionWidget,
                        float: FloatActionWidget,
                        util.float_pair: FloatPairActionWidget,
                        util.float_pair_noomit: FloatPairActionWidget,
                        util.comma_list: MultiValWidget,
                        util.keyval: PairActionWidget,
                        str: TextActionWidget}

    def __init__(self, parent, options, settings, compact=False):
        super(SettingsWidget, self).__init__(parent)

        widget = QWidget(self)
        layout = QFormLayout()

        for a in options._group_actions:
            if getattr(a, "hide_gui", False) or a.help is SUPPRESS:
                continue
            wdgt = self._action_widget(a, getattr(settings, a.dest))
            wdgt.value_changed.connect(self.values_changed)
            layout.addRow(self._action_name(a), wdgt)

        layout.setRowWrapPolicy(QFormLayout.WrapLongRows)
        layout.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        widget.setLayout(layout)
        self.setWidget(widget)
        self.setWidgetResizable(True)

    def _action_name(self, action):
        if hasattr(action, "gui_help"):
            return action.gui_help.split(".")[0]
        elif hasattr(action, "help"):
            return action.help.split(".")[0]
        return action.option_strings[-1]

    def _action_widget(self, action, default):
        if action.type is None and type(action.const) == bool:
            return BooleanActionWidget(self, action, default=default)

        cn = action.__class__.__name__
        if action.choices:
            widget = ChoicesActionWidget
        else:
            try:
                widget = self._widget_type_map[action.type]
            except KeyError:
                raise RuntimeError("Unknown type %s for option %s" % (
                    action.type, action.dest))

        if cn == "_StoreAction":
            return widget(self, action, default=default)
        elif cn == "_AppendAction":
            return MultiValWidget(self, action, widget=widget, default=default)
        elif cn == "Update":
            return MultiValWidget(self, action, widget=widget, default=default,
                                  combiner_func=dict)
        else:
            raise RuntimeError("Unknown class: %s" % cn)

    def widget_iter(self):
        layout = self.widget().layout()
        for i in range(layout.rowCount()):
            itm = layout.itemAt(i, QFormLayout.FieldRole)
            if itm and itm.widget():
                yield i, itm.widget()

    def value_iter(self):
        for i, w in self.widget_iter():
            yield (w.key(), w.value())

    def values(self):
        return dict(self.value_iter())


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
                return str(itm.meta(key))
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
            return str(self.open_files[idx].meta(name))
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


class AddColumnDialog(QDialog):

    def __init__(self, parent, path=None):
        super(AddColumnDialog, self).__init__(parent)
        uic.loadUi(get_ui_file("addcolumn.ui"), self)

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
        return str(self.metadataPathEdit.text())

    def get_name(self):
        return str(self.columnNameEdit.text())


class UpdateDisabler(object):

    def __init__(self, widget):
        self.widget = widget

    def __enter__(self):
        self.widget.setUpdatesEnabled(False)

    def __exit__(self, *ignored):
        self.widget.setUpdatesEnabled(True)
        self.widget.update()


class FigureManager(matplotlib.backend_bases.FigureManagerBase):
    def __init__(self, widget, canvas):
        super(FigureManager, self).__init__(canvas, 0)
        self.widget = widget

    def get_window_title(self):
        return self.widget.title


class ResultWidget(QWidget):

    update_start = Signal()
    update_end = Signal()
    plot_changed = Signal('QString', 'QString')
    new_plot = Signal()
    name_changed = Signal()
    default_title = "New tab"

    def __init__(self, parent, settings, worker_pool):
        super(ResultWidget, self).__init__(parent)
        uic.loadUi(get_ui_file("resultwidget.ui"), self)
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
            logger.exception("Plot '%s' failed: %s. "
                             "Falling back to default plot '%s'.",
                             self.settings.PLOT, e,
                             self.settings.DEFAULTS['PLOT'])

            self.settings.PLOT = self.settings.DEFAULTS['PLOT']
            self.plotter = plotters.new(self.settings)

        if self.settings.GUI_NO_DEFER:
            self.redraw()

    def init_canvas(self):

        self.canvas = FigureCanvas(self.plotter.figure)
        self.canvas.setParent(self.graphDisplay)
        self.toolbar = NavigationToolbar(self.canvas, self.graphDisplay)
        self.manager = FigureManager(self, self.canvas)

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
            self.results = ResultSet.load_file(str(results))
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
            if self.add_extra(ResultSet.load_file(str(f))):
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

    def highlight(self, val=None):
        if val is not None and val != self.settings.HOVER_HIGHLIGHT:
            self.settings.HOVER_HIGHLIGHT = val
            self.update()
        return self.settings.HOVER_HIGHLIGHT

    def zoom(self, axis, direction='in'):
        if self.plotter:
            self.plotter.zoom(axis, direction)

    def update_settings(self, values):
        if not self.results:
            t = self.default_title
        elif values['OVERRIDE_TITLE']:
            t = "%s - %s" % (self.results.meta('NAME'), values['OVERRIDE_TITLE'])
        else:
            t = self.results.title

        if t != self.title:
            self.title = t
            self.name_changed.emit()

        if self.settings.update(values):
            self.update()

    def change_plot(self, plot_name):
        if not self.plotter:
            return
        if isinstance(plot_name, QModelIndex):
            plot_name = self.plotModel.name_of(plot_name)
        plot_name = str(plot_name)
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
            logger.exception("Aborting plotting due to error: %s", str(e))
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
