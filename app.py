import os, sys, subprocess, threading, json, time
from flask import Flask, render_template, jsonify, request
import subprocess
import threading
import signal
import os
import sys

app = Flask(__name__)
process = None  # global process reference

PROMPTS_ROOT = "prompts"
GENDER_TO_DIR = {"female": "female_char", "male": "male_char"}

def list_scenarios():
    """
    Scan prompts/ and return folder names that are directories and not hidden.
    Example return: ["scenario_1", "scenario_2", "test_example"]
    """
    if not os.path.isdir(PROMPTS_ROOT):
        return []
    entries = []
    for name in os.listdir(PROMPTS_ROOT):
        full = os.path.join(PROMPTS_ROOT, name)
        if os.path.isdir(full) and not name.startswith("."):
            entries.append(name)
    entries.sort()
    return entries

def display_label(folder_name: str) -> str:
    # Show as "test example" (keep lowercase as requested, just replace underscores with spaces)
    return folder_name.replace("_", " ")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/options', methods=['GET'])
def options():
    scenarios = [
        {"id": s, "label": display_label(s)}
        for s in list_scenarios()
    ]
    return jsonify({
        "scenarios": scenarios,
        "genders": [
            {"id": "female", "label": "female"},
            {"id": "male", "label": "male"}
        ]
    })

@app.route('/launch', methods=['POST'])
def launch():
    global process

    # If already running, short-circuit
    if process is not None and process.poll() is None:
        return jsonify({"status": "already running"})

    # Parse choices from client
    data = request.get_json(silent=True) or {}
    selected_scenario = data.get("scenario")  # expects folder name like "scenario_1" or "test_example"
    selected_gender = data.get("gender")      # "female" or "male"

    # Fallbacks if nothing provided
    available = list_scenarios()
    if not available:
        return jsonify({"status": "error", "message": "No scenarios found under prompts/"}), 400

    if not selected_scenario or selected_scenario not in available:
        selected_scenario = available[0]

    if selected_gender not in GENDER_TO_DIR:
        selected_gender = "female"

    # Build prompt.json path
    gender_dir = GENDER_TO_DIR[selected_gender]
    prompt_file = os.path.join(PROMPTS_ROOT, selected_scenario, gender_dir, "prompt.json")

    if not os.path.isfile(prompt_file):
        return jsonify({
            "status": "error",
            "message": f"prompt.json not found for scenario '{selected_scenario}' and gender '{selected_gender}'",
            "prompt_file": prompt_file
        }), 400

    # Create a unique output file per run
    ts = time.strftime("%Y%m%d-%H%M%S")
    os.makedirs("outputs", exist_ok=True)
    output_file = os.path.join("outputs", f"{selected_scenario}_{selected_gender}_{ts}.txt")

    cmd = [
        'python', 'main.py',
        '--prompt-file', prompt_file,
        '--output-file', output_file,
        '--tts-config', 'tts_config_cosyvoice.json'
    ]

    # Start the process (Windows vs POSIX)
    if sys.platform == "win32":
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            preexec_fn=os.setsid
        )

    # Background thread to continuously read output and save to file
    def log_reader():
        with open("outputs/web_log.txt", "w", encoding="utf-8") as logf:
            for line in process.stdout:
                logf.write(line)
                logf.flush()

    threading.Thread(target=log_reader, daemon=True).start()

    return jsonify({
        "status": "launched",
        "scenario": selected_scenario,
        "gender": selected_gender,
        "prompt_file": prompt_file,
        "output_file": output_file
    })

@app.route('/run', methods=['POST'])
def run_step():
    global process
    if process is None or process.poll() is not None:
        return jsonify({"status": "process not running"})

    # Send ENTER to stdin to trigger the next stage
    process.stdin.write("\n")
    process.stdin.flush()
    return jsonify({"status": "enter sent"})

@app.route('/stop', methods=['POST'])
def stop():
    global process
    if process is None or process.poll() is not None:
        return jsonify({"status": "no process running"})

    try:
        if sys.platform == "win32":
            # Windows: emulate Ctrl-C using CTRL_BREAK_EVENT to the process group
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            # POSIX: send SIGINT to the whole group (like Ctrl-C)
            os.killpg(process.pid, signal.SIGINT)

        # Optionally close stdin so the app can see EOF if it listens for it
        try:
            process.stdin.close()
        except Exception:
            pass

        # Give it a moment to exit gracefully; then escalate if needed
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Try a softer terminate, then kill
            if sys.platform == "win32":
                process.terminate()
            else:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if sys.platform == "win32":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()

        status = "stopped"
    except Exception as e:
        status = f"error: {e}"

    process = None
    return jsonify({"status": status})

@app.route('/logs', methods=['GET'])
def get_logs():
    try:
        with open("outputs/web_log.txt", "r", encoding="utf-8") as f:
            return jsonify({"log": f.read()})
    except FileNotFoundError:
        return jsonify({"log": ""})

if __name__ == '__main__':
    app.run(debug=True)
