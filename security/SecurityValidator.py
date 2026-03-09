import os
import re
import shlex
import unicodedata
from urllib.parse import unquote
from typing import Set, List, Tuple

class SecurityValidator:
    """
    SecurityValidator handles command validation and security checks for the Vault AI Agent.

    This class is responsible for:
    - Validating commands for security before execution
    - Detecting dangerous command patterns
    - Preventing shell injection attempts
    - Blocking interactive commands
    - Managing allowed paths for file operations
    """

    def __init__(self, dangerous_commands: Set[str] = None, allowed_paths: List[str] = None):
        """
        Initialize the SecurityValidator with optional custom dangerous commands and allowed paths.

        Args:
            dangerous_commands: Set of dangerous command patterns to block
            allowed_paths: List of allowed paths for file operations
        """
        # String patterns retained for compatibility with add/remove APIs.
        self.dangerous_commands = dangerous_commands or {
            'rm -rf /', 'rm -rf /*', 'rm -rf /home', 'rm -rf /etc', 'rm -rf /var',
            'rm -rf /usr', 'rm -rf /boot', 'rm -rf /root',
            'dd if=/dev/', 'mkfs.', 'fdisk /dev/', 'wipefs', 'shred /dev/',
            'passwd root', 'usermod -p ', 'chpasswd',
            'sudo su', 'su root', 'sudo -i', 'sudo -s',
            'crontab -r', 'history -c', 'unset HISTFILE',
            'chmod u+s', 'chmod g+s', 'chmod 4', 'chmod 2',
            'iptables -F', 'iptables -X', 'ufw --force disable',
            'reboot', 'shutdown', 'halt', 'poweroff',
            'umount /', 'umount -a',
            'find / -delete', 'find / -exec rm',
        }

        # Allowed paths for file operations
        self.allowed_paths = allowed_paths or ['/tmp', '/var/tmp', '/home', '/usr/local', '/opt']
        self._dangerous_regexes = self._build_dangerous_regexes(self.dangerous_commands)
        self._chain_split_re = re.compile(r'\s*(?:&&|\|\||;|\n)\s*')
        self._blocked_paths = (
            "/proc",
            "/sys",
            "/dev",
            "/etc/shadow",
            "/root/.ssh",
        )

    def validate_command(self, command: str) -> Tuple[bool, str]:
        """
        Validate a command for security before execution.

        Args:
            command: The command string to validate

        Returns:
            tuple: (is_valid, reason_if_invalid)
        """
        if not command or not isinstance(command, str):
            return False, "Command must be a non-empty string"

        normalized = self._normalize_command(command)
        if not normalized:
            return False, "Command must be a non-empty string"

        # Block command substitution and indirect expansions commonly used to bypass checks.
        for token in ('`', '$(', '${'):
            if token in normalized:
                return False, f"Command contains potential shell injection: '{token}'"

        segments = [seg.strip() for seg in self._chain_split_re.split(normalized) if seg.strip()]
        if not segments:
            return False, "Command is empty after normalization"

        for segment in segments:
            is_safe, reason = self._validate_segment(segment)
            if not is_safe:
                return False, reason

        return True, ""

    def validate_file_path(self, file_path: str) -> Tuple[bool, str]:
        """
        Validate a file path against allowed paths.

        Args:
            file_path: The file path to validate

        Returns:
            tuple: (is_valid, reason_if_invalid)
        """
        if not file_path or not isinstance(file_path, str):
            return False, "File path must be a non-empty string"

        normalized_input = unicodedata.normalize("NFKC", file_path).strip()
        decoded_input = unquote(normalized_input)
        if "\x00" in decoded_input:
            return False, "File path contains null bytes"

        abs_path = os.path.abspath(decoded_input)
        real_path = os.path.realpath(abs_path)
        real_path_norm = os.path.normpath(real_path)

        for blocked in self._blocked_paths:
            if real_path_norm == blocked or real_path_norm.startswith(blocked + os.sep):
                return False, f"File path '{file_path}' points to blocked location '{blocked}'"

        allowed_real_paths = [os.path.realpath(p) for p in self.allowed_paths]
        for allowed_real in allowed_real_paths:
            try:
                if os.path.commonpath([real_path_norm, allowed_real]) == allowed_real:
                    return True, ""
            except ValueError:
                continue

        return False, f"File path '{file_path}' is not in allowed paths: {self.allowed_paths}"

    def add_dangerous_command(self, command_pattern: str):
        """
        Add a new dangerous command pattern to the block list.

        Args:
            command_pattern: The command pattern to add
        """
        if command_pattern and isinstance(command_pattern, str):
            self.dangerous_commands.add(command_pattern)
            self._dangerous_regexes = self._build_dangerous_regexes(self.dangerous_commands)

    def remove_dangerous_command(self, command_pattern: str):
        """
        Remove a dangerous command pattern from the block list.

        Args:
            command_pattern: The command pattern to remove
        """
        if command_pattern in self.dangerous_commands:
            self.dangerous_commands.remove(command_pattern)
            self._dangerous_regexes = self._build_dangerous_regexes(self.dangerous_commands)

    def add_allowed_path(self, path: str):
        """
        Add a new allowed path for file operations.

        Args:
            path: The path to add
        """
        if path and isinstance(path, str) and path not in self.allowed_paths:
            self.allowed_paths.append(path)

    def remove_allowed_path(self, path: str):
        """
        Remove an allowed path for file operations.

        Args:
            path: The path to remove
        """
        if path in self.allowed_paths:
            self.allowed_paths.remove(path)

    def _normalize_command(self, command: str) -> str:
        return unicodedata.normalize("NFKC", command).strip().lower()

    def _build_dangerous_regexes(self, patterns: Set[str]) -> List[re.Pattern]:
        regexes = [
            re.compile(r'\brm\s+-[^\n]*\brf\b'),
            re.compile(r'\bdd\b[^\n]*(if|of)\s*=\s*/dev/'),
            re.compile(r'\b(?:mkfs|wipefs|fdisk|parted|sfdisk|shred)\b'),
            re.compile(r'\b(?:reboot|shutdown|halt|poweroff)\b'),
            re.compile(r'\b(?:iptables\s+-f|iptables\s+-x|ufw\s+--force\s+disable)\b'),
            re.compile(r'\bcurl\b[^\n|>]*\|\s*(?:bash|sh)\b'),
            re.compile(r'\bwget\b[^\n|>]*\|\s*(?:bash|sh)\b'),
            re.compile(r'>\s*/dev/(?:sd[a-z]\d*|nvme\d+n\d+(?:p\d+)?|vd[a-z]\d*|xvd[a-z]\d*)'),
            re.compile(r':\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:'),
        ]

        for pattern in patterns:
            escaped = re.escape(pattern.lower().strip())
            if escaped:
                regexes.append(re.compile(escaped))
        return regexes

    def _validate_segment(self, segment: str) -> Tuple[bool, str]:
        for regex in self._dangerous_regexes:
            if regex.search(segment):
                return False, f"Command contains dangerous pattern: '{regex.pattern}'"

        try:
            tokens = shlex.split(segment)
        except ValueError:
            return False, "Command parsing failed (possibly malformed quoting)"

        if not tokens:
            return False, "Empty command segment detected"

        interactive_cmds = {'vi', 'vim', 'nano', 'emacs', 'less', 'more', 'top', 'htop', 'mc', 'passwd'}
        cmd = os.path.basename(tokens[0])
        if cmd in interactive_cmds:
            return False, f"Interactive command not allowed: '{cmd}'"

        if cmd == "sudo" and len(tokens) > 1:
            sudo_target = os.path.basename(tokens[1])
            if sudo_target in interactive_cmds or sudo_target in {"-i", "-s", "su"}:
                return False, f"Interactive/shell escalation command not allowed: 'sudo {tokens[1]}'"

        if cmd == "su":
            return False, "Command 'su' is not allowed in automated mode"

        return True, ""
