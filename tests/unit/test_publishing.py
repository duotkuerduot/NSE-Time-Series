"""Publishing helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime

import numpy as np
import pytest

from nsefc.api import v1
from nsefc.publishing.build import forecast_prices


@pytest.mark.parametrize("seed", range(5))
def test_forecast_prices_always_satisfy_the_contract(seed: int) -> None:
    rng = np.random.default_rng(seed)
    for _ in range(200):
        close = float(rng.choice([0.317, 1.0049, 10.0049, 28.4567, 389.999, 2500.125]))
        point = float(rng.normal(0, 0.03))
        prices = forecast_prices(close, point, point - 0.02, point + 0.02)
        v1.ForecastLatest.model_validate(
            {
                "origin_session": date(2025, 10, 31),
                "target_session": date(2025, 11, 3),
                **prices,
                "model": {"model_id": "B3", "label": "AR(1) baseline", "version": "x"},
                "generated_at": datetime(2026, 10, 16, tzinfo=UTC),
                "data_through": date(2025, 10, 31),
                "is_late": False,
                "target_in_past": True,
                "target_from_calendar": True,
            }
        )
