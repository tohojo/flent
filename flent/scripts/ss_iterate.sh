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

length=20
interval=0.1
host=localhost
filter=""

usage()
{
    echo "$0 -l length -I interval -H host -t target"
}

while getopts "l:I:H:t:p:f:" opt; do
    case $opt in
        l) length="$OPTARG" ;;
        I) interval="$OPTARG" ;;
        H) host="$OPTARG" ;;
        t) target="$OPTARG" ;;
        f) filter="$OPTARG" ;;
    esac
done

if [ -z "$target" ]
then
    usage
    exit 1
fi

command_string=$(cat <<EOF
endtime=\$(date -d "$length sec" +%s%N);
while (( \$(date +%s%N) <= \$endtime )); do
    ss -t -i -p -n state connected "dst $target $filter"
    echo ''
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
