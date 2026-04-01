import os
import re
import shutil
import fnmatch
import shlex
import tempfile
import subprocess
import logging
import time
import unicodedata
from urllib.parse import unquote
from typing import Dict, Any, Optional, Tuple, List

class FileOperator:
    def __init__(self, terminal, logger=None):
        self.terminal = terminal
        self.logger = logger or logging.getLogger(__name__)
        self._blocked_local_paths = (
            "/proc",
            "/sys",
            "/dev",
            "/etc/shadow",
            "/root/.ssh",
        )

    def _normalize_input_path(self, file_path: str) -> str:
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError("Path must be a non-empty string")
        normalized = unicodedata.normalize("NFKC", file_path).strip()
        decoded = unquote(normalized)
        if "\x00" in decoded or "\n" in decoded or "\r" in decoded:
            raise ValueError("Path contains forbidden control characters")
        return decoded

    def _resolve_local_path(self, file_path: str) -> str:
        decoded = self._normalize_input_path(file_path)
        abs_path = decoded if os.path.isabs(decoded) else os.path.join(os.getcwd(), decoded)
        real_path = os.path.realpath(os.path.abspath(abs_path))
        real_path = os.path.normpath(real_path)

        workspace_base = os.path.realpath(getattr(self.terminal, "workspace", os.getcwd()) or os.getcwd())
        workspace_base = os.path.normpath(workspace_base)
        if not os.path.isabs(decoded):
            if os.path.commonpath([real_path, workspace_base]) != workspace_base:
                raise ValueError(f"Relative path escapes workspace: '{file_path}'")

        for blocked in self._blocked_local_paths:
            if real_path == blocked or real_path.startswith(blocked + os.sep):
                raise ValueError(f"Access to blocked path is not allowed: '{file_path}'")

        return real_path

    def _sanitize_remote_path(self, file_path: str) -> str:
        decoded = self._normalize_input_path(file_path)
        normalized = os.path.normpath(decoded)
        if ".." in normalized.split("/"):
            raise ValueError(f"Path traversal detected in remote path: '{file_path}'")
        return normalized

    def _prepare_path(self, file_path: str) -> str:
        if self.terminal.ssh_connection:
            return self._sanitize_remote_path(file_path)
        return self._resolve_local_path(file_path)

    def _q(self, value: str) -> str:
        return shlex.quote(value)

    def _scp_target(self, remote: str, path: str) -> str:
        return f"{remote}:{self._q(path)}"

    def write_file(self, file_path, content, explain=""):
        """
        Write file content to the specified path, handling both local and remote operations.

        Args:
            file_path (str): Path to the file to write
            content (str): Content to write to the file
            explain (str): Explanation of what this operation does

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            file_path = self._prepare_path(file_path)
        except ValueError as e:
            self.logger.error("Path validation failed for write_file '%s': %s", file_path, e)
            return False

        preview = content[:100] + ("..." if len(content) > 100 else "")

        if self.terminal.ssh_connection:
            return self._write_file_remote(file_path, content, explain, preview)
        else:
            return self._write_file_local(file_path, content, explain, preview)

    def _write_file_local(self, file_path, content, explain, preview):
        try:
            self._create_directories(file_path)
            # Remove existing file if it exists
            if os.path.exists(file_path):
                os.remove(file_path)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            self.logger.info(f"File '{file_path}' written successfully. Preview: {preview}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to write file '{file_path}': {e}")
            return False

    def _write_file_remote(self, file_path, content, explain, preview):
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmpf:
                tmpf.write(content)
                tmpf_path = tmpf.name

            remote = f"{self.terminal.user}@{self.terminal.host}" if self.terminal.user and self.terminal.host else self.terminal.host
            password = getattr(self.terminal, "ssh_password", None)

            remote_tmp_path = f"/tmp/{os.path.basename(file_path)}"
            q_file_path = self._q(file_path)
            q_remote_tmp_path = self._q(remote_tmp_path)

            # Remove existing file on remote host if exists
            rm_cmd = f"rm -f {q_file_path}"
            self.terminal.execute_remote_pexpect(rm_cmd, remote, password=password)
            # Remove existing temp file on remote host if exists
            rm_tmp_cmd = f"rm -f {q_remote_tmp_path}"
            self.terminal.execute_remote_pexpect(rm_tmp_cmd, remote, password=password)

            scp_cmd = (
                ["scp"]
                + (["-P", str(self.terminal.port)] if self.terminal.port else [])
                + [tmpf_path, self._scp_target(remote, remote_tmp_path)]
            )
            try:
                result = subprocess.run(scp_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    needs_sudo = not (self.terminal.user == "root" or file_path.startswith(f"/home/{self.terminal.user}") or file_path.startswith("/tmp"))
                    if remote_tmp_path == file_path:
                        code = 0
                        out = ""
                    else:
                        if needs_sudo:
                            cp_cmd = (
                                f"sudo cp {q_remote_tmp_path} {q_file_path} "
                                f"&& sudo rm {q_remote_tmp_path}"
                            )
                        else:
                            cp_cmd = f"mv {q_remote_tmp_path} {q_file_path}"
                        out, code = self.terminal.execute_remote_pexpect(cp_cmd, remote, password=password)
                    if code == 0:
                        self.logger.info(f"File '{file_path}' copied to remote host. Preview: {preview}")
                        return True
                    else:
                        self.logger.error(f"Failed to move file to '{file_path}' on remote host: {out}")
                        return False
                else:
                    self.logger.error(f"Failed to copy file to remote tmp: {result.stderr}")
                    return False
            finally:
                try:
                    os.remove(tmpf_path)
                except Exception:
                    pass
        except Exception as e:
            self.logger.error(f"Failed to write file '{file_path}' remotely: {e}")
            return False

    def edit_file(self, file_path, action, search, replace=None, line=None, explain=""):
        """
        Edit a file with the specified action, handling both local and remote operations.

        Args:
            file_path (str): Path to the file to edit
            action (str): Edit action ('replace', 'insert_after', 'insert_before', 'delete_line')
            search (str): Search string for the operation
            replace (str, optional): Replacement string for 'replace' action
            line (str, optional): Line to insert for 'insert_after'/'insert_before' actions
            explain (str): Explanation of what this operation does

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            file_path = self._prepare_path(file_path)
        except ValueError as e:
            self.logger.error("Path validation failed for edit_file '%s': %s", file_path, e)
            return False

        if self.terminal.ssh_connection:
            return self._edit_file_remote(file_path, action, search, replace, line, explain)
        else:
            return self._edit_file_local(file_path, action, search, replace, line, explain)

    def _edit_file_local(self, file_path, action, search, replace, line, explain):
        # Input validation
        if not search:
            self.logger.error("Search string cannot be empty")
            return False

        if action == "replace" and not replace:
            self.logger.error("Replace string is required for replace action")
            return False

        if action in ["insert_after", "insert_before"] and not line:
            self.logger.error("Line is required for insert actions")
            return False

        try:
            # Use atomic file operations with temporary file
            temp_path = file_path + ".tmp"
            with open(file_path, "r", encoding="utf-8") as f_in, open(temp_path, "w", encoding="utf-8") as f_out:
                changed = False
                for l in f_in:
                    if action == "replace" and search.strip() == l.strip():
                        f_out.write(replace + "\n")
                        changed = True
                    elif action == "insert_after" and search.strip() == l.strip():
                        f_out.write(l)
                        f_out.write(line + "\n")
                        changed = True
                    elif action == "insert_before" and search.strip() == l.strip():
                        f_out.write(line + "\n")
                        f_out.write(l)
                        changed = True
                    elif action == "delete_line" and search.strip() == l.strip():
                        changed = True
                    else:
                        f_out.write(l)

            if changed:
                # Atomic file replacement
                os.replace(temp_path, file_path)
                self.logger.info(f"File '{file_path}' edited successfully with action '{action}'")
                return True
            else:
                # Clean up temp file if no changes
                os.remove(temp_path)
                self.logger.info(f"No changes made to '{file_path}' with action '{action}'")
                return True
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.remove(temp_path)
            self.logger.error(f"Failed to edit file '{file_path}': {e}")
            return False

    def _edit_file_remote(self, file_path, action, search, replace, line, explain):
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                local_tmp_path = os.path.join(tmpdir, os.path.basename(file_path))
                remote_tmp_path = f"/tmp/{os.path.basename(file_path)}"
                remote = f"{self.terminal.user}@{self.terminal.host}" if self.terminal.user and self.terminal.host else self.terminal.host
                password = getattr(self.terminal, "ssh_password", None)
                q_file_path = self._q(file_path)

                # Get remote file
                scp_get = (
                    ["scp"]
                    + (["-P", str(self.terminal.port)] if self.terminal.port else [])
                    + [self._scp_target(remote, file_path), local_tmp_path]
                )
                result = subprocess.run(scp_get, capture_output=True, text=True)
                if result.returncode != 0:
                    self.logger.error(f"Failed to fetch remote file '{file_path}': {result.stderr}")
                    return False

                # Edit locally
                success = self._edit_file_local(local_tmp_path, action, search, replace, line, explain)

                if success:
                    # Remove existing target file on remote if it exists
                    rm_cmd = f"rm -f {q_file_path}"
                    self.terminal.execute_remote_pexpect(rm_cmd, remote, password=password)

                    # Send back edited file directly to target location
                    scp_put = (
                        ["scp"]
                        + (["-P", str(self.terminal.port)] if self.terminal.port else [])
                        + [local_tmp_path, self._scp_target(remote, file_path)]
                    )
                    result = subprocess.run(scp_put, capture_output=True, text=True)
                    if result.returncode == 0:
                        self.logger.info(f"File '{file_path}' edited and uploaded to remote host with action '{action}'")
                        return True
                    else:
                        self.logger.error(f"Failed to upload edited file to '{file_path}' on remote host: {result.stderr}")
                        return False
                else:
                    return False
        except Exception as e:
            self.logger.error(f"Failed to edit file '{file_path}' remotely: {e}")
            return False

    def _create_directories(self, file_path):
        """Create directory structure for the given file path if it doesn't exist."""
        dir_name = os.path.dirname(file_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

    # ==================== NEW TOOLS ====================

    def read_file(self, file_path: str, start_line: int = None, end_line: int = None, 
                  explain: str = "") -> Dict[str, Any]:
        """
        Read file content from the specified path, handling both local and remote operations.

        Args:
            file_path: Path to the file to read
            start_line: Optional start line number (1-based)
            end_line: Optional end line number (1-based)
            explain: Explanation of what this operation does

        Returns:
            Dictionary with 'success', 'content', 'path', 'lines_count', and optionally 'error'
        """
        try:
            file_path = self._prepare_path(file_path)
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "path": file_path
            }

        if self.terminal.ssh_connection:
            return self._read_file_remote(file_path, start_line, end_line, explain)
        else:
            return self._read_file_local(file_path, start_line, end_line, explain)

    def _read_file_local(self, file_path: str, start_line: int, end_line: int, 
                         explain: str) -> Dict[str, Any]:
        """Read file locally."""
        try:
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": f"File '{file_path}' does not exist",
                    "path": file_path
                }
            
            content_parts: List[str] = []
            total_lines = 0
            lines_returned = 0
            start = max((start_line or 1) - 1, 0)
            end = end_line

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for idx, line in enumerate(f):
                    total_lines += 1
                    if start_line is None and end_line is None:
                        content_parts.append(line)
                        lines_returned += 1
                        continue

                    if idx < start:
                        continue
                    if end is not None and idx + 1 > end:
                        continue
                    content_parts.append(line)
                    lines_returned += 1

            content = "".join(content_parts)
            
            self.logger.info(f"File '{file_path}' read successfully. Lines: {lines_returned}/{total_lines}")
            
            return {
                "success": True,
                "content": content,
                "path": file_path,
                "lines_count": lines_returned,
                "total_lines": total_lines,
                "start_line": start_line,
                "end_line": end_line
            }
            
        except Exception as e:
            self.logger.error(f"Failed to read file '{file_path}': {e}")
            return {
                "success": False,
                "error": str(e),
                "path": file_path
            }

    def _read_file_remote(self, file_path: str, start_line: int, end_line: int, 
                          explain: str) -> Dict[str, Any]:
        """Read file remotely via SSH."""
        try:
            remote = f"{self.terminal.user}@{self.terminal.host}" if self.terminal.user and self.terminal.host else self.terminal.host
            password = getattr(self.terminal, "ssh_password", None)
            
            # Build command based on line range
            if start_line is not None or end_line is not None:
                start = start_line or 1
                end = end_line or "$"
                cmd = f"sed -n '{start},{end}p' {self._q(file_path)}"
            else:
                cmd = f"cat {self._q(file_path)}"
            
            out, code = self.terminal.execute_remote_pexpect(cmd, remote, password=password)
            
            if code == 0:
                # Get total line count
                wc_cmd = f"wc -l {self._q(file_path)}"
                wc_out, wc_code = self.terminal.execute_remote_pexpect(wc_cmd, remote, password=password)
                total_lines = int(wc_out.split()[0]) if wc_code == 0 else "unknown"
                
                lines_returned = len(out.split('\n')) if out else 0
                
                self.logger.info(f"File '{file_path}' read remotely. Lines: {lines_returned}")
                
                return {
                    "success": True,
                    "content": out,
                    "path": file_path,
                    "lines_count": lines_returned,
                    "total_lines": total_lines,
                    "start_line": start_line,
                    "end_line": end_line
                }
            else:
                return {
                    "success": False,
                    "error": out or f"Failed to read file (exit code: {code})",
                    "path": file_path
                }
                
        except Exception as e:
            self.logger.error(f"Failed to read file '{file_path}' remotely: {e}")
            return {
                "success": False,
                "error": str(e),
                "path": file_path
            }

    def list_directory(self, dir_path: str, recursive: bool = False, 
                       pattern: str = None, explain: str = "") -> Dict[str, Any]:
        """
        List directory contents, handling both local and remote operations.

        Args:
            dir_path: Path to the directory to list
            recursive: Whether to list recursively
            pattern: Optional glob pattern to filter files (e.g., "*.log")
            explain: Explanation of what this operation does

        Returns:
            Dictionary with 'success', 'entries', 'path', and optionally 'error'
        """
        try:
            dir_path = self._prepare_path(dir_path)
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "path": dir_path
            }

        if self.terminal.ssh_connection:
            return self._list_directory_remote(dir_path, recursive, pattern, explain)
        else:
            return self._list_directory_local(dir_path, recursive, pattern, explain)

    def _list_directory_local(self, dir_path: str, recursive: bool, 
                               pattern: str, explain: str) -> Dict[str, Any]:
        """List directory locally."""
        try:
            if not os.path.exists(dir_path):
                return {
                    "success": False,
                    "error": f"Directory '{dir_path}' does not exist",
                    "path": dir_path
                }
            
            if not os.path.isdir(dir_path):
                return {
                    "success": False,
                    "error": f"'{dir_path}' is not a directory",
                    "path": dir_path
                }
            
            entries = []
            
            if recursive:
                for root, dirs, files in os.walk(dir_path):
                    for name in dirs:
                        full_path = os.path.join(root, name)
                        rel_path = os.path.relpath(full_path, dir_path)
                        if pattern is None or self._matches_pattern(name, pattern):
                            try:
                                stat = os.stat(full_path)
                                entries.append({
                                    "name": name,
                                    "path": full_path,
                                    "relative_path": rel_path,
                                    "type": "directory",
                                    "size": 0,
                                    "permissions": oct(stat.st_mode)[-3:]
                                })
                            except Exception:
                                pass
                    
                    for name in files:
                        full_path = os.path.join(root, name)
                        rel_path = os.path.relpath(full_path, dir_path)
                        if pattern is None or self._matches_pattern(name, pattern):
                            try:
                                stat = os.stat(full_path)
                                entries.append({
                                    "name": name,
                                    "path": full_path,
                                    "relative_path": rel_path,
                                    "type": "file",
                                    "size": stat.st_size,
                                    "permissions": oct(stat.st_mode)[-3:]
                                })
                            except Exception:
                                pass
            else:
                for entry in os.scandir(dir_path):
                    if pattern is None or self._matches_pattern(entry.name, pattern):
                        try:
                            stat = entry.stat()
                            entries.append({
                                "name": entry.name,
                                "path": entry.path,
                                "relative_path": entry.name,
                                "type": "directory" if entry.is_dir() else "file",
                                "size": stat.st_size if entry.is_file() else 0,
                                "permissions": oct(stat.st_mode)[-3:]
                            })
                        except Exception:
                            pass
            
            # Sort: directories first, then files, alphabetically
            entries.sort(key=lambda x: (0 if x["type"] == "directory" else 1, x["name"].lower()))
            
            self.logger.info(f"Directory '{dir_path}' listed. Entries: {len(entries)}")
            
            return {
                "success": True,
                "entries": entries,
                "path": dir_path,
                "total_count": len(entries),
                "recursive": recursive
            }
            
        except Exception as e:
            self.logger.error(f"Failed to list directory '{dir_path}': {e}")
            return {
                "success": False,
                "error": str(e),
                "path": dir_path
            }

    def _list_directory_remote(self, dir_path: str, recursive: bool, 
                                pattern: str, explain: str) -> Dict[str, Any]:
        """List directory remotely via SSH."""
        try:
            remote = f"{self.terminal.user}@{self.terminal.host}" if self.terminal.user and self.terminal.host else self.terminal.host
            password = getattr(self.terminal, "ssh_password", None)
            
            # Build ls command
            if recursive:
                # Using find for recursive listing
                if pattern:
                    # Escape pattern for shell
                    escaped_pattern = self._q(pattern)
                    cmd = (
                        f"find {self._q(dir_path)} -name {escaped_pattern} "
                        f"-exec ls -ld {{}} \\;"
                    )
                else:
                    cmd = f"find {self._q(dir_path)} -exec ls -ld {{}} \\;"
            else:
                if pattern:
                    escaped_pattern = self._q(pattern)
                    cmd = (
                        f"find {self._q(dir_path)} -maxdepth 1 -name {escaped_pattern} "
                        f"-exec ls -ld {{}} \\;"
                    )
                else:
                    cmd = (
                        f"ls -ld {self._q(dir_path)}/* {self._q(dir_path)}/.* "
                        f"2>/dev/null | grep -v '^d.*\\.$'"
                    )
            
            out, code = self.terminal.execute_remote_pexpect(cmd, remote, password=password)
            
            if code == 0 or out:
                entries = self._parse_ls_output(out, dir_path)
                
                # Sort: directories first, then files, alphabetically
                entries.sort(key=lambda x: (0 if x["type"] == "directory" else 1, x["name"].lower()))
                
                self.logger.info(f"Directory '{dir_path}' listed remotely. Entries: {len(entries)}")
                
                return {
                    "success": True,
                    "entries": entries,
                    "path": dir_path,
                    "total_count": len(entries),
                    "recursive": recursive
                }
            else:
                return {
                    "success": False,
                    "error": out or f"Failed to list directory (exit code: {code})",
                    "path": dir_path
                }
                
        except Exception as e:
            self.logger.error(f"Failed to list directory '{dir_path}' remotely: {e}")
            return {
                "success": False,
                "error": str(e),
                "path": dir_path
            }

    def _parse_ls_output(self, output: str, base_path: str) -> List[Dict[str, Any]]:
        """Parse ls -ld output into structured entries."""
        entries = []
        
        for line in output.strip().split('\n'):
            if not line.strip():
                continue
            
            # Parse ls -l format: permissions, links, owner, group, size, date, date, date, name
            match = re.match(
                r'^([d\-ls]) ([rwx\-]{9})\s+(\d+)\s+(\S+)\s+(\S+)\s+(\d+)\s+(\w+\s+\d+\s+\d+:?\d*)\s+(.+)$',
                line
            )
            
            if match:
                perm_char, perms, links, owner, group, size, date, name = match.groups()
                
                # Determine type
                entry_type = "directory" if perm_char == 'd' else "file"
                if perm_char == 'l':
                    entry_type = "link"
                    # Handle symlink target
                    if ' -> ' in name:
                        name = name.split(' -> ')[0]
                
                # Handle full path in output (from find command)
                if '/' in name and not name.startswith('/'):
                    full_path = name
                    name = os.path.basename(name)
                else:
                    full_path = os.path.join(base_path, name) if not name.startswith('/') else name
                
                entries.append({
                    "name": name,
                    "path": full_path,
                    "relative_path": os.path.relpath(full_path, base_path) if full_path.startswith(base_path) else name,
                    "type": entry_type,
                    "size": int(size),
                    "permissions": perms,
                    "owner": owner,
                    "group": group
                })
        
        return entries

    def _matches_pattern(self, name: str, pattern: str) -> bool:
        """Check if name matches glob pattern."""
        import fnmatch
        return fnmatch.fnmatch(name, pattern)

    def copy_file(self, source: str, destination: str, overwrite: bool = False,
                  explain: str = "") -> Dict[str, Any]:
        """
        Copy file or directory, handling both local and remote operations.

        Args:
            source: Source file/directory path
            destination: Destination path
            overwrite: Whether to overwrite existing destination
            explain: Explanation of what this operation does

        Returns:
            Dictionary with 'success', 'source', 'destination', and optionally 'error'
        """
        try:
            source = self._prepare_path(source)
            destination = self._prepare_path(destination)
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "source": source,
                "destination": destination
            }

        if self.terminal.ssh_connection:
            return self._copy_file_remote(source, destination, overwrite, explain)
        else:
            return self._copy_file_local(source, destination, overwrite, explain)

    def _copy_file_local(self, source: str, destination: str, overwrite: bool, 
                         explain: str) -> Dict[str, Any]:
        """Copy file locally."""
        try:
            if not os.path.exists(source):
                return {
                    "success": False,
                    "error": f"Source '{source}' does not exist",
                    "source": source,
                    "destination": destination
                }
            
            if os.path.exists(destination) and not overwrite:
                return {
                    "success": False,
                    "error": f"Destination '{destination}' already exists. Use overwrite=True to replace.",
                    "source": source,
                    "destination": destination
                }
            
            # Create destination directory if needed
            if os.path.isdir(source):
                # Copy directory
                if os.path.exists(destination):
                    if overwrite:
                        shutil.rmtree(destination)
                    else:
                        return {
                            "success": False,
                            "error": f"Destination '{destination}' already exists",
                            "source": source,
                            "destination": destination
                        }
                shutil.copytree(source, destination)
            else:
                # Copy file
                self._create_directories(destination)
                shutil.copy2(source, destination)
            
            self.logger.info(f"Copied '{source}' to '{destination}'")
            
            return {
                "success": True,
                "source": source,
                "destination": destination,
                "type": "directory" if os.path.isdir(source) else "file"
            }
            
        except Exception as e:
            self.logger.error(f"Failed to copy '{source}' to '{destination}': {e}")
            return {
                "success": False,
                "error": str(e),
                "source": source,
                "destination": destination
            }

    def _copy_file_remote(self, source: str, destination: str, overwrite: bool, 
                          explain: str) -> Dict[str, Any]:
        """Copy file remotely via SSH."""
        try:
            remote = f"{self.terminal.user}@{self.terminal.host}" if self.terminal.user and self.terminal.host else self.terminal.host
            password = getattr(self.terminal, "ssh_password", None)
            
            # Check if source exists
            q_source = self._q(source)
            q_destination = self._q(destination)
            check_cmd = f"test -e {q_source} && echo exists || echo not_found"
            check_out, _ = self.terminal.execute_remote_pexpect(check_cmd, remote, password=password)
            
            if "not_found" in check_out:
                return {
                    "success": False,
                    "error": f"Source '{source}' does not exist",
                    "source": source,
                    "destination": destination
                }
            
            # Check if destination exists
            check_dest_cmd = f"test -e {q_destination} && echo exists || echo not_found"
            check_dest_out, _ = self.terminal.execute_remote_pexpect(check_dest_cmd, remote, password=password)
            
            if "exists" in check_dest_out and not overwrite:
                return {
                    "success": False,
                    "error": f"Destination '{destination}' already exists. Use overwrite=True to replace.",
                    "source": source,
                    "destination": destination
                }
            
            # Determine if source is directory
            is_dir_cmd = f"test -d {q_source} && echo dir || echo file"
            is_dir_out, _ = self.terminal.execute_remote_pexpect(is_dir_cmd, remote, password=password)
            is_dir = "dir" in is_dir_out
            
            # Build copy command
            if "exists" in check_dest_out and overwrite:
                rm_cmd = f"rm -rf {q_destination}"
                self.terminal.execute_remote_pexpect(rm_cmd, remote, password=password)
            
            # Create parent directory for destination
            dest_dir = os.path.dirname(destination)
            if dest_dir:
                mkdir_cmd = f"mkdir -p {self._q(dest_dir)}"
                self.terminal.execute_remote_pexpect(mkdir_cmd, remote, password=password)
            
            # Copy
            cp_cmd = f"cp -{'r' if is_dir else ''}p {q_source} {q_destination}"
            out, code = self.terminal.execute_remote_pexpect(cp_cmd, remote, password=password)
            
            if code == 0:
                self.logger.info(f"Copied '{source}' to '{destination}' remotely")
                return {
                    "success": True,
                    "source": source,
                    "destination": destination,
                    "type": "directory" if is_dir else "file"
                }
            else:
                return {
                    "success": False,
                    "error": out or f"Copy failed with exit code {code}",
                    "source": source,
                    "destination": destination
                }
                
        except Exception as e:
            self.logger.error(f"Failed to copy '{source}' to '{destination}' remotely: {e}")
            return {
                "success": False,
                "error": str(e),
                "source": source,
                "destination": destination
            }

    def delete_file(self, file_path: str, backup: bool = False, 
                    explain: str = "") -> Dict[str, Any]:
        """
        Delete file or directory, handling both local and remote operations.

        Args:
            file_path: Path to file or directory to delete
            backup: Whether to create backup before deletion
            explain: Explanation of what this operation does

        Returns:
            Dictionary with 'success', 'path', and optionally 'error' or 'backup_path'
        """
        try:
            file_path = self._prepare_path(file_path)
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "path": file_path
            }

        if self.terminal.ssh_connection:
            return self._delete_file_remote(file_path, backup, explain)
        else:
            return self._delete_file_local(file_path, backup, explain)

    def search_in_file(self, file_path: str, query: str, context_lines: int = 3, 
                       max_results: int = 10, explain: str = "") -> Dict[str, Any]:
        """
        Search for a query pattern in a file, handling both local and remote operations.

        Args:
            file_path: Path to the file to search in
            query: Search query/pattern (supports regex)
            context_lines: Number of lines to show before/after matches
            max_results: Maximum number of results to return
            explain: Explanation of what this operation does

        Returns:
            Dictionary with 'success', 'matches', 'total_matches', 'path', and optionally 'error'
        """
        try:
            file_path = self._prepare_path(file_path)
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "path": file_path
            }

        if self.terminal.ssh_connection:
            return self._search_in_file_remote(file_path, query, context_lines, max_results, explain)
        else:
            return self._search_in_file_local(file_path, query, context_lines, max_results, explain)

    def _search_in_file_local(self, file_path: str, query: str, context_lines: int, 
                              max_results: int, explain: str) -> Dict[str, Any]:
        """Search for pattern in file locally."""
        try:
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": f"File '{file_path}' does not exist",
                    "path": file_path
                }
            
            # Compile regex pattern
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error as e:
                return {
                    "success": False,
                    "error": f"Invalid regex pattern '{query}': {e}",
                    "path": file_path
                }
            
            matches = []
            total_matches = 0
            
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            
            for line_num, line in enumerate(lines, 1):
                # Find all matches in the line
                line_matches = list(pattern.finditer(line))
                if line_matches:
                    total_matches += len(line_matches)
                    
                    # Only process up to max_results total matches
                    if len(matches) >= max_results:
                        continue
                    
                    for match in line_matches:
                        if len(matches) >= max_results:
                            break
                        
                        # Get context lines
                        start_idx = max(0, line_num - context_lines - 1)
                        end_idx = min(len(lines), line_num + context_lines)
                        
                        context_before = []
                        context_after = []
                        
                        # Collect context lines before
                        for i in range(start_idx, line_num - 1):
                            context_before.append(lines[i].rstrip())
                        
                        # Collect context lines after
                        for i in range(line_num, end_idx):
                            context_after.append(lines[i].rstrip())
                        
                        matches.append({
                            "line_number": line_num,
                            "content": line.rstrip(),
                            "match_start": match.start(),
                            "match_end": match.end(),
                            "context_before": context_before,
                            "context_after": context_after
                        })
            
            self.logger.info(f"Search in '{file_path}' completed. Total matches: {total_matches}, Returned: {len(matches)}")
            
            return {
                "success": True,
                "matches": matches,
                "total_matches": total_matches,
                "path": file_path,
                "query": query,
                "context_lines": context_lines,
                "max_results": max_results
            }
            
        except Exception as e:
            self.logger.error(f"Failed to search in file '{file_path}': {e}")
            return {
                "success": False,
                "error": str(e),
                "path": file_path
            }

    def _search_in_file_remote(self, file_path: str, query: str, context_lines: int, 
                               max_results: int, explain: str) -> Dict[str, Any]:
        """Search for pattern in file remotely via SSH."""
        try:
            remote = f"{self.terminal.user}@{self.terminal.host}" if self.terminal.user and self.terminal.host else self.terminal.host
            password = getattr(self.terminal, "ssh_password", None)
            
            # Escape query for shell
            escaped_query = self._q(query)
            
            # Use grep for efficient remote search
            # -n: show line numbers
            # -i: case insensitive
            # -C: context lines (before and after)
            # grep -C output format:
            #   - For matches: "line_number:content"
            #   - For context:  "line_number-content"
            #   - Separator:    "--"
            grep_cmd = f"grep -n -i -C {context_lines} {escaped_query} {self._q(file_path)}"
            
            out, code = self.terminal.execute_remote_pexpect(grep_cmd, remote, password=password)
            
            if code == 0 or out:
                # Parse grep output correctly
                # Format: linenum:match or linenum-context
                matches = []
                total_matches = 0
                current_match = None
                expecting_context_after = False
                
                lines = out.strip().split('\n')
                for line in lines:
                    if not line.strip():
                        continue
                    
                    stripped = line.strip()
                    
                    # Skip separator lines (--)
                    if stripped == "--":
                        # Reset expecting_context_after when we hit a separator
                        expecting_context_after = False
                        continue
                    
                    # Find the first colon or dash separator
                    # Format: "linenum:content" for match or "linenum-content" for context
                    sep_pos = -1
                    sep_char = None
                    for i, ch in enumerate(stripped):
                        if ch == ':':
                            sep_pos = i
                            sep_char = ':'
                            break
                        elif ch == '-':
                            # Could be context line or negative line number (unlikely but handle it)
                            if i > 0 and stripped[:i].isdigit():
                                sep_pos = i
                                sep_char = '-'
                                break
                    
                    if sep_pos == -1:
                        # No separator found - might be multiline content continuation
                        if current_match and expecting_context_after:
                            current_match["context_after"].append(stripped)
                        continue
                    
                    # Extract line number
                    prefix = stripped[:sep_pos]
                    rest = stripped[sep_pos + 1:]
                    
                    try:
                        line_num = int(prefix)
                    except ValueError:
                        # Not a valid line number - might be grep error or weird output
                        continue
                    
                    if sep_char == ':':
                        # This is a MATCH line
                        current_match = {
                            "line_number": line_num,
                            "content": rest,
                            "context_before": [],
                            "context_after": []
                        }
                        matches.append(current_match)
                        total_matches += 1
                        expecting_context_after = True
                        
                        # Limit results
                        if len(matches) >= max_results:
                            break
                    elif sep_char == '-':
                        # This is a CONTEXT line
                        if current_match:
                            if expecting_context_after:
                                current_match["context_after"].append(rest)
                            else:
                                current_match["context_before"].append(rest)
                
                self.logger.info(f"Remote search in '{file_path}' completed. Total matches: {total_matches}, Returned: {len(matches)}")
                
                return {
                    "success": True,
                    "matches": matches,
                    "total_matches": total_matches,
                    "path": file_path,
                    "query": query,
                    "context_lines": context_lines,
                    "max_results": max_results
                }
            else:
                # Check if file exists
                check_cmd = f"test -f {self._q(file_path)} && echo exists || echo not_found"
                check_out, _ = self.terminal.execute_remote_pexpect(check_cmd, remote, password=password)
                
                if "not_found" in check_out:
                    return {
                        "success": False,
                        "error": f"File '{file_path}' does not exist",
                        "path": file_path
                    }
                else:
                    return {
                        "success": False,
                        "error": f"No matches found for '{query}' in '{file_path}'",
                        "path": file_path
                    }
                
        except Exception as e:
            self.logger.error(f"Failed to search in file '{file_path}' remotely: {e}")
            return {
                "success": False,
                "error": str(e),
                "path": file_path
            }

    def _delete_file_local(self, file_path: str, backup: bool, 
                           explain: str) -> Dict[str, Any]:
        """Delete file locally."""
        try:
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": f"'{file_path}' does not exist",
                    "path": file_path
                }
            
            # Determine type BEFORE deletion
            is_dir = os.path.isdir(file_path)
            backup_path = None
            
            # Create backup if requested
            if backup:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                backup_path = f"{file_path}.backup_{timestamp}"
                if is_dir:
                    shutil.copytree(file_path, backup_path)
                else:
                    shutil.copy2(file_path, backup_path)
                self.logger.info(f"Created backup: {backup_path}")
            
            # Delete
            if is_dir:
                shutil.rmtree(file_path)
            else:
                os.remove(file_path)
            
            self.logger.info(f"Deleted '{file_path}'")
            
            return {
                "success": True,
                "path": file_path,
                "backup_path": backup_path,
                "type": "directory" if is_dir else "file"
            }
            
        except Exception as e:
            self.logger.error(f"Failed to delete '{file_path}': {e}")
            return {
                "success": False,
                "error": str(e),
                "path": file_path
            }

    def _delete_file_remote(self, file_path: str, backup: bool, 
                            explain: str) -> Dict[str, Any]:
        """Delete file remotely via SSH."""
        try:
            remote = f"{self.terminal.user}@{self.terminal.host}" if self.terminal.user and self.terminal.host else self.terminal.host
            password = getattr(self.terminal, "ssh_password", None)
            
            # Check if path exists
            q_file_path = self._q(file_path)
            check_cmd = f"test -e {q_file_path} && echo exists || echo not_found"
            check_out, _ = self.terminal.execute_remote_pexpect(check_cmd, remote, password=password)
            
            if "not_found" in check_out:
                return {
                    "success": False,
                    "error": f"'{file_path}' does not exist",
                    "path": file_path
                }
            
            # Check if directory
            is_dir_cmd = f"test -d {q_file_path} && echo dir || echo file"
            is_dir_out, _ = self.terminal.execute_remote_pexpect(is_dir_cmd, remote, password=password)
            is_dir = "dir" in is_dir_out
            
            backup_path = None
            
            # Create backup if requested
            if backup:
                import time
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                backup_path = f"{file_path}.backup_{timestamp}"
                cp_cmd = f"cp -{'r' if is_dir else ''} {q_file_path} {self._q(backup_path)}"
                cp_out, cp_code = self.terminal.execute_remote_pexpect(cp_cmd, remote, password=password)
                if cp_code == 0:
                    self.logger.info(f"Created backup: {backup_path}")
                else:
                    self.logger.warning(f"Failed to create backup: {cp_out}")
                    backup_path = None
            
            # Delete
            rm_cmd = f"rm -rf {q_file_path}"
            out, code = self.terminal.execute_remote_pexpect(rm_cmd, remote, password=password)
            
            if code == 0:
                self.logger.info(f"Deleted '{file_path}' remotely")
                return {
                    "success": True,
                    "path": file_path,
                    "backup_path": backup_path,
                    "type": "directory" if is_dir else "file"
                }
            else:
                return {
                    "success": False,
                    "error": out or f"Delete failed with exit code {code}",
                    "path": file_path
                }
                
        except Exception as e:
            self.logger.error(f"Failed to delete '{file_path}' remotely: {e}")
            return {
                "success": False,
                "error": str(e),
                "path": file_path
            }
