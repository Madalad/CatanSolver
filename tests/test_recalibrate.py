"""Phase 4.2b: isotonic recalibration of the advisor's win-prob."""
from catansolver.eval import Calibrator, fit_isotonic, reliability


def test_isotonic_corrects_underconfidence():
    # raw says 0.5 but the move actually wins 80% -> calibrated ~0.8
    samples = [(0.5, 1.0)] * 80 + [(0.5, 0.0)] * 20
    cal = fit_isotonic(samples)
    assert abs(cal(0.5) - 0.8) < 1e-9


def test_isotonic_is_monotone_and_improves_ece():
    # under-confident at two levels: raw .3 -> .5 actual, raw .6 -> .9 actual
    samples = [(0.3, 1.0)] * 50 + [(0.3, 0.0)] * 50 + [(0.6, 1.0)] * 90 + [(0.6, 0.0)] * 10
    cal = fit_isotonic(samples)
    assert cal(0.3) <= cal(0.6)
    assert abs(cal(0.3) - 0.5) < 1e-9 and abs(cal(0.6) - 0.9) < 1e-9
    raw_ece = reliability(samples).ece
    recal = [(cal(p), o) for p, o in samples]
    assert reliability(recal).ece < raw_ece  # recalibration tightens ECE


def test_isotonic_pools_non_monotone_bins():
    # observed dips (0.8 then 0.7) -> PAVA pools them to a single monotone value
    cal = fit_isotonic([(0.5, 0.8), (0.6, 0.7)], weights=[100, 100])
    assert cal(0.5) == cal(0.6)  # pooled
    assert abs(cal(0.5) - 0.75) < 1e-9  # weighted mean of the violators


def test_interpolates_between_knots_and_clamps():
    cal = fit_isotonic([(0.2, 0.0), (0.8, 1.0)])
    assert cal(0.2) == 0.0 and cal(0.8) == 1.0
    assert abs(cal(0.5) - 0.5) < 1e-9  # midpoint interpolation
    assert cal(0.0) == 0.0 and cal(1.0) == 1.0  # clamp outside range


def test_compression_is_lossless_and_small():
    from catansolver.eval.recalibrate import Calibrator, _compress_knots

    knots = [(0.0, 0.0), (0.1, 0.0), (0.2, 0.0), (0.3, 0.5), (0.4, 1.0), (0.5, 1.0), (0.6, 1.0)]
    comp = _compress_knots(knots)
    full, compact = Calibrator(knots), Calibrator(comp)
    assert len(comp) < len(knots)  # the two flat runs collapse to their endpoints
    for x in (0.0, 0.05, 0.15, 0.25, 0.3, 0.35, 0.45, 0.55, 0.6):
        assert abs(full(x) - compact(x)) < 1e-12  # identical function


def test_fit_output_is_compact():
    # PAVA leaves one knot per tail sample; fit must collapse them
    samples = [(x / 200, 1.0 if x > 100 else 0.0) for x in range(201)] * 4
    cal = fit_isotonic(samples)
    assert len(cal.knots) < 15


def test_calibrator_json_round_trip(tmp_path):
    cal = fit_isotonic([(0.3, 0.0), (0.4, 1.0), (0.7, 1.0)])
    path = tmp_path / "cal.json"
    cal.save(path)
    cal2 = Calibrator.load(path)
    assert all(abs(cal(x) - cal2(x)) < 1e-12 for x in (0.1, 0.3, 0.5, 0.7, 0.9))
