# -*- coding: utf-8 -*-
#
# testcontrol-web-service.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     25 October 2014
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

import json
import os
import re
import select
import shlex
import subprocess
import sys

try:
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
    from SocketServer import ForkingMixIn
except ImportError:
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from socketserver import ForkingMixIn

tests = [{'name': 'test',
          'args': {'ipver': 'IP version (4 or 6)'},
          'exec': './test-exec.sh ${ipver}'}]


class TestWebServer(ForkingMixIn, HTTPServer):
    pass


class TestWebService(BaseHTTPRequestHandler):
    _INTERP_REGEX = re.compile(r"(^|[^$])(\$\{([^}]+)\})")
    _MAX_INTERP = 1000

    def respond(self, obj):
        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf8")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode("utf-8"))
        self.wfile.write("\n".encode("utf-8"))

    def find_test(self, name):
        for t in tests:
            if t['name'] == name:
                return t
        self.send_error(404, "Test not found: %s" % name)
        return None

    def do_GET(self):
        print(self.headers)
        parts = os.path.split(self.path)
        if len(parts) < 3 and not parts[1]:
            self.respond(list([i['name'] for i in tests]))
        else:
            test = self.find_test(parts[1])
            if test:
                self.respond(test['args'])

    def parse_input(self):
        length = self.headers.get('content-length')
        input_type = self.headers.get('Content-Type')
        parts = input_type.split(";", 1)
        if parts[0].strip().lower() != 'application/json':
            self.send_error(415, 'Invalid format. Needs application/json')
            return None
        if len(parts) > 1 and parts[1].startswith('charset='):
            charset = parts[1].split("=", 1)[1].strip()
        else:
            charset = 'utf-8'

        try:
            nbytes = int(length)
        except (TypeError, ValueError):
            self.send_error(411)
            return None

        if nbytes > 0:
            data = self.rfile.read(nbytes)

        while select.select([self.rfile], [], [], 0)[0]:
            if not self.rfile.read(1):
                break

        try:
            return json.loads(data.decode(charset))
        except Exception as e:
            self.send_error(400, "Unable to decode: %s" % e)

    def interpolate(self, string, req):
        m = self._INTERP_REGEX.search(string)
        i = 0
        while m is not None:
            k = m.group(3)
            if k in req:
                string = string.replace(m.group(2), str(req[k]))
            else:
                string = string.replace(m.group(2), "$${%s}" % k)
            m = self._INTERP_REGEX.search(string)
            i += 1
            if i > self._MAX_INTERP:
                self.send_error(
                    500, "Too many interpolations performed for exec string.")
                return None
        return string.replace("$$", "$")

    def handle_test(self, test, req):
        cmdline = self.interpolate(test['exec'], req)
        if cmdline:
            args = shlex.split(cmdline)
            proc = subprocess.Popen(args, stdout=subprocess.PIPE)
            resp = json.loads(proc.stdout.readline().decode('utf-8'))
            self.respond(resp)

    def do_POST(self):
        parts = os.path.split(self.path)
        if not parts[1]:
            self.send_error(405)
            return
        test = self.find_test(parts[1])
        if test:
            req = self.parse_input()
            if req:
                self.handle_test(test, req)


if __name__ == "__main__":
    server_addr = ('localhost', 8000)
    server = TestWebServer(server_addr, TestWebService)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
