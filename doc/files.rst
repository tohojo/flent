Configuration files
===================

The RC file
-----------

Some of the command line options can be specified in an rc file. By default,
flent looks for this in :file:`~/.flentrc`, but an alternative location can be
specified with the :option:`--rcfile` command line option.

The rc file allows options to be specified globally, an optionally overridden
for specific tests. For an explanation of the options, refer to the annotated
example rc file, by default installed to
:file:`/usr/share/doc/flent/flentrc.example`.

Batch Files
-----------

Flent supports reading batch files to automate running several tests and
do setup/teardown of test environment etc. This greatly aids
reproducibility of tests.

The batch file is parsed as an ini file, and can have three types of sections:
batches, commands and args. Each section also has a name; type and name are
separated with two colons. 'Batches' are named tests that can be selected from
the command line, 'commands' are system commands to be run before or after each
test run, and 'args' are used in the looping mechanism (which allows repeating
tests multiple times with different parameters).

Variables in sections control the operation of Flent and can be modified in
several ways: Sections of the same type can inherit from each other and the
variables in an 'arg' section will be interpolated into the batch definition on
each iteration of a loop. In addition, variable contents can be substituted into
other variables by using the ${varname} syntax. These three operations are
resolved in this order (inheritance, arg interpolation and variable
substitution).

An annotated example batchfile is distributed with the source code, and is by
default installed to :file:`/usr/share/doc/flent/batchfile.example`.
