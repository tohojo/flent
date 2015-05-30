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

The batch file format is based on the standard .ini file format, with
sections being split into three namespaces: Commands, starting with
Command::, batches, starting with Batch::, and arguments, starting with
Arg::. Briefly, a batch is the entity that will be run, commands can be
run before or after each batch iteration, and arguments allows
parameterising batches.

.. todo::

   Expand this section; for now, try looking at the :file:`batchfile.example`
   file supplied with the source code, and try to work things out from there :).

