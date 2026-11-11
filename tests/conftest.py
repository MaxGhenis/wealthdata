"""Shared Hypothesis strategies: small synthetic balance sheets."""

from __future__ import annotations

import numpy as np
import pandas as pd
from hypothesis import HealthCheck, settings
from hypothesis import strategies as st

from wealthdata import project

settings.register_profile(
    "wealthdata",
    deadline=None,
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
settings.load_profile("wealthdata")

amounts = st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False, width=64)
signed_amounts = st.floats(
    min_value=-1e8, max_value=1e9, allow_nan=False, allow_infinity=False, width=64
)
weights = st.floats(min_value=0.5, max_value=5e4, allow_nan=False, allow_infinity=False, width=64)
factors = st.floats(min_value=0.2, max_value=5.0, allow_nan=False, allow_infinity=False, width=64)


@st.composite
def samples(draw, min_size: int = 1, max_size: int = 40, values=signed_amounts):
    """Values and weights of one weighted sample."""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    x = draw(st.lists(values, min_size=size, max_size=size))
    w = draw(st.lists(weights, min_size=size, max_size=size))
    return np.array(x), np.array(w)


@st.composite
def sheets(draw, min_households: int = 2, max_households: int = 12, implicate_count: int = 3):
    """A synthetic balance sheet frame with the columns projections expect.

    Business and other financial assets may be negative, as in the SCF.
    """
    households = draw(st.integers(min_value=min_households, max_value=max_households))
    rows = households * implicate_count
    frame = pd.DataFrame(
        {
            "case": np.tile(np.arange(1, households + 1), implicate_count),
            "implicate": np.repeat(np.arange(1, implicate_count + 1), households).astype("int8"),
            "wgt": np.tile(
                draw(st.lists(weights, min_size=households, max_size=households)), implicate_count
            ),
            "agecl": np.tile(
                draw(st.lists(st.integers(1, 6), min_size=households, max_size=households)),
                implicate_count,
            ).astype("int8"),
            "racecl4": np.tile(
                draw(st.lists(st.integers(1, 4), min_size=households, max_size=households)),
                implicate_count,
            ).astype("int8"),
        }
    )
    for name in project.CLASSES:
        strategy = signed_amounts if name in ("business", "other_financial") else amounts
        frame[name] = draw(st.lists(strategy, min_size=rows, max_size=rows))
    frame["networth"] = project.net_worth(frame)
    return frame


class_factor_maps = st.fixed_dictionaries({name: factors for name in project.CLASSES})
