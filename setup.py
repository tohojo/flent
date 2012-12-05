## -*- coding: utf-8 -*-
##
## setup.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:      4 december 2012
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

import sys, os
from distutils.core import setup
from distutils.command.build_py import build_py as _build_py
from glob import glob

version_string = "0.1.0"

if sys.version_info[:2] < (2,6):
    sys.stderr.write("Sorry, netperf-wrapper requires v2.6 or later of Python\n")
    sys.exit(1)

class build_py(_build_py):
    """build_py command

    This specific build_py command will modify module
    'netperf_wrapper.build_config' so that it contains information on
    installation prefixes afterwards.
    """
    def build_module (self, module, module_file, package):
        orig_content = None
        if isinstance(package, basestring):
            package = package.split('.')
        elif type(package) not in (ListType, TupleType):
            raise TypeError, \
                  "'package' must be a string (dot-separated), list, or tuple"

        if ( module == 'build_info' and len(package) == 1 and
            package[0] == 'netperf_wrapper' and 'install' in self.distribution.command_obj):
            iobj = self.distribution.command_obj['install']
            with open(module_file, 'r') as module_fp:
                orig_content = module_fp.read()

            with open(module_file, 'w') as module_fp:
                module_fp.write('# -*- coding: UTF-8 -*-\n\n')
                module_fp.write("DATA_DIR = '%s'\n"%(
                    os.path.join(iobj.install_data, 'share', 'netperf-wrapper')))
                module_fp.write("LIB_DIR = '%s'\n"%(iobj.install_lib))
                module_fp.write("SCRIPT_DIR = '%s'\n"%(iobj.install_scripts))

        _build_py.build_module(self, module, module_file, package)

        if orig_content is not None:
            with open(module_file, 'w') as module_fp:
                module_fp.write(orig_content)

data_files = [('share/netperf-wrapper/tests',
               glob("tests/*.conf") + \
                   glob("tests/*.inc")),
              ('share/doc/netperf-wrapper',
               ['BUGS',
                'README.org']),
              ('share/doc/netperf-wrapper/misc',
               glob("misc/*.patch"))]

setup(name="netperf-wrapper",
      version=version_string,
      description="Wrapper for running network tests such as netperf concurrently",
      author="Toke Høiland-Jørgensen <toke@toke.dk>",
      author_email="toke@toke.dk",
      url="https://github.com/tohojo/netperf-wrapper",
      license = "GNU GPLv3",
      platforms = ['Linux'],
      packages = ["netperf_wrapper"],
      scripts = ["netperf-wrapper"],
      data_files = data_files,
      cmdclass = {'build_py': build_py},
    )
