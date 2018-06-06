#!/bin/bash

set -o nounset
set -o errexit

length=60
host=localhost
url=

while getopts "l:u:H:" opt; do
    case $opt in
        l) length="$OPTARG" ;;
        H) host="$OPTARG" ;;
        u) url="$OPTARG" ;;
        *) exit 1;;
    esac
done

if [ -z "$url" ] ; then
    echo "missing URL" >&2 ;
    exit 1
fi

command_string=$(cat <<EOF
BROWSER=\$(which chromium 2>/dev/null);
[ -n "\$BROWSER" ] || BROWSER=\$(which chromium-browser 2>/dev/null);

XVFB=\$(which xvfb-run 2>/dev/null);
[ -n "\$XVFB" -a -n "\$BROWSER" ] || exit 1;

set -o nounset;

DATA_DIR=\$(mktemp -d);

trap "rm -rf \"\$DATA_DIR\";" EXIT;

date '+Start time: %s.%N';
timeout $length env TMPDIR="\$DATA_DIR" \$XVFB \$BROWSER --no-sandbox --enable-logging=stderr --url "$url" --user-data-dir="\$DATA_DIR" --autoplay-policy=no-user-gesture-required;
EOF
)


if [[ "$host" == "localhost" ]]; then
    eval $command_string
else
    echo $command_string | ssh $host sh
fi
