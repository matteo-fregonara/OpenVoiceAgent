import json
import os
import time
import requests
import threading
from typing import Callable, Dict, Any, List
from lib.conversation import Conversation

class LLMHandler:
    """
    Class that handles connections to the LLM through LMStudio.
    
    Internal States:
    - completeion_params: json of parameters for the LLM
    - max_tokens: max_tokens to be stored in the conversation history
    - conversation: Conversation object that stores history
    - log_stats: whether to log statistics of operation or not.
    """
    def __init__(
            self,
            completion_params_file: str = "llm_lmstudio/completion_params.json",
            max_tokens: int = 1000,
            log_stats: bool = False):

        self.completion_params = self.load_completion_params(completion_params_file)
        self.max_tokens = max_tokens
        self.conversation = Conversation(max_tokens)
        self.log_stats = log_stats
        
        # LMStudio typically runs on localhost:1234
        self.api_url = "http://localhost:1234/v1/chat/completions"

        # Variables that support streaming abort during user interruption
        self.session = requests.Session()
        self._active_response = None
        self._abort = threading.Event()

    def load_completion_params(self, file_path: str) -> Dict[str, Any]:
        """Loads the parameter json file."""
        with open(file_path, 'r') as f:
            return json.load(f)

    def add_user_text(self, text: str):
        """Adds user text to the conversation."""
        self.conversation.add_user_message(text)

    def add_assistant_text(self, text: str):
        """Adds ai text to the conversation."""
        self.conversation.add_assistant_message(text)

    def create_messages(self, system_prompt: str) -> List[Dict[str, str]]:
        """Creates the list of messages dictionary with the original system prompt."""
        messages = [{"role": "system", "content": system_prompt}]
        for role, message in self.conversation.get_history():
            messages.append({"role": role, "content": message})
        return messages

    def generate_response(
            self,
            system_prompt: str,
            on_token: Callable[[str], None] = None):
        """Queries LMStudio LLM to get AI response."""

        messages = self.create_messages(system_prompt)
        
        payload = {
            "model": self.completion_params["model"],
            "messages": messages,
            "stream": True,
            **self.completion_params.get("parameters", {})
        }

        self.payload = json.dumps(payload, indent=4)

        start_time = time.time()
        collected_messages = []
        self._abort.clear()

        try:
            # NOTE: leave read timeout None for long streams. Connect timeout small.
            response = self.session.post(self.api_url, json=payload, stream=True, timeout=(3.05, None))
            self._active_response = response

            for line in response.iter_lines():
                if self._abort.is_set():
                    break
                if line:
                    line = line.decode('utf-8')
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if data['choices'][0]['finish_reason'] is not None:
                            break
                        token = data['choices'][0]['delta'].get('content', '')
                        if token:
                            collected_messages.append(token)
                            if on_token:
                                on_token(token)
                        
                            if self.log_stats:
                                chunk_time = time.time() - start_time
                                print(f"Token received {chunk_time:.2f} seconds after request: {token}")

            full_response = ''.join(collected_messages)

            if self.log_stats:
                total_time = time.time() - start_time
                print(f"Full response received {total_time:.2f} seconds after request")
                print(f"Full response: {full_response}")

        except RuntimeError as e:
            # Let our barge-in cancellation bubble up
            if "CancelledByBargeIn" in str(e):
                raise
            else:
                print(f"RuntimeError: {e}")
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            try:
                if self._active_response is not None:
                    self._active_response.close()
            except Exception as e:
                print(f"A finally error occured: {e}")
            self._active_response = None

    def abort(self):
        """Aborts the currently active response during user interruption."""
        self._abort.set()
        try:
            if self._active_response is not None:
                self._active_response.close()
        except Exception:
            pass

    def write_payload(self, file_path: str = 'payload.txt', mode='w'):
        """Write the message history and LLM payload to a txt file."""
        with open(file_path, mode) as f:
            f.write(self.payload)