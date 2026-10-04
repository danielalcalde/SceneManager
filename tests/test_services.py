"""Tests for Scene Manager services."""
import pytest
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util
from unittest.mock import patch

from custom_components.scene_manager.services import (
    resolve_time,
)
from custom_components.scene_manager.const import (
    DIRECTION_FORWARD,
    DIRECTION_BACKWARD,
)

async def test_resolve_time_absolute():
    """Test absolute time resolution."""
    now = dt_util.now().replace(year=2024, month=1, day=1, hour=12, minute=0, second=0, microsecond=0)
    
    # Test valid time
    resolved = resolve_time(None, "time", "08:00", None, 0, None, None, now.date(), now)
    assert resolved is not None
    assert resolved.hour == 8
    assert resolved.minute == 0
    assert resolved.date() == now.date()
    
    # Test invalid time
    resolved_invalid = resolve_time(None, "time", "99:99", None, 0, None, None, now.date(), now)
    assert resolved_invalid is None

@patch("custom_components.scene_manager.services.get_astral_event_date")
async def test_resolve_time_sun(mock_get_astral_event_date):
    """Test sun-based time resolution with bounds."""
    now = dt_util.now().replace(year=2024, month=1, day=1, hour=12, minute=0, second=0, microsecond=0)
    
    # Mock get_astral_event_date to return 06:00 for sunrise
    mock_get_astral_event_date.return_value = now.replace(hour=6)
    
    # Normal sun event with offset
    resolved = resolve_time(None, "sun", None, "sunrise", 30, None, None, now.date(), now)
    assert resolved is not None
    assert resolved.hour == 6
    assert resolved.minute == 30
    
    # Bounded sun - earliest limit (limit is 07:00, sunrise is 06:00 -> should bound to 07:00)
    resolved_bounded_early = resolve_time(None, "bounded_sun", None, "sunrise", 0, "earliest", "07:00", now.date(), now)
    assert resolved_bounded_early.hour == 7
    
    # Bounded sun - latest limit (limit is 05:00, sunrise is 06:00 -> should bound to 05:00)
    resolved_bounded_late = resolve_time(None, "bounded_sun", None, "sunrise", 0, "latest", "05:00", now.date(), now)
    assert resolved_bounded_late.hour == 5
