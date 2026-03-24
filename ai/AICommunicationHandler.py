import json
import time
import re
import random
import os
import threading
import queue
import signal
import sys
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
        
        # Multi-engine routing configuration
        self.ai_engines = getattr(terminal, 'ai_engines', [terminal.ai_engine])
        self.ai_engine_route = getattr(terminal, 'ai_engine_route', 'round-robin')
        self._round_robin_index = 0
        self._round_robin_lock = threading.Lock()
        
        # Log routing configuration
        if len(self.ai_engines) > 1:
            self.logger.info(f"AICommunicationHandler: Multi-engine mode with {len(self.ai_engines)} engines")
            self.logger.info(f"AICommunicationHandler: Routing mode = {self.ai_engine_route}")
        else:
            self.logger.info(f"AICommunicationHandler: Single-engine mode ({self.ai_engines[0]})")
        
        # Load timeout and retry configuration from terminal
        self._load_timeout_config()
    
    def _load_timeout_config(self):
        """Load timeout and retry configuration from terminal environment"""
        try:
            # Load timeout and retry settings from environment
            self.ai_api_timeout = int(os.getenv("AI_API_TIMEOUT", "120"))
            self.ai_api_max_retries = int(os.getenv("AI_API_MAX_RETRIES", "3"))
            self.ai_api_retry_delay = float(os.getenv("AI_API_RETRY_DELAY", "2"))
            self.ai_api_retry_backoff = float(os.getenv("AI_API_RETRY_BACKOFF", "2"))
            
            # Load timeout buffer for main thread (should be 5-10 seconds more than worker thread timeout)
            self.ai_main_thread_timeout_buffer = int(os.getenv("AI_MAIN_THREAD_TIMEOUT_BUFFER", "5"))
            
            # Load timeout API selection setting with proper validation
            use_timeout_value = os.getenv("USE_TIMEOUT_API", "true").lower()
            if use_timeout_value in ["true", "1", "yes", "on"]:
                self.use_timeout_api = True
            elif use_timeout_value in ["false", "0", "no", "off"]:
                self.use_timeout_api = False
            else:
                # Invalid value, default to true
                self.use_timeout_api = True
            
            self.logger.debug(f"AI API timeout config loaded: timeout={self.ai_api_timeout}s, "
                             f"max_retries={self.ai_api_max_retries}, retry_delay={self.ai_api_retry_delay}s, "
                             f"backoff={self.ai_api_retry_backoff}, use_timeout_api={self.use_timeout_api}, "
                             f"main_thread_timeout_buffer={self.ai_main_thread_timeout_buffer}s")
        except Exception as e:
            self.logger.warning(f"Failed to load timeout config, using defaults: {e}")
            # Set default values
            self.ai_api_timeout = 120
            self.ai_api_max_retries = 3
            self.ai_api_retry_delay = 2
            self.ai_api_retry_backoff = 2
            self.ai_main_thread_timeout_buffer = 5
            self.use_timeout_api = True

    def _get_next_engine(self) -> str:
        """
        Get the next engine based on routing mode.
        
        For round-robin: Returns engines in rotation order
        For fallback: Always returns the first engine (fallback logic is handled at higher level)
        
        Returns:
            Engine name string
        """
        if len(self.ai_engines) == 1:
            return self.ai_engines[0]
        
        if self.ai_engine_route == "round-robin":
            with self._round_robin_lock:
                engine = self.ai_engines[self._round_robin_index]
                self._round_robin_index = (self._round_robin_index + 1) % len(self.ai_engines)
                self.logger.debug(f"Round-robin selected engine: {engine} (next index: {self._round_robin_index})")
                return engine
        else:  # fallback mode
            # In fallback mode, we always start with the first engine
            # The fallback logic is handled by trying each engine in sequence
            return self.ai_engines[0]

    def _get_engine_config(self, engine: str) -> dict:
        """
        Get configuration for a specific engine.
        
        Args:
            engine: Engine name (e.g., "openai", "ollama", "openrouter")
            
        Returns:
            Dict with engine configuration (api_key, model, temperature, max_tokens, etc.)
        """
        engine_configs = getattr(self.terminal, 'engine_models', {})
        api_keys = getattr(self.terminal, 'engine_api_keys', {})
        
        config = engine_configs.get(engine, {})
        config['api_key'] = api_keys.get(engine)
        
        return config

    def _call_single_engine(self, engine: str, system_prompt: str, user_prompt: str, 
                           max_tokens: Optional[int] = None, timeout: Optional[int] = None) -> Optional[str]:
        """
        Call a specific AI engine.
        
        Args:
            engine: Engine name to call
            system_prompt: System prompt content
            user_prompt: User prompt content
            max_tokens: Optional max tokens override
            timeout: Optional timeout override
            
        Returns:
            AI response or None on failure
        """
        # Get engine configuration
        config = self._get_engine_config(engine)
        
        # Use provided values or fall back to config
        call_max_tokens = max_tokens if max_tokens is not None else config.get('max_tokens')
        call_timeout = timeout if timeout is not None else self.ai_api_timeout
        
        # Temporarily swap terminal's api_key and model settings for this call
        original_api_key = getattr(self.terminal, 'api_key', None)
        original_model = None
        original_temperature = None
        
        # Save original values based on engine type
        if engine == "openai":
            original_model = self.terminal.default_model
            original_temperature = self.terminal.default_temperature
            self.terminal.api_key = config.get('api_key') or self.terminal.api_key
            self.terminal.default_model = config.get('model') or self.terminal.default_model
            self.terminal.default_temperature = config.get('temperature', self.terminal.default_temperature)
        elif engine == "ollama":
            original_model = self.terminal.ollama_model
            original_temperature = self.terminal.ollama_temperature
            self.terminal.ollama_model = config.get('model') or self.terminal.ollama_model
            self.terminal.ollama_temperature = config.get('temperature', self.terminal.ollama_temperature)
        elif engine == "ollama-cloud":
            original_model = self.terminal.ollama_cloud_model
            original_temperature = self.terminal.ollama_cloud_temperature
            self.terminal.api_key = config.get('api_key') or self.terminal.api_key
            self.terminal.ollama_cloud_model = config.get('model') or self.terminal.ollama_cloud_model
            self.terminal.ollama_cloud_temperature = config.get('temperature', self.terminal.ollama_cloud_temperature)
        elif engine == "google":
            original_model = self.terminal.gemini_model
            self.terminal.api_key = config.get('api_key') or self.terminal.api_key
            self.terminal.gemini_model = config.get('model') or self.terminal.gemini_model
        elif engine == "openrouter":
            original_model = self.terminal.openrouter_model
            original_temperature = self.terminal.openrouter_temperature
            self.terminal.api_key = config.get('api_key') or self.terminal.api_key
            self.terminal.openrouter_model = config.get('model') or self.terminal.openrouter_model
            self.terminal.openrouter_temperature = config.get('temperature', self.terminal.openrouter_temperature)
            self.terminal.openrouter_max_tokens = config.get('max_tokens', self.terminal.openrouter_max_tokens)
        elif engine == "groq":
            original_model = self.terminal.groq_model
            original_temperature = self.terminal.groq_temperature
            self.terminal.api_key = config.get('api_key') or self.terminal.api_key
            self.terminal.groq_model = config.get('model') or self.terminal.groq_model
            self.terminal.groq_temperature = config.get('temperature', self.terminal.groq_temperature)
            self.terminal.groq_max_tokens = config.get('max_tokens', self.terminal.groq_max_tokens)
        
        try:
            # Make the actual API call
            if engine == "ollama":
                return self.terminal.connect_to_ollama(system_prompt, user_prompt, max_tokens=call_max_tokens, timeout=call_timeout)
            elif engine == "ollama-cloud":
                return self.terminal.connect_to_ollama_cloud(system_prompt, user_prompt, max_tokens=call_max_tokens, timeout=call_timeout)
            elif engine == "google":
                return self.terminal.connect_to_gemini(f"{system_prompt}\n{user_prompt}", max_tokens=call_max_tokens, timeout=call_timeout)
            elif engine == "openai":
                return self.terminal.connect_to_chatgpt(system_prompt, user_prompt, max_tokens=call_max_tokens, timeout=call_timeout)
            elif engine == "openrouter":
                return self.terminal.connect_to_openrouter(system_prompt, user_prompt, max_tokens=call_max_tokens, timeout=call_timeout)
            elif engine == "groq":
                return self.terminal.connect_to_groq(system_prompt, user_prompt, max_tokens=call_max_tokens, timeout=call_timeout)
            else:
                raise ValueError(f"Unsupported AI engine: {engine}")
        finally:
            # Restore original values
            if original_api_key is not None:
                self.terminal.api_key = original_api_key
            if original_model is not None:
                if engine == "openai":
                    self.terminal.default_model = original_model
                    self.terminal.default_temperature = original_temperature
                elif engine == "ollama":
                    self.terminal.ollama_model = original_model
                    self.terminal.ollama_temperature = original_temperature
                elif engine == "ollama-cloud":
                    self.terminal.ollama_cloud_model = original_model
                    self.terminal.ollama_cloud_temperature = original_temperature
                elif engine == "google":
                    self.terminal.gemini_model = original_model
                elif engine == "openrouter":
                    self.terminal.openrouter_model = original_model
                    self.terminal.openrouter_temperature = original_temperature
                elif engine == "groq":
                    self.terminal.groq_model = original_model
                    self.terminal.groq_temperature = original_temperature

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
        # Use configured retry settings, but respect compact mode limits
        max_attempts = 1 if operation.startswith("compact_") else self.ai_api_max_retries
        if operation.startswith("analysis_data_tool") and max_attempts == 0:
            # Prevent effectively unbounded retries for analysis helper calls.
            max_attempts = 1
        if max_attempts == 0:
            max_attempts = float('inf')  # No retry limit
        
        # Calculate input tokens for tracking
        input_text = f"{system_prompt}\n{user_prompt}"
        input_tokens = self._estimate_tokens(input_text)
        
        # Convert max_attempts to int for range function, but keep infinity logic
        range_limit = 100 if max_attempts == float('inf') else int(max_attempts)
        
        for attempt in range(1, range_limit + 1):
            try:
                # Use the selected API method based on configuration
                if self.use_timeout_api:
                    self.logger.debug(f"Using timeout-enabled API call (attempt {attempt}/{max_attempts})")
                    response, used_engine = self._call_ai_api_with_timeout(system_prompt, user_prompt, max_tokens=max_tokens)
                else:
                    self.logger.debug(f"Using legacy API call without timeout (attempt {attempt}/{max_attempts})")
                    response, used_engine = self._call_ai_api(system_prompt, user_prompt, max_tokens=max_tokens)
                
                if not response:
                    raise ValueError("Empty response from AI")

                self.logger.debug(
                    "AI response stats: operation=%s attempt=%s len=%d format=%s",
                    operation,
                    attempt,
                    len(response),
                    request_format,
                )
                
                # Calculate output tokens
                output_tokens = self._estimate_tokens(response)
                
                # Track token usage with model information
                self._track_token_usage(
                    operation=operation,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    attempt=attempt,
                    model=used_engine
                )
                
                if request_format == "json":
                    return self._process_json_response(response)
                
                return response
            
            except Exception as e:
                self._handle_retry_error(attempt, max_attempts, e)
                
                # Check if we should retry
                should_retry = max_attempts == float('inf') or attempt < max_attempts
                
                if should_retry:
                    # Calculate delay with exponential backoff
                    delay = self.ai_api_retry_delay * (self.ai_api_retry_backoff ** (attempt - 1))
                    # Add jitter to prevent thundering herd
                    jitter = random.uniform(0, delay * 0.1)
                    delay_with_jitter = delay + jitter
                    
                    self.logger.debug(f"Retrying in {delay_with_jitter:.2f} seconds...")
                    time.sleep(delay_with_jitter)
                else:
                    break  # No more retries allowed
        
        return None

    def send_request_with_model(
        self,
        system_prompt: str,
        user_prompt: str,
        request_format: str = "json",
        operation: str = "ai_request",
        max_tokens: Optional[int] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Handles AI communication with retries and standardized error handling.
        Returns both the response and the model/engine used.
        
        Args:
            system_prompt: Base system instructions for the AI
            user_prompt: User-provided prompt content
            request_format: Expected response format ('json' or 'text')
            operation: Operation name for token accounting
            max_tokens: Optional max tokens for the model response
            
        Returns:
            Tuple of (AI response content or None, model/engine name or None)
        """
        # Use configured retry settings, but respect compact mode limits
        max_attempts = 1 if operation.startswith("compact_") else self.ai_api_max_retries
        if operation.startswith("analysis_data_tool") and max_attempts == 0:
            # Prevent effectively unbounded retries for analysis helper calls.
            max_attempts = 1
        if max_attempts == 0:
            max_attempts = float('inf')  # No retry limit
        
        # Calculate input tokens for tracking
        input_text = f"{system_prompt}\n{user_prompt}"
        input_tokens = self._estimate_tokens(input_text)
        
        # Convert max_attempts to int for range function, but keep infinity logic
        range_limit = 100 if max_attempts == float('inf') else int(max_attempts)
        
        for attempt in range(1, range_limit + 1):
            try:
                # Use the selected API method based on configuration
                if self.use_timeout_api:
                    self.logger.debug(f"Using timeout-enabled API call (attempt {attempt}/{max_attempts})")
                    response, used_engine = self._call_ai_api_with_timeout(system_prompt, user_prompt, max_tokens=max_tokens)
                else:
                    self.logger.debug(f"Using legacy API call without timeout (attempt {attempt}/{max_attempts})")
                    response, used_engine = self._call_ai_api(system_prompt, user_prompt, max_tokens=max_tokens)
                
                if not response:
                    raise ValueError("Empty response from AI")

                self.logger.debug(
                    "AI response stats: operation=%s attempt=%s len=%d format=%s",
                    operation,
                    attempt,
                    len(response),
                    request_format,
                )
                
                # Calculate output tokens
                output_tokens = self._estimate_tokens(response)
                
                # Track token usage with model information
                self._track_token_usage(
                    operation=operation,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    attempt=attempt,
                    model=used_engine
                )
                
                if request_format == "json":
                    processed_response = self._process_json_response(response)
                    return processed_response, used_engine
                
                return response, used_engine
            
            except Exception as e:
                self._handle_retry_error(attempt, max_attempts, e)
                
                # Check if we should retry
                should_retry = max_attempts == float('inf') or attempt < max_attempts
                
                if should_retry:
                    # Calculate delay with exponential backoff
                    delay = self.ai_api_retry_delay * (self.ai_api_retry_backoff ** (attempt - 1))
                    # Add jitter to prevent thundering herd
                    jitter = random.uniform(0, delay * 0.1)
                    delay_with_jitter = delay + jitter
                    
                    self.logger.debug(f"Retrying in {delay_with_jitter:.2f} seconds...")
                    time.sleep(delay_with_jitter)
                else:
                    break  # No more retries allowed
        
        return None, None

    def _call_ai_api_with_timeout(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Route request to appropriate AI engine with timeout using threading and signal-based fallback.
        Supports multi-engine routing (round-robin and fallback modes).
        
        Returns:
            Tuple of (response, engine_name) or (None, None) on failure
        """
        # Determine engines to try based on routing mode
        if len(self.ai_engines) == 1:
            engines_to_try = [self.ai_engines[0]]
        elif self.ai_engine_route == "round-robin":
            # Round-robin: try only the selected engine
            engines_to_try = [self._get_next_engine()]
        else:  # fallback mode
            # Fallback: try all engines in order
            engines_to_try = self.ai_engines.copy()
        
        last_exception = None
        
        for engine in engines_to_try:
            self.logger.debug(f"Attempting engine: {engine}")
            
            # Create a queue for thread-safe result passing
            result_queue = queue.Queue()
            exception_queue = queue.Queue()
            
            def target_function():
                """Target function to run in separate thread"""
                try:
                    result = self._call_single_engine(engine, system_prompt, user_prompt, max_tokens=max_tokens, timeout=self.ai_api_timeout)
                    result_queue.put(result)
                except Exception as e:
                    exception_queue.put(e)
            
            # Create and start the worker thread
            worker_thread = threading.Thread(target=target_function, daemon=True)
            worker_thread.start()
            
            # Set up signal-based timeout for Unix/Linux systems
            signal_handler_set = False
            old_alarm_handler = None
            old_alarm_time = 0
            
            if sys.platform != 'win32':  # Unix/Linux systems
                try:
                    def timeout_handler(signum, frame):
                        pass
                    
                    # Set up the alarm
                    old_alarm_handler = signal.signal(signal.SIGALRM, timeout_handler)
                    old_alarm_time = signal.alarm(self.ai_api_timeout)
                    signal_handler_set = True
                except (ValueError, OSError) as e:
                    self.logger.debug(f"Signal-based timeout not available: {e}")
            
            try:
                # Wait for result with timeout - main thread timeout should be longer than worker thread timeout
                # to account for thread coordination overhead and prevent race conditions
                main_thread_timeout = self.ai_api_timeout + self.ai_main_thread_timeout_buffer
                
                try:
                    result = result_queue.get(timeout=main_thread_timeout)
                    if result:
                        return result, engine
                    else:
                        self.logger.warning(f"Engine {engine} returned empty result, trying next engine")
                        last_exception = ValueError(f"Empty response from {engine}")
                        continue
                except queue.Empty:
                    self.logger.warning(f"Engine {engine} timed out after {main_thread_timeout}s (worker timeout: {self.ai_api_timeout}s), trying next engine")
                    last_exception = TimeoutError(f"Timeout from {engine}")
                    continue
            
            except TimeoutError:
                # Timeout handling
                if signal_handler_set:
                    signal.alarm(0)
                    if old_alarm_handler is not None:
                        signal.signal(signal.SIGALRM, old_alarm_handler)
                    if old_alarm_time > 0:
                        signal.alarm(old_alarm_time)
                
                worker_thread.join(timeout=1.0)
                
                self.logger.warning(f"AI API call timed out after {self.ai_api_timeout} seconds. "
                                  f"Engine: {engine}, Thread alive: {worker_thread.is_alive()}")
                last_exception = TimeoutError(f"Timeout from {engine}")
                continue
            
            except Exception as e:
                # Other exceptions
                if signal_handler_set:
                    signal.alarm(0)
                    if old_alarm_handler is not None:
                        signal.signal(signal.SIGALRM, old_alarm_handler)
                    if old_alarm_time > 0:
                        signal.alarm(old_alarm_time)
                
                self.logger.warning(f"Engine {engine} failed: {e}, trying next engine")
                last_exception = e
                continue
            
            finally:
                # Ensure thread cleanup
                if worker_thread.is_alive():
                    pass
        
        # All engines failed
        if last_exception:
            raise last_exception
        return None, None

    def _call_ai_api(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Route request to appropriate AI engine (legacy method without timeout).
        Supports multi-engine routing (round-robin and fallback modes).
        
        Returns:
            Tuple of (response, engine_name) or (None, None) on failure
        """
        # Determine engines to try based on routing mode
        if len(self.ai_engines) == 1:
            engines_to_try = [self.ai_engines[0]]
        elif self.ai_engine_route == "round-robin":
            # Round-robin: try only the selected engine
            engines_to_try = [self._get_next_engine()]
        else:  # fallback mode
            # Fallback: try all engines in order
            engines_to_try = self.ai_engines.copy()
        
        last_exception = None
        
        for engine in engines_to_try:
            self.logger.debug(f"Attempting engine: {engine}")
            try:
                result = self._call_single_engine(engine, system_prompt, user_prompt, max_tokens=max_tokens)
                if result:
                    return result, engine
                else:
                    self.logger.warning(f"Engine {engine} returned empty result, trying next engine")
                    last_exception = ValueError(f"Empty response from {engine}")
            except Exception as e:
                self.logger.warning(f"Engine {engine} failed: {e}, trying next engine")
                last_exception = e
                continue
        
        # All engines failed
        if last_exception:
            raise last_exception
        return None, None

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

    def _handle_retry_error(self, attempt: int, max_attempts: float, error: Exception):
        """Log and handle retry errors"""
        # Handle infinite retry case
        max_attempts_str = "∞" if max_attempts == float('inf') else str(int(max_attempts))
        error_msg = f"Attempt {attempt}/{max_attempts_str} failed: {str(error)}"
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

    def _track_token_usage(self, operation: str, input_tokens: int, output_tokens: int, attempt: int = 1, model: Optional[str] = None):
        """
        Track token usage for this AI communication.
        
        Args:
            operation: Type of operation (e.g., "ai_request", "plan_creation")
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated
            attempt: Retry attempt number
            model: Model/engine used for this operation (optional)
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
        
        # Add model information if provided
        if model:
            operation_record['model'] = model
        
        self.token_usage['operations'].append(operation_record)
        
        # Log token usage
        model_info = f", model={model}" if model else ""
        self.logger.debug(f"Token usage - {operation} (attempt {attempt}): "
                         f"input={input_tokens}, output={output_tokens}, total={total_tokens}{model_info}")
