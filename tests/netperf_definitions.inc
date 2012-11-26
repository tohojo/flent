## -*- coding: utf-8 -*-

GLOBAL_COMMAND="netperf -P 0 -v 0 -D -%.1f" % STEP_SIZE
PING="ping"
if IP_VERSION == 4:
    GLOBAL_COMMAND += " -4"
elif IP_VERSION == 6:
    GLOBAL_COMMAND += " -6"
    PING="ping6"
AGGREGATOR='timeseries'
TOTAL_LENGTH=LENGTH+2*DELAY
