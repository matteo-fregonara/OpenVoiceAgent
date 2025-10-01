
rem Set the python address used to run the file (CHANGE TO CORRECT ENVIRONMENT)
set "PYTHON_EXE=%USERPROFILE%\miniconda3\envs\emovc\python.exe"

rem Run the command
"%PYTHON_EXE%" "main.py" ^
  --char-gender "female" ^
  --scenario 2 ^
  --guidelines "long" ^
  --output-file "outputs\poc_tests\p4_s2.txt" ^
  --tts-config "tts_config_cosyvoice.json" ^
  --start-message "ALERT: LLM MUST BE ON: llama-3.2-3b-instruct WITH llama-3.2-1b-instruct AS SPECULATIVE DECODING. Start scenario? (press Enter to begin, Ctrl+C to exit) "