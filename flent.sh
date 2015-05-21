#!/bin/sh

OURDIR=$(realpath $(dirname $0))

PYTHONPATH="$OURDIR:$PYTHONPATH" python -m flent "$@"
