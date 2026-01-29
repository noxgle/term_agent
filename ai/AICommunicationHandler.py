import json
import time
import re
from typing import Optional

class AICommunicationHandler:
    def __init__(self, terminal, logger=None):
        self.terminal = terminal
        self.logger = logger if logger else self._create_dummy_logger()

    def send_request(self, system_prompt: str, user_prompt: str, request_format: str = "json") -> Optional[str]:
        """
        Handles AI communication with retries and standardized error handling.
        
        Args:
            system_prompt: Base system instructions for the AI
            user_prompt: User-provided prompt content
            request_format: Expected response format ('json' or 'text')
            
        Returns:
            AI response content or None on failure
        """
        max_attempts = 5
        base_delay = 10  # seconds
        
        for attempt in range(1, max_attempts + 1):
            try:
                response = self._call_ai_api(system_prompt, user_prompt)
                if not response:
                    raise ValueError("Empty response from AI")
                
                if request_format == "json":
                    return self._process_json_response(response)
                
                return response
            
            except Exception as e:
                self._handle_retry_error(attempt, max_attempts, e)
                if attempt < max_attempts:
                    time.sleep(base_delay * attempt)
        
        return None

    def _call_ai_api(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """Route request to appropriate AI engine"""
        engine = self.terminal.ai_engine
        
        if engine == "ollama":
            return self.terminal.connect_to_ollama(system_prompt, user_prompt)
        elif engine == "ollama-cloud":
            return self.terminal.connect_to_ollama_cloud(system_prompt, user_prompt)
        elif engine == "google":
            return self.terminal.connect_to_gemini(f"{system_prompt}\n{user_prompt}")
        elif engine == "openai":
            return self.terminal.connect_to_chatgpt(system_prompt, user_prompt)
        elif engine == "openrouter":
            return self.terminal.connect_to_openrouter(system_prompt, user_prompt)
        else:
            raise ValueError(f"Unsupported AI engine: {engine}")

    def _process_json_response(self, response: str) -> Optional[str]:
        """Extract and validate JSON response"""
        try:
            json_match = re.search(r'```json\s*(\{.*\}|\[.*\])\s*```', response, re.DOTALL)
            if not json_match:
                json_match = re.search(r'(\{.*\}|\[.*\])', response, re.DOTALL)

            if json_match:
                return json_match.group(1)
            return json.loads(response)
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error: {e}")
            raise ValueError("Invalid JSON response") from e

    def _handle_retry_error(self, attempt: int, max_attempts: int, error: Exception):
        """Log and handle retry errors"""
        error_msg = f"Attempt {attempt}/{max_attempts} failed: {str(error)}"
        if self.logger:
            self.logger.warning(error_msg)
        else:
            print(f"AICommunicationHandler: {error_msg}")

    def _create_dummy_logger(self):
        """Fallback logger if none provided"""
        class DummyLogger:
            def log(self, *args, **kwargs): pass
            def debug(self, *args, **kwargs): pass
            def info(self, *args, **kwargs): pass
            def warning(self, *args, **kwargs): pass
            def error(self, *args, **kwargs): pass
        return DummyLogger()