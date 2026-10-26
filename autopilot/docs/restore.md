# Restoring the sandbox

The scripts run in the Higgsfield sandbox (`mcp__Higgsfield__sandbox_exec`), the only place that reaches Meta,
Higgsfield uploads, Kick and Twitch. When a call answers `sandbox_created:true` everything is gone and must be
restored. The exact commands are in every task prompt's RESTORE CHECK; CLIP FACTORY's is the fullest.

1. `~/secrets/connect.json`: read the Google Doc whose id is `ops/autopilot.connectBackupDoc.driveFileId`
   (title "AgentCity-autopilot-connect.json v2"), unescape `\_` to `_`, write it with mode 600.
2. Code: `cd ~ && curl -fsSL -o /tmp/ap.zip <ops/autopilot.codeZip> && unzip -oq /tmp/ap.zip && bash ~/autopilot/bin/restore.sh <ops/autopilot.codeZip>`
   (restore.sh unzips `autopilot/bin`, `autopilot/kits`, `requirements.txt`, `vendor/LICENSES.md`, `byb/fonts`, then pulls the Instagram tokens from the vault with `connect_pull.py --all`).
3. Packages: `env -u PYTHONPATH python3 -m pip install -q --target /home/user/pylib -r ~/autopilot/requirements.txt`
   and `env -u PYTHONPATH python3 -m pip install -q --target /home/user/pylib_cv opencv-contrib-python-headless`
   (the FSRCNN upscaler in pipframe.py; without it pipframe falls back to a plain lanczos resize and says so).
4. Host files and v6 tools: `ops/autopilot.hostZip` (m1-m5.mp4, v1.png, host-point-cut.png, FSRCNN_x3.pb,
   channels.json, zoom_lib.py and copies of the v6 scripts). Unzip into `~/autopilot/host/`, move `FSRCNN_x3.pb`
   to `~/autopilot/ref/sr/`, `zoom_lib.py` to `~/autopilot/vendor/add-zooms/scripts/`, `channels.json` to
   `~/autopilot/state/`.
5. `~/byb/engine`, `~/camps/bin`: `ops/autopilot.engineZip` (old Whop lane engine; history only).
6. Vendored repos (`~/autopilot/vendor/clipify`, `add-zooms`, `cut-video`, `social-media-skills`, `superpowers`):
   not in the zips; re-clone from their upstreams (see `vendor/LICENSES.md`) if a step needs them
   (`captions.py` needs `clipify/scripts/build_ass.py`, `zooms.py` needs `add-zooms/scripts/zoom_lib.py`, which the host zip also carries).

Then run `test -f` on every script in `bin/` and `ig_publish.py --whoami pullsdaily.cards` to confirm the token works.
Log "restored" in the run record.

## Backups

`backup.sh <presigned PUT url>` zips `autopilot/bin`, `autopilot/kits`, `requirements.txt`, `vendor/LICENSES.md`
and the fonts and uploads it; CLIP KEEPER does this every Sunday and writes `ops/autopilot.codeZip` + `codeZipAt`.
This repository is the second copy: KEEPER's weekly step also commits `bin/` and the prompts here.
