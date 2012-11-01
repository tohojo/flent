#!/bin/bash

interface=eth0
count=10
interval=0.1
command=qdisc

while getopts "i:c:I:C:" opt; do
    case $opt in
        i) interface=$OPTARG ;;
        c) count=$OPTARG ;;
        I) interval=$OPTARG ;;
        C) command=$OPTARG ;;
    esac
done

for i in $(seq $count); do
    tc -s $command show dev $interface
    date '+Time: %s.%N'
    echo "---"
    sleep $interval
done
