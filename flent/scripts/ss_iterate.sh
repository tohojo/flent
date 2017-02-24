#!/bin/bash
#Copyright (C) 2016  Matthias Tafelmeier

#ss_iterate.sh is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.

#ss_iterate.sh is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with this program. If not, see <http://www.gnu.org/licenses/>.

count=10
interval=0.1
host=localhost
filter=""
surveil=""

usage()
{
    echo "$0 -c count -I interval -H host -t target -f filter"
}

while getopts "c:I:H:t:p:f:s:" opt; do
    case $opt in
        c) count="$OPTARG" ;;
        I) interval="$OPTARG" ;;
        H) host="$OPTARG" ;;
        t) target="$OPTARG" ;;
        f) filter="$OPTARG" ;;
        s) surveil="$OPTARG" ;;
    esac
done

if [ -z "$surveil" ] && ([ -z "$target" ] || [ -z "$filter" ])
then
    usage
    exit 1
fi

FILTER=""
if [ -z "$surveil" ]
then
    FILTER="dst $target $filter"
fi

command_string=$(cat <<EOF
for i in \$(seq $count); do
    ss -t -i -p -n state connected $FILTER
    date '+Time: %s.%N';
    echo "---";
    sleep $interval || exit 1;
done
EOF
)

if [[ "$host" == "localhost" ]]; then
    eval "$command_string"
else
    echo $command_string | ssh $host sh
fi
