#!/bin/sh

OURDIR=$(realpath $(dirname $0))

PYTHONPATH="$OURDIR:$PYTHONPATH" "$OURDIR/bin/flent" "$@"
