# JIP 2025: KLM Next-Gen AI/XR Trainings

## Installation

0. Install Visual Studio with C++ Build Tools

1. Install a version of [miniconda](https://repo.anaconda.com/miniconda/)

2. Initialize your environment (in miniconda)

```
> conda create -n jip-klm python=3.10.9
> conda activate jip-klm
```

3. Clone this repository

```
> git clone https://github.com/mfregonara/jip-klm-OpenAgent.git
> cd jip-klm-OpenAgent
```

4. Install the required dependencies (assuming gpu)
```
> pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu118
> pip install -r requirements.txt 
> conda install -c conda-forge ffmpeg=4.3.1 
```

5. Download the [TTS model](https://drive.google.com/file/d/16WU3U3RIUbLzrUZo9E5hNifvvK-k67WT/view?usp=sharing) and unzip in `models/` directory

6. Install [LMStudio](https://lmstudio.ai/) and download the `Llama-3.2-3b-instruct` and `Llama-3.2-1b-instruct` models

7. Change the TTS model path

In tts_config.json
```
"local_models_path": "YOUR_PATH_HERE/jip-klm-OpenAgent/models",
```

8. Run the application

```
> python main.py
```


______
NATANAEL (me) DO LATER

git submodule update --init --recursive

testing: put whytorturingme in assetes

Run pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host=mirrors.aliyun.com in cosyvoice 

git clone https://www.modelscope.cn/iic/CosyVoice2-0.5B.git pretrained_models/CosyVoice2-0.5B [supah slow]

update config file

pip install resampy
