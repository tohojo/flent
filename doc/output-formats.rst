Output Formats
==============

The following output formats are currently supported by Flent:


Plot output (:option:`-f plot<-f>`)
-----------------------------------

Output test data as one of a series of graphical plots of timeseries data or
summarised as a CDF plot. Each test supplies a number of different plots; the
list of plots for a given test is output by the :option:`--list-plots` switch
(which must be supplied along with a test name).

The plots are drawn by matplotlib, and can be displayed on the screen
interactively (requires a graphical display), or output to a file in svg, pdf,
ps and png formats. Using the :option:`-o` switch turns out file output (the
file format is inferred from the file name), while not supplying the switch
turns on the interactive plot viewer.

Tabulated output (:option:`-f csv<-f>` and :option:`-f org_table<-f>`)
----------------------------------------------------------------------

These formats output the numeric data in a tabulated format to be consumed by
other applications. The *csv* output format is a comma-separated output that can
be imported into e.g. spreadsheets, while *org_table* outputs a tabulated output
in the table format supported by Emacs org mode. The data is output in text
format to standard output, or written to a file if invoked with the :option:`-o`
parameter.

Statistics output (:option:`-f stats<-f>`)
------------------------------------------

This output format outputs various statistics about the test data, such as total
bandwidth consumed, and various statistical measures (min/max/mean/median/std
dev/variance) for each data source specified in the relevant test (this can
include some data sources not includes on plots). The data is output in text
format to standard output, or written to a file if invoked with the :option:`-o`
parameter.

Metadata output (:option:`-f metadata<-f>`)
-------------------------------------------

This output format outputs the test metadata as pretty-printed JSON (also
suitable for human consumption). It is output as a list of objects, where each
object corresponds to the metadata of one test. Mostly useful for inspecting
metadata of stored data files.
