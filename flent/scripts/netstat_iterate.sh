#!/bin/bash

count=10
interval=0.1
host=localhost

while getopts "c:I:H:" opt; do
    case $opt in
        c) count=$OPTARG ;;
        I) interval=$OPTARG ;;
        H) host=$OPTARG ;;
    esac
done

command_string=$(cat <<EOF
[ -e /proc/net/netstat ] || exit 1;
for i in \$(seq $count); do
    date '+Time: %s.%N';
    cat /proc/net/netstat;
    echo "---";
    sleep $interval || exit 1;
done
EOF
)

if [ "$host" == "localhost" ]; then
    eval $command_string
else
    echo $command_string | ssh $host sh
fi
