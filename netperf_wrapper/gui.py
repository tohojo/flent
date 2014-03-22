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
except ImportError:
    raise RuntimeError("PyQt4 must be installed to use the GUI.")

from netperf_wrapper.build_info import DATA_DIR

__all__ = ['run_gui']

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
        def __init__(self):
            base.__init__(self)
    return C


class MainWindow(get_ui_class("mainwindow.ui")):

    def __init__(self):
        super(MainWindow, self).__init__()
        self.setupUi(self)

def run_gui(settings):
    app = QtGui.QApplication(sys.argv[:1])
    mainwindow = MainWindow()
    mainwindow.show()
    sys.exit(app.exec_())
