"""Is the stadium art one set of pictures, or several?

Ethan, 2026-08-13, after a cache-bust that fixed a real problem but not
his: "the stadium issue is not fixed."

`variants/` held TWO GENERATIONS — three sharp 1536x1024 neutral singles
and fifteen softer tiles cut out of colour sheets — and `venueVariant`
picks a slot from the home team's kit, so a neutral-kitted club got the
sharp render and a colour-kitted club got a sheet tile, deterministically,
every time. Two cards side by side did not look like the same website.

NOTHING IN THE CHAIN COULD SEE THAT. A person had to notice. The fix at
the time was to serve only the generation we had all of; this module is
the other half — the measurement that would have caught it, and the one
that says when the colours are allowed back.

The strongest test here is `test_the_survey_agrees_with_the_shipped_set`:
run against the real art, the measurement independently arrives at
`{"steel"}`, which is the call a human made by eye on 2026-08-13. Two
unrelated methods, one answer.
"""

import os
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import venueart as va                            # noqa: E402


# --- the JPEG header, parsed by hand because this must stay stdlib ----------
def _jpeg(w, h, pad=0, exif=True):
    """A minimal but structurally real JPEG: SOI, an optional APP1 block,
    then an SOF0 frame header carrying the dimensions."""
    out = b"\xff\xd8"
    if exif:
        # An APP1 segment long enough that a fixed-offset reader would
        # sail straight past the real frame header.
        payload = b"Exif\x00\x00" + b"\x00" * 60
        out += b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
    sof = b"\x08" + struct.pack(">HH", h, w) + b"\x03" + b"\x00" * 9
    out += b"\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof
    out += b"\xff\xda" + b"\x00" * pad
    return out


def _write(path, w, h, kb):
    """A file of the given dimensions padded to roughly ``kb`` kilobytes,
    which is what makes bytes-per-pixel controllable in a test."""
    head = _jpeg(w, h)
    Path(path).write_bytes(head + b"\x00" * max(0, kb * 1024 - len(head)))


def test_the_dimensions_come_out_of_the_frame_header():
    p = os.path.join(tempfile.mkdtemp(), "a.jpg")
    _write(p, 1536, 1024, 10)
    assert va.jpeg_size(p) == (1536, 1024)


def test_a_leading_exif_block_is_walked_past_not_guessed_over():
    """A fixed offset reads a thumbnail's dimensions on some encoders and
    garbage on others. The marker chain is walked."""
    p = os.path.join(tempfile.mkdtemp(), "a.jpg")
    Path(p).write_bytes(_jpeg(800, 600, exif=True))
    assert va.jpeg_size(p) == (800, 600)
    q = os.path.join(tempfile.mkdtemp(), "b.jpg")
    Path(q).write_bytes(_jpeg(800, 600, exif=False))
    assert va.jpeg_size(q) == (800, 600)


def test_a_non_jpeg_is_none_rather_than_an_exception():
    p = os.path.join(tempfile.mkdtemp(), "a.jpg")
    Path(p).write_bytes(b"not a jpeg at all")
    assert va.jpeg_size(p) is None


def test_a_missing_file_is_none():
    assert va.jpeg_size("/nowhere/at/all.jpg") is None
    assert va.describe("/nowhere/at/all.jpg") is None


def test_a_truncated_file_does_not_hang_or_throw():
    p = os.path.join(tempfile.mkdtemp(), "a.jpg")
    Path(p).write_bytes(b"\xff\xd8\xff\xc0\x00")
    assert va.jpeg_size(p) is None


# --- what makes a render off-generation -------------------------------------
REF = {"aspect": 1.5, "pixels": 1536 * 1024, "detail": 0.32}


def test_a_matching_render_has_no_complaints():
    d = {"aspect": 1.5, "pixels": 1536 * 1024, "detail": 0.32}
    assert va._issues(d, REF) == []


def test_a_square_crop_is_caught():
    """THE LOUDEST MISMATCH. The card crops to cover, so a 1:1 source is a
    different composition of a different scene — no amount of tinting or
    sharpening rescues it. Every 2026-08-11 sheet tile failed here."""
    d = {"aspect": 1.03, "pixels": 1536 * 1024, "detail": 0.32}
    issues = va._issues(d, REF)
    assert issues and "aspect" in issues[0]


def test_a_small_render_is_caught():
    d = {"aspect": 1.5, "pixels": int(1536 * 1024 * 0.6), "detail": 0.32}
    assert any("pixels" in i for i in va._issues(d, REF))


def test_a_soft_render_is_caught_even_at_the_right_size():
    """`football-blue` is 1518x1010 at exactly 3:2 — geometrically
    perfect and still visibly softer. Without the detail check it would
    have passed and gone back on the site."""
    d = {"aspect": 1.5, "pixels": 1536 * 1024, "detail": 0.32 * 0.6}
    assert any("detail" in i for i in va._issues(d, REF))


def test_no_reference_means_no_verdict():
    """We cannot call a file off-generation when there is no generation to
    be off. That is a different problem and `survey` reports it as one."""
    assert va._issues({"aspect": 1.0, "pixels": 1, "detail": 0.01}, None) == []


def test_the_detail_measure_is_per_family_not_global():
    """`basketball-steel` carries 0.18 bytes per pixel and `football-blue`
    carries 0.21. Compared globally the soft tile beats the good
    reference — an empty wooden arena simply holds less fine structure
    than a stadium bowl. Each family is judged against its own steel."""
    data = va.survey()
    refs = {f: data["families"][f]["reference"]["detail"] for f in va.FAMILIES}
    assert refs["basketball"] < refs["football"], refs
    # And the cross-family trap is real: basketball's REFERENCE is thinner
    # than football's rejected blue tile.
    fb = data["families"]["football"]["slots"]["blue"]
    assert fb["detail"] > refs["basketball"]
    assert fb["matches"] is False, "the per-family rule stopped working"


# --- against the real art ---------------------------------------------------
def test_the_measurement_reproduces_the_2026_08_13_call():
    """Run on the actual files, the measurement independently arrives at
    exactly the answer Ethan reached by eye on 2026-08-13 — steel alone.
    Two unrelated methods, one result, which is what makes the measurement
    worth trusting at all.

    Note this asserts the MEASUREMENT, not what the site serves. Those are
    allowed to differ; see below."""
    assert va.matched_colours(va.survey()) == ["steel"]


def test_the_site_may_serve_more_than_the_measurement_endorses():
    """2026-08-14: "i want my colored renders back."

    A measurement is evidence, not a veto. Ethan restored all six colours
    knowing the tiles are off-generation, because a board of white
    stadiums was the worse of the two problems — and there is no setting
    that is sharp, consistent AND coloured until fifteen matching renders
    exist.

    So the test asserts the SHAPE of the disagreement rather than
    forbidding it: everything the measurement endorses must be served
    (never withhold art that passes), and anything extra is a documented
    override. A site serving LESS than it could would be a real bug."""
    endorsed = set(va.matched_colours(va.survey()))
    served = set(va.served_by_site())
    assert endorsed <= served, f"art that passes is being withheld: {endorsed - served}"
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    if served - endorsed:
        i = app.index("const VENUE_MATCHED = new Set(")
        note = app[max(0, i - 1400):i]
        assert "RESTORED" in note, \
            "serving unendorsed art with nothing on record saying why"


def test_restoring_the_colours_bumped_the_cache_key():
    """New bytes under an old filename is the one failure nothing else in
    the chain can detect — but so is an old CACHED file under a filename
    whose meaning changed. Every card's venue URL had to miss once for the
    colours to actually appear."""
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    i = app.index("const VENUE_ART_V = ")
    assert '"20260812"' not in app[i:i + 40], \
        "the colours came back but the cache key did not move"


def test_every_family_has_its_reference():
    data = va.survey()
    for family in va.FAMILIES:
        ref = data["families"][family]["reference"]
        assert ref is not None, f"{family} has no {va.REFERENCE} render"
        assert ref["width"] == 1536 and ref["height"] == 1024


def test_all_twenty_four_slots_are_filled():
    """The colours are wrong, not missing. A file that is absent and a
    file that is present-and-off need different fixes, and the probe has
    to tell them apart."""
    data = va.survey()
    assert data["present"] == data["expected"] == 24


def test_the_fifteen_colour_files_are_all_flagged():
    """Every one of them, which is the point — the 2026-08-11 batch is a
    single bad generation, not a couple of unlucky files."""
    data = va.survey()
    bad = [f"{f}-{c}" for f in va.FAMILIES for c in va.COLOURS
           if c != va.REFERENCE and not data["families"][f]["slots"][c]["matches"]]
    assert len(bad) == 15, bad


def test_a_colour_needs_every_family_to_pass():
    """A colour is served site-wide, so one family's soft tile disqualifies
    it everywhere — otherwise a baseball card and a football card on the
    same screen come from different shoots again, which is the original
    complaint."""
    data = va.survey()
    # Pretend football's red became perfect. It still must not be served,
    # because baseball's and basketball's are unchanged.
    data["families"]["football"]["slots"]["red"]["matches"] = True
    data["families"]["football"]["slots"]["red"]["issues"] = []
    assert "red" not in va.matched_colours(data)


def test_a_colour_good_everywhere_would_be_served():
    """The other direction, so the gate is not simply stuck shut."""
    data = va.survey()
    for family in va.FAMILIES:
        slot = data["families"][family]["slots"]["red"]
        slot["matches"], slot["issues"] = True, []
    assert "red" in va.matched_colours(data)


def test_the_missing_list_names_files_and_says_why():
    """A checklist that only counts is a checklist nobody can act on."""
    todo = va.missing(va.survey())
    assert len(todo) == 15
    assert all("variants/" in line and "(" in line for line in todo)


# --- what the probe TELLS you to do -----------------------------------------
def test_a_sheet_in_incoming_is_named_as_a_sheet():
    """Mirrors the ingest's own rule, and the two must agree — this
    module tells a reader what running that tool would do."""
    k = va.classify_incoming(["football-colors.png", "football-red.png",
                              "octagon-sheet.png", "baseball-grid.jpg"])
    assert k["sheets"] == ["football-colors.png", "octagon-sheet.png",
                           "baseball-grid.jpg"]
    assert k["singles"] == ["football-red.png"]


def test_the_already_installed_sources_are_not_offered_as_work():
    """CAUGHT ON ETHAN'S LAPTOP, TWICE.

    The first probe said "Run `python3 tools/venues_ingest.py` to cut and
    install them" about seven files that were the ORIGINAL 2026-08-11
    sources — the sheets whose tiles the same output had just rejected
    fifteen times, three inches higher up the screen.

    The second version learned to say "4 of those are SHEETS" and then
    told him "3 single render(s) ready" about the three `-neutral` files,
    which ARE the steel references already installed. Right
    classification, same useless instruction. So it now checks the target
    slot instead of classifying the filename."""
    t = va.incoming_targets(
        ["baseball-colors.png", "baseball-neutral.png",
         "football-neutral.png"], va.survey())
    assert t["sheets"] == ["baseball-colors.png"]
    assert set(t["noop"]) == {"baseball-neutral.png", "football-neutral.png"}
    assert t["useful"] == [], "already-installed sources offered as work"


def test_real_new_colours_are_offered_as_work():
    """The gate must not be stuck shut — the whole point is to say YES the
    day fifteen good renders land."""
    t = va.incoming_targets(
        ["football-red.png", "baseball-violet.png", "basketball-gold.png"],
        va.survey())
    assert len(t["useful"]) == 3 and not t["noop"]


def test_a_mixed_drop_is_split_three_ways():
    t = va.incoming_targets(
        ["football-red.png", "football-neutral.png", "football-colors.png"],
        va.survey())
    assert t["useful"] == ["football-red.png"]
    assert t["noop"] == ["football-neutral.png"]
    assert t["sheets"] == ["football-colors.png"]


def test_a_file_we_cannot_place_is_left_for_the_tool_to_judge():
    """Guessing "no-op" about a name we do not understand would silently
    hide a render the ingest could have used."""
    t = va.incoming_targets(["mystery.png", "octagon-2.png"], va.survey())
    assert t["useful"] == ["mystery.png", "octagon-2.png"]


def test_the_probe_does_not_offer_a_run_that_would_change_nothing():
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    i = src.index("def show_venues()")
    body = src[i:src.index("\ndef ", i + 1)]
    assert "incoming_targets" in body
    assert "Nothing here to install" in body


# --- the probe and the kit --------------------------------------------------
def test_the_probe_is_wired_into_the_launcher():
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert '"--venues" in argv' in src and "show_venues()" in src


def test_the_probe_points_at_the_switch_and_the_cache_key():
    """Reading a verdict and then hunting for where to apply it is where
    the time goes; hand-translating it into JavaScript is where the
    transcription error lives. So the probe names the constant, offers a
    paste-able line when there IS something to paste, and reminds about
    the cache key."""
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    i = src.index("def show_venues()")
    body = src[i:src.index("\ndef ", i + 1)]
    assert "VENUE_MATCHED" in body
    assert "new Set([" in body, "no paste-able line when art starts passing"
    assert "VENUE_ART_V" in body, "nothing reminds anyone to bust the cache"


def test_the_probe_reports_both_sets_rather_than_assuming_they_match():
    """Once the site can legitimately serve more than the measurement
    endorses, printing one number is a lie by omission — the reader needs
    to see the gap to know it is intentional."""
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    i = src.index("def show_venues()")
    body = src[i:src.index("\ndef ", i + 1)]
    assert "SERVED BY THE SITE" in body and "MEASUREMENT ENDORSES" in body
    assert "served_by_site" in body


def test_the_probe_does_not_nag_about_a_deliberate_override():
    """Ethan restored the colours with the evidence in front of him.
    Repeating "you should change this" every run would be arguing with a
    decision, not reporting a fact."""
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    i = src.index("def show_venues()")
    body = src[i:src.index("\ndef ", i + 1)]
    assert "deliberate choice" in body
    assert "should read" not in body, "the probe is still issuing orders"


def test_the_prompt_pack_exists_and_pins_the_geometry():
    """The square crop was the single loudest failure of the first batch.
    A prompt pack that does not state the aspect ratio invites it back."""
    doc = (ROOT / "docs" / "VENUE_PROMPTS.md").read_text(encoding="utf-8")
    assert "1536x1024" in doc and "3:2" in doc
    assert "floodlight" in doc.lower()
    # The other four failure modes, each named.
    for phrase in ("sky", "sharp", "no text", "keeps its natural colour"):
        assert phrase in doc.lower(), phrase


def test_the_prompt_pack_lists_every_missing_filename():
    doc = (ROOT / "docs" / "VENUE_PROMPTS.md").read_text(encoding="utf-8")
    for family in va.FAMILIES:
        for colour in va.COLOURS:
            if colour == va.REFERENCE:
                continue
            assert f"{family}-{colour}.png" in doc, f"{family}-{colour}"


def test_the_pack_warns_against_generating_a_sheet():
    """The ingest CAN cut sheets, and that ability is what produced the
    problem: a sheet divides one image's pixel budget five ways."""
    doc = (ROOT / "docs" / "VENUE_PROMPTS.md").read_text(encoding="utf-8")
    assert "Do not make a sheet" in doc


def test_the_pack_says_to_bump_the_cache_key():
    """New bytes under an old filename is the one failure nothing in the
    chain can detect, and phones hold image caches longest."""
    doc = (ROOT / "docs" / "VENUE_PROMPTS.md").read_text(encoding="utf-8")
    assert "VENUE_ART_V" in doc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
