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
        # Default dangerous commands that should be blocked.
        # Only truly destructive operations are listed - common admin tools
        # like curl, wget, systemctl, chmod +x, etc. are intentionally NOT blocked
        # because they are required for normal Linux administration tasks.
        self.dangerous_commands = dangerous_commands or {
            # Recursive filesystem destruction
            'rm -rf /', 'rm -rf /*', 'rm -rf /home', 'rm -rf /etc', 'rm -rf /var',
            'rm -rf /usr', 'rm -rf /boot', 'rm -rf /root',
            # Disk/partition operations
            'dd if=/dev/', 'mkfs.', 'fdisk /dev/', 'wipefs', 'shred /dev/',
            # Direct credential modification
            'passwd root', 'usermod -p ', 'chpasswd',
            # Privilege escalation
            'sudo su', 'su root', 'sudo -i', 'sudo -s',
            # Audit trail destruction
            'crontab -r', 'history -c', 'unset HISTFILE',
            # Setuid/setgid (privilege escalation via file permissions)
            'chmod u+s', 'chmod g+s', 'chmod 4', 'chmod 2',
            # Firewall destruction
            'iptables -F', 'iptables -X', 'ufw --force disable',
            # System halt/reboot (destructive in automated context)
            'reboot', 'shutdown', 'halt', 'poweroff',
            # Root filesystem unmount
            'umount /', 'umount -a',
            # Find with mass delete/exec on root
            'find / -delete', 'find / -exec rm',
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

        # Check for shell injection patterns.
        # NOTE: Shell redirections (>, <, 2>, &>, |) are intentionally NOT blocked here
        # because they are standard and necessary for Linux administration.
        # Only true injection metacharacters are checked.
        injection_patterns = [';', '`', '$(', '${']
        for pattern in injection_patterns:
            if pattern in command:
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