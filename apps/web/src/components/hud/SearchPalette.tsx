/**
 * Last-Seen Search (Ctrl/Cmd+K): find any remembered object, see when and
 * where it was last observed — with a clear distinction between "last
 * seen" and "currently present" — then jump the camera to it.
 */

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";

import { formatAgo } from "../../lib/format";
import { popSpring } from "../../lib/motion/presets";
import { presenceColor, presenceLabel } from "../../lib/palette";
import { useSessionStore } from "../../state/sessionStore";
import { useUiStore } from "../../state/uiStore";
import { useWorldStore } from "../../state/worldStore";

export function SearchPalette() {
  const reduced = useReducedMotion() ?? false;
  const open = useUiStore((state) => state.searchOpen);
  const setOpen = useUiStore((state) => state.setSearchOpen);
  const select = useUiStore((state) => state.select);
  const requestFocus = useUiStore((state) => state.requestFocus);
  const entities = useWorldStore((state) => state.entities);
  const order = useWorldStore((state) => state.order);
  const submitCommand = useSessionStore((state) => state.submitCommand);
  const sceneId = useSessionStore((state) => state.sceneId);

  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const timer = window.setTimeout(() => {
      setQuery("");
      setCursor(0);
      inputRef.current?.focus();
    }, 20);
    return () => {
      window.clearTimeout(timer);
    };
  }, [open]);

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return order
      .map((id) => entities[id])
      .filter(
        (record): record is NonNullable<typeof record> =>
          record !== undefined &&
          (needle === "" || record.label.toLowerCase().includes(needle)),
      )
      .slice(0, 8);
  }, [order, entities, query]);

  const commit = (entityId: string) => {
    select(entityId);
    requestFocus(entityId);
    if (sceneId !== null) {
      void submitCommand({
        command: "find_last_seen",
        sceneId,
        entityId,
      });
    }
    setOpen(false);
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="palette-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onClick={() => {
            setOpen(false);
          }}
        >
          <motion.div
            className="palette"
            role="dialog"
            aria-modal="true"
            aria-label="Last-seen search"
            initial={reduced ? { opacity: 0 } : { opacity: 0, y: -26, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduced ? { opacity: 0 } : { opacity: 0, y: -14, scale: 0.98 }}
            transition={popSpring}
            onClick={(event) => {
              event.stopPropagation();
            }}
          >
            <div className="palette__field">
              <span className="palette__prompt" aria-hidden="true">
                ⌕
              </span>
              <input
                ref={inputRef}
                className="palette__input"
                placeholder="Where is my…"
                value={query}
                aria-label="Search remembered objects"
                onChange={(event) => {
                  setQuery(event.target.value);
                  setCursor(0);
                }}
                onKeyDown={(event) => {
                  if (event.key === "ArrowDown") {
                    event.preventDefault();
                    setCursor((value) => Math.min(results.length - 1, value + 1));
                  } else if (event.key === "ArrowUp") {
                    event.preventDefault();
                    setCursor((value) => Math.max(0, value - 1));
                  } else if (event.key === "Enter") {
                    const chosen = results[cursor];
                    if (chosen !== undefined) {
                      commit(chosen.id);
                    }
                  } else if (event.key === "Escape") {
                    setOpen(false);
                  }
                }}
              />
              <kbd className="palette__kbd">esc</kbd>
            </div>
            <ul className="palette__results" role="listbox" aria-label="Matching objects">
              {results.length === 0 && (
                <li className="palette__empty">
                  Nothing remembered matches “{query}”.
                </li>
              )}
              {results.map((record, index) => {
                const present =
                  record.presence === "visible" ||
                  record.presence === "rediscovered";
                return (
                  <li key={record.id}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={index === cursor}
                      className={`palette__row${index === cursor ? " palette__row--active" : ""}`}
                      onMouseEnter={() => {
                        setCursor(index);
                      }}
                      onClick={() => {
                        commit(record.id);
                      }}
                    >
                      <span
                        className="palette__lamp"
                        style={{ background: presenceColor[record.presence] }}
                        aria-hidden="true"
                      />
                      <span className="palette__label">{record.label}</span>
                      <span className="palette__meta">
                        {present
                          ? "currently present"
                          : record.lastVisibleAt !== null
                            ? `last seen ${formatAgo(record.lastVisibleAt)}`
                            : "never observed"}
                        {" · "}
                        {presenceLabel[record.presence]}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <p className="palette__hint">
              ↑↓ to choose · enter jumps the camera and queries the backend
            </p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
