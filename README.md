netperf-wrapper
===============

Python wrapper to run multiple simultaneous netperf instances and aggregate the
results.

Basically provides a way to specify a set of netperf runs in a config file,
which are then run simultaneously. This can be done for multiple iterations, and
the results will be collected in a table suitable for import into Emacs Org
mode.

At the moment the script is relatively crude, and relies on the fact that
netperf (with the right invocation) outputs exactly one number as the result. It
works slightly better than a shell script for me, though. :)
