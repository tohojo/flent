## -*- coding: utf-8 -*-
##
## setup.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:      4 December 2012
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
from distutils.command.install import install as _install
from netperf_wrapper.build_info import VERSION
from glob import glob

version_string = VERSION

if sys.version_info[:2] < (2,6):
    sys.stderr.write("Sorry, netperf-wrapper requires v2.6 or later of Python\n")
    sys.exit(1)

class install(_install):
    user_options = _install.user_options + [('fake-root', None,
                                              'indicates that --root is fake'
                                              ' (e.g. when creating packages.)')]
    boolean_options = _install.boolean_options + ['fake-root']

    def initialize_options(self):
        _install.initialize_options(self)
        self.fake_root = False

class build_py(_build_py):
    """build_py command

    This specific build_py command will modify module
    'netperf_wrapper.build_config' so that it contains information on
    installation prefixes afterwards.
    """

    def build_module (self, module, module_file, package):
        orig_content = None
        if ( module == 'build_info' and package == 'netperf_wrapper'
             and 'install' in self.distribution.command_obj):
            iobj = self.distribution.command_obj['install']
            with open(module_file, 'rb') as module_fp:
                orig_content = module_fp.read()

            if iobj.fake_root:
                prefix = iobj.prefix
            else:
                prefix = iobj.install_data

            with open(module_file, 'w') as module_fp:
                module_fp.write('# -*- coding: UTF-8 -*-\n\n')
                module_fp.write("VERSION='%s'\n"%(version_string))
                module_fp.write("DATA_DIR='%s'\n"%(
                    os.path.join(prefix, 'share', 'netperf-wrapper')))

        _build_py.build_module(self, module, module_file, package)

        if orig_content is not None:
            with open(module_file, 'wb') as module_fp:
                module_fp.write(orig_content)

data_files = [('share/netperf-wrapper', ['matplotlibrc.dist']),
              ('share/netperf-wrapper/tests',
               glob("tests/*.conf") + \
                   glob("tests/*.inc")),
              ('share/netperf-wrapper/ui',
               glob("ui/*.ui")),
              ('share/doc/netperf-wrapper',
               ['BUGS',
                'README.rst']+glob("*.example")),
              ('share/man/man1',
               ['man/netperf-wrapper.1']),
              ('share/doc/netperf-wrapper/misc',
               glob("misc/*")),
              ('share/mime/packages',
               ['netperf-wrapper-mime.xml']),
              ('share/applications',
               ['netperf-wrapper.desktop'])]

with open("README.rst") as fp:
    long_description = "\n"+fp.read()

setup(name="netperf-wrapper",
      version=version_string,
      description="Wrapper for running network tests such as netperf concurrently",
      long_description=long_description,
      author="Toke Høiland-Jørgensen <toke@toke.dk>",
      author_email="toke@toke.dk",
      url="https://github.com/tohojo/netperf-wrapper",
      license = "GNU GPLv3",
      platforms = ['Linux'],
      packages = ["netperf_wrapper"],
      scripts = ["netperf-wrapper"],
      data_files = data_files,
      cmdclass = {'build_py': build_py, 'install': install},
    )
