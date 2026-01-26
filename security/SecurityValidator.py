import re
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
        # Default dangerous commands that should be blocked
        self.dangerous_commands = dangerous_commands or {
            'rm -rf /', 'rm -rf /*', 'rm -rf /home', 'rm -rf /etc', 'rm -rf /var',
            'dd if=', 'mkfs', 'fdisk', 'format', 'wipefs', 'shred',
            'passwd root', 'usermod -p', 'chpasswd',
            'sudo su', 'su root', 'sudo -i', 'sudo -s',
            'crontab -r', 'history -c', 'unset HISTFILE',
            '> /dev/null', '>/dev/null', '2>/dev/null', '&>/dev/null',
            'curl -s', 'wget -q', 'curl -O', 'wget -O',
            'chmod 777', 'chmod +x', 'chmod u+s', 'chmod g+s',
            'chown root', 'chown 0', 'chgrp root', 'chgrp 0',
            'iptables -F', 'iptables -X', 'ufw --force disable',
            'systemctl stop', 'systemctl disable', 'service stop',
            'pkill -9', 'killall -9', 'kill -9',
            'reboot', 'shutdown', 'halt', 'poweroff',
            'mount /dev', 'umount /', 'mount -t nfs',
            'ssh-keygen', 'ssh-copy-id', 'scp',
            'mysql -e', 'psql -c', 'sqlite3',
            'python -c', 'python3 -c', 'perl -e', 'ruby -e',
            'eval', 'exec', 'source', 'bash -c', 'sh -c',
            'nohup', 'screen', 'tmux', 'at', 'batch', 'cron',
            'find / -exec', 'find / -delete', 'find / -print0 | xargs',
            'tar -xzf /dev/null', 'gzip -dc /dev/null',
            'base64 -d', 'openssl enc', 'gpg --decrypt'
        }

        # Allowed paths for file operations
        self.allowed_paths = allowed_paths or ['/tmp', '/var/tmp', '/home', '/usr/local', '/opt']

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

        # Check for dangerous command patterns
        cmd_lower = command.lower().strip()
        for dangerous in self.dangerous_commands:
            if dangerous in cmd_lower:
                return False, f"Command contains dangerous pattern: '{dangerous}'"

        # Check for shell injection attempts
        # Allow legitimate command chaining with &&, || when properly separated
        dangerous_patterns = [';', '`', '$(', '${', '>', '<', '2>', '&>', '&>>']
        for pattern in dangerous_patterns:
            if pattern in command and not (pattern in ['>', '2>'] and ' ' in command.split(pattern)[0]):  # Allow redirection after commands
                return False, f"Command contains potential shell injection: '{pattern}'"

        # Special handling for && and || - allow when used for legitimate command chaining
        # Check if && appears to be used for command injection vs legitimate chaining
        if '&&' in command:
            # Split by && and check if each part looks like a separate command
            parts = command.split('&&')
            for part in parts:
                part = part.strip()
                if not part:  # Empty part suggests malformed command
                    return False, "Command contains malformed '&&' usage"
                # If any part contains suspicious patterns, block it
                if any(suspicious in part for suspicious in ['$(', '${', '`', ';']):
                    return False, f"Command contains suspicious pattern near '&&': '{part}'"

        if '||' in command:
            # Similar logic for ||
            parts = command.split('||')
            for part in parts:
                part = part.strip()
                if not part:
                    return False, "Command contains malformed '||' usage"
                if any(suspicious in part for suspicious in ['$(', '${', '`', ';']):
                    return False, f"Command contains suspicious pattern near '||': '{part}'"

        # Check for interactive commands
        interactive_cmds = ['vi', 'vim', 'nano', 'emacs', 'less', 'more', 'top', 'htop', 'mc', 'passwd', 'su', 'sudo -i', 'sudo -s']
        cmd_parts = command.split()
        if cmd_parts and any(cmd_parts[0].endswith(interactive) for interactive in interactive_cmds):
            return False, f"Interactive command not allowed: '{cmd_parts[0]}'"

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

        # Check if path starts with any allowed path
        for allowed_path in self.allowed_paths:
            if file_path.startswith(allowed_path):
                return True, ""

        return False, f"File path '{file_path}' is not in allowed paths: {self.allowed_paths}"

    def add_dangerous_command(self, command_pattern: str):
        """
        Add a new dangerous command pattern to the block list.

        Args:
            command_pattern: The command pattern to add
        """
        if command_pattern and isinstance(command_pattern, str):
            self.dangerous_commands.add(command_pattern)

    def remove_dangerous_command(self, command_pattern: str):
        """
        Remove a dangerous command pattern from the block list.

        Args:
            command_pattern: The command pattern to remove
        """
        if command_pattern in self.dangerous_commands:
            self.dangerous_commands.remove(command_pattern)

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