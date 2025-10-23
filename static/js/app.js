
/**
 * @file app.js
 * @description
 * Front-end controller for the AI caller demo.
 *
 * Handles:
 *  - Loading available scenarios and genders from Flask backend (/options)
 *  - Launching, polling, and stopping the backend process (/launch, /logs, /stop)
 *  - Managing the UI states of the phone interface and timer
 *
 * Usage:
 *  Called automatically on page load via `loadOptions()` and `setGender('female')`.
 *
 */

const scenarioSelect = document.getElementById('scenarioSelect');
const statusEl       = document.getElementById('status');
const logsEl         = document.getElementById('logs');

const callBtn        = document.getElementById('callBtn');
const phoneContent   = document.getElementById('phoneContent');
const phoneTimeEl    = document.getElementById('phoneTime');
const voiceSelect    = document.getElementById('voiceSelect');

let selectedGender   = 'female';
let isModelLoaded    = false;
let isCallActive     = false;
let callTimer        = null;
let callSeconds      = 0;
let loadingPollTimer = null;
let isConnecting     = false; // Track if we're in the connecting/loading phase
let loadingDotsTimer = null; // Track the animated ellipsis interval
let voicesByGender   = { female: [], male: [] };

/**
 * Set the selected gender and update button UI.
 * @param {"female"|"male"} g
 */
function setGender(g) {
  selectedGender = g;
  document.querySelectorAll('.gender-btn').forEach(btn => {
    btn.dataset.active = (btn.dataset.gender === g) ? 'true' : 'false';
  });
  populateVoiceOptions(selectedGender);
}

/** Update the voice options based on gender state. */
function populateVoiceOptions(gender) {
  const voices = (voicesByGender[gender] || []);
  voiceSelect.innerHTML = '';

  if (!voices.length) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = '(no voices found)';
    voiceSelect.appendChild(opt);
    voiceSelect.disabled = true;
    return;
  }

  voices.forEach(v => {
    const opt = document.createElement('option');
    opt.value = v.id;      // folder name
    opt.textContent = v.label;
    voiceSelect.appendChild(opt);
  });

  voiceSelect.disabled = false;
}

/** Update the main launch button label and style based on app state. */
function updateLaunchButton() {
  const btn = document.getElementById('launchBtn');
  if (!btn) return;

  if (isConnecting) {
    // State 2: Connecting/Loading - show "Cancel loading"
    btn.textContent = 'Cancel loading';
    btn.className = 'w-full h-12 text-base font-semibold rounded-xl bg-red-600 hover:bg-red-700 text-white shadow-md transition-colors';
    btn.disabled = false;
  } else if (isModelLoaded || isCallActive) {
    // State 3 & 4: Model loaded or call active - show "Stop caller"
    btn.textContent = isCallActive ? 'End & unload' : 'Stop caller';
    btn.className = 'w-full h-12 text-base font-semibold rounded-xl bg-red-600 hover:bg-red-700 text-white shadow-md transition-colors';
    btn.disabled = false;
  } else {
    // State 1: Not loaded - show "Load caller"
    btn.textContent = 'Load caller';
    btn.className = 'w-full h-12 text-base font-semibold rounded-xl bg-branddark hover:bg-[#033551] text-white shadow-md transition-colors';
    btn.disabled = false;
  }
}

/** Update the fake phone clock UI (HH:MM AM/PM). */
function updatePhoneTime(){
  const now = new Date();
  phoneTimeEl.textContent = now.toLocaleTimeString('en-US', { hour: 'numeric', minute:'2-digit', hour12:true });
}
setInterval(updatePhoneTime, 1000);
updatePhoneTime();

/**
 * Update the phone panel to a specific UI state.
 * @param {"not-loaded"|"connecting"|"ready"|"connected"} state
 * @param {string} [scenarioLabel]
 * @param {string} [genderLabel]
 */
function setPhoneState(state, scenarioLabel='', genderLabel=''){
  // Clear any existing loading animation
  if (loadingDotsTimer) {
    clearInterval(loadingDotsTimer);
    loadingDotsTimer = null;
  }

  phoneContent.innerHTML = '';
  if(state === 'not-loaded'){
    phoneContent.innerHTML = `
      <div class="text-2xl font-medium text-slate-900 leading-tight">Caller not loaded yet</div>
      <div class="text-sm text-slate-500 mt-2">Load the caller on the left side</div>
    `;
    callBtn.disabled = true;
    callBtn.className = "w-16 h-16 rounded-full bg-gray-300 cursor-not-allowed flex items-center justify-center shadow-lg";
  } else if(state === 'connecting'){
    phoneContent.innerHTML = `
      <div class="text-2xl font-medium text-slate-900 leading-tight">Connecting</div>
      <div class="text-sm text-slate-500 mt-2"><span id="loadingText">Please wait.</span></div>
    `;
    callBtn.disabled = true;
    callBtn.className = "w-16 h-16 rounded-full bg-gray-300 cursor-not-allowed flex items-center justify-center shadow-lg";

    // Start animated ellipsis (cycle through 1, 2, 3 dots)
    let dotCount = 1;
    const loadingTextEl = document.getElementById('loadingText');
    loadingDotsTimer = setInterval(() => {
      if (!loadingTextEl) return;
      const dots = '.'.repeat(dotCount);
      loadingTextEl.textContent = `Please wait${dots}`;
      dotCount = (dotCount % 3) + 1; // Cycle through 1, 2, 3 (always at least 1 dot)
    }, 400);
  } else if(state === 'ready'){
    phoneContent.innerHTML = `
      <div class="text-2xl font-medium text-slate-900 leading-tight">Ready to start</div>
      <div class="text-sm text-slate-500 mt-2">Tap the button below to begin</div>
    `;
    callBtn.disabled = false;
    callBtn.className = "w-16 h-16 rounded-full bg-green-500 hover:bg-green-600 hover:scale-105 flex items-center justify-center shadow-lg transition-all";
  } else if(state === 'connected'){
    // Capitalize first letter of gender label
    const capitalizedGender = genderLabel ? genderLabel.charAt(0).toUpperCase() + genderLabel.slice(1) : '';
    const subtitle = (scenarioLabel && capitalizedGender) ? `${scenarioLabel} - ${capitalizedGender}` : (scenarioLabel || '');
    phoneContent.innerHTML = `
      <div class="text-center px-6 flex flex-col items-center">
        <div class="mb-6 flex items-center justify-center gap-1 h-12">
          <div class="audio-bar-call w-1.5 bg-brandblue rounded-full" style="animation: audioWave1 1.2s ease-in-out infinite;"></div>
          <div class="audio-bar-call w-1.5 bg-brandblue rounded-full" style="animation: audioWave2 1.0s ease-in-out infinite;"></div>
          <div class="audio-bar-call w-1.5 bg-brandblue rounded-full" style="animation: audioWave3 1.4s ease-in-out infinite;"></div>
          <div class="audio-bar-call w-1.5 bg-[#02b1ea] rounded-full" style="animation: audioWave4 1.1s ease-in-out infinite;"></div>
          <div class="audio-bar-call w-1.5 bg-brandblue rounded-full" style="animation: audioWave3 1.3s ease-in-out infinite;"></div>
          <div class="audio-bar-call w-1.5 bg-[#02b1ea] rounded-full" style="animation: audioWave2 1.15s ease-in-out infinite;"></div>
          <div class="audio-bar-call w-1.5 bg-brandblue rounded-full" style="animation: audioWave1 1.25s ease-in-out infinite;"></div>
        </div>
        <div class="text-xl font-semibold text-slate-900 mb-1.5">Call in progress</div>
        <div class="text-base text-slate-500 mb-3">${subtitle}</div>
        <div id="callTimer" class="text-2xl font-light text-branddark">00:00</div>
      </div>
    `;
    callBtn.disabled = false;
    callBtn.className = "w-16 h-16 rounded-full bg-red-500 hover:bg-red-600 flex items-center justify-center shadow-lg transition-colors";
  }
}

// Gender buttons
document.getElementById('genderFemale').addEventListener('click', () => setGender('female'));
document.getElementById('genderMale').addEventListener('click',    () => setGender('male'));

/**
 * Fetches the available scenarios and genders from the backend.
 * Populates the dropdown and resets the phone UI.
 * 
 * @async
 * @returns {Promise<void>}
 */
async function loadOptions() {
  try {
    const res = await fetch('/options');
    const data = await res.json();

    scenarioSelect.innerHTML = '';
    (data.scenarios || []).forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.id;      // e.g., "scenario_1" or "test_example"
      opt.textContent = s.label;
      scenarioSelect.appendChild(opt);
    });

    // data.voices is an array like [{id:"female", voices:[{id,label}...]}, {id:"male", ...}]
    voicesByGender = { female: [], male: [] };
    (data.voices || []).forEach(group => {
      if (group && group.id && Array.isArray(group.voices)) {
        voicesByGender[group.id] = group.voices;
      }
    });

    // Initialize voice dropdown for current gender
    populateVoiceOptions(selectedGender);

    // initial phone message - always start with not-loaded
    setPhoneState('not-loaded');
    updateLaunchButton();
  } catch (e) {
    console.error(e);
    statusEl.textContent = 'Failed to load options from server. Check /options route.';
    setPhoneState('not-loaded');
    updateLaunchButton();
  }
}

/**
 * Poll the server logs and detect readiness marker.
 * @returns {Promise<boolean>} true when ready line is seen
 */
async function pollForModelReady() {
  try {
    const res = await fetch('/logs');
    const data = await res.json();
    const logText = data.log || '';

    if (logText.includes('Models are loaded and ready.')) {
      // Model is ready!
      if (loadingPollTimer) {
        clearInterval(loadingPollTimer);
        loadingPollTimer = null;
      }
      isConnecting = false;
      isModelLoaded = true;
      setPhoneState('ready');
      updateLaunchButton();
      return true;
    }
    return false;
  } catch (e) {
    console.error('Error polling logs:', e);
    return false;
  }
}

// Multi-purpose Launch/Stop button handler
document.getElementById('launchBtn').addEventListener('click', async (event) => {
  const btn = event?.currentTarget || document.getElementById('launchBtn');

  // If we're connecting, loaded, or in a call, this button stops/cancels
  if (isConnecting || isModelLoaded || isCallActive) {
    await stopCaller();
    return;
  }

  // Otherwise, we're in State 1 - launch the caller
  statusEl.textContent = '';
  const scenario = scenarioSelect.value;
  if(!scenario){
    alert('Please select a scenario');
    return;
  }

  const voice = voiceSelect.value;
  if (!voice) {
    alert('Please select a voice for the chosen gender');
    return;
  }

  try {
    // Show loading state
    if(btn){ btn.textContent = 'Loading...'; btn.disabled = true; }
    setPhoneState('connecting');
    isConnecting = true;

    const res = await fetch('/launch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario, gender: selectedGender, voice })
    });
    const data = await res.json();
    statusEl.textContent = JSON.stringify(data, null, 2);

    // Check if launch was successful
    if (data.status === 'launched' || data.status === 'already running') {
      // Update button to show "Cancel loading"
      updateLaunchButton();

      // Start polling for "Models are loaded and ready."
      if (loadingPollTimer) {
        clearInterval(loadingPollTimer);
      }

      // Check immediately first
      const ready = await pollForModelReady();
      if (!ready) {
        // If not ready yet, poll every 500ms
        loadingPollTimer = setInterval(pollForModelReady, 500);
      }
    } else {
      // Launch failed
      alert(data.message || data.status || 'Launch error');
      isConnecting = false;
      setPhoneState('not-loaded');
      updateLaunchButton();
    }
  } catch (e) {
    console.error(e);
    statusEl.textContent = 'Failed to launch. See console.';
    alert('Failed to launch');
    isConnecting = false;
    setPhoneState('not-loaded');
    updateLaunchButton();
  }
});

// Phone Call button (start/stop)
callBtn.addEventListener('click', async () => {
  if(!isModelLoaded){
    return;
  }
  if(!isCallActive){
    // START call -> /run
    try {
      const res = await fetch('/run', { method: 'POST' });
      await res.json();
      // treat any ok status as success to keep behavior same as your previous UI
      isCallActive = true;
      callSeconds = 0;
      const scenarioLabel = scenarioSelect.options[scenarioSelect.selectedIndex]?.textContent || '';
      setPhoneState('connected', scenarioLabel, selectedGender);
      updateLaunchButton(); // Update to show "End & unload"
      callTimer = setInterval(() => {
        callSeconds += 1;
        const m = String(Math.floor(callSeconds/60)).padStart(2,'0');
        const s = String(callSeconds%60).padStart(2,'0');
        const el = document.getElementById('callTimer');
        if(el) el.textContent = `${m}:${s}`;
      }, 1000);
    } catch {
      /* ignore */
    }
  } else {
    // END call -> /stop (this will also stop the caller)
    await stopCaller();
  }
});

/** Unified stop/cancel behavior; clears timers and resets UI. */
async function stopCaller(){
  const btn = document.getElementById('launchBtn');

  try {
    // Show stopping feedback
    if(btn){ btn.textContent = 'Stopping...'; btn.disabled = true; }

    const res = await fetch('/stop', { method: 'POST' });
    await res.json();
  } catch (e) {
    console.error('Error stopping caller:', e);
  }

  // Reset all state
  isCallActive = false;
  isModelLoaded = false;
  isConnecting = false;

  // Clear all timers
  if(callTimer){ clearInterval(callTimer); callTimer = null; }
  if(loadingPollTimer){ clearInterval(loadingPollTimer); loadingPollTimer = null; }
  if(loadingDotsTimer){ clearInterval(loadingDotsTimer); loadingDotsTimer = null; }

  // Reset UI to initial state
  setPhoneState('not-loaded');
  updateLaunchButton();
}

/** Periodically refresh the text logs panel. */
async function refreshLogs(){
  try {
    const res = await fetch('/logs');
    const data = await res.json();
    logsEl.textContent = data.log || '';
  } catch { /* ignore */ }
}
setInterval(refreshLogs, 2000);

// Init
loadOptions();
setGender('female');
