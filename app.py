from flask import Flask, render_template, jsonify
import subprocess
import threading
import signal
import os
import sys

app = Flask(__name__)
process = None  # global process reference

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/launch', methods=['POST'])
def launch():
    global process
    if process is not None and process.poll() is None:
        return jsonify({"status": "already running"})

    cmd = [
        'python', 'main.py',
        '--char-gender', 'female',
        '--scenario', '1',
        '--guidelines', 'long',
        '--output-file', 'outputs/example.txt',
        '--tts-config', 'tts_config_cosyvoice.json'
    ]

    if sys.platform == "win32":
        # Windows: create a new process group so we can send CTRL_BREAK_EVENT
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
        # POSIX: start in a new session (new process group)
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

    return jsonify({"status": "launched"})

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
