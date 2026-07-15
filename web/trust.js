// docintel — trust/accuracy panel (Story 3.9). Fetches GET /trust over HTTP only
// (AD-15) and renders the proof headline into the native <dialog>. The HTML/
// escaping lives in lib.js `trustPanelHTML` (unit-tested); this owns only the
// fetch + dialog lifecycle.
import { trustPanelHTML } from "/lib.js";

export function wireTrust(openBtn, closeBtn, dialog, body) {
  if (!openBtn || !dialog) return;

  async function open() {
    body.innerHTML = "Loading…";
    // showModal() when available (focus-trapped, Esc-closable); jsdom-less envs fall back.
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    try {
      const res = await fetch("/trust", { headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error(`/trust ${res.status}`);
      body.innerHTML = trustPanelHTML(await res.json());
    } catch (err) {
      // Never leave the panel blank — a legible fallback (the panel must always render).
      body.innerHTML = trustPanelHTML({ source: "placeholder" });
      console.error(err);
    }
  }

  function close() {
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
    openBtn.focus(); // return focus to the affordance that opened it
  }

  openBtn.addEventListener("click", open);
  closeBtn?.addEventListener("click", close);
  // Click on the backdrop (the dialog element itself, outside its content) closes.
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog) close();
  });
}
