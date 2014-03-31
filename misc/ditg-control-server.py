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

import sys, os, optparse, subprocess, time, tempfile, shutil, json, random, string, signal, traceback, time

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

class AlarmException(Exception):
    pass


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
    datafile_pattern = "%s.json"

    def __init__(self, bind_address):
        self.working_dir = tempfile.mkdtemp(prefix='ditgman-')
        self.seen = {}
        self.children = []
        self.garbage = []
        self.toplevel = True
        self.bind_address = bind_address

        signal.signal(signal.SIGINT, self._exit)
        signal.signal(signal.SIGTERM, self._exit)
        signal.signal(signal.SIGALRM, self._alarm)
        signal.signal(signal.SIGCHLD, self._collect_garbage)

    def get_test_results(self, test_id):
        filename = os.path.join(self.working_dir,  self.datafile_pattern % test_id)
        if not os.path.exists(filename):
            raise KeyError("Data for test ID '%s' not found" % test_id)
        with open(filename, 'rt') as fp:
            data = json.load(fp)
            self.garbage.append(filename)
            return data

    def request_new_test(self, duration, interval):
        duration = int(duration)
        interval = int(interval)
        if duration <= 0 or interval <= 0:
            raise Exception("Duration and interval must be positive integers.")
        if duration > 7200:
            raise Exception("Two hour test maximum exceeded.")
        if interval > duration*1000:
            raise Exception("Interval must be <= duration")
        test_id = "".join(random.sample(ALPHABET, 20))
        self._spawn_receiver(test_id, duration, interval)

        return {'status': 'OK', 'id': test_id}

    def _clean_fork(self, output=None):
        pid = os.fork()
        if pid:
            self.children.append(pid)
        else:
            self.children = []
            self.garbage = []
            self.toplevel = False
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

    def _unlink(self, filename):
        try:
            os.unlink(filename)
        except FileNotFoundError:
            pass

    def _spawn_receiver(self, test_id, duration, interval):
        stdout = "%s.recv.out" % test_id
        datafile = self.datafile_pattern % test_id
        if self._clean_fork(stdout):
            try:
                ret = self._run_receiver(test_id, duration, interval)
            except Exception as e:
                traceback.print_exc()
                ret = {'status': 'Error', 'message': str(e)}
            try:
                # Write data to temp file, atomically rename to final file name
                with open('%s.tmp' % datafile, 'wt') as fp:
                    json.dump(ret, fp)
                    os.rename('%s.tmp' % datafile, datafile)
            finally:
                if 'status' in ret and ret['status'] == 'OK':
                    self._unlink(stdout)
                    os._exit(0)
                os._exit(1)


    def _run_receiver(self, test_id, duration, interval):
        logfile = '%s.log' % test_id
        txtlog = '%s.log.txt' % test_id
        outfile = '%s.dat' % test_id
        ret = {}

        # Run ITGRecv; does not terminate after the end of the test, so wait for
        # the test duration + a grace time of 5 seconds, then kill the process
        proc = subprocess.Popen(['ITGRecv',
                                 '-l', logfile,
                                 '-I',
                                 '-a', self.bind_address])
        self.children.append(proc.pid)

        # Use an alarm signal for the timeout; means we don't have to wait for the
        # entire test duration if the ITGRecv process terminates before then
        signal.alarm(duration + 5)
        try:
            proc.wait()
        except AlarmException:
            proc.terminate()
        signal.alarm(0)

        # Call ITGDec on the log file output, read in the resulting data
        if not os.path.exists(logfile):
            ret['status'] = 'No data file produced'
        else:
            try:
                subprocess.check_call(['ITGDec', logfile,
                                       '-c', str(interval), outfile,
                                       '-l', txtlog])
                with open(outfile, 'rt') as fp:
                    ret['data'] = fp.read()

                # Read start of text log file to get timestamp of first received packet
                with open(txtlog, 'rt') as fp:
                    data = fp.read(1024)
                    try:
                        idx_s = data.index('rxTime>') + len('rxTime>')
                        idx_e = data.index('Size>')
                        t,microsec = data[idx_s:idx_e].split(".")
                        h,m,s = t.split(":")
                        dt = datetime.utcnow()
                        dt.replace(hour=int(h), minute=int(m), second=int(s), microsecond=int(microsec))
                        ret['utc_offset'] = float(time.mktime(dt.timetuple())) + dt.microsecond / 10**6
                    except Exception as e:
                        traceback.print_exc()
                        ret['utc_offset'] = None
                    ret['status'] = 'OK'
            except Exception as e:
                traceback.print_exc()
                ret['status'] = 'Error'
                ret['message'] = e.msg()


        # Clean up temporary files and exit
        for f in logfile, txtlog, outfile:
            self._unlink(f)

        return ret

    def _collect_garbage(self, signum, frame):
        while self.garbage:
            f = self.garbage.pop()
            os.unlink(f)
        for p in self.children:
            if os.waitpid(p, os.WNOHANG) != (0,0):
                self.children.remove(p)

    def _alarm(self, signum, frame):
        raise AlarmException()

    def _exit(self, signum, frame):
        for p in self.children:
            os.kill(p, signum)

        # Do not call normal exit handlers when we are a subprocess
        if not self.toplevel:
            os._exit(0)

        # SIGTERM is successful exit, others are not
        if signum == signal.SIGTERM:
            sys.exit(0)
        sys.exit(1)

    def __del__(self):
        if self.toplevel:
            shutil.rmtree(self.working_dir, ignore_errors=True)


def run():
    options,args = parser.parse_args()
    if not XML_DEFUSED and not options.INSECURE_XML:
        sys.stderr.write("XML EXPANSION ATTACK VULNERABILITY DETECTED. ABORTING!\n"
                         "Run with --insecure-xml to run anyway (will leave the server vulnerable!)\n")
        sys.exit(1)

    server = SimpleXMLRPCServer((options.BIND_ADDRESS, options.BIND_PORT), allow_none=True)
    manager = DITGManager(options.ITG_ADDRESS or options.BIND_ADDRESS)
    server.register_instance(manager)
    server.register_introspection_functions()
    server.serve_forever()



if __name__ == "__main__":
    run()
