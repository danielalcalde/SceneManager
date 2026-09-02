"""Tests for Scene Manager services."""
import pytest
from datetime import datetime

from homeassistant.util import dt as dt_util

from custom_components.scene_manager.services import (
    resolve_time,
    is_time_in_schedule,
)
from custom_components.scene_manager.const import (
    DIRECTION_FORWARD,
    DIRECTION_BACKWARD,
)

async def test_resolve_time_absolute():
    """Test absolute time resolution."""
    now = dt_util.now().replace(year=2024, month=1, day=1, hour=12, minute=0, second=0, microsecond=0)
    
    # Test valid time
    resolved = resolve_time(None, "time", "08:00", None, 0, now)
    assert resolved is not None
    assert resolved.hour == 8
    assert resolved.minute == 0
    assert resolved.date() == now.date()
    
    # Test invalid time
    resolved_invalid = resolve_time(None, "time", "99:99", None, 0, now)
    assert resolved_invalid is None

async def test_is_time_in_schedule():
    """Test time window evaluation, including wrap-around midnight."""
    # Faked "now" is noon local time
    base_now = dt_util.now().replace(year=2024, month=1, day=1, minute=0, second=0, microsecond=0)
    now = base_now.replace(hour=12)
    
    # Schedule: 08:00 to 18:00 (12:00 is IN)
    schedule_day = {
        "start_type": "time", "start_time": "08:00",
        "end_type": "time", "end_time": "18:00"
    }
    assert is_time_in_schedule(None, now, schedule_day) == True

    # Schedule: 18:00 to 22:00 (12:00 is OUT)
    schedule_evening = {
        "start_type": "time", "start_time": "18:00",
        "end_type": "time", "end_time": "22:00"
    }
    assert is_time_in_schedule(None, now, schedule_evening) == False
    
    # Wrap around midnight: 20:00 to 06:00 (12:00 is OUT)
    schedule_night = {
        "start_type": "time", "start_time": "20:00",
        "end_type": "time", "end_time": "06:00"
    }
    assert is_time_in_schedule(None, now, schedule_night) == False
    
    # Night time test (now is 23:00)
    now_night = base_now.replace(hour=23)
    assert is_time_in_schedule(None, now_night, schedule_night) == True

    # Early morning test (now is 03:00)
    now_morning = (base_now.replace(day=2, hour=3))
    assert is_time_in_schedule(None, now_morning, schedule_night) == True
