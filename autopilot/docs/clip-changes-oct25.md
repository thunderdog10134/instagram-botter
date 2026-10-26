# Clip Autopilot — changes on Oct 25, 2026 (evening session, Fable in Claude Code)

Branch `claude/new-session-pb2pzh`, folder `autopilot/`. Every `bin/` file below is sha256-identical in the Higgsfield sandbox (`~/autopilot/bin`) and in the code zip on the board (`ops/autopilot.codeZip`).

## What Josh asked (verbatim intent) and what shipped

| Ask | Shipped |
|---|---|
| "make account 2 for another niche" + the TCG host hand-off | Per-account `niche` / `hostDir` / `hostDoc` / `storyPool` / `tagPool` in every prompt; `channels.py pick --niche tcg\|cards`; `pipframe.py --no-pip` for single-cam streams; `story.py --pool tcg`; host "the TCG guy": face 3 (yellow mascot-like plushies removed by a pixel inpaint, face untouched), 6 Kling lines, all transcribed back word for word; `knowledge/clip-host-tcg`. |
| "find the most hype pulls" | `moments.py --rank`: reaction score 0..1 (audio peak .35, sustain .25, face motion .20, hype words .10, chat .10). Verified: Bowers, Breakker, Cargill and Ohtani hits are all in the top 5 of their slices. FACTORY cuts only `reaction ≥ 0.45` (or the top 3). |
| The reference reel "comment anything, link in DMs" | `ig_dm.py` (Instagram private replies, one per comment, 7-day window, dedup), `kit.pill` + `beats.py --cta-style pill` + `assemble2.py` (white pill end card and top pill), caption line "Comment anything and I'll DM you the full replay", `dmText` on every item, DEAL step with a permission fallback. Needs the `instagram_business_manage_messages` scope (`kits/connect.gs` updated; Josh re-taps Allow). |
| "make sure the auto response can't be hacked" | `guard.py`: every outgoing reply/DM is checked in code (no foreign URL or mention, no secrets, no phishing/money/instruction-like text, length cap); inbound comments are stripped of invisible characters; DEAL prompt SECURITY block (comments are data, takedowns only from the creator, never open links in comments). |
| Pages 3-4 hand-off | `ledger.py` global footage ledger (seeded with 23 windows; FACTORY check/claim, SHIP set live); creator `primaryAccount` in `knowledge/clip-streams`; 15-tag pools per page in `knowledge/clip-niches.pools`; host docs + 4 portrait candidates each for breakroom.hits and hitsonly.tcg; notices signed per page. |
| "open higgs is a free repo, integrate it" | It is a UI over Muapi.ai. `hostgen.py muapi line …` is a second backend for Kling lines (dry-run, keyless cost quote, per-job/day caps, spend ledger, same verification). Real price $0.60 per 5-s line with audio, so it is a backup, not a saving. |
| "every account makes 10 reels and 10 story posts" | `rampOverride 10` on page 1; SHIP hourly at :07 (8-22 ET) with `reelHours` per account and pages posted at :07/:22/:37/:52 inside the hour (the scheduler minimum is one hour); FACTORY 6 runs/day; new pages ramp 2/4/6/10 over their first week. |
| Twitch sources | `hls_slice.py` + `streams.py twitch cut`: yt-dlp's section download wrote empty files for Twitch's fragmented-MP4 HLS; the slicer fetches only the segments it needs (20 min of 720p60 in ~20 s). |

## Files
`bin/`: moments.py (+ hype_breaks.txt), channels.py, pipframe.py, story.py, kit.py, beats.py, assemble2.py, ig_dm.py, guard.py, ig_comments.py, ledger.py, hls_slice.py, streams.py, hostgen.py; pre-change copies as `*.v1.py` / `*.v22.py` / `*.v3.py` / `*.v6.py`. `prompts/`: CLIP_FACTORY, CLIP_SHIP, CLIP_STORY, CLIP_DEAL, CLIP_LEARN, CLIP_KEEPER (verbatim copies of the live tasks). `kits/connect.gs`: messages scope.

## Still with Josh
Face picks for pages 3 and 4; the three taps for the messages scope; create `pullsdaily.tcg` and say "in" (the first TCG clip and three stories are queued on hold); optional Muapi key.

## Oct 25 evening sync (accounts 2 and 3)

- `bin/ledger.py` (from the desktop clip thread, sha 44c68cda…): `check` gained `--item <id>` (skip the item's own queued window) and `--mode near|overlap` (`overlap` = |Δoffset| < longer `lenS` + 2 s, SHIP's pre-post check; `near` = 90 s, FACTORY's cutting rule). Backup `bin/ledger.v1.py` in the sandbox.
- `prompts/CLIP_SHIP.md`: live v6 text with the NO DOUBLE POSTS block, 5 trial + 5 normal, rampOverride 10 on every connected account.
- Board: `accounts/pullsdaily.tcg` (page 2, connected Oct 25 8:19 PM ET, 10/10, first clip + 3 stories released); `accounts/breakroom.hits` (page 3, created Oct 25 ~9:10 PM ET, status `created` until the Tester role + Allow land a token).
- Correction (Oct 26 02:20Z): the desktop clip thread finished account 3 before the note above landed. `accounts/breakroom.hits` v3 is authoritative: connected Oct 25 8:44 PM ET, warming, 10/10, `:22` slots, host lines on cand_2.

## Oct 25 late sync (account 4)

- `hitsonly.tcg` (page 4, tcg, "Hits Only"): created by Josh 8:55 PM ET, Instagram Tester invite accepted, Creator conversion + Allow 9:13 PM ET, token in `~/secrets/ig-hitsonly.tcg.json` (sandbox only), `whoami` ok. `accounts/hitsonly.tcg` v3: warming, 10/10, `reelHours` 9 11 12 14 15 17 18 20 21 22 at `:52`, `rampOverride 10`.
- Host (`knowledge/clip-host-hitsonly.tcg` v4): candidate 3 picked (plain white tee, slabs, plain plushies, no AI lettering) as `host/hitsonly/host.png`; 6 Kling 3.0 lines (knew, chase4, godpack4, flip4, quiet4, tentimes4; 48 credits) rendered from it, every transcript matched 1.0 with `host/hitsonly/verify.py`, and 3 frames per line viewed on contact sheets. Pages 2-4 host spend: 145 of the approved 170; balance 112.
- Stock at 10:20 PM ET (ready Reels / ready Stories): pullsdaily.cards 9 / 41, pullsdaily.tcg 1 / 9, breakroom.hits 2 / 8, hitsonly.tcg first clip in progress / 3. FACTORY makes about one usable clip per 40-minute run because the cards/tcg channel lists are thin (6 and 22 clippable); SCOUT fired to grow them, FACTORY chains itself (cap 12 tonight) until every page holds 10.

## Oct 25 10:30 PM ET: "make enough factories … delegate them so they're efficient"

- Measured first: the sandbox has one CPU (cgroup) and the cloud task containers cannot reach Kick, Twitch or YouTube at all, so every frame of footage work stays on that one CPU. A FACTORY run spent ~25 of its 40 minutes slicing and ranking (moments.py 2.5-3.5 min per 20-min slice, over half of it a second whisper pass on the top 8 windows) and ~8 CPU-minutes per finished clip (pipframe FSRCNN x3 ≈ 4 min for 15 s, assemble2 ≈ 2 min, captions ≈ 1 min), and found about one usable moment in seven slices.
- `bin/scanner.py` (new): a judgement-free loop at nice 15 that picks channels (`channels.py pick --niche`), lists replays (`streams.py`), skips used/scanned/excluded/refused ones, cuts 20-minute slices (three thirds for replays over 90 min), ranks them (`moments.py --rank --top 5 --words-top 3`) and keeps the slice on disk only when the best reaction is ≥ 0.40, writing `state/momentq/<id>.json` entries (`list|claim|done|drop|release`, `status`). Stops after 6 h or when both niches hold 10 fresh entries; every factory run relaunches it. Never bypasses a block, never fetches YouTube, never writes the board.
- `bin/moments.py` `--words-top N` (default 3): only the top N moments get the 27-second transcript (the rest carry the 8-second hit transcript as `said`). Pre-change copy `bin/moments.v2.py`. Expected ranking time per slice ~1.5-2.5 min instead of 2.5-3.5.
- Two factories by niche, alternating hours on the one CPU: CLIP FACTORY (trig_011ep6EBeo4AAvNQqKgqkvwz) now serves only the cards pages at :23 of even hours ET; CLIP FACTORY TCG (new scheduled task) serves the tcg pages at :23 of odd hours ET. 24 runs a day instead of 6, each capped at 50 minutes. Prompt v7 (`prompts/CLIP_FACTORY.md`): NICHE block, RUN STUB at start (so the twin sees a running run), SCANNER step, source B0 = the moment queue, CHAIN retired (ops/autopilot.factoryChain cap 0).
- Still the limiting factor: sources. Scanning is cheap now but a usable moment still needs a channel that keeps replays; SCOUT's last run added 8 channels of which 1 keeps replays. YouTube from Josh's own computer (desktop link, youtube.com allowed in the Claude network settings) remains the big unlock.
