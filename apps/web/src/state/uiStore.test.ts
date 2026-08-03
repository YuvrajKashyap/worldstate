import { beforeEach, describe, expect, it } from "vitest";

import { useUiStore } from "./uiStore";

describe("uiStore", () => {
  beforeEach(() => {
    useUiStore.setState({
      selectedEntityId: null,
      pinnedEntityIds: [],
      hiddenEntityIds: [],
      layers: { ghosts: true, graph: false, uncertainty: true, labels: true },
      timelineMode: "live",
      scrubTime: null,
      searchOpen: false,
      helpOpen: false,
      evidenceOpen: false,
      scanPanelOpen: false,
      holoActive: false,
      focusRequest: null,
    });
  });

  it("selects and clears entities, closing evidence on deselect", () => {
    const store = useUiStore.getState();
    store.select("a");
    useUiStore.getState().setEvidenceOpen(true);
    useUiStore.getState().select(null);
    const state = useUiStore.getState();
    expect(state.selectedEntityId).toBeNull();
    expect(state.evidenceOpen).toBe(false);
  });

  it("toggles pin and hidden lists idempotently", () => {
    const store = useUiStore.getState();
    store.togglePin("a");
    store.togglePin("b");
    useUiStore.getState().togglePin("a");
    expect(useUiStore.getState().pinnedEntityIds).toEqual(["b"]);

    useUiStore.getState().toggleHidden("x");
    useUiStore.getState().toggleHidden("x");
    expect(useUiStore.getState().hiddenEntityIds).toEqual([]);
  });

  it("toggles view layers independently", () => {
    useUiStore.getState().toggleLayer("graph");
    expect(useUiStore.getState().layers.graph).toBe(true);
    expect(useUiStore.getState().layers.ghosts).toBe(true);
  });

  it("clears scrub time when returning to live", () => {
    useUiStore.getState().setTimeline("scrub", 12345);
    expect(useUiStore.getState().scrubTime).toBe(12345);
    useUiStore.getState().setTimeline("live");
    expect(useUiStore.getState().scrubTime).toBeNull();
  });

  it("focus requests select the entity and stamp a version", () => {
    useUiStore.getState().requestFocus("entity-1");
    const state = useUiStore.getState();
    expect(state.selectedEntityId).toBe("entity-1");
    expect(state.focusRequest?.entityId).toBe("entity-1");
  });
});
