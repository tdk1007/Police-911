# Police 24/7 (Police 911 / The Keisatsukan) — Research Dossier

Compiled from 7 parallel Sonnet research subagents, each with a non-overlapping charter and live web access. This is a compilation of what the web currently says, not a build plan or a recommendation. Confidence levels and sourcing are preserved from each agent's own findings; conflicts are reported, not resolved.

---

## Executive summary

The 8–12 most important compiled facts, across all agents:

1. **Konami's official PS2 camera accessory has a name and model number**: the **"Capture Eye," model RU035** — confirmed by psxdatacenter's peripheral listing for both the PAL (SLES-50285) and JP (SLPM-62097) SKUs. This wasn't in the original grounding facts and is a concrete anchor for hardware research.
2. **The Sony EyeToy is consistently reported as incompatible** with this title, across independent forum threads, the NeoGAF motion-controls retrospective, and general search synthesis — though one OCAU thread flags "conflicting reports" and leaves it formally unresolved.
3. **PCSX2's own compatibility wiki states outright**: Police 24/7 "requires a special Konami camera, EyeToy cameras will not work (though you can still play the game without a camera)." This is the emulator project's own documentation, not a fan claim.
4. **No first-hand evidence anywhere on the public web** — video, forum post, or GitHub issue — shows the camera-based duck/lean motion mechanic actually working under PCSX2 emulation (via real webcam or OBS Virtual Camera). This is the single biggest open gap for the larger project.
5. **The game does not use GunCon or GunCon 2 at all.** A PCSX2 GitHub feature request (#7889) states it is "the only PS2 game not compatible with Guncon 1 or 2." Real hardware instead wants a **Hyper Blaster / Justifier-protocol gun or a compatible "multi gun,"** per multiple forum accounts and the Sinden Lightgun wiki.
6. **Under PCSX2 today, aiming is done via the generic PS2 mouse-peripheral emulation** (relative motion), not any gun-specific protocol — there is no native PCSX2 support for the Hyperblaster/Justifier protocol (open, unimplemented feature request). A full playthrough exists on YouTube using PCSX2 1.7's "HID Mouse" USB device.
7. **A PCSX2 core maintainer (stenzek) explicitly closed an "absolute mouse" feature request** for the sibling Konami gun game Silent Scope, stating standard USB mice only report relative deltas — GunCon works because it natively reports absolute coordinates like a USB tablet. This is the technical root of the gun-input ambiguity for the whole Konami PS2 gun-game family, not just this title.
8. **OpenFIRE does not natively emulate the GunCon protocol either** — it outputs standard HID modes (5-button absolute mouse, gamepad, or keyboard). Its absolute-mouse HID mode is what's typically routed into PCSX2's GunCon2 config, but no source confirms OpenFIRE's output has been tested/validated specifically against this game or the Hyperblaster/mouse-controller input path it actually needs.
9. **The Insta360 Link 2C has no gimbal** (fixed FOV, 79.5° DFOV/67° HFOV) — all "AI tracking/Auto Framing" is digital crop, not mechanical. It enumerates as standard UVC/UAC on Linux, but the one community Linux control tool for this camera family (vrwallace/Insta360-Link-Controller) explicitly supports only the original Link and Link 2 (by USB VID:PID) — **not the Link 2C** — so it's unconfirmed whether AI-tracking can be disabled at all on Linux for this specific model.
10. **PAL vs JP camera behavior diverges at the software level, not just hardware**: one forum tester reports the JP Capture Eye camera works fine with the JP disc but is rejected entirely by the PAL disc (even at forced 60Hz), suggesting a region lock on the camera check baked into the PAL build — separate from the EyeToy-vs-Capture-Eye chipset question.
11. **Real, working tools exist today for streaming iPhone ARKit/LiDAR body-skeleton data to a PC over OSC/UDP** (TDLidar, LOTA, ZIG SIM), and one iOS app (VGamepad Lite) markets body tracking specifically as PC game-controller input — but no precedent was found of anyone routing this into a PS2 emulator specifically, and this whole avenue is flagged by its own researching agent as speculative/would-require-custom-glue-code.
12. **Two authoritative-looking real-hardware peripheral listings actively disagree**: psxdatacenter lists official peripherals as "Capture Eye camera / Mouse Controller" with light guns = "None," while the Sinden Lightgun wiki says the game "requires HyperBlaster/Multi Gun + Konami Capture Eye camera." These are not reconciled anywhere in the sources found.

---

## Agent 1 — Game & motion system

### Summary
- Arcade cabinet ran on Konami Viper hardware and used overhead motion-detection hardware to read body position for dodge/duck/lean, without a button — described as "infrared sensors" in most sources, though one conflicting source describes "two cameras on posts."
- The PS2 port replicates this via a USB webcam (Konami's own "Capture Eye Ru035") instead of the arcade's overhead sensor bar.
- Camera compatibility is narrow: Konami-recommended OmniVision (OV511/OV511+-class) cameras work; Sony's EyeToy is explicitly rejected; many nominally-same-chipset third-party webcams still fail in practice.
- One hands-on forum tester reports motion tracking as reactive and graduated (partial peeking around cover, not just binary), though this is a single testimonial.
- Game is fully playable without a camera, falling back to a Time-Crisis-style button (Square) for duck/cover; enemies keep firing during cover, so it isn't a safe-forever state.
- PAL (SLES-50285, 50Hz) and JP (SLPM-62097, 60Hz) differ in video timing and in mission order/tone (JP starts in Tokyo; PAL/US reverses to LA and swaps a newspaper-headline penalty for a rank deduction); one report of the JP camera being rejected specifically by the PAL disc.

### Key findings
- Arcade ran on Konami Viper hardware — confidence: Med — source: en.wikipedia.org/wiki/Police_911
- "The game uses infrared sensors to determine a player's location," enabling dodge/duck/lean — confidence: Med — source: en.wikipedia.org/wiki/Police_911
- Conflicting claim: "two cameras... mounted on high yellow posts" on the cabinet — confidence: Low, unverified, conflicts with IR-sensor claim — source: search synthesis (arcade-museum.com/giantbomb.com, not directly opened)
- A repeated "three infrared sensors (L, R, Center) on a bar overhead" claim traces to Grokipedia, which could not be fetched to verify — confidence: Low
- PSXDataCenter lists the official accessory as "Capture Eye Ru035" for both PAL and JP releases — confidence: High — sources: psxdatacenter.com SLES-50285 and SLPM-62097 pages
- Sony EyeToy explicitly NOT compatible with the PS2 port — confidence: High — sources: hokutonoshock.blogspot.com, assemblergames.org/viewtopic.php?t=35723
- Konami recommended an OmniVision-based camera (OV511/OV511+ bridge-chip class: Aiptek, Creative Labs, D-Link, Samsung, Trust, etc.) — confidence: Med — no single primary Konami document located
- Even chipset-matching third-party cameras often fail (a Creative Labs CT6840 owner got "USB camera not connected") — confidence: Med, single testimonial — source: assemblergames.org/viewtopic.php?t=35723
- One hands-on account: motion tracking "reacts perfectly," supports partial peeking, not binary — confidence: Med, single testimonial — source: forum.arcadecontrols.com/index.php?topic=161966.0
- Same account: JP Capture Eye camera worked with the JP disc but was rejected by the PAL disc even at forced 60Hz — confidence: Low-Med, single unreplicated tester — source: forum.arcadecontrols.com/index.php?topic=161966.0
- Game playable without a camera via Square-button cover, Time-Crisis style; firing while "in cover" still possible — confidence: Med — sources: PSXDataCenter control-scheme fields, backloggd.com/u/87th/review/541909
- PS2 port adds at least one camera-driven minigame: shooting balloons before they land — confidence: Med — source: en.wikipedia.org/wiki/Police_911
- Regional differences: JP starts in Tokyo; US/EU build reverses to start in LA, replaces newspaper-headline penalty with rank deduction — confidence: Med — source: en.wikipedia.org/wiki/Police_911
- Video mode: JP 60Hz vs PAL 50Hz only, no progressive/16:9 — confidence: High — PSXDataCenter
- PAL release date cited as both April 11, 2002 (PSXDataCenter) and April 19, 2002 (Wikipedia) — minor conflict

### Confirmed vs contested
- **Confirmed**: PS2 camera hardware is picky; EyeToy definitively doesn't work; game is fully playable camera-free; PAL/JP differ in TV format and mission-order/penalty design.
- **Contested**: Arcade sensing mechanism (IR sensors vs. cameras on posts) — no primary hardware source (manual/PCB/teardown) resolves this. Exact camera name — "Capture Eye Ru035" (PSXDataCenter, high confidence) vs. "Konami Magic Eye" (appears in some search-synthesis text but untraceable to a primary source — treat as likely incorrect). Exact PAL release date. Whether the PAL-disc camera rejection is a real region-lock or a single unreplicated anecdote.

### Open questions / gaps
- No primary source describes the arcade cabinet's actual sensor technology or its resolution/refresh behavior.
- No source quantifies motion-tracking forgiveness (lighting sensitivity, distance requirements, false-positive rates) from a primary source.
- Several likely-rich threads (PCSX2 wiki, AtariAge, GameFAQs, TVTropes, GiantBomb, Grokipedia) returned 403 and were only seen via search-engine synthesis — lower confidence than a direct read.
- No official Konami documentation confirming the OmniVision recommendation in Konami's own words.
- Only one PS2-exclusive camera minigame (balloon shooting) found; unclear if there are others.

### Best sources
- psxdatacenter.com SLES-50285 / SLPM-62097 — authoritative SKU-level specs (region, Hz, controller/camera model, release date).
- en.wikipedia.org/wiki/Police_911 (raw wikitext) — most complete single narrative on motion sensing and regional differences, though itself uncited.
- forum.arcadecontrols.com/index.php?topic=161966.0 — only detailed first-hand account of actual motion-tracking behavior.
- hokutonoshock.blogspot.com/2014/02/police-247... — most detailed compiled webcam-compatibility list.
- assemblergames.org/viewtopic.php?t=35723 — real-world evidence of camera compatibility unreliability.

---

## Agent 2 — PS2 camera compatibility

### Summary
- Konami's official PS2 accessory: **"Capture Eye," model RU035** — confirmed via psxdatacenter and eBay/collector listings.
- Multiple threads state the Sony EyeToy doesn't work; one poster's test suggests the block may be software/region-enforced rather than purely hardware, and the OCAU thread shows this isn't fully settled ("conflicting reports").
- A forum-relayed list (Spanish-language forum, relayed via ASSEMBLERgames) names ~15–18 third-party webcams claimed to share the Capture Eye's chipset — including an OmniVision OV51+/OV511-class unit plus Aiptek, Creative, D-Link, Samsung, Trust, Terratec, and others.
- Claims that the Creative WebCam Pro PD1030 also works are lower-confidence — not confirmed in any fetched primary source.
- No manual/box text or official Konami documentation was retrieved; all camera-list claims trace to enthusiast/collector forum posts.
- A documented case: the JP Capture Eye works with the JP disc on a PAL console (via homebrew loader) but fails with the PAL disc — pointing to software/region gating.

### Key findings
- Official accessory: "Capture Eye," RU035, sold boxed with camera/stand/manual/registration card — confidence: High — psxdatacenter.com/psx2/games2/SLES-50285.html, ebay.com/itm/303599648648
- PAL release (SLES-50285): 50Hz only, Multi-5 language menus, English voice, requires Capture Eye or a mouse controller — confidence: High — psxdatacenter
- Forum-relayed compatibility list names: Aiptek HyperVcam Home/Mobile, Amitech AWK-300, TEVion MD 9308, D-Link DU-C300/LVC100, Hawking Tech UC-110, Creative Labs WebCam3/WebCam Plus/CT6840, Samsung Anycam MPC-M10, Mtekvision Zeca MV402, MediaForte PC Vision 300, Terratec TerraCam Pro, OmniVision OV51+, Trust SpaceCam 200/300, Lifetec LT 9388, BestBuy EasyCam U, TCE NetCam 310u, Medion MD9388, Webeye 200B — confidence: Med (several steps removed from a primary source) — assemblergames.org/viewtopic.php?t=35723
- One forum tester's Creative CT6840 (on the "compatible" list) still failed with "USB camera not connected"; EyeToy also failed for them — confidence: Med — same source
- NeoGAF: game used "a custom designed webcam that would real time identify your bodies position"; one commenter: "the PS2 EyeToy (which Police 911 doesn't use)" — confidence: Med — neogaf.com thread on Police 911 motion controls
- arcadecontrols.com: JP Capture Eye worked with JP disc (via FMCB homebrew on PAL console) but "still not detected" with the PAL disc even at forced 60Hz — confidence: Med — forum.arcadecontrols.com/index.php?topic=161966.0
- OCAU thread: poster owns "3 models of the eyetoy," notes "conflicting reports that the eyetoy will work with this game," unverified claim it "reportedly worked with other older webcams including some from Logitech"; also frames the original camera as predating and influencing EyeToy design — confidence: Low, thread ends unresolved — forums.overclockers.com.au/threads/police-24-7-on-ps2-camera-help.607408
- OmniVision OV511/OV511+ bridge chip (paired with OV6620/OV6630/OV7610/OV7620 sensors) was a widely-used late-90s/early-2000s USB webcam chipset family with an open Linux driver project cataloging compatible models — general chipset background, not game-specific confirmation — confidence: High (chipset facts), Low (relevance beyond one list entry) — ovcam.org/ov511/cameras.html

### Confirmed vs contested
- **Confirmed**: Konami sold a proprietary "Capture Eye" (RU035) camera for this game. EyeToy is reported not to work, independently, across multiple threads.
- **Contested**: Whether EyeToy *ever* works (OCAU thread flags explicit conflicting reports). PD1030 substitute claim (surfaces in search synthesis, not confirmed in a primary source). Whether non-detection is a hardware/chipset mismatch (CT6840 case) vs. a software/region check (JP-camera-on-PAL-disc case) — these look like two different failure modes, not resolved against each other. Exact "Konami recommended OmniVision" wording — no primary Konami-authored source located.

### Open questions / gaps
- No manual/box-text scan located confirming Konami's exact recommended camera/chipset in their own words.
- Original "Spanish forum" list source not tracked down directly — only known via the ASSEMBLERgames relay.
- No technical explanation found for *why* EyeToy fails (frame rate/resolution/USB descriptor check/driver lock) — sources assert incompatibility without mechanism.
- Several likely-relevant threads (AtariAge, PCSX2 wiki, GameFAQs) returned 403 and weren't directly accessible.
- PD1030 and "Logitech" claims remain unconfirmed.

### Best sources
- psxdatacenter.com/psx2/games2/SLES-50285.html — catalog reference naming the required Capture Eye (RU035) and specs.
- assemblergames.org/viewtopic.php?t=35723 — most detailed compatibility list plus a documented real-world failure case.
- forum.arcadecontrols.com/index.php?topic=161966.0 — only source with a controlled JP-camera/PAL-disc test.
- neogaf.com Police 911 motion-controls thread — clearest statement that the game doesn't use EyeToy.
- ovcam.org/ov511/cameras.html — authoritative reference on the OmniVision OV511/OV511+ chipset family.

---

## Agent 3 — Light gun / gun protocol

### Summary
- Consistently reported as **not compatible with GunCon or GunCon 2** — multiple independent sources agree.
- Real PS2 hardware instead wants the older **Justifier/Hyper Blaster protocol** (Konami's PS1-era controller-port-only gun) or a compatible third-party "multi gun."
- **PCSX2 has no native Hyperblaster-protocol emulation** (an open 2023 GitHub feature request is unimplemented); players instead drive the crosshair via PCSX2's generic PS2 mouse-peripheral emulation, which is imprecise (relative-motion drag/shakiness).
- Silent Scope (a different Konami PS2 gun series) shows the same pattern: Konami gun, not GunCon; same mouse-emulation fallback and jitter issues.
- A PCSX2 core maintainer (stenzek) explicitly closed an "absolute mouse" request as not feasible as requested — standard USB mice only report relative deltas; GunCon avoids this because it natively reports absolute coordinates like a USB tablet.
- psxdatacenter complicates the picture: it lists official peripherals as "Capture Eye camera / Mouse Controller" and states no official light gun is compatible — possibly implying a PS2-native "Mouse Controller" peripheral (not a gun protocol at all) is the sanctioned input, which doesn't fully square with the Hyperblaster/multi-gun forum reports.

### Key findings
- "This would make the game Police 24/7 ak Police 911 playable as its the only ps2 game not compatible with Guncon 1 or 2." — confidence: High — github.com/PCSX2/pcsx2/issues/7889 (opened 2023-01-14, still open)
- Sinden Lightgun wiki: Police 24/7 listed as non-working, "Requires HyperBlaster/Multi Gun and Konami Capture Eye camera" — confidence: High — sindenwiki.org/wiki/PCSX2
- Forum poster (2008, arcadecontrols): "You cant use a G con. You either need a hyperblaster or a multi gun" — confidence: Med
- Another poster reports several "multi guns" "all work pretty well" on real PS2 hardware; 4gamers brand recommended — confidence: Med — same thread
- Conflicting real-hardware report: a poster "gotten the game to work with a generic PS1/PS2 lightgun," with GunCon 1 possibly compatible but unconfirmed — confidence: Low — assemblergames.org/viewtopic.php?t=35723
- psxdatacenter (SLES-50285): peripherals = "USB Camera - Capture Eye (Ru035) / Mouse Controller"; no official light gun compatible — confidence: Med
- Silent Scope: "Guncon is not working for this game, it's Konami gun" — confidence: High — github.com/PCSX2/pcsx2/issues/10863 (nixxou, 2024-02-27)
- PCSX2 maintainer stenzek: "USB mouse doesn't provide absolute coordinates to begin with — the HID packets are relative"; "GunCon doesn't have this issue, because it reports absolute coordinates... like USB tablets" — confidence: High, direct quote — github.com/PCSX2/pcsx2/issues/10863#issuecomment-1966180239
- Real PS2 Silent Scope owners only got a mouse-driven version, unlike Xbox's bundled rifle peripheral — confidence: Med
- "Mouse works in PCSX2 Nightly for playing Police 24/7"; Wiimote-as-mouse produces an "unstable" crosshair — confidence: Med — forums.pcsx2.net thread, emuline.org video mirror
- Konami's Hyper Blaster/Justifier connects only to a controller port (no video-sync cable), unlike GunCon which also needs the video-out port for CRT-timing aiming — confidence: High — en.wikipedia.org/wiki/GunCon
- "Certain third-party light guns were also produced that support switching between Hyper Blaster and GunCon modes" (no specific models named) — confidence: Med — en.wikipedia.org/wiki/GunCon
- No evidence found of a pack-in/bundled gun for the PAL retail release — confidence: Low/gap

### Confirmed vs contested
- **Confirmed** (multiple independent sources): No GunCon/GunCon2 compatibility. No native PCSX2 Hyperblaster/Justifier emulation — mouse-peripheral emulation is the current PC path, and it's imprecise. Silent Scope shares the "Konami gun, not GunCon" trait, and the PCSX2 team has declined absolute-mouse support because standard HID mice can't report absolute position.
- **Contested**: What real-hardware peripheral the game actually needs. GitHub issue + Sinden wiki + one arcadecontrols poster say Hyper Blaster/multi-gun (Justifier-protocol). Another arcadecontrols poster reports success with a generic PS1/PS2 lightgun and flags GunCon 1 as possibly working (unconfirmed). psxdatacenter instead names a "Mouse Controller" as the official non-camera peripheral and says no official gun is compatible at all — three framings, not reconciled by any source.

### Open questions / gaps
- No primary source (manual/box scan/Konami documentation) states the exact protocol Police 24/7's code reads for gun input.
- No specific third-party "multi gun" model/part numbers beyond a vague "4gamers" brand mention.
- No evidence of a bundled gun for the PAL retail release.
- Whether psxdatacenter's "Mouse Controller" means the Sony PS2 Mouse (SCPH-10160) or a generic term for something else is unconfirmed — related PCSX2 forum threads returned 403.
- PCSX2's GunCon2 input-plugin implementation wasn't independently verified against source code, only inferred from a maintainer comment.

### Best sources
- github.com/PCSX2/pcsx2/issues/7889 — primary tracked request naming the game as the GunCon-incompatible outlier.
- github.com/PCSX2/pcsx2/issues/10863 — direct maintainer explanation of why absolute-mouse/GunCon-style input can't be trivially emulated for Konami gun games.
- sindenwiki.org/wiki/PCSX2 — maintained compatibility list from a commercial lightgun vendor, explicit on required hardware.
- forum.arcadecontrols.com/index.php?topic=161966.0 — real-hardware, first-person accounts running the game with various guns.
- psxdatacenter.com/psx2/games2/SLES-50285.html — structured peripheral-compatibility field, though it conflicts with other sources (ideally re-verify by direct view, as WebFetch access was anti-bot-blocked).

---

## Agent 4 — Emulation reality (PCSX2 & alternatives)

### Summary
- PCSX2 (1.7+ through current 2.6.3 stable / 2.7.x nightly, fully monolithic) has a native "Webcam (EyeToy)" USB device slot: Settings → Controllers → USB → port → "Webcam (EyeToy)" → select camera/virtual device. Stock, documented feature.
- The PCSX2 wiki page for Police 24/7 explicitly states it **requires a special Konami camera and Sony EyeToy cameras will not work** (though playable without a camera) — a game-side lockout, not a PCSX2 limitation.
- Police 24/7 is documented (GitHub issue #7889) as **the one PS2 game incompatible with GunCon 1/2**; psxdatacenter lists official peripherals as "Capture Eye (Ru035)" camera + "Mouse Controller," with official light guns = "None."
- First-hand evidence exists that the *shooting* half runs under PCSX2 1.7 via the "HID Mouse" USB device (a full playthrough video; a comment confirms the same trick works for Silent Scope). **No first-hand evidence found of the camera/motion (duck-and-lean) mechanic working under any PCSX2 configuration** — this gap remains unfilled by the public web.
- Mirrors a better-documented parallel case: PCSX2 issue #10863 confirms Silent Scope also can't use GunCon and needs absolute-mouse support PCSX2 currently lacks (only relative mouse implemented); closed as "not planned."
- On real hardware, the JP Capture Eye reportedly works with the JP disc but not the PAL disc even after 50/60Hz and IRX-swap workarounds — suggesting the PAL lockout is a software gate, mirroring Agent 1/2's finding.

### Key findings
- PCSX2 has a built-in "Webcam (EyeToy)" USB device selectable per port, feeding any connected/virtual camera — confidence: High — wiki.pcsx2.net/Police_24/7 (via cache), retrodeck.readthedocs.io eyetoy docs
- PCSX2 wiki: "requires a special Konami camera, EyeToy cameras will not work (though you can still play the game without a camera)" — confidence: High — wiki.pcsx2.net/Police_24/7
- Police 24/7 is "the only PS2 game not compatible with Guncon 1 or 2" per an open feature request for generic PS2 lightgun support — confidence: High — github.com/PCSX2/pcsx2/issues/7889
- psxdatacenter: camera = "Capture Eye (Ru035)"; light guns = "None"; also lists "Mouse Controller" support — confidence: High
- A full playthrough was recorded using PCSX2 1.7 with USB port set to "Hid mouse"; a commenter confirms the same trick works for Silent Scope — confidence: Med, secondhand video description — emuline.org/video/284-police-247-ps2-full-playthrough-mouse-support-pcsx2-17 (original youtube.com/watch?v=Dbr62h36EV0, not independently fetchable)
- No web evidence found of the camera-based duck/lean mechanic working under PCSX2, via real webcam or OBS Virtual Camera — confidence: High (absence, not proof of impossibility)
- Silent Scope (issue #10863) needs absolute mouse because "Guncon is not working for this game" and relative mouse just drags the cursor; closed "not planned" — confidence: High
- Sinden Lightgun wiki lists Police 24/7 as "Non working," "Requires HyperBlaster/Multi Gun and Konami Capture Eye camera" — confidence: High
- JP camera works with JP disc but not PAL disc on real hardware, per a single tester who concluded it's coded into the PAL build — confidence: Med, single account
- Older PCSX2 EyeToy bug (#3921, 2020, fixed by PR #3922) shows EyeToy support has had real regressions (Windows wide-string bug causing "no video") — confidence: High
- A 2015 PCSX2 tracking issue (#525) cataloging games needing USB Guitar/EyeToy/Mic support does **not** list Police 24/7 or Police 911 — confidence: Med (may simply predate/omit it)

### Confirmed vs contested
- **Confirmed**: PCSX2 has a native EyeToy/webcam USB device slot and native GunCon2 support; the game rejects GunCon and uses a "Mouse Controller" input mode instead; a full-game mouse-based playthrough under PCSX2 1.7 is documented; there's an open, unresolved PCSX2 request for absolute-mouse/generic-lightgun support partly driven by this game family.
- **Contested**: What hardware the real game demands — psxdatacenter says camera "Capture Eye (Ru035)" + light guns "None" (implying mouse-controller mode is sanctioned); Sinden wiki says it "Requires HyperBlaster/Multi Gun + Konami Capture Eye camera" (implying a dedicated gun peripheral is mandatory). These do not agree. Also unresolved: whether the PAL camera lockout is a genuine software region-check or an unreplicated anecdote.

### Open questions / gaps
- No first-hand evidence anywhere that the motion-sensing duck/lean mechanic runs at all under PCSX2, with a real webcam or OBS Virtual Camera — genuinely untested/unreported territory.
- No GitHub issue threads together "Police 24/7" + "EyeToy device" + repro steps — the webcam-device and lightgun/mouse-device discussions never intersect for this title.
- Unclear whether PCSX2's "Webcam (EyeToy)" device even attempts to emulate the game-specific motion-tracking protocol, or just passes raw frames the game's driver then rejects (consistent with the wiki's flat "EyeToy cameras will not work" line reading like a driver-level/protocol mismatch, not image quality).
- The two seed YouTube URLs could not be read directly (fetch returned only nav/footer boilerplate) — content unverified from this pass.

### Best sources
- github.com/PCSX2/pcsx2/issues/7889 — official repo, names Police 24/7 as the GunCon-incompatible outlier.
- psxdatacenter.com/psx2/games2/SLES-50285.html — long-standing peripheral database, most authoritative real-hardware listing found.
- github.com/PCSX2/pcsx2/issues/10863 — ties the "needs absolute mouse" problem to Konami's gun-game family directly.
- sindenwiki.org/wiki/PCSX2 — detailed compatibility table flagging required real hardware.
- wiki.pcsx2.net/Police_24/7 — canonical PCSX2 compatibility wiki entry (reachable only via search cache; direct fetch 403).

---

## Agent 5 — OpenFIRE light gun system

### Summary
- OpenFIRE is a free/open-source RP2040 (and now RP2350) light-gun firmware + companion "OpenFIRE App" (Qt/C++, Win/Linux/RPi), maintained by TeamOpenFIRE — successor to Samuel Ballantyne's SAMCO project and Prow7's fork, refined by "That One Seong."
- **It does not natively emulate the GunCon USB protocol.** It presents as standard HID in one of several modes: 5-button absolute mouse, dual-stick gamepad (camera mappable to either stick, with d-pad), or keyboard. PCSX2's GunCon2 config accepts absolute-pointer/mouse input, so OpenFIRE's mouse mode is what feeds GunCon2 indirectly. True GunCon *hardware protocol* emulation is instead done by companies selling GunCon-shell conversion kits (e.g. SAMCO) with OpenFIRE-class firmware inside an original gun housing.
- Supports two IR-emitter geometries per profile: recommended "double lightbar" (2+2 LEDs, effectively a rectangle) and a single 4-LED "diamond" (Xwiigun-compatible). Recommended LEDs: SFH 4547 with 5.6Ω resistors, tracked by a DFRobot SEN0158 IR positioning camera with real-time perspective-adjusted tracking.
- Calibration via the OpenFIRE Desktop App's interactive fullscreen UI plus an "IR Emitter Alignment Assistant"; profiles/button maps/hardware settings stored on-device (LittleFS), switchable on the fly.
- Force feedback well supported: 12/24V solenoids and 5V rumble motors, temperature-sensor safety cutoffs, compatible with MAMEHOOKER, "The Hook of the Reaper," QMamehook.
- Connectivity: primarily USB (TinyUSB, reportedly 8kHz polling); Bluetooth only in beta on Pico W with known TinyUSB/Serial conflicts; a separate community ESP32-S3 port adds low-latency ESP-NOW wireless.

### Key findings
- HID output modes: Mouse & Keyboard, or Gamepad (camera→stick, d-pad) — confidence: High — github.com/TeamOpenFIRE/OpenFIRE-Firmware/releases
- No native GunCon/Konami protocol emulation documented; absolute-mouse HID is what's typically routed into PCSX2's GunCon2 pointer input — confidence: Med — github.com/TeamOpenFIRE/OpenFIRE-Firmware, forums.pcsx2.net/Thread-Playing-lightgun-games-with-a-mouse
- Physical GunCon 1/2 shell conversions (SAMCO-branded, "PiCON") exist, being updated to use OpenFIRE internals — confidence: Med
- Dual IR layouts: recommended double lightbar (rectangle) and diamond (Xwiigun-style), per-profile — confidence: High
- Recommended parts: SFH 4547 LEDs + 5.6Ω resistors; DFRobot SEN0158 IR positioning camera — confidence: High — osrtos.com project writeup
- Real-time perspective-adjusted tracking keeps aim accurate off-axis — confidence: High
- Calibration via OpenFIRE App's fullscreen UI + IR Emitter Alignment Assistant; profiles stored on-device — confidence: High
- MiSTer FPGA integration: automatic gamepad-compatible mode, dedicated F10-menu calibration aimed at game-image borders — confidence: High
- Force feedback: 12/24V solenoid + 5V rumble, temperature-cutoffs, MAMEHOOKER/Hook-of-the-Reaper/QMamehook compatible — confidence: High
- USB via TinyUSB, ~8kHz polling; Bluetooth beta-only on Pico W with a known init bug when BT enabled — confidence: Med-High
- Community ESP32-S3 port adds ESP-NOW wireless as an alternative — confidence: Med
- Latest firmware as of this research: v6.2 "Long Bridge" (2026-04-19), v6.1 "Little Angel" (2026-01-02), v6.0 "White Valkyrja" (2025-05-24, major breaking overhaul requiring App v3.0+) — confidence: High
- PCSX2's own GunCon2 config requires "Acquire" + calibration, reload modes Manual/Semi — confidence: High

### Confirmed vs contested
- **Confirmed**: OpenFIRE outputs HID mouse/keyboard/gamepad, not a proprietary GunCon HID class (multiple independent sources agree). Dual IR layouts. Solenoid + rumble FFB and MAMEHOOKER-family compatibility.
- **Contested/unclear**: Exact recommended emitter spacing/distance-from-screen numbers — official docs describe layout types but are explicitly marked "work in progress," with only anecdotal forum numbers found (e.g. "2.5ft from a 37" screen"). Whether "GunCon-style emulation" is a fair characterization at all — one framing (PCSX2 forums) treats absolute-mouse HID guns as functionally interchangeable with GunCon2 input; another (SAMCO/PiCON) implies true GunCon emulation needs a physical shell/board conversion. Sources don't reconcile these.

### Open questions / gaps
- No official numeric IR-emitter placement spec (LED spacing, min/max screen distance, recommended screen-size range) found on openfirelightgun.org — both firmware and app pages are marked "work in progress."
- No direct confirmation OpenFIRE's absolute-mouse mode has been validated against Konami PS2 titles specifically (e.g. the Hyperblaster/mouse-controller path this game actually needs) — no vendor/community doc discusses Konami PS2 lightgun titles at all.
- Bluetooth is explicitly beta/buggy on Pico W; unclear if resolved in recent v6.x releases, or whether the ESP32 fork is the recommended wireless path.
- No detailed calibration walkthrough found for OpenFIRE itself (page unfinished); the most concrete walkthrough found was for a competing platform (Gun4IR) — don't assume parity.

### Best sources
- github.com/TeamOpenFIRE/OpenFIRE-Firmware — primary README: features, HID modes, IR layouts, FFB, USB/Bluetooth caveats.
- github.com/TeamOpenFIRE/OpenFIRE-Firmware/releases — versioned changelog with HID-mode and MiSTer-integration detail.
- github.com/TeamOpenFIRE/OpenFIRE-App — calibration UI and IR Emitter Alignment Assistant.
- osrtos.com/projects/openfire-the-open-four-infa-red-emitter-light-gun-system — most complete single-page technical summary.
- openfirelightgun.org — official project site (docs marked WIP, authoritative for project identity/links).

---

## Agent 6 — Insta360 Link 2C (target webcam)

### Summary
- **Fixed-position webcam** — no gimbal, no mechanical pan/tilt/zoom (this is the key difference from the Link 2, which has a 2-axis gimbal). All "tracking" is digital zoom/crop within a fixed 79.5° DFOV / 67° HFOV sensor image.
- Core specs: 1/2" sensor, up to 3840×2160@30fps / 1920×1080@60fps / 1280×720@60fps, f/1.8, 26mm (35mm-equiv), USB-C (USB 2.0, 480 Mbps per secondary sources), H.264 + MJPEG, dual mics with AI noise modes.
- Appears as a standard **UVC/UAC device on Linux** — basic video/audio streaming works without drivers, but Insta360's Link Controller app (which exposes AI Tracking/Auto Framing toggles) is Windows/Mac only.
- On Windows/Mac, Auto Framing and AI/gesture tracking toggle off via the Link Controller UI or a physical touch-key/palm gesture; a "Pause-Track Area" feature can lock framing to a defined region.
- On Linux, an open-source community controller (vrwallace/Insta360-Link-1-and-2-Controller-for-Linux) uses UVC Extension Unit ioctl calls for pan/tilt/zoom/exposure/AI-tracking control — but **explicitly only lists support for "Insta360 Link" and "Insta360 Link 2" (VID:PID 2E1A:4C01 / 2E1A:4C04), with no mention of the Link 2C.** Since the 2C has no gimbal, most of that tool's pan/tilt logic likely doesn't apply anyway; whether its AI-tracking-disable commands work on the 2C is unconfirmed.
- Reviewers frame the 2C as the "fixed-frame, no-robotics" sibling of the Link 2, supporting its viability as a plain fixed webcam — but no source specifically confirms it was tested as a "dumb" camera for non-Insta360 software.

### Key findings
- Sensor: 1/2" ("Sony Starlight" per one reseller listing, not confirmed on Insta360's own page) — confidence: Med
- Resolutions/framerates: 3840×2160@30, 1920×1080@60, 1280×720@60 — confidence: Med — microcenter.com listing (official spec page didn't render full table via fetch)
- FOV: 79.5° DFOV, 67° HFOV; 26mm equiv; f/1.8 — confidence: High — onlinemanual.insta360.com/link2/en-us/faq/specs/shooting
- Dimensions 62.7×30.2×26mm, 46.5g (111.5g with magnetic mount); confirmed no gimbal (Link 2 has ±141° yaw/±90° pitch) — confidence: High — onlinemanual.insta360.com/link2c/en-us/specs/hardware
- USB: USB-C, USB 2.0, 480 Mbps — confidence: Med, derived from search synthesis, not verified on a single primary page
- Codecs: H.264 + MJPEG; "4K and 1080p@60fps Portrait Mode do not support H.264"; YUV via virtual camera or "Low Resolution" mode in Link Controller — confidence: Med-High
- 8-bit color, HDR supported — confidence: Med
- Dual mics (omni + directional), beamforming, 3 AI audio modes; mic independently selectable as a separate UAC device — confidence: Med
- Auto Framing toggle in Link Controller's control bar, or via palm gesture (green flash = recognized) — confidence: High (via search synthesis; direct fetch blocked by client-side rendering)
- AI Tracking has a separate toggle in Link Controller / touch-key on the unit — confidence: Med
- "Pause-Track Area" feature locks framing to a defined region — confidence: Med
- Insta360 Link family shows up as standard UVC on Linux exposing V4L2 controls (brightness/contrast/pan/tilt/zoom/focus/exposure) — confidence: Med — github.com/vrwallace/Insta360-Link-1-and-2-Controller-for-Linux
- That Linux tool explicitly supports only VID:PID 2E1A:4C01 (Link) and 2E1A:4C04 (Link 2) — no Link 2C PID listed — confidence: High (absence confirmed by direct repo read)
- That tool disables AI Tracking via UVC Extension Unit commands; known-unsupported-on-Linux: tracking-target selection, HDR, gesture control, privacy mode, portrait mode — confidence: Med
- Reviewers (PC Gamer, Tom's Guide, TechRadar) describe the 2C as intentionally "fixed position, no robotic movement" — confidence: Med, relied on search-result summaries after a second fetch attempt failed

### Confirmed vs contested
- **Confirmed**: No physical gimbal on Link 2C; FOV 79.5°/67°; USB-C; H.264+MJPEG; standard UVC/UAC enumeration. Community Linux controller exists but does not list Link 2C support at all — a real gap, not just thin documentation.
- **Contested**: Whether "USB 2.0 at 480 Mbps" is an Insta360-stated spec or an inference/aggregator claim — could not verify verbatim on an Insta360-owned page (fetches of onlinemanual.insta360.com repeatedly returned only header/nav due to client-side rendering). Whether the 2C has a "Starlight" sensor designation (appeared only on a reseller page).

### Open questions / gaps
- No confirmation the community Linux UVC controller's AI-Tracking-disable commands work against the Link 2C's actual firmware/PID — needs empirical verification (`lsusb` for VID:PID, then test whether the tool's UVC XU calls are accepted).
- No official statement on default AI/Auto-Framing state at first boot on Linux — unresolved whether Auto Framing runs on-camera (firmware-side) or is purely a Link Controller software layer on top of a full-FOV UVC stream. This matters directly for the project's "lock the frame" requirement.
- Could not retrieve the full official resolution/framerate table directly from Insta360 (JS-rendered pages returned only nav chrome); framerate table above sourced from a reseller, not insta360.com directly.
- No data on digital zoom range/factor during Auto Framing, or latency/quality impact when disabled vs enabled.
- No confirmation of the Link 2C's exact USB PID for Linux enumeration.

### Best sources
- onlinemanual.insta360.com/link2c/en-us/specs/hardware — official manual, confirms no-gimbal design, dimensions/weight.
- onlinemanual.insta360.com/link2/en-us/faq/specs/shooting — official manual, FOV/focal-length/codec details shared across Link 2/2C.
- github.com/vrwallace/Insta360-Link-1-and-2-Controller-for-Linux — primary source for actual Linux/UVC control mechanics and explicit PID support statement.
- pcgamer.com/hardware/webcams/insta360-link-2c-review, techradar.com/computing/webcams/insta360-link-2c-review — independent reviews characterizing the fixed-frame design.

---

## Agent 7 — iPhone LiDAR/ARKit body pose as input (speculative)

### Summary
- Real, working tools exist for streaming iPhone ARKit body-skeleton data to a PC over OSC/UDP on a local network — this part is well-documented, not speculative.
- The most direct precedent for the project's actual goal (body motion controlling a game/emulator) is an app called **VGamepad Lite**, which advertises "AR Body Tracking (iPhone XS+): play certain games using body motion" while emulating a standard game controller over Wi-Fi/LAN to a PC.
- General-purpose ARKit/LiDAR-to-OSC streaming tools (TDLidar, LOTA, ZIG SIM) are built for VJ/mocap/art pipelines (TouchDesigner, Unity, Unreal, Max/MSP), not game/emulator control — you'd have to build the OSC→input-mapping bridge yourself.
- No evidence found of anyone piping ARKit body pose into a PS2/retro emulator (PCSX2, Dolphin, RetroArch) specifically. The closest console-emulation precedent is Kinect skeletal tracking, and even that is only an experimental, in-progress feature for Xbox 360 emulation (Xenia), with no PS2/PCSX2 equivalent.
- Network dependency is universal: iPhone and PC must share local Wi-Fi; OSC is UDP-based, typically needing multicast/Bonjour discovery.
- LiDAR upgrades body tracking from a flat 2D projection to real metric depth (z-values) — relevant if depth/torso-lean precision matters.

### Key findings
- VGamepad Lite (iOS) has "AR Body Tracking" mode (iPhone XS+) for playing "certain games," emulating a controller (incl. Joy-Con) over Wi-Fi/LAN — confidence: Med — apps.apple.com/us/app/vgamepad-lite/id1477007195
- No detail found on which games/emulators support that mode, or how movements map to buttons — confidence: Low
- TDLidar streams a full ARKit+LiDAR body skeleton (17 joints × x,y,z) as OSC to TouchDesigner/Unity/Unreal/Max — confidence: High — derivative.ca tutorial
- LOTA streams an 18-joint body skeleton plus face/hand landmarks over OSC — confidence: High — lidarota.app/docs
- ZIG SIM Pro streams ARKit body-position and 6DoF data via OSC/UDP-JSON, with open-source Unity receiver wrappers — confidence: High
- VMC (Virtual Motion Capture) Protocol is an OSC-based avatar-motion standard, cross-platform, a possible existing schema to piggyback on instead of a bespoke one — confidence: Med
- VRChat's OSC Trackers / "OSC as Input Controller" shows a working precedent for turning tracker data into first-class in-app input via a documented OSC address scheme — confidence: High
- Apple's ARKit body-pose model tracks up to 92 joint types, one body at a time, requires A12 Bionic+, needs a Pro-model device for LiDAR fusion — confidence: High — Apple developer docs (2020-04-29, updated 2023-03-27)
- Kinect-to-emulator skeletal tracking is only experimental/in-progress in Xenia (Xbox 360), no PS2 equivalent found — confidence: Med, aggregated

### Confirmed vs contested
- **Confirmed**: Multiple actively-maintained apps can stream ARKit/LiDAR body-skeleton data from iPhone to PC via OSC/UDP over local Wi-Fi today. At least one app (VGamepad Lite) markets body tracking specifically as PC game-controller input.
- **Contested/thin**: Whether VGamepad Lite's body tracking has actually been used with retro emulators — search summaries mention "reviews... emulators" but no primary review text or emulator name surfaced; treat as unverified anecdote.
- **Silent**: No source on OSC-over-WiFi body-tracking latency in a real-time gaming context; no documented ARKit→PS2-emulator bridge anywhere.

### Open questions / gaps
- Actual end-to-end latency of iPhone ARKit body tracking → Wi-Fi OSC → PC input mapping is undocumented — matters a lot for a game requiring quick reaction (duck/cover).
- No documented turnkey solution for ARKit/LiDAR pose feeding a game/emulator input the way a webcam+motion-detection approach would — this whole avenue would require custom glue code (OSC receiver → input mapper).
- Whether "torso lean"/coarse motion-triggering is even necessary versus full skeletal precision isn't addressed by any source — a design question for the project, not a research gap.

### Best sources
- developer.apple.com ARKit body-motion-capture docs — Apple's own primary documentation on capabilities/limits.
- derivative.ca TDLidar tutorial — concrete, current OSC message schema for iPhone LiDAR body skeleton streaming.
- apps.apple.com/us/app/vgamepad-lite/id1477007195 — the one concrete precedent tying iPhone body tracking directly to PC game-controller input.
- docs.vrchat.com/docs/osc-trackers — documents a real, shipped example of mapping external tracker data into in-app input via OSC.
- protocol.vmc.info/english.html — cross-platform OSC avatar-motion protocol spec.

---

## Consolidated Confirmed / Contested / Unknown

| Crux question | Confirmed | Contested | Unknown |
|---|---|---|---|
| **(a) Does motion (duck/lean) work under emulation today?** | PCSX2 has a native "Webcam (EyeToy)" USB device slot; the game runs (shooting portion) under PCSX2 1.7 via mouse-emulated aiming (documented playthrough). | — | **No first-hand evidence anywhere** (video, forum, GitHub issue) that the camera-based motion mechanic actually functions under PCSX2, via real webcam or OBS Virtual Camera. This is a genuine gap, not a settled "it doesn't work" — it's simply untested/unreported on the public web. |
| **(b) Camera-chipset pickiness through PCSX2** | On real PS2 hardware: Konami's "Capture Eye" (RU035) is the sanctioned camera; Sony EyeToy is widely reported not to work; PCSX2's own wiki repeats the EyeToy-incompatibility claim as a game-level lockout. | Whether EyeToy *ever* works is not fully settled (one thread: "conflicting reports"). Whether a PAL-disc camera rejection is a software region-lock (one tester's account) or something else. Whether third-party "OV511-class" cameras reliably work (one tester's chipset-matched camera still failed). | Whether PCSX2's emulated "Webcam (EyeToy)" device even attempts the game's specific motion-detection protocol, or just passes frames the game's own driver-level check then rejects — no source addresses this mechanism directly. |
| **(c) GunCon 2 vs Konami-gun + absolute-vs-relative mouse** | Multiple independent sources agree: the game does **not** work with GunCon/GunCon 2. PCSX2 has no native Hyperblaster/Justifier protocol emulation (open, unimplemented request). A PCSX2 maintainer confirmed standard USB mice can't report absolute coordinates the way GunCon does — this is the documented root cause of the whole ambiguity, corroborated by the identical situation in Silent Scope. | Whether real hardware needs a Hyper Blaster/Justifier-protocol gun or "multi gun" (GitHub issue, Sinden wiki, one forum poster) vs. a plain "Mouse Controller" peripheral (psxdatacenter) vs. a generic PS1/PS2 lightgun with GunCon 1 possibly working (one forum poster) — three framings, not reconciled anywhere. | Whether OpenFIRE's absolute-mouse HID output has ever been tested against this specific game's input path (Hyperblaster-style vs. PS2 Mouse Controller) — no source discusses OpenFIRE + any Konami PS2 gun title at all. |
| **(d) Running camera + gun simultaneously** | PCSX2 supports a "Webcam (EyeToy)" USB device on one USB port and a separate lightgun/mouse USB device concept in general (both are documented PCSX2 USB device types). | — | **No agent found any source — forum post, video, or issue — addressing whether PCSX2 can run both a webcam device and a gun/mouse device simultaneously for this specific game**, or whether the two device slots conflict/compete for the game's own device-detection logic. This is unaddressed by the web entirely; flagged here as a gap rather than a contested claim, since no source even attempts it. |

---

## Open questions, ranked by how much they block the larger project

1. **Does the camera-based motion mechanic work under PCSX2 at all (real webcam or OBS Virtual Camera)?** — Blocks everything; if it doesn't work, the whole "modern webcam" half of the project needs a different approach (e.g., real PS2 hardware + real Capture Eye, or the speculative ARKit/OSC route). **Cheapest test**: boot the actual PAL disc in PCSX2, set USB port to "Webcam (EyeToy)," feed it any UVC camera or OBS Virtual Camera, and see if the game even gets past its camera-detection check (it may reject non-Capture Eye devices at the driver level regardless of emulation, per the wiki's flat "will not work" language) — a 15-minute test that resolves the single biggest unknown in this whole dossier.
2. **Does the game's motion detection tolerate a modern webcam's UVC stream at all, independent of emulation** — i.e., could a real PS2 + a UVC camera masquerading as a Capture Eye (same chipset signature) work, bypassing emulation entirely? — **Cheapest test**: check whether the game's camera check is chipset/VID-PID based (testable by spoofing a known-working OV511-class camera's descriptors) or driver-behavior based; the OV511 Linux driver project (ovcam.org) documents the chipset's protocol in enough detail to attempt this on real hardware first.
3. **What gun protocol does the PAL disc actually require, precisely** (Hyperblaster/Justifier vs. PS2 Mouse Controller vs. something else)? — Blocks the OpenFIRE integration decision (which HID mode to configure it in). **Cheapest test**: acquire a real PS2 "Mouse Controller" (SCPH-10160) or a Justifier-protocol Hyper Blaster gun and test each in isolation on real hardware, or — cheaper still — dump/inspect the PAL disc's peripheral-detection code (a savestate/debugger trace under PCSX2 while it queries the USB port would show which device type ID the game is polling for).
4. **Can PCSX2 run a webcam USB device and a gun/mouse USB device on two separate ports simultaneously for this game, without one interfering with detection of the other?** — Blocks the "full experience" (motion + shooting together) even if items 1–3 resolve individually. **Cheapest test**: once item 1 is resolved (camera-detection working in isolation), add a second USB device (HID Mouse or GunCon2) on the other port and see if the game still detects the camera.
5. **Does the Insta360 Link 2C's Auto Framing/AI tracking run in firmware regardless of host OS, or only via the Windows/Mac Link Controller app?** — Blocks whether the 2C is usable as a "dumb" fixed camera on Linux (relevant to whatever host OS runs PCSX2). **Cheapest test**: plug the Link 2C into a Linux box, open any plain UVC viewer (e.g. `guvcview` or `cheese`), and physically move a hand/subject in frame — if the image auto-crops/zooms without the Link Controller app running, tracking is firmware-side; if it doesn't, it's software-side and Linux is already "dumb" by default.
6. **Does the JP-camera-on-PAL-disc rejection generalize** (is it truly a region lock, or a fluke of one tester's setup)? — Lower urgency; mainly affects whether a JP Capture Eye unit could be used with the PAL disc as a compatibility workaround. **Cheapest test**: near-impossible to cheaply retest without owning both discs and a JP Capture Eye — deprioritize unless a Capture Eye of either region turns up cheaply.

---

## Source bibliography

*Grouped by topic, deduplicated across agents.*

**Game & motion system / Wikipedia / general background**
- https://en.wikipedia.org/wiki/Police_911
- https://en.wikipedia.org/wiki/GunCon
- https://backloggd.com/u/87th/review/541909
- https://grokipedia.com/page/Police_911 (unreachable — 403, unverified)

**PS2 SKU / peripheral database**
- https://psxdatacenter.com/psx2/games2/SLES-50285.html (PAL)
- https://psxdatacenter.com/psx2/games2/SLPM-62097.html (JP)

**Camera compatibility — forums & blogs**
- https://hokutonoshock.blogspot.com/2014/02/police-247-european-release-of-police.html
- https://assemblergames.org/viewtopic.php?t=35723
- http://forum.arcadecontrols.com/index.php?topic=161966.0
- https://forums.overclockers.com.au/threads/police-24-7-on-ps2-camera-help.607408
- https://www.neogaf.com/threads/police-911-motion-controls-on-ps2-long-before-wii-on-a-konami-hidden-gem-and-other-interesting-firsts-and-deep-cut-games-from-common-devs.1656492
- https://www.ebay.com/itm/303599648648
- https://ovcam.org/ov511/cameras.html
- https://ovcam.org/ov511/introduction.html

**Light gun / gun protocol**
- https://github.com/PCSX2/pcsx2/issues/7889
- https://github.com/PCSX2/pcsx2/issues/10863 (incl. comment thread)
- https://www.sindenwiki.org/wiki/PCSX2
- https://forums.pcsx2.net/Thread-police-24-7-with-lightgun-or-wiimote
- https://forums.pcsx2.net/Thread-Playing-lightgun-games-with-a-mouse
- https://www.emuline.org/video/284-police-247-ps2-full-playthrough-mouse-support-pcsx2-17
- http://forum.arcadecontrols.com/index.php?topic=165285.0

**PCSX2 emulation reality**
- https://wiki.pcsx2.net/Police_24/7 (via search cache; direct fetch 403)
- https://retrodeck.readthedocs.io/en/cooker/wiki_controllers/playstation/eyetoy/
- https://github.com/PCSX2/pcsx2/issues/3921 (+ PR #3922)
- https://github.com/PCSX2/pcsx2/issues/525
- https://github.com/PCSX2/pcsx2/blob/master/pcsx2/USB/usb-lightgun/guncon2.cpp

**OpenFIRE**
- https://openfirelightgun.org/
- https://github.com/TeamOpenFIRE/OpenFIRE-Firmware
- https://github.com/TeamOpenFIRE/OpenFIRE-Firmware/releases
- https://github.com/TeamOpenFIRE/OpenFIRE-App
- https://osrtos.com/projects/openfire-the-open-four-infa-red-emitter-light-gun-system/
- https://github.com/alessandro-satanassi/OpenFIRE-Firmware-ESP32

**Insta360 Link 2C**
- https://onlinemanual.insta360.com/link2c/en-us/specs/hardware
- https://onlinemanual.insta360.com/link2/en-us/faq/specs/shooting
- https://onlinemanual.insta360.com/link2c/en-us/faq/functions/autoframing
- https://onlinemanual.insta360.com/link2/en-us/faq/functions/aitracking
- https://onlinemanual.insta360.com/link2c/en-us/operating-tutorials/audio/audio-microphone
- https://github.com/vrwallace/Insta360-Link-1-and-2-Controller-for-Linux
- https://www.microcenter.com/product/686559/insta360-link-2c-standard-edition
- https://www.pcgamer.com/hardware/webcams/insta360-link-2c-review/
- https://www.techradar.com/computing/webcams/insta360-link-2c-review

**iPhone LiDAR/ARKit body pose (speculative)**
- https://developer.apple.com/documentation/arkit/arkit_in_ios/content_anchors/capturing_body_motion_in_3d
- https://derivative.ca/community-post/tutorial/tdlidar-%E2%80%94-your-iphone-depth-camera-3d-scanner-and-sensor-rig-touchdesigner
- https://lidarota.app/docs
- https://1-10.github.io/zigsim/features/arkit.html
- https://protocol.vmc.info/english.html
- https://docs.vrchat.com/docs/osc-trackers
- https://docs.vrchat.com/docs/osc-as-input-controller
- https://apps.apple.com/us/app/vgamepad-lite/id1477007195
- https://lightbuzz.com/body-tracking-arkit-lidar/
