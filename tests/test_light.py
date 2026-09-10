"""Tests for the light platform helper functions."""
from custom_components.scene_manager.light import (
    _interpolate_value,
    _get_brightness,
    _apply_interpolated_attribute,
)

def test_interpolate_value():
    """Test value interpolation."""
    assert _interpolate_value(0, 100, 0.5) == 50
    assert _interpolate_value(100, 200, 0.25) == 125
    assert _interpolate_value(None, 100, 0.5) == 100
    assert _interpolate_value(50, None, 0.5) == 50
    assert _interpolate_value(None, None, 0.5) is None
    # Test float preserving/rounding behavior based on types (type(val1))
    assert _interpolate_value(10, 20, 0.5) == 15
    assert _interpolate_value(10.0, 20.0, 0.5) == 15.0

def test_get_brightness():
    """Test getting brightness from state dict."""
    assert _get_brightness({"brightness": 128}) == 128
    assert _get_brightness({"state": "off"}) == 0
    assert _get_brightness({"state": "on"}) == 255
    assert _get_brightness({}) == 255

def test_apply_interpolated_attribute_scalar():
    """Test applying interpolated scalar attribute."""
    service_data = {}
    lower_state = {"color_temp": 200, "state": "on"}
    upper_state = {"color_temp": 400, "state": "on"}
    
    _apply_interpolated_attribute(service_data, "color_temp", lower_state, upper_state, 0.5)
    assert service_data["color_temp"] == 300
    
def test_apply_interpolated_attribute_list():
    """Test applying interpolated list attribute like rgb_color."""
    service_data = {}
    lower_state = {"rgb_color": [0, 100, 200], "state": "on"}
    upper_state = {"rgb_color": [100, 200, 255], "state": "on"}
    
    _apply_interpolated_attribute(service_data, "rgb_color", lower_state, upper_state, 0.5)
    assert service_data["rgb_color"] == [50, 150, 227]
    
def test_apply_interpolated_attribute_one_off():
    """Test applying interpolated attribute when one state is off."""
    # Lower is off, should use upper
    service_data = {}
    lower_state = {"state": "off"}
    upper_state = {"color_temp": 400, "state": "on"}
    _apply_interpolated_attribute(service_data, "color_temp", lower_state, upper_state, 0.5)
    assert service_data["color_temp"] == 400
    
    # Upper is off, should use lower
    service_data = {}
    lower_state = {"color_temp": 200, "state": "on"}
    upper_state = {"state": "off"}
    _apply_interpolated_attribute(service_data, "color_temp", lower_state, upper_state, 0.5)
    assert service_data["color_temp"] == 200
