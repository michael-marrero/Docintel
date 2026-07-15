// docintel — source drill-down panel (Story 2.3). Owns the sticky 360px source
// panel: it accumulates the brief's cited sources, renders them collapsed, and
// expands one when a citation chip (or a source row) is activated — showing the
// locator, rerank score, and full passage with the supporting span marked
// (UX-DR6, UX-DR8). Esc/re-click collapses back to the `N SOURCES` state.
//
// All HTML building + escaping lives in lib.js `sourcePanelHTML` (unit-tested);
// this controller owns only class-toggling, listeners, and focus.
import { dedupeSources, sourcePanelHTML } from "/lib.js";

export function createPanel(root, { onPin, onDismiss } = {}) {
  let sources = []; // [{cit, score}] unique by chunk_id, first-seen order
  let pinned = null; // pinned chunk_id, or null
  let opener = null; // element to return focus to on dismiss (the prose chip), or null

  const indexOf = (id) => sources.findIndex((s) => s.cit.chunk_id === id);

  function render() {
    const empty = sources.length === 0;
    // The grid gives the panel its column only when it has sources — an empty
    // panel collapses so the brief is full-width (no reserved 360px gutter).
    root.closest(".workspace")?.classList.toggle("panel-open", !empty);
    root.hidden = empty;
    root.innerHTML = empty ? "" : sourcePanelHTML(sources, pinned);
    if (empty) return;

    // Collapsed rows expand on activation (mouse + keyboard, native button).
    for (const b of root.querySelectorAll(".src.collapsed")) {
      b.addEventListener("click", () => setPinned(b.dataset.chunkId, { fromChip: false }));
    }
    // The expanded passage takes focus so keyboard/AT users land on the source.
    if (pinned) root.querySelector("[data-passage]")?.focus();
  }

  function setPinned(id, { fromChip, opener: op } = {}) {
    if (indexOf(id) < 0) return;
    pinned = id;
    opener = op ?? null;
    render();
    if (!fromChip) onPin?.(id); // pinned from a source row → sync the inline chip
  }

  return {
    /** Clear all sources (new brief / view change). */
    reset() {
      sources = [];
      pinned = null;
      opener = null;
      render();
    },
    /** Merge a section's cited sources; `scoresById` is {chunk_id: rerank score}. */
    addCitations(citations, scoresById = {}) {
      for (const cit of dedupeSources(citations)) {
        if (indexOf(cit.chunk_id) < 0) sources.push({ cit, score: scoresById[cit.chunk_id] });
      }
      render();
    },
    /** Pin+expand a source by chunk_id. `opener` is the prose chip to refocus on
     * dismiss (Story 2.3 keyboard flow). */
    pin(id, openerEl) {
      setPinned(id, { fromChip: true, opener: openerEl });
    },
    /** Collapse to the `N SOURCES` state and restore focus — to the opening chip
     * if it's still in the DOM, else the now-collapsed row (focus never lost). */
    dismiss() {
      if (pinned === null) return;
      const prev = pinned;
      pinned = null;
      render();
      const back =
        opener && opener.isConnected
          ? opener
          : root.querySelector(`.src.collapsed[data-chunk-id="${CSS.escape(prev)}"]`);
      back?.focus();
      opener = null;
      onDismiss?.();
    },
    has: (id) => indexOf(id) >= 0,
    get pinnedId() {
      return pinned;
    },
  };
}
