## -*- coding: utf-8 -*-
##
## formatters.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     16 oktober 2012
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

import pprint, sys

class Formatter(object):

    def __init__(self, output, config):
        self.config = config
        if isinstance(output, basestring):
            if output == "-":
                self.output = sys.stdout
            else:
                self.output = open(output, "w")
        else:
            self.output = output

    def format(self, name, results):
        self.output.write(name+"\n")
        self.output.write(results+"\n")


class PprintFormatter(Formatter):

    def format(self, name, results):
        """Use the pprint pretty-printing module to just print out the contents of
        the results list."""

        self.output.write(name+"\n")
        pprint.pprint(results, self.output)

DefaultFormatter = PprintFormatter

class OrgTableFormatter(Formatter):
    """Format the output for an Org mode table. The formatter is pretty crude
    and does not align the table properly, but it should be sufficient to create
    something that Org mode can correctly realign."""

    def format(self, name, results):

        if not results:
            self.output.write(unicode(name) + u" -- empty\n")
        first_row = results[0][1]
        header_row = [name] + sorted(first_row.keys())
        self.output.write(u"| " + u" | ".join(header_row) + u" |\n")
        self.output.write(u"|-" + u"-+-".join([u"-"*len(i) for i in header_row]) + u"-|\n")
        for i,row in results:
            self.output.write(u"| %s | " % i)
            for c in header_row[1:]:
                if isinstance(row[c], float):
                    self.output.write(u"%.2f | " % row[c])
                else:
                    self.output.write(unicode(row[c]) + u" | ")
            self.output.write(u"\n")
