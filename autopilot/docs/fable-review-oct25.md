# Fable review, Oct 25 2026 (Claude Code session, 3:45 PM to late evening ET)

Tables and the full inventory: board doc `knowledge/review-oct25`. Build log: `ops/autopilot-build.notes[]` (12 new notes today, by "fable (claude code)").

## State in five lines

1. The page `@pullsdaily.cards` is on warming day 2 with 0 followers, 7 Reels live and 10 v6 Reels ready (12, 14-22); it posts 6 a day at 9:37, 11:37, 13:37, 15:37, 18:37 and 20:37 ET.
2. The first v6-quality Reel (Brock Bowers auto, Classic Pack Breaks, collaborator invite sent) went live at 15:37 ET; the first trial Reel attempt is the 20:37 ET post.
3. Every clip agent is on and ran today without an error row; the sandbox is intact and freshly backed up (code zip rebuilt, code now also in git).
4. Views are too thin to judge anything: 3 posts with 24-hour numbers (129, 149 and 6 views). At 4:36 PM ET the first v6 post (Bowers) had 20 views at 0.9 h, and the third use of the Breakker footage with the host had 120 views at 4 h, so the "re-posts get 0-5 views" rule from this morning is not holding either.
5. v2.2 of the beats format (Paper Crab additions) is built and previewed on warmq-31; it ships the moment Josh says "ship".

## What works

- All 9 clip tasks plus the Sync Relay are enabled on the right schedules (SHIP six slots, STORY ten, DEAL every 2 h, CLAIM 23:13, SCOUT 8:41, LEARN 21:37, KEEPER Sunday, FACTORY 10:23, Relay every 3 h UTC). Every last run succeeded.
- Dry-runs pass: `ig_publish.py --dry-run` with collaborators + SS_PERFORMANCE (quota 8/100), `ig_comments.py fetch` (0 comments), `channels.py report` (102 probed, 50 clippable) and `pick 4`, `janitor.py --dry-run` (nothing to free), `story.py make rate` (frame checked).
- Frames of three ready v6 Reels and five stories checked by eye: card readable, sticker and credit box inside the frame, PiP clear of the card, captions match the card, story text inside the safe zones.
- Host rotation over the last six items: no line repeats back to back.
- Security: no token on the board (the `AKfycb…` hits are the public Apps Script URL, which needs the key); `~/secrets/*` mode 600; the Drive backup of connect.json matches the sandbox copy; the connect page answers without a login; the Apps Script code md5 matches the board copy; the token expires Dec 24, far outside KEEPER's 10-day refresh rule.
- Sync Relay: 6 clean runs today, acks only after content events (no ping-pong), nothing from Ben's side executed; 2 test notices sit unhandled in `xinbox` (harmless).
- FACTORY timing: pipframe v6 measured at ~3 s per clip second (31 s for a 10 s clip), not 2 min per clip; the 15:24 run made 8 clips in 36 minutes, so 6 a day in one run is fine.

## What was broken

Fixed:
- Trial Reel fallback (ig_publish.py): a refusal only counted when Meta's error text contained the word "trial"; now any non-token error on a trial job makes the script post the same job once more as a normal Reel and report `trialRefused`; SHIP's prompt reads that field. (I could not find Meta's official refusal wording; third-party docs confirm the wording varies and that small pages are refused until eligible.)
- FACTORY prompt told the run to start 3-4 pipframes at once; the sandbox has one CPU, so that only risks the 15-minute background kill. Now one at a time, with the measured timing.
- Story `slowmo` template: the SLOW-MO pill sat on top of the clip's burned captions. The tag now rides on the credit line; the four slow-mo stories (s5, s14, s23, s32) were regenerated.
- CLIP LEARN skipped its Oct 25 slot (its cron was edited after the slot); it runs tonight at 21:37 ET. Nothing to change.

Not fixed (with the reason):
- Sold comps: eBay's sold search, 130point and sportscardspro all answer 403 or a bot check from the sandbox, and rule 3 forbids working around that. `comps.py` uses PriceCharting's public search instead, but its search did not surface the 2025 Topps Chrome / Heritage cards in the dry-runs (Ohtani /10, Bowers), so no price was written anywhere. A free eBay developer key would fix this; that sign-up is Josh's (J-ebay).
- Comment replies have never fired (0 comments on any post), so DEAL step 2b is verified only as far as the fetch. Rule 4 forbids me testing it with a comment of my own.
- The v6 quality fix is visible but small: side by side at the payoff of warmq-12, v6 is a little crisper on the jersey lettering and the signature; the 720p stream inset caps what super-resolution can do.
- KEEPER cannot push to GitHub: its scheduled session has no GitHub connector. Its prompt now pushes when the GitHub tools are present and otherwise says so in the digest.

## Risks

- 0 followers: Instagram will likely refuse trial Reels for weeks; SHIP falls back to a normal post, so no slot is lost.
- All ready stock but one clip is Honey Hole Breaks; rotation depends on FACTORY's channel pick tomorrow (10:23 ET) finding a second usable Kick channel; the registry's top-scored channels are Twitch with unknown replay resolution.
- Collaborator invites: 1 sent (Classic Pack Breaks), none accepted yet; propose dropping the invite for any creator who ignores 5.
- The sandbox is ephemeral; every restore path was checked (zips unzip, every script compiles, no secrets), and the code is now in git too.

## Repos

GitHub is connected to this session, scoped to `thunderdog10134/instagram-botter` only, so I used it rather than creating `pullshot-autopilot` (which this session may not create). Branch `claude/new-session-pb2pzh`, folder `autopilot/`: `bin/` (every script, byte-checked against the sandbox by sha256), `prompts/` (the nine agent prompts verbatim, SHIP and FACTORY as updated today), `kits/connect.gs`, `requirements.txt`, `vendor/LICENSES.md`, `docs/board.md`, `docs/restore.md`, `README.md`, this review. Host videos, the FSRCNN model and the vendored repos stay in the zips (no Git LFS set up). `ops/autopilot.repo/repoCommit/repoAt` point at commit e7ec3a9 (46 files byte-checked by sha256). The repo's old `main.py` is an unrelated "Instagram botter" script from 2023; it is left untouched and is not used by anything.

## Each island

- clip: alive (6 tasks ran today). Keep.
- amz, drop, land: last ran Oct 5-7, no scheduled task exists any more: archive (board docs only).
- etsy, printful: knowledge docs only, no runs, no task: archive. The one enabled stray is "Agent City · PAINTER (art in Gemini)", a fire-only task from the removed Etsy flow (last fired Oct 3): harmless; say "retire painter" and I disable it.
- lab/rnd, main (Director, ANALYST, WARDEN, ARCHITECT, LIBRARIAN), yt, ugc: every task disabled on Josh's side; Ben runs them. J-ben-pause is done with nothing left to pause.
- seo, walk, wl: never ran, no tasks: archive.

## Experiments proposed (knowledge/clip-experiments, nothing started)

1. v1+v6 vs v2.2 beats format, 12 posts each, median views and comments at 24 h decide; starts when Josh says "ship".
2. Trial vs normal Reel, 12 each; starts when Instagram accepts the first trial.
3. Host intro vs plain clip; only if the host arm stays under 50 views after 12 posts.

## Needs Josh (updated 5:00 PM ET)

Josh approved everything at about 4:55 PM ET. Done on that: v2.2 is live (every new clip is built with it; the Ruth preview is queued as warmq-31), SHIP sends 3 trial and 3 normal Reels a day (posts 2, 4, 6), stories stay at 10 a day (the first v2 story went live at 4:55 PM), and the price beat is built: a "LAST SOLD $X" plate with a cha-ching at the payoff. The plate only appears when a real sold comp exists, and no comp source is reachable yet, so:

- Comment "is she AI?" on the newest Reel (De7eoHMCkc8) from any account but the page, so the next DEAL run proves the auto-reply.
- eBay developer key (free, developer.ebay.com with agentcity1965@gmail.com), then say: **ebay key ready**.
- Turn off the stray PAINTER task yourself (claude.ai, scheduled tasks, "Agent City · PAINTER (art in Gemini)"): you approved it, but this session was not allowed to switch a task off.
- Add the GitHub connector to the CLIP KEEPER scheduled task so the weekly git sync runs.
- Still open from before: J2 (sign up pullsdaily.tcg), J-archive (archive the 4 superseded reels), J5 (Stripe key, only before the first paid block), J11 (Healthchecks.io).

Done without Josh today: J-ben-pause (all 14 agents were already off) and J-github (code is in instagram-botter).
