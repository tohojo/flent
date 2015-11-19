#!/bin/bash

interface=eth0
count=10
interval=0.1
command=qdisc
host=localhost

while getopts "i:c:I:C:H:" opt; do
    case $opt in
        i) interface=$OPTARG ;;
        c) count=$OPTARG ;;
        I) interval=$OPTARG ;;
        C) command=$OPTARG ;;
        H) host=$OPTARG ;;
    esac
done

command_string=$(cat <<EOF
for i in \$(seq $count); do
    tc -s $command show dev $interface;
    date '+Time: %s.%N';
    echo "---";
    sleep $interval;
done
EOF
)

if [[ "$host" == "localhost" ]]; then
    eval $command_string
else
    echo $command_string | ssh $host bash
fi
