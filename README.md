# JIP 2025: KLM Next-Gen AI/XR Trainings

## Installation

0. Install Visual Studio with C++ Build Tools

1. Install a version of [miniconda](https://repo.anaconda.com/miniconda/)

2. Initialize your environment (in miniconda)

```
conda create -n jip-klm python=3.10.9
conda activate jip-klm
```

3. Clone this repository

```
git clone https://github.com/mfregonara/jip-klm-OpenAgent.git
cd jip-klm-OpenAgent
```

4. Install the required dependencies (assuming gpu)
```
pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt 
conda install -c conda-forge ffmpeg=4.3.1 
```

5. Install [LMStudio](https://lmstudio.ai/) and download the `Llama-3.2-3b-instruct` and `Llama-3.2-1b-instruct` models

6. Set up the TTS model

    1. Initialize Submodules (including Cosyvoice) 
        ```
        git submodule update --init --recursive
        ```

    2. Navigate and Install Dependencies
        ```
        cd third_party/cosyvoice
        pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host=mirrors.aliyun.com
        pip install resampy
        ```

    3. Download Model Weights
        ```
        git clone https://www.modelscope.cn/iic/CosyVoice2-0.5B.git pretrained_models/CosyVoice2-0.5B
        ```

    4. Run application from root
        ```
        python main.py --char-gender female --scenario 1 --guidelines long --output-file outputs/example.txt --tts-config tts_config_cosyvoice.json
        ```

        - `char-gender`: choose which gender you'd like to talk to. Options: female, male
        - `scenario`: choose which scenario you'd like to practice on. Options: 1, 2, 3
        - `guidelines`: choose if you would like the LLM to be guided by more guidelines (long) or less (short). Options: long, short
        - `output-file`: points to the txt file that will contain the final transcription after the pipeline finishes
        - `tts-config`: points to the json file that contains the parameters for the tts engine

        #### PoC Tests

        If you want to run a PoC test as defined in our research plan, replace `{your conda environment}` in `set "PYTHON_EXE=%USERPROFILE%\miniconda3\envs\{your conda environment}\python.exe"` in the .bat file you would like to run, and execute:
        ```
        poc_tests\pX_sY.bat
        ```

        - `X` should be the participant number (1-9)
        - `Y` should be the scenario number (1-3)

### Troubleshooting

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
