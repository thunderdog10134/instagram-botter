#!/bin/bash
# putmany.sh <list>   lines: localpath|content-type|presigned-url   -> prints "<code> <path>"
while IFS='|' read p ct u; do [ -z "$p" ] && continue; c=$(curl -s -o /dev/null -w "%{http_code}" -X PUT -H "Content-Type: $ct" -H "If-None-Match: *" --data-binary @"$p" "$u"); echo "$c $p"; done < "$1"
