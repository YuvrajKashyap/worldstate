/**
 * Spatial Scan: upload a moving-camera video, launch the scan job, and
 * watch its bounded lifecycle — including cancellation. Backend mode only;
 * the simulation explains why it is unavailable instead of pretending.
 */

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, type JobResponse } from "../../lib/api/http";
import { drawerSpring } from "../../lib/motion/presets";
import { useSessionStore } from "../../state/sessionStore";
import { useUiStore } from "../../state/uiStore";

type UploadPhase =
  | { step: "idle" }
  | { step: "uploading"; name: string }
  | { step: "starting" }
  | { step: "watching"; jobId: string }
  | { step: "failed"; message: string };

export function ScanPanel() {
  const reduced = useReducedMotion() ?? false;
  const open = useUiStore((state) => state.scanPanelOpen);
  const setOpen = useUiStore((state) => state.setScanPanelOpen);
  const mode = useSessionStore((state) => state.mode);
  const canMutate = useSessionStore((state) => state.canMutate);
  const [phase, setPhase] = useState<UploadPhase>({ step: "idle" });
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);

  const refreshJobs = useCallback(async () => {
    if (mode !== "backend") {
      return;
    }
    try {
      const response = await api.listJobs();
      setJobs(response.items.slice(0, 6));
    } catch {
      // Job listing is best-effort while the panel is open.
    }
  }, [mode]);

  useEffect(() => {
    if (!open || mode !== "backend") {
      return;
    }
    const lead = window.setTimeout(() => {
      void refreshJobs();
    }, 40);
    const timer = window.setInterval(() => {
      void refreshJobs();
    }, 1500);
    return () => {
      window.clearTimeout(lead);
      window.clearInterval(timer);
    };
  }, [open, mode, refreshJobs]);

  const beginScan = async (file: File) => {
    setPhase({ step: "uploading", name: file.name });
    try {
      const scenes = await api.listScenes();
      const scene =
        scenes.items[0] ??
        (await api.createScene({
          name: "Desk",
          description: null,
          object_prompts: ["cup", "book", "phone"],
          persistence_enabled: false,
        }));
      const session = await api.createCaptureSession(scene.id, {
        mode: "scan",
        source_name: file.name,
        camera: null,
      });
      const upload = await api.uploadVideo(session.id, file);
      setPhase({ step: "starting" });
      const job = await api.createJob({
        kind: "scan",
        scene_id: scene.id,
        session_id: session.id,
        parameters: { video_artifact_id: upload.artifact_id },
      });
      setPhase({ step: "watching", jobId: job.id });
      void refreshJobs();
    } catch (error) {
      setPhase({
        step: "failed",
        message:
          error instanceof ApiError
            ? error.message
            : "The scan could not be started.",
      });
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.section
          className="scan-panel"
          role="dialog"
          aria-label="Spatial scan"
          initial={reduced ? { opacity: 0 } : { x: 420, opacity: 0.5 }}
          animate={reduced ? { opacity: 1 } : { x: 0, opacity: 1 }}
          exit={reduced ? { opacity: 0 } : { x: 420, opacity: 0 }}
          transition={drawerSpring}
        >
          <header className="memory-panel__header">
            <h2 className="memory-panel__title">spatial scan</h2>
            <button
              type="button"
              className="icon-button"
              title="Close"
              onClick={() => {
                setOpen(false);
              }}
            >
              ✕
            </button>
          </header>

          {mode !== "backend" ? (
            <p className="panel-footnote">
              Scan jobs need the local backend; the simulation cannot
              reconstruct video. Launch WorldState locally to scan.
            </p>
          ) : !canMutate ? (
            <p className="panel-footnote">
              This session is read-only. Relaunch WorldState to obtain a
              fresh capture token.
            </p>
          ) : (
            <>
              <p className="scan-panel__copy">
                Upload a short moving-camera video (MP4/MOV). WorldState
                selects keyframes, estimates geometry, and lifts objects into
                the scene.
              </p>
              <input
                ref={fileInput}
                type="file"
                accept="video/mp4,video/quicktime"
                className="visually-hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file !== undefined) {
                    void beginScan(file);
                  }
                  event.target.value = "";
                }}
              />
              <button
                type="button"
                className="control-button"
                disabled={phase.step === "uploading" || phase.step === "starting"}
                onClick={() => {
                  fileInput.current?.click();
                }}
              >
                {phase.step === "uploading"
                  ? `uploading ${phase.name}…`
                  : phase.step === "starting"
                    ? "starting job…"
                    : "choose video"}
              </button>
              {phase.step === "failed" && (
                <p className="video-dock__error" role="alert">
                  {phase.message}
                </p>
              )}

              <h3 className="memory-panel__subheading">jobs</h3>
              <ul className="job-list">
                {jobs.length === 0 && (
                  <li className="panel-footnote">No jobs yet.</li>
                )}
                {jobs.map((job) => (
                  <li key={job.id} className="job-list__row">
                    <div className="job-list__head">
                      <span className="job-list__kind">{job.kind}</span>
                      <span className={`job-list__status job-list__status--${job.status}`}>
                        {job.status}
                      </span>
                    </div>
                    <div
                      className="job-list__progress"
                      role="progressbar"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(job.progress * 100)}
                      aria-label={`${job.kind} progress`}
                    >
                      <span
                        className="job-list__progress-fill"
                        style={{ width: `${String(job.progress * 100)}%` }}
                      />
                    </div>
                    <span className="job-list__stage">{job.stage}</span>
                    {(job.status === "queued" || job.status === "running") && (
                      <button
                        type="button"
                        className="control-button control-button--ghosted control-button--small"
                        onClick={() => {
                          void api.cancelJob(job.id).then(() => refreshJobs());
                        }}
                      >
                        cancel
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </motion.section>
      )}
    </AnimatePresence>
  );
}
