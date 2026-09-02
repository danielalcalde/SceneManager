# Scene Manager Features

This project provides a Home Assistant Custom Component (HACS) designed to enhance scene management for Areas, introducing dynamic and stateful control over room lighting.

## 1. Iterable Area Scenes
- **Description**: Automatically discovers all scenes associated with a specific Area and makes them iterable.
- **Functionality**: Exposes a new service (e.g., `scene_manager.cycle_area_scene`) in Home Assistant that allows iterating through the scenes of an area sequentially. The iteration loops back to the beginning when reaching the end. The service includes a `direction` data field (`forward` or `backward`), enabling automations to cycle in either direction.
- **Use Case**: Mapping a single physical smart button (like a Hue tap dial or IKEA shortcut button) to cycle forward or backward through all available lighting scenes in a room with subsequent presses.

## 2. Adaptive Time-of-Day/Sun-Based Scene Activation
- **Description**: Intelligently activates specific scenes (themes) when a room's lights are turned on, based on the current time of day or sun position (e.g., before or after sunset).
- **Functionality**: 
  - **Sidebar UI Configuration**: Provides a dedicated configuration tab on the Home Assistant sidebar. Users can map specific times or sun events (e.g., sunrise to sunset, sunset to 1:00 AM) to specific scenes for each area.
  - **Button Integration**: Intercepts the default "turn on area" command when triggered by a physical button (by mapping the button to a custom service).
  - **Voice Assistant Integration**: Intercepts the "turn on lights in area" command when triggered by voice assistants like Alexa (typically by exposing a virtual adaptive switch to the voice assistant).
- **Use Case**: Using the custom UI tab, configure the living room to use a "Morning" scene from sunrise to sunset, and a "Night" scene from sunset to 1:00 AM. Turning on the living room lights at these times activates the appropriate scene automatically.
