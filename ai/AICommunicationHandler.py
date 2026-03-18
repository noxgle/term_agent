import json
import time
import re
from typing import Optional, Tuple

# Import enhanced JSON validator
try:
    from json_validator.JsonValidator import create_validator, JsonValidationError
    JSON_VALIDATOR_AVAILABLE = True
except ImportError:
    JSON_VALIDATOR_AVAILABLE = False


class AICommunicationHandler:
    def __init__(self, terminal, logger=None):
        self.terminal = terminal
        self.logger = logger if logger else self._create_dummy_logger()
        
        # Initialize enhanced JSON validator if available
        self.json_validator = None
        if JSON_VALIDATOR_AVAILABLE:
            try:
                self.json_validator = create_validator("flexible")
                self.logger.info("AICommunicationHandler: Enhanced JSON validator initialized")
            except Exception as e:
                self.logger.warning(f"AICommunicationHandler: Failed to initialize JSON validator: {e}")

    def send_request(
        self,
        system_prompt: str,
        user_prompt: str,
        request_format: str = "json",
        operation: str = "ai_request",
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """
        Handles AI communication with retries and standardized error handling.
        
        Args:
            system_prompt: Base system instructions for the AI
            user_prompt: User-provided prompt content
            request_format: Expected response format ('json' or 'text')
            operation: Operation name for token accounting
            max_tokens: Optional max tokens for the model response
            
        Returns:
            AI response content or None on failure
        """
        max_attempts = 1 if operation.startswith("compact_") else 5
        base_delay = 10  # seconds
        
        # Calculate input tokens for tracking
        input_text = f"{system_prompt}\n{user_prompt}"
        input_tokens = self._estimate_tokens(input_text)
        
        for attempt in range(1, max_attempts + 1):
            try:
                response = self._call_ai_api(system_prompt, user_prompt, max_tokens=max_tokens)
                if not response:
                    raise ValueError("Empty response from AI")
                
                # Calculate output tokens
                output_tokens = self._estimate_tokens(response)
                
                # Track token usage
                self._track_token_usage(
                    operation=operation,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    attempt=attempt
                )
                
                if request_format == "json":
                    return self._process_json_response(response)
                
                return response
            
            except Exception as e:
                self._handle_retry_error(attempt, max_attempts, e)
                if attempt < max_attempts:
                    time.sleep(base_delay * attempt)
        
        return None

    def _call_ai_api(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> Optional[str]:
        """Route request to appropriate AI engine"""
        engine = self.terminal.ai_engine
        
        if engine == "ollama":
            return self.terminal.connect_to_ollama(system_prompt, user_prompt, max_tokens=max_tokens)
        elif engine == "ollama-cloud":
            return self.terminal.connect_to_ollama_cloud(system_prompt, user_prompt, max_tokens=max_tokens)
        elif engine == "google":
            return self.terminal.connect_to_gemini(f"{system_prompt}\n{user_prompt}", max_tokens=max_tokens)
        elif engine == "openai":
            return self.terminal.connect_to_chatgpt(system_prompt, user_prompt, max_tokens=max_tokens)
        elif engine == "openrouter":
            return self.terminal.connect_to_openrouter(system_prompt, user_prompt, max_tokens=max_tokens)
        else:
            raise ValueError(f"Unsupported AI engine: {engine}")

    def _process_json_response(self, response: str) -> Optional[str]:
        """
        Extract and validate JSON response.
        Always returns a JSON string (str), never a dict/list.

        Uses enhanced JsonValidator with multiple strategies:
        - Direct JSON parsing
        - JSON5 parsing (more lenient)
        - YAML parsing
        - Markdown code block extraction
        - AI response cleaning (removes text around JSON)
        - Control characters removal
        - Multi-document JSON handling
        - Streaming JSON repair (for incomplete responses)
        - Aggressive JSON extraction
        """
        # Try enhanced validator first if available
        if self.json_validator:
            try:
                success, data, error = self.json_validator.validate_response(response)
                if success and data is not None:
                    # Return as JSON string
                    return json.dumps(data, ensure_ascii=False)
                else:
                    self.logger.debug(f"Enhanced validator did not succeed: {error}")
            except Exception as e:
                self.logger.debug(f"Enhanced validator exception: {e}")
        
        # Fallback to original parsing strategies
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

            # Strategy 5: Line-by-line NDJSON parsing - collect ALL valid JSON lines
            valid_objects = []
            for line in response.split('\n'):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    valid_objects.append(obj)
                except json.JSONDecodeError:
                    fixed = self._fix_single_quotes(line)
                    try:
                        obj = json.loads(fixed)
                        valid_objects.append(obj)
                    except json.JSONDecodeError:
                        continue

            if len(valid_objects) == 1:
                return json.dumps(valid_objects[0], ensure_ascii=False)
            elif len(valid_objects) > 1:
                return json.dumps(valid_objects, ensure_ascii=False)

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

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text using a simple approximation.
        This is a rough estimate - actual token counts may vary by model.
        
        Args:
            text: Text to estimate tokens for
            
        Returns:
            Estimated token count
        """
        if not text:
            return 0
        
        # Simple approximation: ~4 characters per token for English text
        # More accurate would be to use the actual tokenizer, but this is a good estimate
        return max(1, len(text) // 4)

    def _track_token_usage(self, operation: str, input_tokens: int, output_tokens: int, attempt: int = 1):
        """
        Track token usage for this AI communication.
        
        Args:
            operation: Type of operation (e.g., "ai_request", "plan_creation")
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated
            attempt: Retry attempt number
        """
        # Initialize token tracking if not already done
        if not hasattr(self, 'token_usage'):
            self.token_usage = {
                'total_input_tokens': 0,
                'total_output_tokens': 0,
                'total_tokens': 0,
                'operations': [],
                'cost_estimates': {}
            }
        
        # Calculate total tokens for this operation
        total_tokens = input_tokens + output_tokens
        
        # Add to running totals
        self.token_usage['total_input_tokens'] += input_tokens
        self.token_usage['total_output_tokens'] += output_tokens
        self.token_usage['total_tokens'] += total_tokens
        
        # Record this operation
        operation_record = {
            'operation': operation,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': total_tokens,
            'attempt': attempt,
            'timestamp': time.time()
        }
        self.token_usage['operations'].append(operation_record)
        
        # Log token usage
        self.logger.debug(f"Token usage - {operation} (attempt {attempt}): "
                         f"input={input_tokens}, output={output_tokens}, total={total_tokens}")
