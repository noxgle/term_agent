"""
Enhanced JSON Validator for Vault AI Agent Runner

This module provides more flexible and robust JSON validation that can handle
various AI response formats and recover from common parsing errors.

Enhanced with:
- Multiple parsing strategies for AI responses
- Auto-repair for common JSON issues
- Control character handling
- Multi-document JSON support
- Streaming JSON repair
"""

import json
import re
import json5
import yaml
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from enum import Enum


class ValidationMode(Enum):
    """Validation modes for different tolerance levels"""
    STRICT = "strict"        # Standard JSON only
    LENIENT = "lenient"      # JSON5 + basic error recovery
    FLEXIBLE = "flexible"    # JSON5 + YAML + advanced recovery


class JsonValidationError(Exception):
    """Custom exception for JSON validation errors"""
    pass


class JsonValidator:
    """Enhanced JSON validator with multiple parsing strategies"""
    
    def __init__(self, mode: ValidationMode = ValidationMode.FLEXIBLE):
        self.mode = mode
        self.validation_attempts = []
    
    def validate_response(self, ai_response: str) -> Tuple[bool, Any, str]:
        """
        Validate and parse AI response with multiple strategies
        
        Args:
            ai_response: Raw AI response string
            
        Returns:
            Tuple of (success, parsed_data, error_message)
        """
        if not ai_response or not isinstance(ai_response, str):
            return False, None, "Response must be a non-empty string"
        
        # Clean up the response
        cleaned_response = self._clean_response(ai_response)
        
        # Try different parsing strategies based on mode
        strategies = self._get_parsing_strategies()
        
        for strategy_name, strategy_func in strategies:
            try:
                result = strategy_func(cleaned_response)
                if result is not None:
                    return True, result, ""
            except Exception as e:
                error_msg = f"{strategy_name}: {str(e)}"
                self.validation_attempts.append(error_msg)
                continue
        
        # If all strategies failed, provide detailed error info
        error_details = self._format_error_details(ai_response)
        return False, None, error_details
    
    def _clean_response(self, response: str) -> str:
        """Clean and normalize AI response"""
        # Remove common markdown wrappers and whitespace
        cleaned = response.strip()
        
        # Remove common prefixes/suffixes that might interfere
        patterns_to_remove = [
            r'^```json\s*',
            r'^```\s*',
            r'```\s*$',
            r'^json\s*',
            r'^JSON\s*',
        ]
        
        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE | re.DOTALL)
        
        return cleaned.strip()
    
    def _get_parsing_strategies(self):
        """Get list of parsing strategies based on validation mode"""
        strategies = []
        
        if self.mode == ValidationMode.STRICT:
            strategies.extend([
                ("Direct JSON", self._parse_direct_json),
                ("JSON with regex extraction", self._parse_json_with_regex),
            ])
        elif self.mode == ValidationMode.LENIENT:
            strategies.extend([
                ("Direct JSON", self._parse_direct_json),
                ("JSON5 parsing", self._parse_json5),
                ("JSON with regex extraction", self._parse_json_with_regex),
                ("JSON with error recovery", self._parse_json_with_recovery),
                ("AI response cleaning", self._parse_ai_response_cleaning),
            ])
        else:  # FLEXIBLE mode
            strategies.extend([
                ("Direct JSON", self._parse_direct_json),
                ("JSON5 parsing", self._parse_json5),
                ("YAML parsing", self._parse_yaml),
                ("JSON with regex extraction", self._parse_json_with_regex),
                ("JSON with error recovery", self._parse_json_with_recovery),
                ("AI response cleaning", self._parse_ai_response_cleaning),
                ("Partial JSON extraction", self._parse_partial_json),
                ("Control chars removal", self._parse_with_control_chars_removal),
                ("Multi-document JSON", self._parse_multi_document_json),
                ("Streaming JSON repair", self._parse_streaming_json_repair),
                ("Aggressive JSON extraction", self._parse_aggressive_extraction),
            ])
        
        return strategies
    
    def _parse_direct_json(self, response: str) -> Optional[Any]:
        """Try to parse response directly as JSON"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return None
    
    def _parse_json5(self, response: str) -> Optional[Any]:
        """Parse response using JSON5 (more lenient than standard JSON)"""
        try:
            return json5.loads(response)
        except Exception:
            return None
    
    def _parse_yaml(self, response: str) -> Optional[Any]:
        """Parse response as YAML (often more forgiving than JSON)"""
        try:
            result = yaml.safe_load(response)
            # Only return if it's a dict or list (not scalar values)
            if isinstance(result, (dict, list)):
                return result
            return None
        except Exception:
            return None
    
    def _parse_json_with_regex(self, response: str) -> Optional[Any]:
        """Extract and parse JSON using regex patterns"""
        # Try various JSON block patterns
        patterns = [
            r'```json\s*(\{.*\}|\[.*\])\s*```',  # Markdown JSON blocks
            r'```\s*(\{.*\}|\[.*\])\s*```',      # Generic markdown blocks
            r'(\{.*\}|\[.*\])',                  # Raw JSON objects/arrays
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
            for match in matches:
                try:
                    # Try to parse the extracted JSON
                    result = json5.loads(match)  # Use JSON5 for better error recovery
                    if isinstance(result, (dict, list)):
                        return result
                except Exception:
                    continue
        
        return None
    
    def _parse_json_with_recovery(self, response: str) -> Optional[Any]:
        """Attempt to recover from common JSON errors"""
        try:
            # Try JSON5 first (handles more cases)
            return json5.loads(response)
        except Exception:
            # Try to fix common issues
            fixed = self._fix_common_json_issues(response)
            try:
                return json5.loads(fixed)
            except Exception:
                return None
    
    def _parse_partial_json(self, response: str) -> Optional[Any]:
        """Extract partial JSON from incomplete responses"""
        # Look for the start of a JSON object or array
        json_start_patterns = [
            r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',  # Nested objects
            r'\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]',  # Nested arrays
        ]
        
        for pattern in json_start_patterns:
            matches = re.findall(pattern, response, re.DOTALL)
            for match in matches:
                try:
                    result = json5.loads(match)
                    if isinstance(result, (dict, list)):
                        return result
                except Exception:
                    continue
        
        return None
    
    def _fix_common_json_issues(self, json_str: str) -> str:
        """Fix common JSON formatting issues"""
        fixed = json_str
        
        # Fix trailing commas
        fixed = re.sub(r',(\s*[}\]])', r'\1', fixed)
        
        # Fix single quotes to double quotes (basic cases)
        # This is a simplified approach - more complex cases might need better handling
        if "'" in fixed and '"' not in fixed:
            # Only convert if there are no double quotes already
            fixed = re.sub(r"'([^']*)':", r'"\1":', fixed)
            fixed = re.sub(r"'([^']*)'", r'"\1"', fixed)
        
        # Fix unquoted keys (basic cases)
        fixed = re.sub(r'(\w+):', r'"\1":', fixed)
        
        # Remove comments (/* */ and // style)
        fixed = re.sub(r'/\*.*?\*/', '', fixed, flags=re.DOTALL)
        fixed = re.sub(r'//.*$', '', fixed, flags=re.MULTILINE)
        
        return fixed.strip()
    
    def _parse_ai_response_cleaning(self, response: str) -> Optional[Any]:
        """
        Extract JSON by removing all text before first { or [ and after last } or ].
        Handles AI responses that include explanatory text around JSON.
        """
        # Find first JSON start character
        first_obj = response.find('{')
        first_arr = response.find('[')
        
        if first_obj == -1 and first_arr == -1:
            return None
        
        # Determine which comes first
        if first_obj == -1:
            start = first_arr
        elif first_arr == -1:
            start = first_obj
        else:
            start = min(first_obj, first_arr)
        
        if start == -1:
            return None
        
        # Determine the opening and closing characters
        open_char = response[start]
        close_char = '}' if open_char == '{' else ']'
        
        # Find matching closing bracket using bracket counting
        depth = 0
        in_string = False
        escape_next = False
        
        for i in range(start, len(response)):
            char = response[i]
            
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
                    # Found the matching closing bracket
                    json_str = response[start:i + 1]
                    try:
                        return json5.loads(json_str)
                    except Exception:
                        # Try with additional fixes
                        fixed = self._fix_common_json_issues(json_str)
                        try:
                            return json5.loads(fixed)
                        except Exception:
                            pass
                    break
        
        return None
    
    def _parse_with_control_chars_removal(self, response: str) -> Optional[Any]:
        """
        Remove control characters and try to parse JSON.
        Handles responses with embedded control characters that break parsing.
        """
        # Remove control characters except newline, tab, and carriage return
        # which are valid in JSON strings when properly escaped
        cleaned = ''.join(char for char in response if ord(char) >= 32 or char in '\n\r\t')
        
        # Also try removing all control characters
        fully_cleaned = ''.join(char for char in response if ord(char) >= 32)
        
        for candidate in [cleaned, fully_cleaned]:
            if not candidate:
                continue
            
            # Try direct parsing
            try:
                return json5.loads(candidate)
            except Exception:
                pass
            
            # Try extracting JSON from cleaned response
            result = self._parse_ai_response_cleaning(candidate)
            if result is not None:
                return result
        
        return None
    
    def _parse_multi_document_json(self, response: str) -> Optional[Any]:
        """
        Handle multiple JSON documents in a single response.
        Returns the first valid JSON object or an array of all valid objects.
        """
        # Split by common delimiters
        delimiters = ['\n\n', '\n---\n', '\n```', '```']
        
        for delimiter in delimiters:
            if delimiter in response:
                parts = response.split(delimiter)
                valid_objects = []
                
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    
                    # Try to parse each part
                    try:
                        obj = json5.loads(part)
                        if isinstance(obj, (dict, list)):
                            valid_objects.append(obj)
                    except Exception:
                        # Try extracting JSON from the part
                        result = self._parse_ai_response_cleaning(part)
                        if result is not None:
                            valid_objects.append(result)
                
                if len(valid_objects) == 1:
                    return valid_objects[0]
                elif len(valid_objects) > 1:
                    return valid_objects
        
        # Try line-by-line NDJSON parsing
        valid_objects = []
        for line in response.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            try:
                obj = json5.loads(line)
                if isinstance(obj, (dict, list)):
                    valid_objects.append(obj)
            except Exception:
                # Try fixing the line
                fixed = self._fix_common_json_issues(line)
                try:
                    obj = json5.loads(fixed)
                    if isinstance(obj, (dict, list)):
                        valid_objects.append(obj)
                except Exception:
                    continue
        
        if len(valid_objects) == 1:
            return valid_objects[0]
        elif len(valid_objects) > 1:
            return valid_objects
        
        return None
    
    def _parse_streaming_json_repair(self, response: str) -> Optional[Any]:
        """
        Attempt to repair incomplete/streaming JSON responses.
        Useful when AI response was cut off mid-generation.
        """
        # Check if response looks incomplete
        open_braces = response.count('{')
        close_braces = response.count('}')
        open_brackets = response.count('[')
        close_brackets = response.count(']')
        
        # If braces/brackets are balanced, this strategy won't help
        if open_braces == close_braces and open_brackets == close_brackets:
            return None
        
        # Try to complete the JSON by adding missing closing characters
        missing_braces = open_braces - close_braces
        missing_brackets = open_brackets - close_brackets
        
        # Try adding missing closing characters at the end
        repaired = response.rstrip()
        
        # Remove trailing incomplete content (partial strings, etc.)
        # Find the last complete value
        patterns_to_trim = [
            r',\s*"[^"]*$',          # Trailing incomplete key
            r',\s*$',                 # Trailing comma
            r':\s*"[^"]*$',          # Incomplete string value
            r':\s*$',                 # Trailing colon
            r'"[^"]*$',              # Incomplete string
        ]
        
        for pattern in patterns_to_trim:
            repaired = re.sub(pattern, '', repaired)
        
        # Add missing closing characters
        # We need to determine the order based on what's open
        # Simple approach: add them in reverse order of opening
        closing_sequence = ''
        
        # Analyze the structure to determine closing order
        depth_obj = 0
        depth_arr = 0
        in_string = False
        escape = False
        expected_closing = []
        
        for char in response:
            if escape:
                escape = False
                continue
            if char == '\\' and in_string:
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            
            if char == '{':
                expected_closing.append('}')
            elif char == '[':
                expected_closing.append(']')
            elif char == '}':
                if expected_closing and expected_closing[-1] == '}':
                    expected_closing.pop()
            elif char == ']':
                if expected_closing and expected_closing[-1] == ']':
                    expected_closing.pop()
        
        # Add the missing closing characters in reverse order
        closing_sequence = ''.join(reversed(expected_closing))
        
        repaired += closing_sequence
        
        # Try to parse the repaired JSON
        try:
            return json5.loads(repaired)
        except Exception:
            # Try with fixes
            fixed = self._fix_common_json_issues(repaired)
            try:
                return json5.loads(fixed)
            except Exception:
                pass
        
        return None
    
    def _parse_aggressive_extraction(self, response: str) -> Optional[Any]:
        """
        Most aggressive JSON extraction strategy.
        Uses all available methods to extract any valid JSON.
        """
        # Strategy 1: Find any JSON-like structure with balanced brackets
        result = self._extract_balanced_json(response)
        if result is not None:
            return result
        
        # Strategy 2: Remove all non-JSON characters and try
        json_chars_only = re.sub(r'[^\{\}\[\]\"\'\:\,\-\d\.\w\s]', '', response)
        try:
            return json5.loads(json_chars_only)
        except Exception:
            pass
        
        # Strategy 3: Find JSON key-value patterns and construct object
        kv_pattern = r'"([^"]+)"\s*:\s*("([^"]*)"|(\d+\.?\d*)|(true|false|null)|(\{[^}]*\})|(\[[^\]]*\]))'
        matches = re.findall(kv_pattern, response, re.DOTALL)
        
        if matches:
            constructed = {}
            for match in matches:
                key = match[0]
                # Determine value type and extract
                if match[2]:  # String value
                    constructed[key] = match[2]
                elif match[3]:  # Number
                    constructed[key] = float(match[3]) if '.' in match[3] else int(match[3])
                elif match[4]:  # Boolean or null
                    if match[4] == 'true':
                        constructed[key] = True
                    elif match[4] == 'false':
                        constructed[key] = False
                    else:
                        constructed[key] = None
                elif match[5]:  # Nested object
                    try:
                        constructed[key] = json5.loads(match[5])
                    except Exception:
                        pass
                elif match[6]:  # Nested array
                    try:
                        constructed[key] = json5.loads(match[6])
                    except Exception:
                        pass
            
            if constructed:
                return constructed
        
        # Strategy 4: Last resort - try to find any valid JSON substring
        # Use a more permissive regex that can match incomplete structures
        for i in range(len(response)):
            for j in range(len(response), i, -1):
                substr = response[i:j]
                try:
                    result = json5.loads(substr)
                    if isinstance(result, (dict, list)):
                        return result
                except Exception:
                    continue
        
        return None
    
    def _extract_balanced_json(self, text: str) -> Optional[Any]:
        """Extract the first complete, balanced JSON object or array."""
        # Find all potential JSON start positions
        for i, char in enumerate(text):
            if char in '{[':
                # Try to extract from this position
                open_char = char
                close_char = '}' if char == '{' else ']'
                
                depth = 0
                in_string = False
                escape = False
                
                for j in range(i, len(text)):
                    c = text[j]
                    
                    if escape:
                        escape = False
                        continue
                    
                    if c == '\\' and in_string:
                        escape = True
                        continue
                    
                    if c == '"':
                        in_string = not in_string
                        continue
                    
                    if in_string:
                        continue
                    
                    if c == open_char:
                        depth += 1
                    elif c == close_char:
                        depth -= 1
                        if depth == 0:
                            # Found a complete structure
                            json_str = text[i:j + 1]
                            try:
                                return json5.loads(json_str)
                            except Exception:
                                # Try fixing and parsing
                                fixed = self._fix_common_json_issues(json_str)
                                try:
                                    return json5.loads(fixed)
                                except Exception:
                                    break  # This start position didn't work
                        elif depth < 0:
                            # Unbalanced, break
                            break
        
        return None
    
    def _format_error_details(self, original_response: str) -> str:
        """Format detailed error information"""
        error_msg = "JSON validation failed with the following errors:\n"
        
        # Add all validation attempt errors
        for i, attempt_error in enumerate(self.validation_attempts, 1):
            error_msg += f"  {i}. {attempt_error}\n"
        
        # Add sample of the original response
        sample_length = min(200, len(original_response))
        sample = original_response[:sample_length]
        if len(original_response) > sample_length:
            sample += "..."
        
        error_msg += f"\nOriginal response sample:\n{sample}\n"
        
        # Add suggestions based on common issues
        error_msg += "\nCommon fixes:\n"
        error_msg += "  - Ensure proper JSON formatting (quoted keys, no trailing commas)\n"
        error_msg += "  - Remove markdown formatting if present\n"
        error_msg += "  - Check for balanced braces and brackets\n"
        error_msg += "  - Use JSON5-compatible syntax for more flexibility\n"
        
        return error_msg
    
    def set_mode(self, mode: ValidationMode):
        """Change validation mode"""
        self.mode = mode
        self.validation_attempts = []


def create_validator(mode: str = "flexible") -> JsonValidator:
    """Factory function to create validator with specified mode"""
    mode_map = {
        "strict": ValidationMode.STRICT,
        "lenient": ValidationMode.LENIENT,
        "flexible": ValidationMode.FLEXIBLE,
    }
    
    validation_mode = mode_map.get(mode.lower(), ValidationMode.FLEXIBLE)
    return JsonValidator(validation_mode)