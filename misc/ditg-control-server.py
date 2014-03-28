## -*- coding: utf-8 -*-
##
## ditg-control-server.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     28 marts 2014
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

import sys, os, optparse, socket, subprocess, time, tempfile, shutil, json, random, string

from datetime import datetime

try:
    from defusedxml.xmlrpc import monkey_patch
    monkey_patch()
    del monkey_patch
    XML_DEFUSED=True
except ImportError:
    XML_DEFUSED=False

try:
    # python 2
    from SimpleXMLRPCServer import SimpleXMLRPCServer
except ImportError:
    from xmlrpc.server import SimpleXMLRPCServer

# Nicked from the subprocess module -- for closing open file descriptors
try:
    MAXFD = os.sysconf("SC_OPEN_MAX")
except:
    MAXFD = 256

ALPHABET = list(string.ascii_lowercase) + list(string.digits)


parser = optparse.OptionParser(description="Control server for D-ITG receive component session negotiation.")

parser.add_option('--insecure-xml', action='store_true', dest='INSECURE_XML', default=False,
                  help="Run even though the defusedxml module is unavailable. WARNING: Will leave "
                  "the server open to entity expansion attacks!")
parser.add_option('-a', '--address', action='store', type='string', dest='BIND_ADDRESS',
                  default='localhost', help="Address to bind to. Default: localhost.")
parser.add_option('-p', '--port', action='store', type='int', dest='BIND_PORT', default='8000',
                  help="Bind port. Default: 8000.")
parser.add_option('-A', '--itg-address', action='store', type='string', dest='ITG_ADDRESS',
                  default=None, help="Address to bind ITGRecv to. Default: Same as --address.")

class DITGManager(object):
    def __init__(self, bind_address):
        self.working_dir = tempfile.mkdtemp(prefix='ditgman-')
        self.seen = {}
        self.children = []
        self.bind_address = bind_address

        self._spawn_logserver()

    def get_test_results(self, test_id):
        filename = os.path.join(self.working_dir, "data_%s.json" % test_id)
        if not os.path.exists(filename):
            raise KeyError("Data for test ID '%s' not found" % test_id)
        with open(filename, 'rt') as fp:
            data = json.load(fp)
            return data

    def request_new_test(self, duration):
        test_id = "".join(random.sample(ALPHABET, 20))
        self._spawn_receiver(test_id, duration)

        return ['OK', test_id]

    def _clean_fork(self, output=None):
        pid = os.fork()
        if pid:
            self.children.append(pid)
        else:
            os.chdir(self.working_dir)
            sys.stdin.close()
            os.closerange(3, MAXFD)
            if output is not None:
                with open(os.path.join(self.working_dir, output), "w") as fp:
                    os.dup2(fp.fileno(), 1)
                    os.dup2(fp.fileno(), 2)
            else:
                sys.stdout.close()
                sys.stderr.close()
        return pid == 0

    def _spawn_receiver(self, test_id, duration):
        if self._clean_fork("%s.recv.stdout" % test_id):
            os.execlp('ITGRecv', 'ITGRecv',
                      '-l', '%s.log' % test_id,
                      '-L',
                      '-a', self.bind_address
                )

    def _spawn_logserver(self):
        if self._clean_fork(output="ITGLog.stdout"):
            os.execlp('ITGLog', 'ITGLog')

    def __del__(self):
        shutil.rmtree(self.working_dir, ignore_errors=True)


def run():
    options,args = parser.parse_args()
    if not XML_DEFUSED and not options.INSECURE_XML:
        sys.stderr.write("XML EXPANSION ATTACK VULNERABILITY DETECTED. ABORTING!\n"
                         "Run with --insecure-xml to run anyway (will leave the server vulnerable!)\n")
        sys.exit(1)

    server = SimpleXMLRPCServer((options.BIND_ADDRESS, options.BIND_PORT))
    manager = DITGManager(options.ITG_ADDRESS or options.BIND_ADDRESS)
    server.register_instance(manager)
    server.register_introspection_functions()
    server.serve_forever()



if __name__ == "__main__":
    run()
