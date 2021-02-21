# -*- coding: utf-8 -*-
#
# batch.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     11 April 2014
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

import itertools
import os
import pprint
import random
import re
import signal
import subprocess
import sys
import time
import uuid

from datetime import datetime, timedelta
from fnmatch import fnmatch
from collections import OrderedDict

try:
    from configparser import RawConfigParser
except ImportError:
    from ConfigParser import RawConfigParser

from flent import aggregators, formatters, resultset, loggers
from flent.metadata import record_metadata, record_postrun_metadata
from flent.util import clean_path, format_date, token_split
from flent.settings import parser as SETTINGS_PARSER
from flent.settings import _LOG_DEFER

# Python2/3 compatibility
try:
    basestring
except NameError:
    basestring = str

logger = loggers.get_logger(__name__)


def new(settings):
    return BatchRunner(settings)


class BatchRunner(object):

    _INTERP_REGEX = re.compile(r"(^|[^$])(\$\{([^}]+)\})")
    _MAX_INTERP = 1000

    def __init__(self, settings):
        self.args = OrderedDict()
        self.batches = OrderedDict()
        self.commands = OrderedDict()
        self.settings = settings
        self.killed = False
        self.children = []
        self.logfile = self.logfile_debug = None
        self.tests_run = 0

        for f in settings.BATCH_FILES:
            self.read(f)

    def read(self, filename):
        parser = RawConfigParser(dict_type=OrderedDict)
        read = parser.read(filename)
        if read != [filename]:
            raise RuntimeError("Unable to read batch file: %s." % filename)

        for s in parser.sections():
            typ, nam = s.split("::")
            if typ.lower() == 'arg':
                self.args[nam.lower()] = OrderedDict(parser.items(s))
            elif typ.lower() == 'batch':
                self.batches[nam.lower()] = OrderedDict(parser.items(s))
            elif typ.lower() == 'command':
                self.commands[nam.lower()] = OrderedDict(parser.items(s))
            else:
                raise RuntimeError("Unknown section type: '%s'." % typ)

        self.expand_groups()

    def expand_groups(self):
        for obj in self.args, self.batches, self.commands:
            for name, vals in obj.items():
                # Expand inheritance
                if 'inherits' in vals:
                    for inh in [x.strip() for x in reversed(vals['inherits'].split(','))]:
                        if not inh in obj:
                            raise RuntimeError(
                                "%s inherits from non-existent parent %s."
                                % (name, inh))
                        obj[name] = self.inherit(obj[inh], obj[name])

                # Parse boolean options
                for k, v in obj[name].items():
                    if isinstance(v, basestring) and v.lower() in ('yes', 'true', 'on'):  # noqa: E501
                        obj[name][k] = True
                    elif isinstance(v, basestring) and v.lower() in ('no', 'false', 'off'):  # noqa: E501
                        obj[name][k] = False

    def inherit(self, parent, child):
        new = parent.copy()

        # Make sure children are not declared abstract.
        if 'abstract' in new:
            del new['abstract']

        new.update(child)
        if 'inherits' in parent:
            new['inherits'] = "%s, %s" % (parent['inherits'], child['inherits'])

        return new

    def get_ivar(self, name, ivars, settings):
        if name in ivars:
            return str(ivars[name])
        elif hasattr(settings, name.upper()):
            return str(getattr(settings, name.upper()))
        else:
            return "$${%s}" % name

    def interpolate(self, string, ivars, settings=None):
        """Perform recursive expansion of ${vars}.

        Works by looking for a string matching the expansion syntax and
        replacing that with the value of the ivars dict corresponding to the key
        inside {}. If no key matching key is found, the expansion is escaped (by
        duplicating the $), to make sure the expansion ends. Cyclic expansions
        are protected against by capping the number of iterations."""

        if not isinstance(string, basestring):
            return string

        if settings is None:
            settings = self.settings

        ret = string
        m = self._INTERP_REGEX.search(ret)
        i = 0
        while m is not None:
            k = m.group(3)
            ret = ret.replace(m.group(2), self.get_ivar(k, ivars, settings))
            m = self._INTERP_REGEX.search(ret)
            i += 1
            if i > self._MAX_INTERP:
                raise RuntimeError(
                    "Cyclic interpolation (more than %d expansions performed)."
                    % self._MAX_INTERP)

        return ret.replace("$$", "$")

    def apply_args(self, values, args={}, settings=None):
        new = OrderedDict(values)
        new.update(args)
        for k, v in new.items():
            new[k] = self.interpolate(v, new, settings)

        return new

    def commands_for(self, batch, settings=None):
        if 'commands' not in batch:
            return []
        cmdnames = [i.strip() for i in token_split(batch['commands'])]
        commands = OrderedDict()

        while cmdnames:
            c = cmdnames.pop(0)
            if not c or c in commands:
                continue
            if c not in self.commands:
                raise RuntimeError("Can't find command '%s' when expanding "
                                   "batch command." % c)
            cmd = self.apply_args(self.commands[c], batch, settings)

            # Don't include disabled commands
            if cmd.get('disabled', False) or not cmd.get('enabled', True):
                continue

            # Commands can specify extra commands to run; expand those, use the
            # dictionary to prevent duplicates
            extra = [i.strip() for i in token_split(cmd.get('extra_commands', ''))
                     if i.strip()]
            for e in reversed(extra):
                cmdnames.insert(0, e)
            commands[c] = cmd

        return commands.values()

    def run_command(self, command):
        cmd = command['exec'].strip()
        if self.settings.BATCH_VERBOSE:
            ess = command.get('essential', False)
            if self.settings.BATCH_DRY:
                logger.info("  Would run '%s' (%s)", cmd,
                            'essential' if ess else 'non-essential')
            else:
                logger.info("  Running '%s', (%s)", cmd,
                            'essential' if ess else 'non-essential')

        if self.settings.BATCH_DRY:
            return
        if command['type'] in ('pre', 'post'):
            try:
                res = subprocess.check_output(cmd, universal_newlines=True,
                                              shell=True,
                                              stderr=subprocess.STDOUT)
                logger.debug("Command '%s' executed successfully.", cmd,
                             extra={'output': res})
            except subprocess.CalledProcessError as e:
                if command.get('essential', False):
                    raise RuntimeError("Essential command '%s' failed. "
                                       "Return code: %s.\nOutput:\n %s."
                                       % (cmd, e.returncode,
                                          "\n ".join(e.output.splitlines())))
                else:
                    logger.warning("Command '%s' failed (%d).",
                                   cmd,
                                   e.returncode,
                                   extra={'output': e.output})
        elif command['type'] in ('monitor',):
            proc = subprocess.Popen(cmd, universal_newlines=True, shell=True,
                                    stderr=subprocess.STDOUT)
            self.children.append((proc, command.get('kill', False)))

    def kill_children(self, force=False):
        for proc, kill in self.children:
            if kill or force:
                proc.terminate()
            else:
                proc.wait()
        self.children = []

    def run_commands(self, commands, ctype, essential_only=False):
        for c in commands:
            if c['type'] == ctype and (not essential_only or
                                       c.get('essential', False)):
                try:
                    self.run_command(c)
                except:
                    # When running in essential only mode, suppress errors to
                    # make sure subsequent commands don't fail
                    if not essential_only:
                        raise

    def gen_filename(self, settings, batch, argset, rep):
        p = ["batch", settings.BATCH_NAME]
        if self.settings.BATCH_TIMESTAMP:
            p.append(batch['batch_time'])
        p.append(batch.get('filename_extra', "%s-%s" % (argset, rep)))
        return clean_path("-".join(p))

    def expand_argsets(self, batch, argsets, batch_time, batch_name,
                       print_status=True, no_shuffle=False):

        sets = itertools.product(*argsets)
        if self.settings.BATCH_SHUFFLE and not no_shuffle:
            sets = list(sets)
            random.shuffle(sets)

        for argset in sets:
            rep = argset[-1]
            argset = argset[:-1]
            settings = self.settings.copy()
            if print_status:
                logger.info(" args:%s rep:%02d%s", ",".join(argset), rep,
                            " (dry run)" if settings.BATCH_DRY else "")
            settings.FORMAT = 'null'
            settings.BATCH_NAME = batch_name
            settings.BATCH_TIME = batch_time
            settings.TIME = datetime.utcnow()

            expand_vars = {'repetition': "%02d" % rep,
                           'batch_time': format_date(settings.BATCH_TIME,
                                                     fmt="%Y-%m-%dT%H%M%S")}

            for arg in argset:
                if arg not in self.args:
                    raise RuntimeError("Invalid arg: '%s'." % arg)
                expand_vars.update(self.args[arg])

            b = self.apply_args(batch, expand_vars, settings)

            if 'test_name' not in b:
                raise RuntimeError("Missing test name.")

            settings.load_rcvalues(b.items(), override=True)
            settings.NAME = b['test_name']
            settings.load_test(informational=True)
            settings.DATA_FILENAME = self.gen_filename(settings, b, argset, rep)

            yield b, settings

    def get_argsets(self, batch):
        argsets = []

        for k in batch.keys():
            if k.startswith("for_"):
                argset = []
                for a in token_split(batch[k]):
                    a = a.strip().lower()
                    matches = [arg for arg in self.args if fnmatch(arg, a)]
                    if not matches:
                        raise RuntimeError("No matches for arg: '%s'." % a)
                    argset.extend(matches)
                argsets.append(argset)

        reps = range(1, int(batch.get('repetitions', 1)) + 1)
        argsets.append(reps)

        return argsets

    def get_batch_runtime(self, batch_name):
        if batch_name not in self.batches:
            raise RuntimeError("Can't find batch '%s' to run." % batch_name)
        batch = self.batches[batch_name].copy()
        batch.update(self.settings.BATCH_OVERRIDE)

        if batch.get('abstract', False) or batch.get('disabled', False):
            return (0, 0)

        total_time = 0
        n = 0
        argsets = self.get_argsets(batch)

        for _, s in self.expand_argsets(batch, argsets, self.settings.TIME,
                                        batch_name, print_status=False,
                                        no_shuffle=True):
            total_time += s.TOTAL_LENGTH + int(batch.get('pause', 0))
            n += 1

        return total_time, n

    def run_batch(self, batch_name):
        if batch_name not in self.batches:
            raise RuntimeError("Can't find batch '%s' to run." % batch_name)
        batch = self.batches[batch_name].copy()
        batch.update(self.settings.BATCH_OVERRIDE)

        # A batch declared 'abstract' is not runnable
        if batch.get('abstract', False):
            logger.info(" Batch marked as abstract. Not running.")
            return False
        elif batch.get('disabled', False) or not batch.get('enabled', True):
            logger.info(" Batch disabled.")
            return False

        argsets = self.get_argsets(batch)

        pause = int(batch.get('pause', 0))

        batch_time = None
        if self.settings.BATCH_RESUME is not None and \
           os.path.isdir(self.settings.BATCH_RESUME):
            # We're resuming a batch run. Try to find a data file we can get the
            # original batch run time from.
            for dirpath, dirnames, filenames in os.walk(
                    self.settings.BATCH_RESUME):
                datafiles = [f for f in filenames if f.endswith(resultset.SUFFIX)]
                if datafiles:
                    f = datafiles[0]
                    r = resultset.load(os.path.join(dirpath, f))
                    batch_time = r.meta("BATCH_TIME")
                    try:
                        self.settings.BATCH_UUID = r.meta("BATCH_UUID")
                        logger.info(" Using previous UUID %s.\n",
                                    self.settings.BATCH_UUID)
                    except KeyError:
                        pass
                    break
            if batch_time is None:
                raise RuntimeError("No data files found in resume directory %s."
                                   % self.settings.BATCH_RESUME)
        elif self.settings.BATCH_RESUME:
            raise RuntimeError("Batch resume directory %s doesn't exist!\n"
                               % self.settings.BATCH_RESUME)
        else:
            batch_time = self.settings.TIME

        filenames_seen = set()

        for b, settings in self.expand_argsets(batch, argsets,
                                               batch_time, batch_name):

            if 'output_path' in b:
                output_path = clean_path(b['output_path'], allow_dirs=True)
            else:
                output_path = settings.DATA_DIR

            if settings.BATCH_RESUME is not None:
                if os.path.commonprefix(
                    [os.path.abspath(output_path),
                     os.path.abspath(settings.BATCH_RESUME)]) \
                        != os.path.abspath(settings.BATCH_RESUME):
                    raise RuntimeError("Batch-specified output path is not a "
                                       "subdirectory of resume path. Bailing.")
                if os.path.exists(os.path.join(output_path, "%s%s"
                                               % (settings.DATA_FILENAME,
                                                  resultset.SUFFIX))):
                    logger.info("  Previous result exists, skipping.")
                    continue

            if settings.BATCH_DRY and settings.BATCH_VERBOSE:
                logger.info("  Would output to: %s.\n", output_path)
            elif not settings.BATCH_DRY and not os.path.exists(output_path):
                try:
                    os.makedirs(output_path)
                except OSError as e:
                    raise RuntimeError("Unable to create output path '%s': %s."
                                       % (output_path, e))

            commands = self.commands_for(b, settings)
            if not settings.BATCH_DRY:
                self.logfile = loggers.setup_logfile(
                    os.path.join(output_path,
                                 "%s.log" % settings.DATA_FILENAME),
                    level=loggers.INFO, replay=False)
                if b.get('debug_log', False):
                    self.logfile_debug = loggers.setup_logfile(
                        os.path.join(output_path,
                                     "%s.debug.log" % settings.DATA_FILENAME),
                        level=loggers.DEBUG,
                        maxlevel=loggers.DEBUG,
                        replay=False)

            if settings.DATA_FILENAME in filenames_seen:
                logger.warning("Filename already seen in this run: %s",
                               settings.DATA_FILENAME)
            filenames_seen.add(settings.DATA_FILENAME)

            self.run_commands(commands, 'pre')
            self.run_commands(commands, 'monitor')
            try:
                if settings.BATCH_VERBOSE:
                    if settings.BATCH_DRY:
                        logger.info("  Would run test '%s'.", settings.NAME)
                    else:
                        logger.info("  Running test '%s'.", settings.NAME)
                    logger.info("   data_filename=%s", settings.DATA_FILENAME)
                    for k in sorted(b.keys()):
                        if k.upper() in SETTINGS_PARSER:
                            logger.info("   %s=%s", k, b[k])

                if settings.BATCH_DRY:
                    self.tests_run += 1
                else:
                    # Load test again with informational=False to enable host
                    # lookups and other actions that may fail
                    settings.load_test(informational=False)
                    self.run_test(settings, output_path)
            except KeyboardInterrupt:
                self.run_commands(commands, 'post', essential_only=True)
                raise
            except Exception as e:
                self.run_commands(commands, 'post', essential_only=True)
                logger.exception("  Error running test: %s", str(e))
            else:
                try:
                    self.run_commands(commands, 'post')
                except Exception as e:
                    self.run_commands(commands, 'post', essential_only=True)
                    logger.exception("  Error running post-commands: %s", str(e))
            finally:
                self.kill_children()
                if self.logfile:
                    loggers.remove_log_handler(self.logfile)
                    self.logfile.close()
                    self.logfile = None
                if self.logfile_debug:
                    loggers.remove_log_handler(self.logfile_debug)
                    self.logfile_debug.close()
                    self.logfile_debug = None

            if settings.BATCH_DRY and settings.BATCH_VERBOSE:
                logger.info("  Would sleep for %d seconds.", pause)
            elif not settings.BATCH_DRY:
                time.sleep(pause)

    def run_test(self, settings, output_path, print_datafile_loc=False):
        settings = settings.copy()
        settings.load_test()
        res = resultset.new(settings)

        if settings.LOG_FILE is _LOG_DEFER:
            settings.LOG_FILE = res.dump_filename.replace(res.SUFFIX, ".log")
            loggers.setup_logfile(settings.LOG_FILE)

        record_metadata(res, settings.EXTENDED_METADATA,
                        settings.REMOTE_METADATA)

        if not settings.HOSTS:
            raise RuntimeError("Must specify host (-H option).")

        logger.info("Starting %s test. Expected run time: %d seconds.",
                    settings.NAME, settings.TOTAL_LENGTH)

        self.agg = aggregators.new(settings)
        res = self.agg.postprocess(self.agg.aggregate(res))
        if self.killed:
            logger.debug("Killed while running, not writing data")
            return
        record_postrun_metadata(res, settings.EXTENDED_METADATA,
                                settings.REMOTE_METADATA)
        res.dump_dir(output_path)
        logger.log(loggers.INFO if print_datafile_loc else loggers.DEBUG,
                   "Data file written to %s", res.dump_filename)

        formatter = formatters.new(settings)
        formatter.format([res])

        self.tests_run += 1

    def load_input(self, settings):
        settings = settings.copy()
        results = []
        test_name = None
        for i, filename in enumerate(settings.INPUT):
            r = resultset.load(filename, settings.ABSOLUTE_TIME)
            if test_name is not None and test_name != r.meta("NAME") and \
               not settings.GUI:
                logger.warning("Result sets are not from the same "
                               "test (found %s/%s).",
                               test_name,
                               r.meta("NAME"))
            test_name = r.meta("NAME")
            if results and settings.CONCATENATE:
                results[0].concatenate(r)
            else:
                if len(settings.OVERRIDE_LABELS) > i:
                    r.set_label(settings.OVERRIDE_LABELS[i])
                results.append(r)

        settings.update(results[0].meta())
        settings.load_test(informational=True)

        # Look for missing data series, and if they are computed from other
        # values, try to compute them.
        for res in results:
            settings.compute_missing_results(res)

        formatter = formatters.new(settings)
        formatter.format(results)

    def fork_and_run(self, queue):
        pid = os.fork()
        if pid:
            return pid
        else:
            loggers.set_queue_handler(queue)
            signal.signal(signal.SIGTERM, self.kill)
            try:
                self.run()
            except Exception as e:
                logger.exception(str(e))
            queue.close()
            queue.join_thread()
            os._exit(0)

    def run(self):
        if self.settings.INPUT:
            return self.load_input(self.settings)
        elif self.settings.BATCH_NAMES:
            start_time = self.settings.TIME
            self.settings.BATCH_UUID = str(uuid.uuid4())
            self.settings.LOG_FILE = None  # batch run will generate logs
            logger.info("Started batch run %s at %s.",
                        self.settings.BATCH_UUID,
                        format_date(start_time, fmt="%Y-%m-%d %H:%M:%S"))

            if len(self.settings.BATCH_NAMES) == 1 and \
               self.settings.BATCH_NAMES[0] == 'ALL':
                logger.info("Running all batches.")
                batches = self.batches.keys()
            else:
                batches = self.settings.BATCH_NAMES
            runtimes = [self.get_batch_runtime(b) for b in batches]
            total_time, total_n = map(sum, zip(*runtimes))
            if total_time > 0:
                logger.info("Estimated total runtime: %s (%d tests)",
                            timedelta(seconds=total_time),
                            total_n)
            for b in batches:
                try:
                    logger.info("Running batch '%s'.", b)
                    self.run_batch(b)
                except RuntimeError:
                    raise
                except Exception as e:
                    if self.settings.DEBUG_ERROR:
                        raise
                    raise RuntimeError("Error while running batch '%s': %r."
                                       % (b, e))
            end_time = datetime.utcnow()
            logger.info("Ended batch sequence at %s. %s %d tests in %s.",
                        format_date(end_time, fmt="%Y-%m-%d %H:%M:%S"),
                        "Ran" if not self.settings.BATCH_DRY else 'Would have run',  # noqa: E501
                        self.tests_run,
                        (end_time - start_time))
            return True
        else:
            return self.run_test(self.settings, self.settings.DATA_DIR, True)

    def kill(self, *args):
        logger.debug("Killing child processes")
        self.killed = True
        self.kill_children(force=True)
        try:
            self.agg.kill_runners()
        except AttributeError:
            pass

    def p(self):
        for t in 'args', 'batches', 'commands':
            print("%s:\n%s\n" % (t, pprint.pformat(getattr(self, t))))


if __name__ == "__main__":
    br = BatchRunner({'data_filename': 'testing'})
    br.read(sys.argv[1])
    br.p()
    br.run_batch('tcpfair')
    pprint.pprint(br.commands_for("tcpfair", 'codel'))
