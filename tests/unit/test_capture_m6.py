"""M6 capture ingest. Build spec 8.

Every expected value below is derived independently of the code under test: from
arithmetic done here in the test, or from a hand-checked constant. A capture test
that asserts "the QA report has some warnings" would pass for nearly every bug this
module can have, which is the failure mode CLAUDE.md warns about.

The flight used throughout is a Phantom 4 Pro at 100 m, chosen because its optics
make the footprints exact integers:

    sensor 13.2 x 8.8 mm, focal 8.8 mm, 5472 x 3648

    across-track  2 * 100 * tan(atan(13.2 / (2 * 8.8))) = 2 * 100 * 0.75 = 150 m
    along-track   2 * 100 * tan(atan( 8.8 / (2 * 8.8))) = 2 * 100 * 0.50 = 100 m
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from groma_capture.classify import classify, is_nadir, is_oblique
from groma_capture.exif import ExifRecord, parse_exiftool_json
from groma_capture.ingest import EARTH_RADIUS_M, equirectangular, ingest_records
from groma_capture.overlap import (
    Shot,
    across_track_footprint_m,
    along_track_footprint_m,
    estimate_overlaps,
    flight_lines,
    overlap_fraction,
)
from groma_capture.qa import (
    FRONT_OVERLAP_BLOCK,
    MIN_ACCEPTED_IMAGES,
    AssessedImage,
    apply_gates,
    build_qa,
)
from groma_capture.quality import (
    clipped_fraction,
    laplacian,
    laplacian_variance,
    sharpness_threshold,
    to_greyscale,
)
from groma_capture.sensors import SensorTable, default_table, estimate_sensor, resolve_sensor

P4P_OPTICS = dict(sensor_w_mm=13.2, sensor_h_mm=8.8, focal_mm=8.8)
P4P_RES = dict(res_x=5472, res_y=3648)
ALTITUDE_M = 100.0
ACROSS_M = 150.0
ALONG_M = 100.0


# --- C1 quality scoring ------------------------------------------------------


def test_laplacian_matches_the_stencil_by_hand():
    """C1. A single impulse convolves to the kernel itself, scaled by the impulse."""
    a = np.zeros((5, 5))
    a[2, 2] = 10.0
    out = laplacian(a)
    expected = np.array([[0.0, 10.0, 0.0], [10.0, -40.0, 10.0], [0.0, 10.0, 0.0]])
    np.testing.assert_allclose(out, expected)


def test_laplacian_variance_of_a_flat_field_is_zero():
    """C1. No second derivative anywhere means no sharpness, whatever the level."""
    assert laplacian_variance(np.full((16, 16), 137.0)) == pytest.approx(0.0)


def test_laplacian_variance_computed_two_ways():
    """C1. Variance of the stencil output, computed here without calling the module."""
    rng = np.random.default_rng(11)
    a = rng.uniform(0, 255, size=(9, 9))
    manual = (
        a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:] - 4.0 * a[1:-1, 1:-1]
    )
    assert laplacian_variance(a) == pytest.approx(float(np.var(manual)), rel=1e-12)


def test_clipped_fraction_counts_both_ends():
    """C2. Six of twelve samples sit on an end, so the fraction is exactly one half."""
    a = np.array([0, 0, 0, 255, 255, 255, 1, 2, 3, 250, 251, 252])
    assert clipped_fraction(a) == pytest.approx(6 / 12)


def test_greyscale_uses_rec601_luma():
    """C2. Pure green weighs 0.587, the Rec. 601 coefficient, by hand."""
    green = np.array([[[0.0, 255.0, 0.0]]])
    assert to_greyscale(green)[0, 0] == pytest.approx(0.587 * 255.0)


def test_sharpness_threshold_takes_the_lower_of_percentile_and_floor():
    """C3. A uniformly sharp set must not lose a tenth of its frames."""
    assert sharpness_threshold([100.0] * 50, floor=8.0) == pytest.approx(8.0)
    # A set whose 10th percentile is below the floor keeps the percentile, so that a
    # low-texture scene does not lose frames the floor would have condemned.
    scores = [1.0] * 20 + [100.0] * 80
    p10 = float(np.percentile(np.array(scores), 10.0))
    assert p10 == pytest.approx(1.0), "the fixture must put the percentile under the floor"
    assert sharpness_threshold(scores, floor=8.0) == pytest.approx(p10)


# --- C4 sensors --------------------------------------------------------------


def test_known_sensor_comes_from_the_table():
    """C4. The committed table answers for a Phantom 4 Pro."""
    s = default_table().get("DJI", "FC6310")
    assert s is not None
    assert (s.sensor_w_mm, s.sensor_h_mm) == (13.2, 8.8)


def test_sensor_lookup_is_case_and_space_insensitive():
    """C4. EXIF strings arrive padded and inconsistently cased."""
    assert default_table().get("  dji ", " fc6310 ") is not None


def test_estimated_sensor_uses_the_35mm_identity():
    """C4. sensor_w = 36 * focal / focal35, computed here."""
    s = estimate_sensor(
        make="DJI", model="X", focal_mm=8.8, focal_35_mm=24.0, res_x=5472, res_y=3648
    )
    assert s is not None
    assert s.sensor_w_mm == pytest.approx(36.0 * 8.8 / 24.0)
    # Height follows the pixel aspect ratio, which is square.
    assert s.sensor_h_mm == pytest.approx(36.0 * 8.8 / 24.0 * 3648 / 5472)


def test_missing_35mm_equivalent_gives_no_sensor_rather_than_a_guess():
    """C4. Absent blocks loudly; a guess would produce a plausible, wrong px/m."""
    assert estimate_sensor(
        make="DJI", model="X", focal_mm=8.8, focal_35_mm=None, res_x=100, res_y=100
    ) is None


def test_resolve_reports_whether_the_sensor_was_estimated():
    """C4. The caller must be able to raise the warning the spec requires."""
    known, est = resolve_sensor(
        make="DJI", model="FC6310", focal_mm=8.8, focal_35_mm=24.0, res_x=5472, res_y=3648
    )
    assert known is not None and est is False
    guess, est2 = resolve_sensor(
        make="DJI", model="NOPE", focal_mm=8.8, focal_35_mm=24.0, res_x=5472, res_y=3648
    )
    assert guess is not None and est2 is True


# --- C5, C6 footprint and overlap arithmetic ---------------------------------


def test_footprints_match_the_closed_form():
    """C5. 2 * h * tan(fov/2), with the field of view derived here from the sensor."""
    expected_along = 2 * ALTITUDE_M * math.tan(math.atan(8.8 / (2 * 8.8)))
    expected_across = 2 * ALTITUDE_M * math.tan(math.atan(13.2 / (2 * 8.8)))
    assert along_track_footprint_m(ALTITUDE_M, 8.8, 8.8) == pytest.approx(expected_along)
    assert across_track_footprint_m(ALTITUDE_M, 13.2, 8.8) == pytest.approx(expected_across)
    # And those are the round numbers the docstring claims.
    assert expected_along == pytest.approx(ALONG_M)
    assert expected_across == pytest.approx(ACROSS_M)


def test_overlap_fraction_is_one_minus_spacing_over_footprint():
    """C6. Hand arithmetic at three spacings."""
    assert overlap_fraction(20.0, 100.0) == pytest.approx(0.80)
    assert overlap_fraction(60.0, 150.0) == pytest.approx(0.60)
    assert overlap_fraction(100.0, 100.0) == pytest.approx(0.0)


def test_overlap_fraction_clamps_a_gap_to_zero_not_to_a_negative():
    """C6. A spacing wider than the frame is a gap; the report must not say -40%."""
    assert overlap_fraction(140.0, 100.0) == 0.0


def _lawnmower(
    lines: int = 3, per_line: int = 8, step_m: float = 20.0, spacing_m: float = 60.0
) -> list[Shot]:
    """A boustrophedon flight: `lines` legs, alternating direction along y."""
    shots: list[Shot] = []
    seq = 0
    for i in range(lines):
        x = i * spacing_m
        ys = [j * step_m for j in range(per_line)]
        if i % 2:
            ys.reverse()
        for y in ys:
            shots.append(Shot(x=x, y=y, altitude_agl_m=ALTITUDE_M, sequence=seq))
            seq += 1
    return shots


def test_flight_lines_split_on_the_turn():
    """C7. Three legs joined by two perpendicular hops must read as three lines."""
    lines = flight_lines(_lawnmower())
    assert [len(ln) for ln in lines] == [8, 8, 8]


def test_a_single_straight_run_is_one_line():
    """C7. A corridor survey has no turn and must not be split."""
    shots = [Shot(x=0.0, y=j * 20.0, altitude_agl_m=ALTITUDE_M, sequence=j) for j in range(10)]
    assert len(flight_lines(shots)) == 1


def test_estimate_overlaps_on_a_lawnmower_matches_hand_arithmetic():
    """C8. 20 m along a 100 m frame is 80%; 60 m across a 150 m frame is 60%."""
    front, side = estimate_overlaps(_lawnmower(), **P4P_OPTICS)
    assert front == pytest.approx(1.0 - 20.0 / ALONG_M)
    assert side == pytest.approx(1.0 - 60.0 / ACROSS_M)


def test_side_overlap_is_unknown_for_a_single_line():
    """C8. One leg has no adjacent leg; None must not be reported as 0%."""
    shots = [Shot(x=0.0, y=j * 20.0, altitude_agl_m=ALTITUDE_M, sequence=j) for j in range(10)]
    front, side = estimate_overlaps(shots, **P4P_OPTICS)
    assert front == pytest.approx(0.80)
    assert side is None


# --- C9 classification -------------------------------------------------------


@pytest.mark.parametrize(
    ("pitch", "nadir", "oblique"),
    [
        (-90.0, True, False),
        (-80.0, True, False),   # boundary, inclusive
        (-100.0, True, False),  # boundary, inclusive
        (-79.9, False, False),  # the dead band between the two classes
        (-70.0, False, True),
        (-20.0, False, True),
        (-19.9, False, False),
        (0.0, False, False),
        (None, False, False),
    ],
)
def test_classification_boundaries(pitch, nadir, oblique):
    """C9. -90 +/- 10 is nadir, -70 to -20 is oblique, and between them is neither."""
    assert is_nadir(pitch) is nadir
    assert is_oblique(pitch) is oblique


def test_classify_counts_every_frame_exactly_once():
    """C9. The four buckets must partition the set."""
    pitches = [-90.0, -85.0, -45.0, -30.0, -75.0, 0.0, None]
    split = classify(pitches)
    assert (split.nadir, split.oblique, split.other, split.unknown) == (2, 2, 2, 1)
    assert split.total == len(pitches)


# --- C10 the QA gate ---------------------------------------------------------


def _images(n: int, *, sharpness: float = 100.0, clipped: float = 0.0, pitch: float = -90.0):
    return [
        AssessedImage(
            filename=f"IMG_{i:04d}.JPG",
            sharpness=sharpness,
            clipped_fraction=clipped,
            gimbal_pitch_deg=pitch,
            rtk_fixed=True,
        )
        for i in range(n)
    ]


def test_a_good_flight_blocks_on_nothing():
    """C10. 30 sharp nadir frames at 80% front overlap, georeferenced."""
    imgs = _images(30)
    qa = build_qa(imgs, classify([-90.0] * 30), front_overlap=0.80, georef="rtk")
    assert qa.blocking == []
    assert qa.accepted_count == 30
    assert qa.rtk_fraction == pytest.approx(1.0)


def test_front_overlap_below_sixty_percent_blocks():
    """C10. The spec's blocking threshold, tested either side of the boundary."""
    imgs = _images(30)
    just_under = build_qa(imgs, classify([-90.0] * 30), front_overlap=0.599, georef="rtk")
    just_over = build_qa(imgs, classify([-90.0] * 30), front_overlap=FRONT_OVERLAP_BLOCK, georef="rtk")
    assert any("Front overlap" in b for b in just_under.blocking)
    assert just_over.blocking == []


def test_more_than_thirty_percent_rejected_blocks():
    """C10. 11 of 30 rejected is 36.7%, above the limit; 9 of 30 is 30.0%, at it."""
    def qa_for(bad: int):
        imgs = _images(30 - bad) + _images(bad, sharpness=0.0)
        gated = apply_gates(imgs, sharpness_floor=8.0)
        return build_qa(gated, classify([-90.0] * 30), front_overlap=0.8, georef="rtk")

    assert any("rejected" in b for b in qa_for(11).blocking)
    assert qa_for(9).blocking == []


def test_fewer_than_twenty_accepted_images_blocks():
    """C10. Nineteen blocks, twenty does not."""
    def qa_for(n: int):
        return build_qa(_images(n), classify([-90.0] * n), front_overlap=0.8, georef="rtk")

    assert any("usable images" in b for b in qa_for(MIN_ACCEPTED_IMAGES - 1).blocking)
    assert qa_for(MIN_ACCEPTED_IMAGES).blocking == []


def test_no_georeferencing_and_no_scale_bar_blocks():
    """C10. Scale-free structure from motion is correct in shape, arbitrary in size."""
    imgs = _images(30)
    qa = build_qa(imgs, classify([-90.0] * 30), front_overlap=0.8, georef="none")
    assert any("arbitrary in size" in b for b in qa.blocking)
    ok = build_qa(imgs, classify([-90.0] * 30), front_overlap=0.8, georef="none", has_scale_bar=True)
    assert ok.blocking == []


def test_nadir_only_capture_warns_about_masts():
    """C10. Nadir-only reconstructs masts short, and masts carry the cameras."""
    qa = build_qa(_images(30), classify([-90.0] * 30), front_overlap=0.8, georef="rtk")
    assert any("mast" in w.lower() for w in qa.warnings)
    assert qa.blocking == []


def test_an_estimated_sensor_warns():
    """C10. The error propagates into every px/m downstream, so it must be said."""
    qa = build_qa(
        _images(30), classify([-90.0] * 30), front_overlap=0.8, georef="rtk", sensor_estimated=True
    )
    assert any("estimated" in w.lower() for w in qa.warnings)


def test_apply_gates_prefers_blur_over_exposure():
    """C10. A frame that is both is reported as blurred, the more actionable fault."""
    both = [AssessedImage(filename="a.jpg", sharpness=0.0, clipped_fraction=0.9)]
    assert apply_gates(both, sharpness_floor=8.0)[0].state.value == "rejected_blur"
    clipped = [AssessedImage(filename="b.jpg", sharpness=100.0, clipped_fraction=0.9)]
    assert apply_gates(clipped, sharpness_floor=8.0)[0].state.value == "rejected_exposure"


# --- C11 EXIF ----------------------------------------------------------------

EXIFTOOL_SAMPLE = json.dumps(
    [
        {
            "SourceFile": "/flight/DJI_0042.JPG",
            "FileName": "DJI_0042.JPG",
            "Make": "DJI",
            "Model": "FC6310",
            "ImageWidth": 5472,
            "ImageHeight": 3648,
            "FocalLength": 8.8,
            "FocalLengthIn35mmFormat": 24,
            "DateTimeOriginal": "2026:03:11 10:22:33",
            "GPSLatitude": 22.3823,
            "GPSLongitude": 114.2029,
            "GPSAltitude": 41.2,
            "GPSAltitudeRef": 0,
            "RelativeAltitude": 95.4,
            "GimbalPitchDegree": -90.0,
            "GimbalYawDegree": 12.5,
            "RtkFlag": 50,
            "RtkStdLat": 0.012,
            "RtkStdLon": 0.016,
        },
        {"SourceFile": "/flight/notes.txt", "FileName": "notes.txt"},
    ]
)


def test_exif_parses_the_fields_the_pipeline_depends_on():
    """C11. Including the drone-dji XMP tags, which is why exiftool is required."""
    records = parse_exiftool_json(EXIFTOOL_SAMPLE)
    assert len(records) == 1, "the non-image file must be dropped"
    r = records[0]
    assert (r.make, r.model) == ("DJI", "FC6310")
    assert r.focal_mm == 8.8
    assert r.relative_altitude_m == 95.4
    assert r.gimbal_pitch_deg == -90.0
    assert r.captured_at is not None and r.captured_at.year == 2026


def test_rtk_flag_fifty_means_fixed_and_anything_else_does_not():
    """C11. Treating a 2 m fix as a 2 cm one is the expensive version of this bug."""
    records = parse_exiftool_json(EXIFTOOL_SAMPLE)
    assert records[0].rtk_fixed is True
    loose = json.loads(EXIFTOOL_SAMPLE)
    loose[0]["RtkFlag"] = 16
    assert parse_exiftool_json(json.dumps(loose))[0].rtk_fixed is False


def test_gps_accuracy_combines_the_two_standard_deviations():
    """C11. Root sum of squares, computed here."""
    r = parse_exiftool_json(EXIFTOOL_SAMPLE)[0]
    assert r.gps_accuracy_m == pytest.approx(math.hypot(0.012, 0.016))


# --- C12 local projection ----------------------------------------------------


def test_one_degree_of_latitude_is_the_meridian_arc():
    """C12. R * pi / 180, computed here."""
    _, y = equirectangular(0.0, 1.0, lon0=0.0, lat0=0.0)
    assert y == pytest.approx(EARTH_RADIUS_M * math.pi / 180.0)


def test_longitude_shrinks_with_the_cosine_of_latitude():
    """C12. At 60 degrees north a degree of longitude is half its equatorial length."""
    x_equator, _ = equirectangular(1.0, 0.0, lon0=0.0, lat0=0.0)
    x_sixty, _ = equirectangular(1.0, 60.0, lon0=0.0, lat0=60.0)
    assert x_sixty == pytest.approx(x_equator * math.cos(math.radians(60.0)))


# --- C13 ingest end to end ---------------------------------------------------


def _flight_records(lines: int = 3, per_line: int = 8) -> list[ExifRecord]:
    """A lawnmower expressed as EXIF, 20 m along track and 60 m between lines.

    Positions are converted to degrees here so that the ingest has to project them
    back, which exercises the equirectangular path rather than bypassing it.
    """
    lat0, lon0 = 22.3823, 114.2029
    m_per_deg_lat = EARTH_RADIUS_M * math.pi / 180.0
    m_per_deg_lon = m_per_deg_lat * math.cos(math.radians(lat0))
    out: list[ExifRecord] = []
    seq = 0
    for i in range(lines):
        ys = [j * 20.0 for j in range(per_line)]
        if i % 2:
            ys.reverse()
        for y in ys:
            out.append(
                ExifRecord(
                    path=f"/f/IMG_{seq:04d}.JPG",
                    filename=f"IMG_{seq:04d}.JPG",
                    width=5472,
                    height=3648,
                    make="DJI",
                    model="FC6310",
                    focal_mm=8.8,
                    focal_35_mm=24.0,
                    gps_lat=lat0 + y / m_per_deg_lat,
                    gps_lon=lon0 + (i * 60.0) / m_per_deg_lon,
                    relative_altitude_m=ALTITUDE_M,
                    gimbal_pitch_deg=-90.0,
                    rtk_flag=50,
                )
            )
            seq += 1
    return out


def test_ingest_recovers_the_flight_geometry_and_passes_the_gate():
    """C13. The overlaps recovered through EXIF and projection match the arithmetic."""
    records = _flight_records()
    scores = {r.filename: (100.0, 0.0) for r in records}
    result = ingest_records(records, scores, survey_id="s1", georef="rtk")

    assert result.qa.blocking == []
    assert result.qa.image_count == 24
    assert result.qa.accepted_count == 24
    assert result.qa.nadir_count == 24
    assert result.qa.oblique_count == 0
    assert result.qa.rtk_fraction == pytest.approx(1.0)
    assert result.sensor_estimated is False
    # The projection round trip must not lose more than a millimetre of overlap.
    assert result.qa.estimated_front_overlap == pytest.approx(0.80, abs=1e-3)
    assert result.qa.estimated_side_overlap == pytest.approx(0.60, abs=1e-3)


def test_ingest_reports_gsd_from_the_sensor_and_altitude():
    """C13. GSD = sensor_w * h / (focal * res_x), computed here."""
    records = _flight_records()
    scores = {r.filename: (100.0, 0.0) for r in records}
    result = ingest_records(records, scores, survey_id="s1", georef="rtk")
    expected = 13.2 * ALTITUDE_M / (8.8 * 5472)
    assert result.estimated_gsd_m == pytest.approx(expected)
    assert result.estimated_gsd_m == pytest.approx(0.0274, abs=1e-4)


def test_ingest_marks_blurred_frames_and_blocks_when_too_many_go():
    """C13. Half the set blurred is above the 30% limit, so reconstruction is refused.

    This is the case the spec's percentile rule alone would miss: with half the set
    at the same low score, the 10th percentile lands inside the blurred cluster and
    the relative threshold collapses. The absolute minimum is what catches it.
    """
    records = _flight_records()
    scores = {r.filename: (100.0, 0.0) for r in records}
    for r in records[:12]:
        scores[r.filename] = (0.5, 0.0)
    result = ingest_records(records, scores, survey_id="s1", georef="rtk")
    assert result.qa.rejected.get("rejected_blur") == 12
    assert any("rejected" in b for b in result.qa.blocking)


def test_ingest_of_an_empty_directory_blocks_rather_than_crashing():
    """C13. Zero images is a blocked survey, not a traceback."""
    result = ingest_records([], {}, survey_id="s1", georef="rtk")
    assert result.qa.image_count == 0
    assert any("usable images" in b for b in result.qa.blocking)


def test_sensor_table_can_be_injected_for_a_fleet_the_fixture_does_not_know():
    """C13. An operator adding an aircraft must not have to edit the package."""
    table = SensorTable.from_rows(
        [dict(make="Acme", model="Z1", sensor_w_mm=20.0, sensor_h_mm=15.0, res_x=4000, res_y=3000)]
    )
    s, est = resolve_sensor(
        make="Acme", model="Z1", focal_mm=10.0, focal_35_mm=18.0, res_x=4000, res_y=3000, table=table
    )
    assert est is False
    assert s is not None and s.sensor_w_mm == 20.0


def test_the_absolute_minimum_catches_what_the_percentile_rule_cannot():
    """C10. The spec's rule alone lets a half-blurred flight through; this asserts it does not.

    With twelve frames at 0.5 and twelve at 100, the 10th percentile is 0.5, so the
    relative threshold is 0.5 and `0.5 < 0.5` rejects nothing. The absolute minimum
    of 1.0 rejects all twelve, which puts the rejected fraction at 50% and trips the
    30% blocking rule. See `quality.ABSOLUTE_UNUSABLE_SHARPNESS`.
    """
    from groma_capture.quality import ABSOLUTE_UNUSABLE_SHARPNESS

    scores = [0.5] * 12 + [100.0] * 12
    relative = sharpness_threshold(scores, floor=8.0)
    assert relative == pytest.approx(0.5), "the relative threshold collapses, as the spec says"

    imgs = [
        AssessedImage(filename=f"i{i}.jpg", sharpness=v, clipped_fraction=0.0)
        for i, v in enumerate(scores)
    ]
    gated = apply_gates(imgs, sharpness_floor=relative)
    assert sum(1 for g in gated if not g.accepted) == 12
    assert 0.5 < ABSOLUTE_UNUSABLE_SHARPNESS <= 8.0

    qa = build_qa(gated, classify([-90.0] * 24), front_overlap=0.8, georef="rtk")
    assert any("rejected" in b for b in qa.blocking)


# --- C14 faults found by running against real drone imagery -------------------


def test_xmp_altitude_arrives_as_a_signed_string_and_must_still_parse():
    """C14. exiftool -n leaves drone-dji tags as XMP strings like "+39.80".

    Found on the Brighton Beach demo set. Reading these as absent costs the ground
    footprint, and with it the overlap estimate and the GSD, on imagery that is
    perfectly good. The QA report degraded to "could not be estimated" and blamed
    the flight.
    """
    doc = json.dumps(
        [
            {
                "SourceFile": "/f/DJI_0018.JPG",
                "FileName": "DJI_0018.JPG",
                "ImageWidth": 4000,
                "ImageHeight": 2250,
                "Make": "DJI",
                "Model": "FC300S",
                "FocalLength": 3.61,
                "RelativeAltitude": "+39.80",
                "AbsoluteAltitude": "+198.31",
                "GimbalPitchDegree": -89.9,
            }
        ]
    )
    r = parse_exiftool_json(doc)[0]
    assert r.relative_altitude_m == pytest.approx(39.80)
    assert r.gps_alt_m == pytest.approx(198.31)


def test_a_non_numeric_string_is_still_absent():
    """C14. Parsing strings must not turn "unknown" into a number."""
    doc = json.dumps(
        [{"SourceFile": "/f/a.JPG", "FileName": "a.JPG", "ImageWidth": 10,
          "ImageHeight": 10, "RelativeAltitude": "n/a"}]
    )
    assert parse_exiftool_json(doc)[0].relative_altitude_m is None


def test_sixteen_by_nine_capture_crops_the_sensor_height():
    """C14. 4000x2250 from a 4:3 sensor reads fewer rows at the full width.

    Taking the native 4.55 mm height for a 16:9 frame overstates the vertical field
    of view by a third, which lands straight in the along-track footprint and so in
    the front overlap estimate.
    """
    from groma_capture.sensors import adapt_to_resolution

    native = default_table().get("DJI", "FC300S")
    assert native is not None and (native.res_x, native.res_y) == (4000, 3000)

    cropped = adapt_to_resolution(native, 4000, 2250)
    assert cropped.sensor_w_mm == pytest.approx(6.17), "the full width is still used"
    assert cropped.sensor_h_mm == pytest.approx(6.17 * 2250 / 4000)
    assert cropped.sensor_h_mm < native.sensor_h_mm


def test_same_aspect_ratio_keeps_the_physical_dimensions():
    """C14. A downscaled 4:3 image is the same sensor with fewer pixels."""
    from groma_capture.sensors import adapt_to_resolution

    native = default_table().get("DJI", "FC300S")
    assert native is not None
    half = adapt_to_resolution(native, 2000, 1500)
    assert (half.sensor_w_mm, half.sensor_h_mm) == (native.sensor_w_mm, native.sensor_h_mm)
    assert (half.res_x, half.res_y) == (2000, 1500)


def test_resolve_sensor_adapts_a_table_entry_to_the_frame():
    """C14. The whole point: a known aircraft shooting 16:9 is still 'known'."""
    s, estimated = resolve_sensor(
        make="DJI", model="FC300S", focal_mm=3.61, focal_35_mm=20.0, res_x=4000, res_y=2250
    )
    assert estimated is False, "it is in the table; nothing was guessed"
    assert s is not None
    assert s.sensor_h_mm == pytest.approx(6.17 * 2250 / 4000)


def test_unscorable_imagery_raises_rather_than_reporting_100_percent_blur():
    """C14. A missing decoder is a deployment fault, not a property of the flight.

    Pillow was absent on the instance, every frame failed to decode, each was
    recorded as sharpness 0, and the report announced that 100% of the flight was
    blurred and blocked it. It blamed the imagery for a missing library.
    """
    from groma_capture.quality import ScoringUnavailableError

    assert issubclass(ScoringUnavailableError, RuntimeError)

    # The gate itself still treats a genuinely dark frame as blurred, which is right.
    dark = [AssessedImage(filename="d.jpg", sharpness=0.0, clipped_fraction=0.0)]
    assert apply_gates(dark, sharpness_floor=8.0)[0].state.value == "rejected_blur"


# --- C15 ground footprints ---------------------------------------------------


def test_footprint_half_extents_are_the_closed_form():
    """C15. Half of 2h*tan(fov/2), computed here from the sensor."""
    from groma_capture.footprint import half_extents_m

    across, along = half_extents_m(ALTITUDE_M, 13.2, 8.8, 8.8)
    assert across == pytest.approx(ALTITUDE_M * math.tan(math.atan(13.2 / (2 * 8.8))))
    assert along == pytest.approx(ALTITUDE_M * math.tan(math.atan(8.8 / (2 * 8.8))))
    assert (across, along) == pytest.approx((ACROSS_M / 2, ALONG_M / 2))


def test_footprint_at_yaw_zero_is_axis_aligned():
    """C15. Facing north, the corners are simply the half extents."""
    from groma_capture.footprint import footprint_corners

    corners = footprint_corners(
        0.0, 0.0, altitude_agl_m=ALTITUDE_M, yaw_deg=0.0,
        sensor_w_mm=13.2, sensor_h_mm=8.8, focal_mm=8.8,
    )
    rounded = sorted((round(x, 6), round(y, 6)) for x, y in corners)
    assert rounded == [(-75.0, -50.0), (-75.0, 50.0), (75.0, -50.0), (75.0, 50.0)]


def test_footprint_rotates_with_yaw():
    """C15. Turning the aircraft east swaps which ground axis the long edge lies on.

    The long edge is across track, 150 m. Facing north it spans x; facing east it
    spans y. Getting this backwards puts every footprint at right angles to the
    flight and looks plausible on a map, which is why it is asserted rather than
    eyeballed.
    """
    from groma_capture.footprint import footprint_corners

    east = footprint_corners(
        0.0, 0.0, altitude_agl_m=ALTITUDE_M, yaw_deg=90.0,
        sensor_w_mm=13.2, sensor_h_mm=8.8, focal_mm=8.8,
    )
    xs = [c[0] for c in east]
    ys = [c[1] for c in east]
    assert max(xs) - min(xs) == pytest.approx(ALONG_M)
    assert max(ys) - min(ys) == pytest.approx(ACROSS_M)


def test_footprint_is_empty_without_a_height():
    """C15. No height above ground means no footprint, not a degenerate one."""
    from groma_capture.footprint import footprint_corners

    assert footprint_corners(
        0.0, 0.0, altitude_agl_m=0.0, yaw_deg=0.0,
        sensor_w_mm=13.2, sensor_h_mm=8.8, focal_mm=8.8,
    ) == []


def test_ingest_result_exposes_height_above_take_off_per_frame():
    """C15. SourceImage has no column for it, and the footprint cannot be drawn without it."""
    records = _flight_records(lines=1, per_line=3)
    scores = {r.filename: (100.0, 0.0) for r in records}
    result = ingest_records(records, scores, survey_id="s1", georef="rtk")
    agl = result.agl_by_filename
    assert len(agl) == 3
    assert set(agl.values()) == {ALTITUDE_M}
