class SceneManagerPanel extends HTMLElement {
  set panel(panel) {
    this._panel = panel;
  }
  
  set hass(hass) {
    const firstLoad = !this._hass;
    this._hass = hass;
    if (firstLoad) {
      this.init();
    }
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.state = {
      selectedArea: null,
      schedules: [],
      rotation: { excluded_scenes: [], current_scene_id: null },
      virtual_light: { enabled: true, interpolation_enabled: false, mapping: {} },
      loading: false,
    };
  }

  async init() {
    this.render();
    try {
      await this._hass.connection.subscribeEvents((event) => {
        if (this.state.selectedArea && event.data.area_id === this.state.selectedArea) {
          this.setState({
            rotation: {
              ...this.state.rotation,
              current_scene_id: event.data.scene_id
            }
          });
        }
      }, "scene_manager_active_scene_changed");
    } catch (e) {
      console.error("Failed to subscribe to scene manager events:", e);
    }
  }

  setState(newState) {
    this.state = { ...this.state, ...newState };
    this.render();
  }

  getAreasWithScenes() {
    if (!this._hass) return [];
    
    // Get all scene entities from the entity registry
    const sceneEntities = Object.values(this._hass.entities).filter(ent => ent.entity_id.startsWith("scene."));
    
    // Get all areas
    const areas = Object.values(this._hass.areas);
    
    // Filter areas to only those that have at least one scene assigned
    return areas.filter(area => 
      sceneEntities.some(scene => scene.area_id === area.area_id)
    ).sort((a, b) => a.name.localeCompare(b.name));
  }

  getScenesForArea(areaId) {
    if (!this._hass || !areaId) return [];
    return Object.values(this._hass.entities)
      .filter(ent => ent.entity_id.startsWith("scene.") && ent.area_id === areaId)
      .map(ent => {
         const stateObj = this._hass.states[ent.entity_id];
         return {
            id: ent.entity_id,
            name: stateObj ? stateObj.attributes.friendly_name || ent.name || ent.entity_id : ent.name || ent.entity_id
         };
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  async fetchSchedules(areaId) {
    this.setState({ loading: true });
    try {
      const response = await this._hass.callWS({
        type: "scene_manager/get_schedules",
        area_id: areaId
      });
      const rotationState = await this._hass.callWS({
        type: "scene_manager/get_rotation_state",
        area_id: areaId
      });
      
      const virtualLightState = await this._hass.callWS({
        type: "scene_manager/get_virtual_light_config",
        area_id: areaId
      });
      
      this.setState({ 
        schedules: response || [], 
        rotation: rotationState || { excluded_scenes: [], current_scene_id: null },
        virtual_light: virtualLightState || { enabled: true, interpolation_enabled: false, mapping: {} },
        loading: false, 
        selectedArea: areaId 
      });
    } catch (e) {
      console.error("Error fetching area data:", e);
      this.setState({ schedules: [], rotation: { excluded_scenes: [], current_scene_id: null }, virtual_light: { enabled: true, interpolation_enabled: false, mapping: {} }, loading: false, selectedArea: areaId });
    }
  }

  async saveSchedules() {
    if (!this.state.selectedArea) return;
    this.setState({ loading: true });
    try {
      await this._hass.callWS({
        type: "scene_manager/save_schedules",
        area_id: this.state.selectedArea,
        schedules: this.state.schedules
      });
      await this._hass.callWS({
        type: "scene_manager/save_rotation_config",
        area_id: this.state.selectedArea,
        excluded_scenes: this.state.rotation.excluded_scenes || []
      });
      await this._hass.callWS({
        type: "scene_manager/save_virtual_light_config",
        area_id: this.state.selectedArea,
        config: this.state.virtual_light
      });
      alert("Settings saved successfully!");
    } catch (e) {
      console.error("Error saving settings:", e);
      alert("Failed to save settings.");
    }
    this.setState({ loading: false });
  }

  toggleRotationInclusion(sceneId) {
    let excluded = [...(this.state.rotation.excluded_scenes || [])];
    if (excluded.includes(sceneId)) {
      excluded = excluded.filter(id => id !== sceneId);
    } else {
      excluded.push(sceneId);
    }
    this.setState({ rotation: { ...this.state.rotation, excluded_scenes: excluded } });
  }

  toggleVirtualLight(enabled) {
    this.setState({ virtual_light: { ...this.state.virtual_light, enabled: enabled } });
  }

  toggleInterpolation(enabled) {
    this.setState({ virtual_light: { ...this.state.virtual_light, interpolation_enabled: enabled } });
  }

  updateInterpolationMapping(sceneId, percentage) {
    const mapping = { ...this.state.virtual_light.mapping };
    if (percentage === null || percentage === "") {
      delete mapping[sceneId];
    } else {
      mapping[sceneId] = parseInt(percentage, 10);
    }
    this.setState({ virtual_light: { ...this.state.virtual_light, mapping: mapping } });
  }

  addSchedule() {
    const newSchedule = {
      scene_id: "",
      start_type: "time",
      start_time: "08:00",
      start_sun_event: "sunrise",
      start_offset: 0,
      end_type: "time",
      end_time: "18:00",
      end_sun_event: "sunset",
      end_offset: 0
    };
    this.setState({ schedules: [...this.state.schedules, newSchedule] });
  }

  removeSchedule(index) {
    const newSchedules = [...this.state.schedules];
    newSchedules.splice(index, 1);
    this.setState({ schedules: newSchedules });
  }

  updateSchedule(index, field, value, shouldRender = true) {
    const newSchedules = [...this.state.schedules];
    newSchedules[index] = { ...newSchedules[index], [field]: value };
    if (shouldRender) {
      this.setState({ schedules: newSchedules });
    } else {
      this.state.schedules = newSchedules;
    }
  }

  renderCondition(type, isStart, schedule, index) {
    const prefix = isStart ? 'start' : 'end';
    const currentType = schedule[`${prefix}_type`];
    const timeValue = schedule[`${prefix}_time`];
    const sunEventValue = schedule[`${prefix}_sun_event`];
    const offsetValue = schedule[`${prefix}_offset`];

    return `
      <div class="condition-row">
        <label>Type:</label>
        <select class="input-select" onchange="this.getRootNode().host.updateSchedule(${index}, '${prefix}_type', this.value)">
          <option value="time" ${currentType === 'time' ? 'selected' : ''}>🕒 Fixed Time</option>
          <option value="sun" ${currentType === 'sun' ? 'selected' : ''}>☀️ Sun Event</option>
        </select>
        
        ${currentType === 'time' ? `
          <label>Time:</label>
          <input type="time" class="input-text" value="${timeValue}" onchange="this.getRootNode().host.updateSchedule(${index}, '${prefix}_time', this.value, false)">
        ` : `
          <label>Event:</label>
          <select class="input-select" onchange="this.getRootNode().host.updateSchedule(${index}, '${prefix}_sun_event', this.value)">
            <option value="sunrise" ${sunEventValue === 'sunrise' ? 'selected' : ''}>Sunrise</option>
            <option value="sunset" ${sunEventValue === 'sunset' ? 'selected' : ''}>Sunset</option>
          </select>
          <label>Offset (min):</label>
          <input type="number" class="input-text short" value="${offsetValue}" onchange="this.getRootNode().host.updateSchedule(${index}, '${prefix}_offset', parseInt(this.value) || 0, false)">
        `}
      </div>
    `;
  }

  renderScheduleCard(schedule, index, availableScenes) {
    const sceneOptions = availableScenes.map(scene => 
      `<option value="${scene.id}" ${schedule.scene_id === scene.id ? 'selected' : ''}>${scene.name}</option>`
    ).join('');

    return `
      <div class="card schedule-card">
        <div class="card-header">
          <div class="scene-selector">
            <label>Scene:</label>
            <select class="input-select large" onchange="this.getRootNode().host.updateSchedule(${index}, 'scene_id', this.value)">
              <option value="" disabled ${!schedule.scene_id ? 'selected' : ''}>Select a Scene...</option>
              ${sceneOptions}
            </select>
          </div>
          <button class="btn btn-danger" onclick="this.getRootNode().host.removeSchedule(${index})">
            <svg viewBox="0 0 24 24"><path d="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z" /></svg>
          </button>
        </div>
        
        <div class="condition-box">
          <div class="condition-title">--- Start Condition ---</div>
          ${this.renderCondition('start', true, schedule, index)}
        </div>

        <div class="condition-box">
          <div class="condition-title">--- End Condition ---</div>
          ${this.renderCondition('end', false, schedule, index)}
        </div>
      </div>
    `;
  }

  render() {
    if (!this._hass) return;

    const areas = this.getAreasWithScenes();
    const availableScenes = this.state.selectedArea ? this.getScenesForArea(this.state.selectedArea) : [];

    const areaOptions = areas.map(area => 
      `<option value="${area.area_id}" ${this.state.selectedArea === area.area_id ? 'selected' : ''}>${area.name}</option>`
    ).join('');

    const schedulesHtml = this.state.schedules.map((schedule, idx) => 
      this.renderScheduleCard(schedule, idx, availableScenes)
    ).join('');

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 24px;
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
          background-color: var(--primary-background-color);
          color: var(--primary-text-color);
          height: 100%;
          box-sizing: border-box;
          overflow-y: auto;
        }
        .header {
          display: flex;
          align-items: center;
          gap: 16px;
          margin-bottom: 32px;
        }
        h1 {
          color: var(--primary-text-color);
          margin: 0;
          font-weight: 400;
          font-size: 24px;
        }
        .card {
          background: var(--card-background-color, white);
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0px 2px 1px -1px rgba(0,0,0,0.2), 0px 1px 1px 0px rgba(0,0,0,0.14), 0px 1px 3px 0px rgba(0,0,0,0.12));
          padding: 20px;
          margin-bottom: 24px;
          transition: box-shadow 0.2s ease-in-out;
        }
        .card:hover {
          box-shadow: 0px 4px 4px -2px rgba(0,0,0,0.2), 0px 2px 2px 0px rgba(0,0,0,0.14), 0px 2px 6px 0px rgba(0,0,0,0.12);
        }
        .input-select {
          background-color: var(--secondary-background-color);
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 4px;
          padding: 8px 12px;
          font-size: 16px;
          outline: none;
        }
        .input-text {
          background-color: var(--secondary-background-color);
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 4px;
          padding: 8px 12px;
          font-size: 16px;
          outline: none;
        }
        .input-text.short {
          width: 60px;
        }
        .btn {
          background-color: var(--primary-color);
          color: var(--text-primary-color, white);
          border: none;
          border-radius: 4px;
          padding: 10px 16px;
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          text-transform: uppercase;
          display: flex;
          align-items: center;
          gap: 8px;
          transition: background-color 0.2s;
        }
        .btn:hover {
          filter: brightness(1.1);
        }
        .btn:disabled {
          background-color: var(--disabled-text-color);
          cursor: not-allowed;
        }
        .btn-danger {
          background-color: transparent;
          color: var(--error-color, #f44336);
          padding: 8px;
          border-radius: 50%;
        }
        .btn-danger:hover {
          background-color: rgba(244, 67, 54, 0.1);
          filter: none;
        }
        .btn-danger svg {
          width: 24px;
          height: 24px;
          fill: currentColor;
        }
        
        .area-selector {
          display: flex;
          align-items: center;
          gap: 16px;
          margin-bottom: 24px;
        }
        .area-selector .input-select {
          min-width: 250px;
        }
        
        .schedule-card {
          border-left: 4px solid var(--primary-color);
        }
        .card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
          padding-bottom: 16px;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
        }
        .scene-selector {
          display: flex;
          align-items: center;
          gap: 12px;
          flex: 1;
        }
        .scene-selector .input-select.large {
          font-size: 18px;
          font-weight: 500;
          min-width: 300px;
        }
        
        .condition-box {
          margin-bottom: 16px;
          padding: 16px;
          background-color: var(--secondary-background-color);
          border-radius: 8px;
        }
        .condition-title {
          font-size: 12px;
          text-transform: uppercase;
          letter-spacing: 1px;
          color: var(--secondary-text-color);
          margin-bottom: 12px;
          font-weight: 500;
        }
        .condition-row {
          display: flex;
          align-items: center;
          gap: 16px;
          flex-wrap: wrap;
        }
        .condition-row label {
          color: var(--primary-text-color);
          font-weight: 500;
        }

        .actions {
          display: flex;
          justify-content: flex-end;
          margin-top: 32px;
          padding-top: 24px;
          border-top: 1px solid var(--divider-color, #e0e0e0);
        }
        
        .empty-state {
          text-align: center;
          padding: 48px 24px;
          color: var(--secondary-text-color);
        }
        .empty-state svg {
          width: 64px;
          height: 64px;
          fill: var(--disabled-text-color);
          margin-bottom: 16px;
        }
        
        .help-box {
          margin-top: 48px;
          padding: 20px;
          background-color: var(--secondary-background-color);
          border-radius: 8px;
          border-left: 4px solid var(--info-color, #2196f3);
        }
        .help-box h3 {
          margin-top: 0;
          color: var(--primary-text-color);
        }
        .help-box ul {
          margin-bottom: 0;
          padding-left: 20px;
        }
        .help-box li {
          margin-bottom: 8px;
        }
        .help-box pre {
          background-color: var(--primary-background-color);
          padding: 12px;
          border-radius: 4px;
          overflow-x: auto;
          margin-top: 12px;
        }
        .help-box code {
          background-color: rgba(0,0,0,0.1);
          padding: 2px 4px;
          border-radius: 4px;
          font-family: monospace;
        }
        .help-box pre code {
          background-color: transparent;
          padding: 0;
        }
      </style>
      
      <div class="header">
        <h1>Scene Manager</h1>
      </div>
      
      <div class="area-selector">
        <label>Configuration Area:</label>
        <select class="input-select" onchange="this.getRootNode().host.fetchSchedules(this.value)">
          <option value="" disabled ${!this.state.selectedArea ? 'selected' : ''}>Select an Area...</option>
          ${areaOptions}
        </select>
        ${this.state.loading ? '<span>Loading...</span>' : ''}
      </div>

      </div>

      ${!this.state.selectedArea ? `
        <div class="card" style="text-align: center; padding: 40px 20px; margin-bottom: 24px;">
          <svg style="width:64px;height:64px;fill:var(--primary-color, #03a9f4);margin-bottom:16px;" viewBox="0 0 24 24"><path d="M12,3C10.73,3 9.6,3.8 9.18,5H3V7H4.95L7.44,14H9C9,15.66 10.34,17 12,17C13.66,17 15,15.66 15,14H16.56L19.05,7H21V5H14.82C14.4,3.8 13.27,3 12,3M12,5A1,1 0 0,1 13,6A1,1 0 0,1 12,7A1,1 0 0,1 11,6A1,1 0 0,1 12,5M6.82,7H17.18L15.3,13H8.7L6.82,7M12,14A1,1 0 0,1 11,15A1,1 0 0,1 12,16A1,1 0 0,1 13,15A1,1 0 0,1 12,14Z" /></svg>
          <h2 style="color: var(--primary-text-color); margin-top: 0;">Welcome to Scene Manager</h2>
          <p style="color: var(--secondary-text-color); max-width: 500px; margin: 0 auto; font-size: 1.1em; line-height: 1.5; margin-bottom: 12px;">
            Scene Manager allows you to create adaptive lighting schedules using your existing Home Assistant scenes. 
            <strong>When a Virtual Light is turned on, it automatically calculates the current time and activates the appropriate scene from your schedule!</strong>
          </p>
          <p style="color: var(--secondary-text-color); max-width: 500px; margin: 0 auto; font-size: 1.1em; line-height: 1.5;">
            Select an area above to start building schedules, configure smart button cycling, and expose Virtual Lights to Alexa and Matter.
          </p>
        </div>
      ` : ''}

      ${this.state.selectedArea ? `
        <div class="card" style="margin-bottom: 24px; border-left: 4px solid var(--info-color, #2196f3);">
          <div class="card-header" style="border-bottom:none; margin-bottom:0; padding-bottom:0;">
            <h3 style="margin-top:0; color: var(--primary-text-color); display:flex; align-items:center; gap:8px;">
              <svg style="width:24px;height:24px;fill:currentColor;" viewBox="0 0 24 24"><path d="M12,2A7,7 0 0,0 5,9C5,11.38 6.19,13.47 8,14.74V17A1,1 0 0,0 9,18H15A1,1 0 0,0 16,17V14.74C17.81,13.47 19,11.38 19,9A7,7 0 0,0 12,2M9,21A1,1 0 0,0 10,22H14A1,1 0 0,0 15,21V20H9V21Z"/></svg>
              Virtual Light Settings
            </h3>
          </div>
          <div style="padding-top: 16px;">
            <label style="display:flex; align-items:center; gap:8px; cursor:pointer; color: var(--primary-text-color); font-weight:bold;">
              <input type="checkbox" style="width:16px; height:16px;"
                     ${this.state.virtual_light?.enabled !== false ? 'checked' : ''} 
                     onchange="this.getRootNode().host.toggleVirtualLight(this.checked)">
              Enable Virtual Light for this Area
            </label>
            <p style="margin-top:4px; margin-bottom:16px; font-size: 0.9em; color: var(--secondary-text-color);">
              Creates a single entity (e.g. <code>light.living_room_adaptive_lights</code>) you can expose to Alexa/Google. 
            </p>

            ${this.state.virtual_light?.enabled !== false ? `
              <div style="margin-left: 24px; padding-left: 16px; border-left: 2px solid var(--divider-color, #e0e0e0);">
                <label style="display:flex; align-items:center; gap:8px; cursor:pointer; color: var(--primary-text-color);">
                  <input type="checkbox" style="width:16px; height:16px;"
                         ${this.state.virtual_light?.interpolation_enabled ? 'checked' : ''} 
                         onchange="this.getRootNode().host.toggleInterpolation(this.checked)">
                  <strong>Enable Scene Interpolation</strong>
                </label>
                <p style="margin-top:4px; margin-bottom:8px; font-size: 0.9em; color: var(--secondary-text-color);">
                  Scrub the Virtual Light brightness slider (0-100%) to smoothly blend between different scenes. 
                  <strong style="color: var(--warning-color, #ff9800);">⚠️ Note: True interpolation ONLY works with native HA scenes (created in the UI).</strong> Hub-imported scenes (Hue, etc) are not supported.
                </p>
                
                ${this.state.virtual_light?.interpolation_enabled ? `
                  <div style="margin-top: 12px; background: rgba(0,0,0,0.02); padding: 12px; border-radius: 4px; border: 1px solid var(--divider-color, #e0e0e0);">
                    <p style="margin-top:0; font-size:0.9em; font-weight:bold;">Assign brightness percentages to scenes:</p>
                    <div style="display:grid; gap: 8px;">
                      ${availableScenes.map(scene => `
                        <div style="display:flex; align-items:center; gap:8px;">
                          <input type="number" min="0" max="100" style="width: 60px; padding: 4px;" placeholder="%" 
                                 value="${this.state.virtual_light?.mapping?.[scene.id] ?? ''}"
                                 onchange="this.getRootNode().host.updateInterpolationMapping('${scene.id}', this.value)">
                          <span>% &mdash; ${scene.name}</span>
                        </div>
                      `).join('')}
                    </div>
                  </div>
                ` : ''}
              </div>
            ` : ''}
          </div>
        </div>

        <div class="card" style="margin-bottom: 24px; border-left: 4px solid var(--warning-color, #ff9800);">
          <div class="card-header" style="border-bottom:none; margin-bottom:0; padding-bottom:0;">
            <h3 style="margin-top:0; color: var(--primary-text-color); display:flex; align-items:center; gap:8px;">
              <svg style="width:24px;height:24px;fill:currentColor;" viewBox="0 0 24 24"><path d="M12,18A6,6 0 0,1 6,12C6,11 6.25,10.03 6.7,9.2L5.24,7.74C4.46,8.97 4,10.43 4,12A8,8 0 0,0 12,20V23L16,19L12,15M12,4V1L8,5L12,9V6A6,6 0 0,1 18,12C18,13 17.75,13.97 17.3,14.8L18.76,16.26C19.54,15.03 20,13.57 20,12A8,8 0 0,0 12,4Z"/></svg>
              Cycle Settings
            </h3>
          </div>
          <div style="padding-top: 16px;">
            <p style="margin-top:0;"><strong>Currently Active Scene:</strong> ${
              this.state.rotation.current_scene_id 
              ? (availableScenes.find(s => s.id === this.state.rotation.current_scene_id)?.name || this.state.rotation.current_scene_id)
              : "<em>None tracked</em>"
            }</p>
            <p style="margin-bottom: 8px; color: var(--secondary-text-color);">Select which scenes are included when pressing a cycle button:</p>
            <div style="display:flex; flex-direction:column; gap:8px; padding-left:8px;">
              ${availableScenes.map(scene => `
                <label style="display:flex; align-items:center; gap:8px; cursor:pointer; color: var(--primary-text-color);">
                  <input type="checkbox" style="width:16px; height:16px;"
                         ${!(this.state.rotation.excluded_scenes || []).includes(scene.id) ? 'checked' : ''} 
                         onchange="this.getRootNode().host.toggleRotationInclusion('${scene.id}')">
                  ${scene.name}
                </label>
              `).join('')}
            </div>
          </div>
        </div>

        <h3 style="margin-top: 32px; color: var(--primary-text-color); border-bottom: 1px solid var(--divider-color, #e0e0e0); padding-bottom: 8px;">
          <svg style="width:24px;height:24px;fill:currentColor;vertical-align:middle;margin-right:8px;" viewBox="0 0 24 24"><path d="M15,13H16.5V15.82L18.94,17.23L18.19,18.53L15,16.69V13M19,8H5V19H9.67C9.24,18.09 9,17.07 9,16A7,7 0 0,1 16,9C17.07,9 18.09,9.24 19,9.67V8M5,21C3.89,21 3,20.1 3,19V5C3,3.89 3.89,3 5,3H6V1H8V3H16V1H18V3H19A2,2 0 0,1 21,5V11.1C22.24,12.36 23,14.09 23,16A7,7 0 0,1 16,23C14.09,23 12.36,22.24 11.1,21H5M16,11.15A4.85,4.85 0 0,0 11.15,16C11.15,18.68 13.32,20.85 16,20.85A4.85,4.85 0 0,0 20.85,16C20.85,13.32 18.68,11.15 16,11.15Z" /></svg>
          Timetables
        </h3>
        
        <div class="schedules">
          ${this.state.schedules.length === 0 ? `
            <div class="empty-state card">
              <svg viewBox="0 0 24 24"><path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4M11,7V11H7V13H11V17H13V13H17V11H13V7H11Z" /></svg>
              <h3>No schedules configured</h3>
              <p>Click "Add New Schedule" below to create your first adaptive scene for this area.</p>
            </div>
          ` : schedulesHtml}
          
          <button class="btn" style="margin-bottom: 24px;" onclick="this.getRootNode().host.addSchedule()">
            <svg style="width:20px;height:20px;fill:currentColor;margin-right:4px;" viewBox="0 0 24 24"><path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z" /></svg>
            Add New Schedule
          </button>
          
          <div class="actions">
            <button class="btn" onclick="this.getRootNode().host.saveSchedules()" ${this.state.loading ? 'disabled' : ''}>
              <svg style="width:20px;height:20px;fill:currentColor;margin-right:4px;" viewBox="0 0 24 24"><path d="M15,9H5V5H15M12,19A3,3 0 0,1 9,16A3,3 0 0,1 12,13A3,3 0 0,1 15,16A3,3 0 0,1 12,19M17,3H5C3.89,3 3,3.9 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V7L17,3Z" /></svg>
              Save Changes
            </button>
          </div>
        </div>
      ` : ''}

      <div class="help-box">
        <h3>💡 Automation Tips</h3>
        <p>You can use these services in your Home Assistant automations (Developer Tools -> Services):</p>
        <ul>
          <li><strong><code>scene_manager.turn_on_adaptive</code></strong>: Call this when motion is detected. It will automatically calculate the current time/sun and turn on the correct scene you configured above!</li>
          <li><strong><code>scene_manager.cycle_scene</code></strong>: Map this to a physical smart button or remote to cycle forward or backward through your area's scenes manually.</li>
        </ul>
        ${this.state.selectedArea ? `
        <h4 style="margin-top:16px; margin-bottom:8px; color: var(--primary-text-color);">Example Payloads for this Area:</h4>
        <strong>Adaptive Turn On:</strong>
        <pre><code>action: scene_manager.turn_on_adaptive
data:
  area_id: ${this.state.selectedArea}
  transition: 0.5</code></pre>
        <strong style="display:block; margin-top:12px;">Cycle Scene (Forward or Backward):</strong>
        <pre><code>action: scene_manager.cycle_scene
data:
  area_id: ${this.state.selectedArea}
  direction: forward
  transition: 0.5</code></pre>
        ` : ''}
      </div>
    `;
  }
}

customElements.define("scene-manager-panel", SceneManagerPanel);
