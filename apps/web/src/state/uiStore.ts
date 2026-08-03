/** Interface state: selection, view layers, timeline, overlays. */

import { create } from "zustand";

export type ViewLayers = {
  ghosts: boolean;
  graph: boolean;
  uncertainty: boolean;
  labels: boolean;
};

export type TimelineMode = "live" | "scrub";

export type UiState = {
  selectedEntityId: string | null;
  pinnedEntityIds: string[];
  hiddenEntityIds: string[];
  layers: ViewLayers;
  timelineMode: TimelineMode;
  /** Scrub position in ms since epoch; null while live. */
  scrubTime: number | null;
  searchOpen: boolean;
  helpOpen: boolean;
  evidenceOpen: boolean;
  scanPanelOpen: boolean;
  holoActive: boolean;
  focusRequest: { entityId: string; at: number } | null;
  select: (entityId: string | null) => void;
  togglePin: (entityId: string) => void;
  toggleHidden: (entityId: string) => void;
  toggleLayer: (layer: keyof ViewLayers) => void;
  setTimeline: (mode: TimelineMode, scrubTime?: number | null) => void;
  setSearchOpen: (open: boolean) => void;
  setHelpOpen: (open: boolean) => void;
  setEvidenceOpen: (open: boolean) => void;
  setScanPanelOpen: (open: boolean) => void;
  setHoloActive: (active: boolean) => void;
  requestFocus: (entityId: string) => void;
};

export const useUiStore = create<UiState>((set) => ({
  selectedEntityId: null,
  pinnedEntityIds: [],
  hiddenEntityIds: [],
  // Uncertainty is an analytical overlay, not the default atmosphere. Keep
  // the primary world view crisp and reveal uncertainty on demand.
  layers: { ghosts: true, graph: false, uncertainty: false, labels: true },
  timelineMode: "live",
  scrubTime: null,
  searchOpen: false,
  helpOpen: false,
  evidenceOpen: false,
  scanPanelOpen: false,
  holoActive: false,
  focusRequest: null,

  select(entityId) {
    set((state) => ({
      selectedEntityId: entityId,
      evidenceOpen: entityId === null ? false : state.evidenceOpen,
    }));
  },
  togglePin(entityId) {
    set((state) => ({
      pinnedEntityIds: state.pinnedEntityIds.includes(entityId)
        ? state.pinnedEntityIds.filter((id) => id !== entityId)
        : [...state.pinnedEntityIds, entityId],
    }));
  },
  toggleHidden(entityId) {
    set((state) => ({
      hiddenEntityIds: state.hiddenEntityIds.includes(entityId)
        ? state.hiddenEntityIds.filter((id) => id !== entityId)
        : [...state.hiddenEntityIds, entityId],
    }));
  },
  toggleLayer(layer) {
    set((state) => ({
      layers: { ...state.layers, [layer]: !state.layers[layer] },
    }));
  },
  setTimeline(mode, scrubTime = null) {
    set({ timelineMode: mode, scrubTime: mode === "live" ? null : scrubTime });
  },
  setSearchOpen(open) {
    set({ searchOpen: open });
  },
  setHelpOpen(open) {
    set({ helpOpen: open });
  },
  setEvidenceOpen(open) {
    set({ evidenceOpen: open });
  },
  setScanPanelOpen(open) {
    set({ scanPanelOpen: open });
  },
  setHoloActive(active) {
    set({ holoActive: active });
  },
  requestFocus(entityId) {
    set({ focusRequest: { entityId, at: Date.now() }, selectedEntityId: entityId });
  },
}));
