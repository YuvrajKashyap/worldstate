# Desk Change Set capture protocol

Raw recordings and annotations are private and ignored. Only this protocol,
anonymized manifests, schema, and aggregate measured results may enter Git.

## Minimum design

- 12 sessions and at least 240 scripted events.
- Webcam and uploaded phone video where available.
- Low, medium, and high clutter.
- Bright, dim, and mixed lighting.
- Small, medium, and large ordinary objects.
- Static, panning, orbiting, and deliberately weak camera paths.
- Balanced add, remove, translate, rotate, occlude, and rediscover events.
- Similar-looking distractors for identity evaluation.

## Per-session procedure

1. Record an anonymized session ID, device class, resolution, lighting bucket,
   clutter bucket, and calibration mode.
2. Capture a clean baseline for ten seconds.
3. Perform the prewritten event schedule without changing labels after seeing
   predictions.
4. Include temporary person/hand occlusion; never annotate biometric identity.
5. Record event ground-truth time, object pseudonym, before/after region, and
   optional measured distance.
6. Hash the raw file and annotation file. Keep both outside Git.
7. Assign the complete session to train/calibration/holdout before tuning.

## Quality controls

- Reject only for documented capture failure, not poor model performance.
- Keep correlated frames within the same split.
- Double-review event times and identity labels on the final holdout.
- Freeze primary metrics and thresholds before the final run.
- Report exclusions, negative results, and unrecovered failures.
