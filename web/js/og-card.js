/* This page's drawing, moved out of an inline <script> by the site audit
   (2026-09-24, M-4): the content policy refuses inline script. */
  /* Coors: the most legible Overhead in the set — a real outfield arc, a
     roof state, an altitude plaque and a park factor, so the drawing is
     visibly carrying data rather than decorating. */
  window.ACTIVE_SPORT = "mlb";
  window.ACTIVE_TEAMS = window.MLB_TEAMS;
  document.getElementById("art").innerHTML = ballpark({
    home: "COL", away: "NYY", roof: "open", surface: "grass",
    park_name: "Coors Field", altitude_ft: 5280, factors: { hr: 1.22 },
  });
