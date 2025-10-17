const scenarioSelect = document.getElementById('scenarioSelect');
const statusEl       = document.getElementById('status');
const logsEl         = document.getElementById('logs');

const callBtn        = document.getElementById('callBtn');
const phoneContent   = document.getElementById('phoneContent');
const phoneTimeEl    = document.getElementById('phoneTime');

let selectedGender   = 'female';
let isModelLoaded    = false;
let isCallActive     = false;
let callTimer        = null;
let callSeconds      = 0;
let loadingPollTimer = null;

function setGender(g) {
  selectedGender = g;
  document.querySelectorAll('.gender-btn').forEach(btn => {
    btn.dataset.active = (btn.dataset.gender === g) ? 'true' : 'false';
  });
}

// Update fake phone clock
function updatePhoneTime(){
  const now = new Date();
  phoneTimeEl.textContent = now.toLocaleTimeString('en-US', { hour: 'numeric', minute:'2-digit', hour12:true });
}
setInterval(updatePhoneTime, 1000);
updatePhoneTime();

// UI states for phone
function setPhoneState(state, scenarioLabel='', genderLabel=''){
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
      <div class="text-sm text-slate-500 mt-2">Please wait...</div>
    `;
    callBtn.disabled = true;
    callBtn.className = "w-16 h-16 rounded-full bg-gray-300 cursor-not-allowed flex items-center justify-center shadow-lg";
  } else if(state === 'ready'){
    phoneContent.innerHTML = `
      <div class="text-2xl font-medium text-slate-900 leading-tight">Ready to start</div>
      <div class="text-sm text-slate-500 mt-2">Tap the button below to begin</div>
    `;
    callBtn.disabled = false;
    callBtn.className = "w-16 h-16 rounded-full bg-green-500 hover:bg-green-600 hover:scale-105 flex items-center justify-center shadow-lg transition-all";
  } else if(state === 'connected'){
    const subtitle = (scenarioLabel && genderLabel) ? `${scenarioLabel} - ${genderLabel}` : (scenarioLabel || '');
    phoneContent.innerHTML = `
      <div class="text-center px-6 flex flex-col items-center">
        <div class="relative mb-5">
          <div class="absolute inset-0 bg-brandblue rounded-full pulse-ring opacity-30"></div>
          <div class="w-20 h-20 bg-gradient-to-br from-brandblue to-branddark rounded-full flex items-center justify-center relative z-10">
            <svg class="w-10 h-10 text-white" viewBox="0 0 24 24" fill="currentColor">
              <path d="M6.62 10.79a15.05 15.05 0 006.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.56 0 1 .44 1 1V21c0 .56-.44 1-1 1C10.3 22 2 13.7 2 3c0-.56.44-1 1-1h3.5c.56 0 1 .44 1 1 0 1.24.2 2.45.57 3.57.11.35.03.74-.24 1.02l-2.2 2.2z"/>
            </svg>
          </div>
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

// Options loader
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

    // initial phone message - always start with not-loaded
    setPhoneState('not-loaded');
  } catch (e) {
    console.error(e);
    statusEl.textContent = 'Failed to load options from server. Check /options route.';
    setPhoneState('not-loaded');
  }
}

// Poll logs to check if model is ready
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
      isModelLoaded = true;
      setPhoneState('ready');
      const btn = document.getElementById('launchBtn');
      if (btn) {
        btn.textContent = 'Load caller';
        btn.disabled = false;
      }
      return true;
    }
    return false;
  } catch (e) {
    console.error('Error polling logs:', e);
    return false;
  }
}

// Launch (Load caller)
document.getElementById('launchBtn').addEventListener('click', async (event) => {
  statusEl.textContent = '';
  const scenario = scenarioSelect.value;
  if(!scenario){
    alert('Please select a scenario');
    return;
  }

  const btn = event?.currentTarget || document.getElementById('launchBtn');

  try {
    // show feedback
    if(btn){ btn.textContent = 'Loading caller...'; btn.disabled = true; }
    setPhoneState('connecting');

    const res = await fetch('/launch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario, gender: selectedGender })
    });
    const data = await res.json();
    statusEl.textContent = JSON.stringify(data, null, 2);

    // Check if launch was successful
    if (data.status === 'launched' || data.status === 'already running') {
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
      setPhoneState('not-loaded');
      if(btn){ btn.textContent = 'Load caller'; btn.disabled = false; }
    }
  } catch (e) {
    console.error(e);
    statusEl.textContent = 'Failed to launch. See console.';
    alert('Failed to launch');
    setPhoneState('not-loaded');
    if(btn){ btn.textContent = 'Load caller'; btn.disabled = false; }
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
    // END call -> /stop
    await endCall();
  }
});

async function endCall(){
  try {
    const res = await fetch('/stop', { method: 'POST' });
    await res.json();
  } catch {}
  isCallActive = false;
  isModelLoaded = false; // Reset after call ends
  if(callTimer){ clearInterval(callTimer); callTimer = null; }
  if(loadingPollTimer){ clearInterval(loadingPollTimer); loadingPollTimer = null; }
  setPhoneState('not-loaded');

  // Re-enable the load caller button
  const btn = document.getElementById('launchBtn');
  if (btn) {
    btn.textContent = 'Load caller';
    btn.disabled = false;
  }
}

// Logs - auto-refresh
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
