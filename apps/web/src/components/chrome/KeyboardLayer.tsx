/**
 * Global keyboard parity layer (UI-003): every gesture action has a key.
 * "?" opens the shortcut overlay.
 */

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect } from "react";

import { popSpring } from "../../lib/motion/presets";
import { cameraBus } from "../../lib/world/cameraBus";
import { useUiStore } from "../../state/uiStore";
import { useWorldStore } from "../../state/worldStore";

const SHORTCUTS: { keys: string; action: string }[] = [
  { keys: "ctrl / ⌘ + K", action: "last-seen search" },
  { keys: "J / K", action: "cycle object selection" },
  { keys: "F", action: "focus camera on selection" },
  { keys: "G · R · U · L", action: "ghosts · graph · uncertainty · labels" },
  { keys: "arrows", action: "orbit the world" },
  { keys: "+ / −", action: "zoom" },
  { keys: "0", action: "reset camera" },
  { keys: "T", action: "enter memory scrub (timeline)" },
  { keys: "H", action: "summon / dismiss HoloConsole" },
  { keys: "esc", action: "cancel — closes panels, exits holo" },
  { keys: "?", action: "this overlay" },
];

function isTypingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.tagName === "INPUT" ||
      target.tagName === "TEXTAREA" ||
      target.isContentEditable)
  );
}

export function KeyboardLayer() {
  const reduced = useReducedMotion() ?? false;
  const helpOpen = useUiStore((state) => state.helpOpen);
  const setHelpOpen = useUiStore((state) => state.setHelpOpen);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const ui = useUiStore.getState();
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        ui.setSearchOpen(!ui.searchOpen);
        return;
      }
      if (isTypingTarget(event.target)) {
        return;
      }
      switch (event.key) {
        case "?":
          ui.setHelpOpen(!ui.helpOpen);
          break;
        case "Escape":
          if (ui.searchOpen) {
            ui.setSearchOpen(false);
          } else if (ui.helpOpen) {
            ui.setHelpOpen(false);
          } else if (ui.evidenceOpen) {
            ui.setEvidenceOpen(false);
          } else if (ui.scanPanelOpen) {
            ui.setScanPanelOpen(false);
          } else if (ui.holoActive) {
            ui.setHoloActive(false);
          } else if (ui.timelineMode === "scrub") {
            ui.setTimeline("live");
          } else {
            ui.select(null);
          }
          break;
        case "g":
        case "G":
          ui.toggleLayer("ghosts");
          break;
        case "r":
        case "R":
          ui.toggleLayer("graph");
          break;
        case "u":
        case "U":
          ui.toggleLayer("uncertainty");
          break;
        case "l":
        case "L":
          ui.toggleLayer("labels");
          break;
        case "h":
        case "H":
          ui.setHoloActive(!ui.holoActive);
          break;
        case "f":
        case "F":
          if (ui.selectedEntityId !== null) {
            ui.requestFocus(ui.selectedEntityId);
          }
          break;
        case "j":
        case "J":
        case "k":
        case "K": {
          const { order } = useWorldStore.getState();
          if (order.length === 0) {
            break;
          }
          const direction = event.key.toLowerCase() === "j" ? 1 : -1;
          const currentIndex =
            ui.selectedEntityId !== null
              ? order.indexOf(ui.selectedEntityId)
              : -1;
          const next =
            order[
              (currentIndex + direction + order.length) % order.length
            ];
          if (next !== undefined) {
            ui.select(next);
          }
          break;
        }
        case "t":
        case "T": {
          const world = useWorldStore.getState();
          if (world.timeOrigin !== null) {
            ui.setTimeline("scrub", world.timeOrigin);
          }
          break;
        }
        case "ArrowLeft":
          cameraBus.orbit(-0.14, 0);
          break;
        case "ArrowRight":
          cameraBus.orbit(0.14, 0);
          break;
        case "ArrowUp":
          if (event.shiftKey) {
            cameraBus.pan(0, -0.16);
          } else {
            cameraBus.orbit(0, -0.09);
          }
          break;
        case "ArrowDown":
          if (event.shiftKey) {
            cameraBus.pan(0, 0.16);
          } else {
            cameraBus.orbit(0, 0.09);
          }
          break;
        case "+":
        case "=":
          cameraBus.zoom(0.88);
          break;
        case "-":
        case "_":
          cameraBus.zoom(1.14);
          break;
        case "0":
          cameraBus.reset();
          break;
        default:
          return;
      }
      event.preventDefault();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  return (
    <AnimatePresence>
      {helpOpen && (
        <motion.div
          className="palette-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onClick={() => {
            setHelpOpen(false);
          }}
        >
          <motion.section
            className="help-overlay"
            role="dialog"
            aria-modal="true"
            aria-label="Keyboard shortcuts"
            initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.95, y: 18 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.97, y: 10 }}
            transition={popSpring}
            onClick={(event) => {
              event.stopPropagation();
            }}
          >
            <h2 className="help-overlay__title">controls</h2>
            <ul className="help-overlay__list">
              {SHORTCUTS.map((shortcut) => (
                <li key={shortcut.keys} className="help-overlay__row">
                  <kbd className="help-overlay__keys">{shortcut.keys}</kbd>
                  <span>{shortcut.action}</span>
                </li>
              ))}
            </ul>
            <p className="panel-footnote">
              Every gesture in HoloConsole has an equivalent here — the
              interface is fully operable without a camera.
            </p>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
