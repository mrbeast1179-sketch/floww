"""
Tests for the real volume-spike detector on AlertEngine.

Background: the function `_detect_gex_magnitude_spike` was renamed from
`_detect_volume_spike` because it actually inspects GEX magnitude, not
contract volume. The platform therefore had no real volume-spike detector.

This file pins down the contract for `_detect_volume_spike(current, previous)`:
  * fires when ANY strike within +/- 2% of spot has
        current_volume >= 3 * previous_volume   AND
        current_volume >= 50                    (absolute floor for noise)
  * does NOT fire on illiquid -> moderately liquid jumps
  * does NOT fire on strikes outside the +/- 2% band
  * tolerates missing/empty `volume_by_strike` on either snapshot

The integration test confirms the detector is wired into detect_alerts()
and surfaces a MEDIUM-priority alert with type == "VOLUME_SPIKE".
"""
import pytest

from alert_engine import AlertEngine, GEXSnapshot


def _snap(ticker="SPY", spot=500.0, volume_by_strike=None, regime="POSITIVE"):
    """Build a minimal GEXSnapshot with the right structural defaults.

    The dataclass requires several positional / required fields; we hand the
    detector something realistic so it doesn't trip on unrelated branches.
    """
    return GEXSnapshot(
        ticker=ticker,
        spot_price=spot,
        gamma_flip=spot,            # neutral
        call_wall=spot + 20,
        put_wall=spot - 20,
        max_pain=spot,
        max_gamma_strike=spot,
        total_gex=1.0e9,
        net_gex=1.0e8,
        regime=regime,
        gex_by_strike={spot: 1.0e8},
        volume_by_strike=volume_by_strike or {},
    )


@pytest.fixture
def engine():
    return AlertEngine()


# --------------------------- core detector ---------------------------


def test_volume_spike_fires_on_3x_at_near_spot_strike(engine):
    """Volume tripled at a strike within 2% of spot, with sufficient absolute volume."""
    prev = _snap(volume_by_strike={500.0: 100, 505.0: 200})
    cur  = _snap(volume_by_strike={500.0: 100, 505.0: 800})   # 4x, well above 50 floor
    assert engine._detect_volume_spike(cur, prev) is True


def test_volume_spike_silent_when_previous_was_illiquid(engine):
    """An illiquid -> moderately liquid jump (e.g. 5 -> 25) must NOT trigger.

    Even though 25/5 = 5x, the absolute current volume of 25 is below the 50
    floor — these are exactly the spurious signals the floor exists to kill.
    """
    prev = _snap(volume_by_strike={500.0: 5})
    cur  = _snap(volume_by_strike={500.0: 25})   # 5x ratio, but only 25 contracts
    assert engine._detect_volume_spike(cur, prev) is False


def test_volume_spike_silent_when_strike_is_far_from_spot(engine):
    """A 10x volume jump at a strike more than 2% from spot must NOT trigger."""
    # spot=500 -> 2% band is [490, 510]. 520 is outside the band.
    prev = _snap(spot=500.0, volume_by_strike={520.0: 100})
    cur  = _snap(spot=500.0, volume_by_strike={520.0: 1000})  # 10x, but out-of-band
    assert engine._detect_volume_spike(cur, prev) is False


def test_volume_spike_handles_empty_dicts(engine):
    """Empty / missing volume_by_strike on either side returns False, no exception."""
    prev = _snap(volume_by_strike={})
    cur  = _snap(volume_by_strike={500.0: 1000})
    assert engine._detect_volume_spike(cur, prev) is False

    prev = _snap(volume_by_strike={500.0: 200})
    cur  = _snap(volume_by_strike={})
    assert engine._detect_volume_spike(cur, prev) is False

    prev = _snap(volume_by_strike={})
    cur  = _snap(volume_by_strike={})
    assert engine._detect_volume_spike(cur, prev) is False


# --------------------------- integration: wired into detect_alerts ---------------------------


def test_volume_spike_emits_medium_priority_alert(engine):
    """When the detector fires, detect_alerts() must surface a VOLUME_SPIKE / MEDIUM alert."""
    prev = _snap(volume_by_strike={500.0: 200})
    cur  = _snap(volume_by_strike={500.0: 900})  # 4.5x, above floor
    engine.add_snapshot(prev)
    engine.add_snapshot(cur)

    alerts = engine.detect_alerts("SPY", momentum_score=50)
    spikes = [a for a in alerts if a.type == "VOLUME_SPIKE"]
    assert len(spikes) == 1, f"expected exactly one VOLUME_SPIKE alert, got {[a.type for a in alerts]}"
    assert spikes[0].priority == "MEDIUM"
    assert spikes[0].ticker == "SPY"
