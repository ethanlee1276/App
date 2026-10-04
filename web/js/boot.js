/* Decided BEFORE first paint, or the full masthead renders and then
   collapses — a 790px jump on every load. A file rather than an inline
   <script> since the site audit (2026-09-24, M-4): the content policy
   refuses inline script, and this is loaded in <head>, blocking, exactly
   where the inline block ran. */
try {
  if (localStorage.getItem("qb-seen-intro"))
    document.documentElement.classList.add("intro-seen");
} catch (e) {}
