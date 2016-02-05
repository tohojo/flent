## -*- coding: utf-8 -*-
##
## __init__.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:      6 December 2012
## Copyright (c) 2012-2015, Toke Høiland-Jørgensen
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

from __future__ import absolute_import, division, print_function, unicode_literals

import locale
import os
import signal
import sys

# Convert SIGTERM into SIGINT to apply the same shutdown logic.
def handle_sigterm(sig, frame):
        os.kill(os.getpid(), signal.SIGINT)

def run_flent(gui=False):
    if sys.version_info[:3] < (2,7,3):
        sys.stderr.write("Sorry, Flent requires v2.7.3 or later of Python.\n")
        sys.exit(1)
    try:
        locale.setlocale(locale.LC_ALL, '')
        from flent import batch
        from flent.settings import load

        try:
            signal.signal(signal.SIGTERM, handle_sigterm)
            settings = load(sys.argv[1:])
            if gui or settings.GUI:
                from flent.gui import run_gui
                return run_gui(settings)
            else:
                b = batch.new(settings)
                b.run()

        except RuntimeError as e:
            try:
                if not settings.DEBUG_ERROR:
                    sys.stderr.write("Fatal error: %s\n"% str(e))
                    return 1
                else:
                    raise
            except NameError:
                sys.stderr.write("Fatal error: %s\n"% str(e))
                return 1
    except KeyboardInterrupt:
        try:
            b.kill()
        except NameError:
            pass

        # Proper behaviour on SIGINT is re-killing self with SIGINT to properly
        # signal to surrounding shell what happened.
        # Ref: http://mywiki.wooledge.org/SignalTrap
        try:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            os.kill(os.getpid(), signal.SIGINT)
        except:
            return 1 # Just in case...
    finally:
        try:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
        except:
            pass
    return 0

def run_flent_gui():
    return run_flent(gui=True)


__all__ = ['aggregators', 'build_info', 'formatters', 'gui', 'resultset', 'runners', 'settings', 'transformers', 'util', 'run_flent', 'run_flent_gui']
