## -*- coding: utf-8 -*-
##
## netperf-wrapper.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     October 8th, 2012
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

import subprocess, shlex, optparse, ConfigParser, threading, time, pprint

parser = optparse.OptionParser(description='Wrapper to run concurrent netperf instances',
                               usage="usage: %prog [options] config")

#parser.add_option('config', type=unicode, help='config file defining the netperf instances')


config = ConfigParser.ConfigParser({'delay': 0})
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
        """Runs the configured job. If a delay is set, wait for that many
        seconds, then open the subprocess, wait for it to finish, and collect
        the last word of the output (whitespace-separated)."""

        if self.delay:
            time.sleep(self.delay)
        args = [self.binary] + shlex.split(self.options)
        prog = subprocess.Popen(args,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         close_fds=True)
        out,err=prog.communicate()
        self.result = out.split()[-1].strip()

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
        """Create a ProcessRunner thread for each instance and start them. Wait
        for the threads to exit, then collect the results."""

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

def format_pprint(name, results):
    """Use the pprint pretty-printing module to just print out the contents of
    the results list."""

    print name
    pprint.pprint(results)

def format_org_table(name, results):
    """Format the output for an Org mode table. The formatter is pretty crude
    and does not align the table properly, but it should be sufficient to create
    something that Org mode can correctly realign."""

    if not results:
        print name, "-- empty"
    first_row = results[0]
    header_row = [name] + sorted(first_row.keys())
    print "| " + " | ".join(header_row) + " |"
    print "|-" + "-+-".join(["-"*len(i) for i in header_row]) + "-|"
    for i,row in enumerate(results):
        print "| Run %d |" % (i+1),
        for c in header_row[1:]:
            print row[c], "|",
        print

formatters = {'org_table': format_org_table,
              'pprint': format_pprint}

if __name__ == "__main__":

    (options,args) = parser.parse_args()
    if len(args) < 1:
        parser.error("Missing config file.")
    try:
        with open(args[0]) as fp:
            config.readfp(fp)
    except IOError:
        parser.error("Config file '%s' not found" % args[0])
    except ConfigParser.Error:
        parser.error("Unable to parse config file '%s'" % args[0])

    agg = Aggregator(config.getint('global', 'iterations'),
                     config.get('global', 'cmd_binary'),
                     config.get('global', 'cmd_opts'))

    for s in config.sections():
        if s.startswith('test_'):
            agg.add_instance(config.get(s, 'name'),
                             config.get(s, 'cmd_opts'),
                             config.getint(s, 'delay'))

    results = agg.aggregate()
    formatter = config.get('global', 'output')
    if formatter in formatters:
        formatters[formatter](config.get('global', 'name'),
                              results)
