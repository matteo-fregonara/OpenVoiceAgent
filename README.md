# OpenVoiceAgent (JIP 2025 @ KLM)  
_KLM Next-Gen AI/XR Trainings_

![License](https://img.shields.io/badge/License-Apache_2\.0-blue)
![Python](https://img.shields.io/badge/python-3\.10-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

## Overview

**OpenVoiceAgent** is a proof-of-concept conversational AI agent capable of handling **high-stakes training dialogues**.  
It integrates:
- **STT** (Speech-To-Text for speech recognition)
- **TTT** (Text-to-Text using Large Language Models for text generation)
- **TTS** (Text-To-speech for speech synthesis)
- **Flask frontend** + multi-threaded pipeline

## Key Features
- Fully **on-premise** (no external API calls)
- **FasterWhisper** STT for low-latency speech recognition
- Local inference via **LM Studio** (Llama 3.2 1B / 3B Instruct)
- **CosyVoice** TTS with reference-voice cloning
- CLI and **Flask** frontend interface
- **Multi-threaded** real-time processing pipeline

Developed as part of the TU Delft × KLM Joint Interdisciplinary Project (JIP) 2025.

## Quickstart

0. Install Visual Studio with C++ Build Tools

1. Install a version of [miniconda](https://repo.anaconda.com/miniconda/)

2. Initialize your environment (in miniconda)

```
conda create -n openvoiceagent python=3.10.9
conda activate openvoiceagent
```

3. Clone this repository

```
git clone https://github.com/mfregonara/OpenVoiceAgent.git
cd OpenVoiceAgent
```

4. Install the required dependencies (assuming using the GPU)

```
pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt 
conda install -c conda-forge ffmpeg=4.3.1 
```

_Note: GPU recommended. CPU fallback works but is slower._

5. Install [LMStudio](https://lmstudio.ai/) and download the `Llama-3.2-8b-instruct`, `Llama-3.2-3b-instruct` and `Llama-3.2-1b-instruct` models

6. Set up the TTS model

    1. Initialize Submodules (including Cosyvoice) 
        ```
        git submodule update --init --recursive
        ```

    2. Navigate and Install Dependencies
        ```
        cd third_party/cosyvoice
        pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host=mirrors.aliyun.com
        ```

    3. Download Model Weights
        ```
        git clone https://www.modelscope.cn/iic/CosyVoice2-0.5B.git pretrained_models/CosyVoice2-0.5B
        ```

7. (Optional) Switch Torch versions if using a newer or high-end GPU (e.g., RTX 5090)
    ```
    pip uninstall torch torchvision torchaudio
    pip install torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128 
    ```

    Note: switch out cu128 for the correct cuda runtime shown by `nvidia-smi`

8. Launch LM Studio

   - Load one of the supported models: `Llama-3.2-8b-instruct` or `Llama-3.2-3b-instruct`
   - For best real-time performance, use `Llama-3.2-1b-instruct`
   - Start the **Local Inference Server** (typically runs on `localhost:1234`)
   - Verify the server is active before launching the pipeline

9. Run application (two options)
    1. CLI: From command line with terminal intermediate outputs
        ```
        python main.py --prompt-file prompts/scenario_1/female_char/prompt.json --output-file outputs/example.txt --tts-config tts_config_cosyvoice.json --wavs-directory wavs/reference_woman/Standard
        ```

        - `prompt-file`: points to the JSON file containing the system prompt to the LLM
        - `output-file`: points to the txt file that will contain the final transcription after the pipeline finishes
        - `tts-config`: points to the json file that contains the parameters for the tts engine

    2. Flask: With frontend without intermediate outputs
        ```
        flask run
        ```

### Frontend usage
1. Launch LM Studio → Load model → Start local server
2. Run `flask run`
3. Open browser at `http://127.0.0.1:5000`
4. Select scenario, gender, and voice → Click **Load Model**
5. Logs appear in `outputs/web_log.txt`

### CLI Parameters
_Note: optional if using Flask frontend_

| Flag               | Description                    |
| ------------------ | ------------------------------ |
| `--prompt-file`    | Path to LLM system prompt JSON |
| `--output-file`    | Path for the output transcript |
| `--tts-config`     | TTS configuration JSON         |
| `--wavs-directory` | Reference voice folder path    |

## Repository Structure

```
.
├─ main.py                                  # Pipeline entry-point (CLI)
├─ app.py / templates / static              # Flask frontend
├─ prompts/
│  ├─ scenario_1/
│  │  ├─ female_char/prompt.json
│  │  └─ male_char/prompt.json
│  └─ scenario_2/...
├─ wavs/
│  ├─ reference_woman/Standard/...
│  └─ reference_man/Standard/...
├─ third_party/
│  ├─ CosyVoice/                             # TTS engine submodule
│  │  └─ pretrained_models/CosyVoice2-0.5B   # TTS model weights (downloaded from ModelScope)
│  └─ pengzhendong/wetext/                   # Python text-processing submodule
├─ tts_config_cosyvoice.json
├─ requirements.txt
└─ outputs/

```

## Customization

### Adding Your Own Prompts

Each prompt defines a training scenario and lives in `prompts/`:

```
prompts/
└─ scenario_{N}/
   ├─ female_char/prompt.json
   └─ male_char/prompt.json
```

An example of `prompt.json`

```
{
    "char": "Miss Johnson",
    "user": "KLM care team member",
    "system_prompt": "You are {char}, a 31-year-old woman, worried and angry about her missing brother. Do not act like an AI. [..]"
}
```

Prompts are dynamically loaded by the frontend dropdowns. `scenario_{N}` and `prompt.json` can be any name.

### Adding Your Own Voices

Add new voice reference samples under wavs/:

```
wavs/
└─ reference_{woman|man}/
   └─ <VariantName>/
      ├─ ref_01.wav
      ├─ ref_02.wav
      └─ ...
```

**Recommended audio requirements**
- `.wav` format  
- **16 kHz** sample rate (CosyVoice automatically downsamples higher rates)  
- **Mono** or **stereo** — both accepted  
- Typical **16-bit PCM** (default for most recorders)  
- Each clip: 3 – 10 seconds of clear speech  
- Avoid background noise, music, or long silences

## Troubleshooting

If you encounter errors related to NVIDIA libraries, follow these steps to resolve them.

---

#### `RealTimeSTT: root - ERROR - Library cublas64_12.dll is not found or cannot be loaded`

This error means a required NVIDIA library is missing. To fix this, you need to download and install the cuDNN library.

1.  Go to the official **NVIDIA cuDNN downloads** page: [https://developer.nvidia.com/cudnn-downloads](https://developer.nvidia.com/cudnn-downloads)
2.  Download the appropriate version.
3.  Once downloaded, copy the files from the `bin` folder of your cuDNN installation (e.g., `C:\Program Files\NVIDIA\CUDNN\v9.13\bin\12.9`) and paste them into your Conda environment's library bin folder.

    **Example Path:**
    `C:\Users\<your_username>\miniconda3\envs\<your_env_name>\Library\bin`

---

#### `RealTimeSTT: root - ERROR - cuDNN failed with status CUDNN_STATUS_EXECUTION_FAILED`

This error often indicates a **GPU memory issue**. The GPU may not have enough free memory to run the process.

**Solution:** Check your GPU's memory usage and close any other applications that might be using it. You can use a tool like **NVIDIA-SMI** to monitor GPU memory.

If your GPU memory is truly empty, you may need to install the CPU version of PyTorch as a fallback. Run the following command:

```bash
pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --index-url [https://download.pytorch.org/whl/cpu](https://download.pytorch.org/whl/cpu)
```

---

#### `HTTPConnectionPool(host='localhost', port=1234): Max retries exceeded`

This error indicates that the application is trying to connect to a server that is not running.

**Solution:** If you are using **LM Studio**, make sure you have loaded a model and started the local inference server. You can find the button to start the server in the **Local Server** tab of the LM Studio application.

---

#### `Could not locate cudnn_ops64_9.dll. Please make sure it is in your library path!`

**Solution:** Run command.

```
pip install "nvidia-cuda-runtime-cu12" "nvidia-cublas-cu12" "nvidia-cudnn-cu12==9.*" "nvidia-cuda-nvrtc-cu12"
```

## Supported Environments

| Component | Tested Version                        |
| --------- | ---------------------------           |
| OS        | Windows 11, Ubuntu 22.04              |
| Python    | 3.10.9                                |
| GPU       | RTX 4070 (slow), RTX 5090 (optimal)   |
| STT       | FasterWhisper                         |
| TTT/LLM   | LM Studio – Llama 3.2 1B/3B/8b        |
| TTS       | CosyVoice 0.5B                        |

## License

This project is released under the **Apache License 2.0**.  
Refer to the [`LICENSE`](LICENSE) file for details.  
Components such as **CosyVoice**, **FasterWhisper**, and **Llama** follow their respective licenses.

## Acknowledgements

- **KLM Royal Dutch Airlines**  
- **TU Delft — Joint Interdisciplinary Project (JIP) 2025**  
- Open-source frameworks powering this project:  
  **FasterWhisper**, **CosyVoice**, **LM Studio**, **PyTorch**, and **Meta Llama**
