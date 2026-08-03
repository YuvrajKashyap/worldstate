/**
 * The temporal instrument: scrub through remembered states without
 * mutating live memory. Event ticks are color-coded by kind; releasing
 * the scrubber reports the selected time over the command channel.
 */

import { motion, useReducedMotion } from "motion/react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { formatAgo, formatClock, formatDuration } from "../../lib/format";
import { gravitationalEase } from "../../lib/motion/presets";
import { eventColor } from "../../lib/palette";
import { useSessionStore } from "../../state/sessionStore";
import { useUiStore } from "../../state/uiStore";
import { useWorldStore } from "../../state/worldStore";

export function TimeDeck() {
  const reduced = useReducedMotion() ?? false;
  const timeOrigin = useWorldStore((state) => state.timeOrigin);
  const lastFrameAt = useWorldStore((state) => state.lastFrameAt);
  const events = useWorldStore((state) => state.events);
  const timelineMode = useUiStore((state) => state.timelineMode);
  const scrubTime = useUiStore((state) => state.scrubTime);
  const setTimeline = useUiStore((state) => state.setTimeline);
  const submitCommand = useSessionStore((state) => state.submitCommand);
  const sceneId = useSessionStore((state) => state.sceneId);

  const trackRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);
  const [playing, setPlaying] = useState(false);

  const range = useMemo(() => {
    if (timeOrigin === null || lastFrameAt === null) {
      return null;
    }
    return { start: timeOrigin, end: Math.max(lastFrameAt, timeOrigin + 1000) };
  }, [timeOrigin, lastFrameAt]);

  const fractionFor = useCallback(
    (timeMs: number) => {
      if (range === null) {
        return 1;
      }
      return Math.min(
        1,
        Math.max(0, (timeMs - range.start) / (range.end - range.start)),
      );
    },
    [range],
  );

  const timeForFraction = useCallback(
    (fraction: number) => {
      if (range === null) {
        return Date.now();
      }
      return range.start + fraction * (range.end - range.start);
    },
    [range],
  );

  const reportScrub = useCallback(
    (atMs: number) => {
      if (sceneId !== null) {
        void submitCommand({
          command: "set_timeline_time",
          sceneId,
          arguments: { at: new Date(atMs).toISOString() },
        });
      }
    },
    [sceneId, submitCommand],
  );

  const scrubToClient = useCallback(
    (clientX: number) => {
      const track = trackRef.current;
      if (track === null || range === null) {
        return;
      }
      const rect = track.getBoundingClientRect();
      const fraction = Math.min(
        1,
        Math.max(0, (clientX - rect.left) / rect.width),
      );
      const value = timeForFraction(fraction);
      if (fraction >= 0.997) {
        setTimeline("live");
      } else {
        setTimeline("scrub", value);
      }
    },
    [range, setTimeline, timeForFraction],
  );

  // Replay playback: advance the scrub head until it reaches the present.
  useEffect(() => {
    if (!playing || range === null) {
      return;
    }
    const timer = window.setInterval(() => {
      const state = useUiStore.getState();
      const current = state.scrubTime ?? range.start;
      const next = current + 200;
      if (next >= range.end) {
        state.setTimeline("live");
        setPlaying(false);
      } else {
        state.setTimeline("scrub", next);
      }
    }, 200);
    return () => {
      window.clearInterval(timer);
    };
  }, [playing, range]);

  if (range === null) {
    return (
      <section className="time-deck time-deck--empty" aria-label="Timeline">
        <span className="time-deck__hint">
          The temporal record begins when capture starts.
        </span>
      </section>
    );
  }

  const playheadTime = timelineMode === "scrub" && scrubTime !== null ? scrubTime : range.end;
  const playheadFraction = fractionFor(playheadTime);
  const memorySpanSeconds = (range.end - range.start) / 1000;

  return (
    <motion.section
      className="time-deck"
      aria-label="Timeline scrubber"
      initial={reduced ? false : { opacity: 0, y: 26 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.75, ease: gravitationalEase, delay: 0.35 }}
    >
      <div className="time-deck__readout">
        <span
          className={`time-deck__mode time-deck__mode--${timelineMode}`}
          aria-live="polite"
        >
          {timelineMode === "live" ? "LIVE" : "MEMORY"}
        </span>
        <span className="time-deck__clock">{formatClock(playheadTime)}</span>
        <span className="time-deck__ago">
          {timelineMode === "live"
            ? `${formatDuration(memorySpanSeconds)} recorded`
            : formatAgo(playheadTime)}
        </span>
      </div>

      <div
        ref={trackRef}
        className={`time-deck__track${dragging ? " time-deck__track--dragging" : ""}`}
        role="slider"
        tabIndex={0}
        aria-label="Scrub through remembered time"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(playheadFraction * 100)}
        aria-valuetext={
          timelineMode === "live" ? "Live" : formatClock(playheadTime)
        }
        onPointerDown={(event) => {
          setDragging(true);
          setPlaying(false);
          event.currentTarget.setPointerCapture(event.pointerId);
          scrubToClient(event.clientX);
        }}
        onPointerMove={(event) => {
          if (dragging) {
            scrubToClient(event.clientX);
          }
        }}
        onPointerUp={(event) => {
          event.currentTarget.releasePointerCapture(event.pointerId);
          setDragging(false);
          const state = useUiStore.getState();
          if (state.timelineMode === "scrub" && state.scrubTime !== null) {
            reportScrub(state.scrubTime);
          }
        }}
        onKeyDown={(event) => {
          const step = 1000;
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            const direction = event.key === "ArrowLeft" ? -1 : 1;
            const base =
              timelineMode === "scrub" && scrubTime !== null
                ? scrubTime
                : range.end;
            const next = Math.min(range.end, Math.max(range.start, base + direction * step));
            if (next >= range.end - 250) {
              setTimeline("live");
            } else {
              setTimeline("scrub", next);
              reportScrub(next);
            }
          } else if (event.key === "Home") {
            event.preventDefault();
            setTimeline("scrub", range.start);
          } else if (event.key === "End") {
            event.preventDefault();
            setTimeline("live");
          }
        }}
      >
        <div className="time-deck__rail" aria-hidden="true">
          <div
            className="time-deck__fill"
            style={{ transform: `scaleX(${String(playheadFraction)})` }}
          />
          {events.map((event) => (
            <span
              key={event.id}
              className="time-deck__tick"
              style={{
                left: `${String(fractionFor(Date.parse(event.occurred_at)) * 100)}%`,
                background: eventColor[event.kind],
              }}
              title={event.kind}
            />
          ))}
          <div
            className={`time-deck__head${timelineMode === "scrub" ? " time-deck__head--memory" : ""}`}
            style={{ left: `${String(playheadFraction * 100)}%` }}
          >
            <span className="time-deck__head-glow" />
          </div>
        </div>
      </div>

      <div className="time-deck__actions">
        <button
          type="button"
          className="control-button control-button--ghosted"
          onClick={() => {
            if (timelineMode === "live") {
              setTimeline("scrub", range.start);
              setPlaying(true);
            } else {
              setPlaying((value) => !value);
            }
          }}
        >
          {playing ? "pause" : "replay"}
        </button>
        <button
          type="button"
          className="control-button"
          disabled={timelineMode === "live"}
          onClick={() => {
            setPlaying(false);
            setTimeline("live");
          }}
        >
          return to present
        </button>
      </div>
    </motion.section>
  );
}
