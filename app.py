from flask import Flask, render_template, jsonify
import subprocess
import threading
import signal

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

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
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

    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=3)  # wait up to 3 seconds
    except subprocess.TimeoutExpired:
        process.kill()  # force kill if still running

    return jsonify({"status": "terminated"})

@app.route('/logs', methods=['GET'])
def get_logs():
    try:
        with open("outputs/web_log.txt", "r", encoding="utf-8") as f:
            return jsonify({"log": f.read()})
    except FileNotFoundError:
        return jsonify({"log": ""})

if __name__ == '__main__':
    app.run(debug=True)
