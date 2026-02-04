"""
Enhanced JSON Validator for Vault AI Agent Runner

This module provides more flexible and robust JSON validation that can handle
various AI response formats and recover from common parsing errors.
"""

import json
import re
import json5
import yaml
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
            ])
        else:  # FLEXIBLE mode
            strategies.extend([
                ("Direct JSON", self._parse_direct_json),
                ("JSON5 parsing", self._parse_json5),
                ("YAML parsing", self._parse_yaml),
                ("JSON with regex extraction", self._parse_json_with_regex),
                ("JSON with error recovery", self._parse_json_with_recovery),
                ("Partial JSON extraction", self._parse_partial_json),
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