# Scene Manager for Home Assistant



Scene Manager is a custom Home Assistant integration that gives you powerful, UI-driven tools to manage your scenes dynamically based on time of day, sun events, and smart button interactions.

## Features

- **Adaptive Lighting Schedules:** Build dynamic timetables for any room. Link your existing Home Assistant scenes to specific times of day or sun events (e.g., "Morning" at sunrise, "Day" at 10:00 AM). Whenever the room's Virtual Light is turned on, Scene Manager automatically calculates the current time and triggers the correct scene.
- **True Scene Interpolation:** Go beyond basic toggling. Map your scenes to specific brightness milestones (e.g., 10% = Nightlight, 100% = Daylight). When you scrub the Virtual Light's brightness slider (or ask Alexa to dim the room to 50%), the backend mathematically blends the RGB colors, color temperatures, and brightness of your scenes to create a perfectly interpolated midpoint!
- **Smart Button Cycling:** Give your physical smart switches (like Hue or IKEA remotes) superpowers. Use the `scene_manager.cycle_scene` service to seamlessly rotate through your favorite scenes with a single button press, while skipping any scenes you've explicitly hidden in the UI. *(Recommended to use alongside [SwitchManager](https://github.com/Sian-Lee-SA/Home-Assistant-Switch-Manager))*
- **Voice Assistant Integration:** Automatically generate a single "Virtual Light" for each area that you can easily expose to Alexa, Google Home, or Apple HomeKit. Voice commands like "Turn on the Kitchen" instantly proxy to your dynamic adaptive schedule.
    
![Scene Manager Dashboard](images/screenshot.png)
## Installation

### Via HACS (Recommended)
1. Open HACS in Home Assistant.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Add `https://github.com/danielalcalde/SceneManager` and select **Integration** as the category.
4. Click **Add**, then search for "Scene Manager" in HACS and click **Download**.
5. Restart Home Assistant.
6. The Scene Manager UI will automatically appear in your sidebar.

### Manual Installation
1. Download this repository.
2. Copy the `custom_components/scene_manager` folder to your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.
4. The Scene Manager UI will automatically appear in your sidebar.

## Usage

### UI Dashboard
Open the "Scene Manager" panel in the sidebar to configure schedules, select which scenes to include in button cycling, and configure the Virtual Light interpolation map.

### Automation Services
- `scene_manager.turn_on_adaptive`: Calculates the correct scene for the current time and activates it.
- `scene_manager.cycle_scene`: Cycles to the next/previous scene in the rotation. Accepts a `direction` (`forward` or `backward`).

Both services support an optional `transition` parameter (in seconds) for smooth fading.
