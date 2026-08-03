# WorldState portfolio demo script

## Goal

Record a three-to-four-minute demonstration that proves WorldState is a real
spatial-memory system, not a visual mockup. Use an ordinary desk, the laptop
webcam, three visually distinct objects, and the local production launcher.
Do not expose private video, a bootstrap token, absolute file paths, or raw
model files in the recording.

## Before recording

1. Run `scripts\doctor.ps1` and confirm the GPU and all six models are ready.
2. Run `scripts\run.ps1`; let it build the frontend and open the one-time
   same-origin session.
3. Frame a desk with a cup, a book, and a phone. Use even lighting.
4. Keep the browser console, terminal secrets, and private capture folders out
   of the recording.
5. Rehearse the object changes so the narration and visual state stay aligned.

## Shot list

### 0:00–0:20 — The premise

Show the live memory volume and say:

> WorldState gives an ordinary webcam a persistent memory of physical space. It
> does not just detect what is in one frame; it remembers entities, change,
> uncertainty, relationships, and the evidence behind each conclusion.

Briefly show that the session is local and that learned models are ready.

### 0:20–0:55 — Establish the world

Start capture and slowly pan across the desk. Let the Active Scan Coach guide
one corrective movement. Point out:

- open-vocabulary discovery;
- asynchronous semantic and mask refresh;
- optical-flow tracking and predictive overlays between discoveries;
- approximate depth and object extents;
- the useful-update and latency telemetry.

Avoid claiming metric scale unless a calibration reference is active.

### 0:55–1:30 — Make the room change

Perform this sequence with a short pause after each action:

1. add the cup;
2. move the book;
3. cover the phone with the book;
4. remove the cup from view;
5. bring the cup back in a different location.

Show Change Pulses and the event feed identifying added, moved, occluded,
missing, and rediscovered states.

### 1:30–2:05 — Prove persistence

Enable Ghost Mode, then drag the Time Scrubber backward. Select the cup and
open Object Memory. Show:

- earlier positions;
- the confidence trace;
- observation and event history;
- supporting evidence;
- current versus last-seen state.

Use Last-Seen Search for the temporarily removed phone and jump to its final
observation.

### 2:05–2:35 — Show the world model

Enable the Scene Graph and Uncertainty View. Explain that relationships and
uncertain geometry are data-backed states, not decorative animation. Show one
relationship changing after moving an object.

Summon HoloConsole with the deliberate two-palm hold and use one gesture to
select or navigate memory. Immediately demonstrate the keyboard equivalent so
the interaction remains credible and accessible even without gesture support.

### 2:35–3:05 — Reconstruct and export

Upload a short prerecorded phone scan. Show:

- bounded job progress and cancellation control;
- the reconstruction quality label;
- the resulting geometry;
- GLB and PLY artifacts;
- explicit approximate-scale labeling when no reference measurement exists.

If the scan uses a degraded fallback, say so and show the provider recorded in
the result instead of hiding it.

### 3:05–3:35 — Engineering receipts

Cut to the measured-status page and briefly show:

- 110 Python tests and 123 frontend tests;
- generated OpenAPI and WebSocket contracts;
- the final 30-minute learned-provider soak;
- measured latency, useful update rate, VRAM, and stable RAM/VRAM trends;
- checksum-pinned local models and loopback-only security.

Close with:

> The interface is the visible part. Underneath it is a bounded GPU runtime,
> temporal entity graph, content-addressed evidence store, reconstruction
> pipeline, and reproducible evaluation harness—all running locally on a laptop
> RTX 4060.

## Recording integrity

- Label simulation or replay footage everywhere it appears.
- Do not splice replay output into a segment narrated as live inference.
- Do not claim accuracy targets that remain unmeasured.
- Keep failed or degraded states visible when they are relevant.
- Capture one continuous live-change sequence to make the temporal-memory claim
  independently understandable.
