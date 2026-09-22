"""v4: a caveat folds to two lines.

`.list-note` is "a caveat under content that IS there" and `.es-sub`
is the sentence under an empty state's headline. Nineteen of them run
past three lines on a phone; Ethan (2026-09-22): "hard to read all the
data" — the data was under the caveats. Past 160 characters a note
keeps its first two lines and the rest waits behind the same amber
apparatus as why?. Nothing is deleted, and `.ls-note` — on an empty
likelihood board, the whole answer — is never folded.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    body = APP[i:APP.index("\n}\n", i)]
    return re.sub(r"^\s*//.*$", "", body, flags=re.M)


def test_long_caveats_fold_and_short_ones_do_not():
    body = _fn("enhanceNotes")
    assert 'querySelectorAll(".list-note, .es-sub")' in body
    assert "if (text.length <= NOTE_FOLD_CHARS) return;" in body
    assert "const NOTE_FOLD_CHARS = 160;" in APP
    assert 'note.classList.add("note-folded");' in body
    assert "if (note.dataset.noteEnhanced) return;" in body, "re-renders would stack buttons"


def test_the_empty_boards_explanation_is_never_folded():
    body = _fn("enhanceNotes")
    assert ".ls-note" not in body, "an empty likelihood board's only sentence would be hidden"
    assert ".panel-empty" not in body and ".empty-slate" not in body


def test_the_fold_is_the_why_apparatus_and_a_control():
    body = _fn("enhanceNotes")
    assert 'btn.className = "why-toggle note-more";' in body
    assert 'btn.setAttribute("aria-expanded", "false");' in body
    assert 'btn.textContent = folded ? "more" : "less";' in body
    assert "note.after(btn);" in body


def test_it_runs_with_the_sub_enhancer_on_every_render():
    subs = _fn("enhanceSectionSubs")
    assert "enhanceNotes(root);" in subs, "notes drawn by a later render would never fold"
    assert "function watchSectionSubs()" in APP and "enhanceSectionSubs()" in _fn("watchSectionSubs")


def test_the_folded_note_is_two_lines():
    assert ".note-folded { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }" in CSS
    assert ".note-more { display: inline-block;" in CSS


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
