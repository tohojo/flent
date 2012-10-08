## -*- coding: utf-8 -*-
##
## netperf-wrapper.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:      8 oktober 2012
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

# Wrapper to run multiple concurrent netperf instances, in several iterations,
# and aggregate the result.

import subprocess, shlex, argparse, ConfigParser, threading, time, pprint

parser = argparse.ArgumentParser(description='Wrapper to run concurrent netperf instances')

parser.add_argument('config', type=unicode, help='config file defining the netperf instances')


config = ConfigParser.ConfigParser({'delay': 0}, dict, True)
config.add_section('global')
config.set('global', 'name', 'Netperf')
config.set('global', 'iterations', '1')
config.set('global', 'output', 'org_table')
config.set('global', 'cmd_opts', '-P 0 -v 0')
config.set('global', 'cmd_binary', '/usr/bin/netperf')

class ProcessRunner(threading.Thread):

    def __init__(self, binary, options, delay, *args, **kwargs):
        threading.Thread.__init__(self,*args, **kwargs)
        self.binary = binary
        self.options = options
        self.delay = delay
        self.result = None

    def run(self):
        if self.delay:
            time.sleep(self.delay)
        args = [self.binary] + shlex.split(self.options)
        prog = subprocess.Popen(args,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         close_fds=True)
        out,err=prog.communicate()
        self.result = out.strip()

class Aggregator(object):

    def __init__(self, iterations, binary, global_options):
        self.iterations = iterations
        self.binary = binary
        self.global_options = global_options
        self.instances = {}

    def add_instance(self, name, options, delay=None):
        self.instances[name] = {'options': self.global_options + " " + options,
                               'delay': delay}

    def iterate(self):
        result = {}
        threads = {}
        for n,i in self.instances.items():
            threads[n] = ProcessRunner(self.binary, i['options'], i['delay'])
            threads[n].start()
        for n,t in threads.items():
            t.join()
            result[n] = t.result

        return result

    def aggregate(self):
        results = []
        for i in range(self.iterations):
            results.append(self.iterate())
        return results

def format_pprint(results):
    pprint.pprint(results)

def format_org_table(results):
    pass

if __name__ == "__main__":

    args = parser.parse_args()
    config.read(args.config)

    agg = Aggregator(config.getint('global', 'iterations'),
                     config.get('global', 'cmd_binary'),
                     config.get('global', 'cmd_opts'))

    for s in config.sections():
        if s.startswith('test_'):
            agg.add_instance(config.get(s, 'name'),
                             config.get(s, 'cmd_opts'),
                             config.getint(s, 'delay'))

    pprint.pprint(agg.instances)
