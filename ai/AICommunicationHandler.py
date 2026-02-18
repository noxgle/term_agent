import json
import time
import re
from typing import Optional, Tuple

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
        """
        Extract and validate JSON response.
        Always returns a JSON string (str), never a dict/list.

        Handles multiple formats:
        - Single JSON object
        - JSON in markdown code blocks
        - NDJSON (newline-delimited JSON) - extracts first valid object
        - Python-style dict with single quotes
        """
        try:
            # Strategy 1: Try to parse the entire response as-is
            try:
                json.loads(response)
                return response
            except json.JSONDecodeError:
                pass

            # Strategy 2: Extract from markdown code blocks
            code_block_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', response)
            if code_block_match:
                extracted = code_block_match.group(1).strip()
                try:
                    json.loads(extracted)
                    return extracted
                except json.JSONDecodeError:
                    fixed = self._fix_single_quotes(extracted)
                    try:
                        json.loads(fixed)
                        return fixed
                    except json.JSONDecodeError:
                        pass

            # Strategy 3: Find first complete JSON object using balanced brackets
            json_obj = self._extract_first_json_object(response, '{', '}')
            if json_obj:
                try:
                    json.loads(json_obj)
                    return json_obj
                except json.JSONDecodeError:
                    fixed = self._fix_single_quotes(json_obj)
                    try:
                        json.loads(fixed)
                        return fixed
                    except json.JSONDecodeError:
                        pass

            # Strategy 4: Find first complete JSON array
            json_arr = self._extract_first_json_object(response, '[', ']')
            if json_arr:
                try:
                    json.loads(json_arr)
                    return json_arr
                except json.JSONDecodeError:
                    fixed = self._fix_single_quotes(json_arr)
                    try:
                        json.loads(fixed)
                        return fixed
                    except json.JSONDecodeError:
                        pass

            # Strategy 5: Line-by-line NDJSON parsing - extract first valid JSON line
            for line in response.split('\n'):
                line = line.strip()
                if not line:
                    continue
                try:
                    json.loads(line)
                    return line
                except json.JSONDecodeError:
                    fixed = self._fix_single_quotes(line)
                    try:
                        json.loads(fixed)
                        return fixed
                    except json.JSONDecodeError:
                        continue

            raise ValueError("Could not extract valid JSON from response")

        except Exception as e:
            self.logger.error(f"JSON decode error: {e}")
            raise ValueError(f"Invalid JSON response") from e

    def _extract_first_json_object(self, text: str, open_char: str, close_char: str) -> Optional[str]:
        """
        Extract the first complete JSON object or array using balanced bracket counting.
        Correctly handles nested structures and string literals.
        """
        start_idx = text.find(open_char)
        if start_idx == -1:
            return None

        depth = 0
        in_string = False
        escape_next = False

        for i in range(start_idx, len(text)):
            char = text[i]

            if escape_next:
                escape_next = False
                continue

            if char == '\\' and in_string:
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == open_char:
                depth += 1
            elif char == close_char:
                depth -= 1
                if depth == 0:
                    return text[start_idx:i + 1]

        return None

    def _fix_single_quotes(self, text: str) -> str:
        """
        Convert Python-style single-quoted dict syntax to valid JSON.
        Best-effort fix for common AI response formatting issues.
        """
        result = text
        # Handle keys: 'key': -> "key":
        result = re.sub(r"'([^']+)'(\s*:)", r'"\1"\2', result)
        # Handle string values: : 'value' -> : "value"
        result = re.sub(r":\s*'([^']*)'", r': "\1"', result)
        # Handle remaining single-quoted strings
        result = re.sub(r"'([^']+)'", r'"\1"', result)
        return result

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