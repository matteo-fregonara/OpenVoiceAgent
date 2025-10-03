import logging
from typing import List, Tuple

class Conversation:
    def __init__(self, max_tokens: int = 1548, debug = False, _user_msg_check_max = 4):
        self.debug = debug
        self.history: List[Tuple[str, str]] = []
        self.max_tokens = max_tokens
        self._user_msg_check_max = _user_msg_check_max # Max number of user messages to merge during check

    def add_user_message(self, text: str):
        self.history.append(("user", text))

    def add_assistant_message(self, text: str):
        self.history.append(("assistant", text))

    def get_history(self) -> List[Tuple[str, str]]:
        # Check if the user has created many messages without LLM response
        accumulated_user_messages = list()
        # Run through the most recent messages, accumulating the last four
        for role, message in reversed(self.history):
            if role != "user" or len(accumulated_user_messages) >= self._user_msg_check_max: # if a non-user message appears or we've accumulated 4 move on
                break
            accumulated_user_messages.append(message) # accumulate the text of the last user messages

        if len(accumulated_user_messages) >= 2: # only replace the last messages if there were more than one user message
            self.history = self.history[:-len(accumulated_user_messages)] + [("user", ' '.join(reversed(accumulated_user_messages)))]
        return self.history

    def clear_history(self):
        self.history.clear()

    def truncate_history(self, system_prompt: str, count_tokens_func):
        system_tokens = count_tokens_func(system_prompt)
        total_tokens = system_tokens
        truncated_history = []

        for role, message in reversed(self.history):
            message_tokens = count_tokens_func(message)
            if total_tokens + message_tokens <= self.max_tokens:
                truncated_history.insert(0, (role, message))
                total_tokens += message_tokens
            else:
                break

        removed_messages = len(self.history) - len(truncated_history)
        self.history = truncated_history

        # Log token usage information
        history_tokens = total_tokens - system_tokens
        fill_percentage = (total_tokens / self.max_tokens) * 100

        if self.debug:
            print(f"Token usage: {total_tokens}/{self.max_tokens} ({fill_percentage:.2f}%)")
            print(f"System prompt tokens: {system_tokens}")
            print(f"History tokens: {history_tokens}")
            print(f"Remaining tokens for response: {self.max_tokens - total_tokens}")

            if removed_messages > 0:
                print(f"History truncated. {removed_messages} messages removed.")

        return total_tokens