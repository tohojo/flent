## -*- coding: utf-8 -*-
##
## batch.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     11 April 2014
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
import sys, pprint, string, re, time

try:
    from configparser import RawConfigParser
except ImportError:
    from ConfigParser import RawConfigParser
try:
    from collections import OrderedDict
except ImportError:
    from netperf_wrapper.ordereddict import OrderedDict

# Python2/3 compatibility
try:
    basestring
except NameError:
    basestring=str


class BatchRunner(object):

    _INTERP_REGEX =  re.compile(r"(^|[^$])(\$\{([^}]+)\})")
    _MAX_INTERP = 1000


    def __init__(self, settings):
        self.args = {}
        self.batches = {}
        self.commands = {}
        self.settings = settings
        self.interpolation_values = dict()


    def read(self, filename):
        parser = RawConfigParser(dict_type=OrderedDict)
        read = parser.read(filename)
        if read != [filename]:
            raise RuntimeError("Unable to read batch file: %s." % filename)

        for s in parser.sections():
            typ,nam = s.split("::")
            if typ.lower() == 'arg':
                self.args[nam.lower()] = dict(parser.items(s))
            elif typ.lower() == 'batch':
                self.batches[nam.lower()] = dict(parser.items(s))
            elif typ.lower() == 'command':
                self.commands[nam.lower()] = dict(parser.items(s))
            else:
                raise RuntimeError("Unknown section type: '%s'." % typ)

        self.expand_groups()

    def expand_groups(self):
        for obj in self.args, self.batches, self.commands:
            for name, vals in obj.items():
                # Expand inheritance
                if 'inherits' in vals:
                    if not vals['inherits'] in obj:
                        raise RuntimeError("%s inherits from non-existent parent %s." % (name, vals['inherits']))
                    obj[name] = self.inherit(obj[vals['inherits']], vals)

                # Parse boolean options
                for k,v in obj[name].items():
                    if isinstance(v, basestring) and v.lower() in ('yes', 'true', 'on'):
                        obj[name][k] = True
                    elif isinstance(v, basestring) and v.lower() in ('no', 'false', 'off'):
                        obj[name][k] = False

    def inherit(self, parent, child):
        new = parent.copy()
        new.update(child)
        if 'inherits' in parent:
            new['inherits'] = "%s, %s" % (parent['inherits'], child['inherits'])
        return new

    def interpolate(self, string, ivars):
        """Perform recursive expansion of ${vars}.

        Works by looking for a string matching the expansion syntax and
        replacing that with the value of the ivars dict corresponding to the key
        inside {}. If no key matching key is found, the expansion is escaped (by
        duplicating the $), to make sure the expansion ends. Cyclic expansions
        are protected against by capping the number of iterations."""

        if not isinstance(string, basestring):
            return string

        ret = string
        m = self._INTERP_REGEX.search(ret)
        i = 0
        while m is not None:
            k = m.group(3)
            if k in ivars:
                ret = ret.replace(m.group(2), ivars[k])
            else:
                ret = ret.replace(m.group(2), "$"+m.group(2))
            m = self._INTERP_REGEX.search(ret)
            i += 1
            if i > self._MAX_INTERP:
                raise RuntimeError("Cyclic interpolation (more than %d expansions performed)." % self._MAX_INTERP)

        return ret.replace("$$", "$")

    def apply_args(self, values, args=None):
        new = self.interpolation_values.copy()
        if args is not None:
            new.update(args)
        new.update(values)
        for k,v in new.items():
            new[k] = self.interpolate(v, new)

        return new

    def commands_for(self, batchname, arg=None):
        if arg and not arg in self.args:
            raise RuntimeError("Can't find arg '%s' when expanding batch commands." % arg)
        if not batchname in self.batches:
            raise RuntimeError("Can't find batch '%s' to expand." % batchname)
        batch = self.batches[batchname]
        if not 'commands' in batch:
            return []
        cmdnames = [i.strip() for i in batch['commands'].split(',')]
        commands = []

        args = {'batch_name': batchname}

        for c in cmdnames:
            if not c in self.commands:
                raise RuntimeError("Can't find command '%s' when expanding batch command." % c)
            a = args.copy()
            if arg:
                a.update(self.args[arg])
            commands.append(self.apply_args(self.commands[c], a))

        return commands


    def run_batch(self, batchname):
        if not batchname in self.batches:
            raise RuntimeError("Can't find batch '%s' to run." % name)
        batch = self.batches[batchname]

        args = [i.strip() for i in batch.get('for_args', '').split(',')]
        pause = int(batch.get('pause', 0))

        for arg in args:
            commands = self.commands_for(batchname, arg)
            print("Running test %s for arg %s" % (batch['test_name'], arg))
            # TODO
            print("Sleeping for %d seconds" % pause)
            time.sleep(pause)

    def p(self):
        for t in 'args', 'batches', 'commands':
            print("%s:\n%s\n"% (t, pprint.pformat(getattr(self, t))))


if __name__ == "__main__":
    br = BatchRunner({'data_filename': 'testing'})
    br.read(sys.argv[1])
    br.p()
    br.run_batch('tcpfair')
    pprint.pprint(br.commands_for("tcpfair", 'codel'))
