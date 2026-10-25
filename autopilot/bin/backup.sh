#!/bin/bash
# Code backup (no secrets): zips ~/autopilot/bin, ~/autopilot/kits and the four fonts the kit/hostcut/story scripts need (OFL) and PUTs it to the presigned URL given as $1.
# The vault pointer (~/secrets/connect.json) is backed up separately to Josh's Google Drive by the session.
set -e
cd ~
rm -f /tmp/autopilot-code.zip
zip -qr /tmp/autopilot-code.zip autopilot/bin autopilot/kits autopilot/requirements.txt autopilot/vendor/LICENSES.md byb/fonts/Anton-Regular.ttf byb/fonts/BebasNeue-Regular.ttf byb/fonts/ArchivoBlack-Regular.ttf byb/fonts/Poppins-Bold.ttf -x '*/__pycache__/*'
curl -sS -f -o /dev/null -w "%{http_code}\n" -X PUT -H "Content-Type: application/octet-stream" -H "If-None-Match: *" --data-binary @/tmp/autopilot-code.zip "$1"
rm -f /tmp/autopilot-code.zip
