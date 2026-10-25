import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Start every test with empty rate-limit counters."""
    import main
    main.visitor_limiter.reset()
    main.global_limiter.reset()
    yield
