## -*- coding: utf-8 -*-
##
## setup.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:      4 December 2012
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

import sys, os

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py
from setuptools.command.sdist import sdist as _sdist

from flent.build_info import VERSION
from glob import glob

version_string = VERSION

if sys.version_info[:3] < (2,7,3):
    sys.stderr.write("Sorry, Flent requires v2.7.3 or later of Python.\n")
    sys.exit(1)

def rewrite_build_info(module_file):
    with open(module_file, 'w') as module_fp:
        module_fp.write('# -*- coding: UTF-8 -*-\n\n')
        module_fp.write("import os\n")
        module_fp.write("VERSION='%s'\n"%(version_string))
        module_fp.write("DATA_DIR=os.path.dirname(__file__)\n")

class build_py(_build_py):
    """build_py command

    This specific build_py command will modify module
    'flent.build_config' so that it contains information on
    installation prefixes afterwards.
    """

    def build_module (self, module, module_file, package):
        orig_content = None
        if module == 'build_info' and package == 'flent':
            with open(module_file, 'rb') as module_fp:
                orig_content = module_fp.read()

            rewrite_build_info(module_file)

        _build_py.build_module(self, module, module_file, package)

        if orig_content is not None:
            with open(module_file, 'wb') as module_fp:
                module_fp.write(orig_content)

class sdist(_sdist):
    def make_release_tree(self, base_dir, files):
        if 'flent/build_info.py' in files and not self.dry_run:
            files = [f for f in files if f != 'flent/build_info.py']
            _sdist.make_release_tree(self,base_dir,files)
            rewrite_build_info(os.path.join(base_dir, 'flent/build_info.py'))
        else:
            _sdist.make_release_tree(self,base_dir,files)

data_files = [('share/doc/flent',
               ['BUGS',
                'README.rst']+glob("*.example")),
              ('share/man/man1',
               ['man/flent.1']),
              ('share/doc/flent/misc',
               glob("misc/*")),
              ('share/mime/packages',
               ['flent-mime.xml']),
              ('share/applications',
               ['flent.desktop'])]

classifiers = [
    'Development Status :: 4 - Beta',
    'Environment :: Console',
    'Environment :: MacOS X',
    'Environment :: X11 Applications',
    'Environment :: X11 Applications :: KDE',
    'Intended Audience :: Developers',
    'Intended Audience :: Education',
    'Intended Audience :: Science/Research',
    'Intended Audience :: System Administrators',
    'Intended Audience :: Telecommunications Industry',
    'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
    'Operating System :: MacOS :: MacOS X',
    'Operating System :: POSIX',
    'Programming Language :: Python',
    'Programming Language :: Python :: 2',
    'Programming Language :: Python :: 2.7',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.3',
    'Programming Language :: Python :: 3.4',
    'Topic :: Internet',
    'Topic :: System :: Benchmark',
    'Topic :: System :: Networking',
    'Topic :: Utilities',
]

with open("README.rst") as fp:
    long_description = "\n"+fp.read()

setup(name="flent",
      version=version_string,
      description="The FLExible Network Tester",
      long_description=long_description,
      include_package_data=True,
      author="Toke Høiland-Jørgensen <toke@toke.dk>",
      author_email="toke@toke.dk",
      url="http://flent.org",
      license = "GNU GPLv3",
      classifiers = classifiers,
      packages = ["flent"],
      entry_points = {'console_scripts': ['flent = flent:run_flent'],
                      'gui_scripts': ['flent-gui = flent:run_flent_gui']},
      zip_safe=False,
      data_files = data_files,
      cmdclass = {'build_py': build_py, 'sdist': sdist},
      extras_require = {
          'GUI': ['PyQt4>=4.9'],
          'Plots': ['matplotlib>=1.1'],
      },
    )
