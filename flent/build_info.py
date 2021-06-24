# -*- coding: utf-8 -*-
#
# build_info.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:      6 December 2012
# Copyright (c) 2012-2016, Toke Høiland-Jørgensen
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

# setup.py rewrites this file with the install prefix info

import os

# this value works for the source distribution
VERSION = "2.0.1-git"
DATA_DIR = os.path.dirname(__file__)

ENCODING = "UTF-8"
try:
    import locale
    ENCODING = locale.getpreferredencoding(False)
except:
    pass

if VERSION.endswith("-git") and os.path.exists(
        os.path.realpath(os.path.join(DATA_DIR, '..', '.git'))):
    try:
        import subprocess
        commit = subprocess.check_output(
            ["git", "log", "--format=%h", "-1"], cwd=DATA_DIR).decode(ENCODING)
        VERSION += "-%s" % commit.strip()
    except:
        pass
