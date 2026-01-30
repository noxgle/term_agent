import os
import tempfile
import subprocess
import logging

class FileOperator:
    def __init__(self, terminal, logger=None):
        self.terminal = terminal
        self.logger = logger or logging.getLogger(__name__)

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
        if file_path and not file_path.startswith("/"):
            file_path = os.path.join(os.getcwd(), file_path)

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

            # Remove existing file on remote host if exists
            rm_cmd = f"rm -f '{file_path}'"
            self.terminal.execute_remote_pexpect(rm_cmd, remote, password=password)
            # Remove existing temp file on remote host if exists
            rm_tmp_cmd = f"rm -f '{remote_tmp_path}'"
            self.terminal.execute_remote_pexpect(rm_tmp_cmd, remote, password=password)

            scp_cmd = ["scp"] + (["-P", str(self.terminal.port)] if self.terminal.port else []) + [tmpf_path, f"{remote}:{remote_tmp_path}"]
            try:
                result = subprocess.run(scp_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    needs_sudo = not (self.terminal.user == "root" or file_path.startswith(f"/home/{self.terminal.user}") or file_path.startswith("/tmp"))
                    if remote_tmp_path == file_path:
                        code = 0
                        out = ""
                    else:
                        if needs_sudo:
                            cp_cmd = f"sudo cp '{remote_tmp_path}' '{file_path}' && sudo rm '{remote_tmp_path}'"
                        else:
                            cp_cmd = f"mv '{remote_tmp_path}' '{file_path}'"
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
        if file_path and not file_path.startswith("/"):
            file_path = os.path.join(os.getcwd(), file_path)

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

                # Get remote file
                scp_get = ["scp"] + (["-P", str(self.terminal.port)] if self.terminal.port else []) + [f"{remote}:{file_path}", local_tmp_path]
                result = subprocess.run(scp_get, capture_output=True, text=True)
                if result.returncode != 0:
                    self.logger.error(f"Failed to fetch remote file '{file_path}': {result.stderr}")
                    return False

                # Edit locally
                success = self._edit_file_local(local_tmp_path, action, search, replace, line, explain)

                if success:
                    # Remove existing target file on remote if it exists
                    rm_cmd = f"rm -f '{file_path}'"
                    self.terminal.execute_remote_pexpect(rm_cmd, remote, password=password)

                    # Send back edited file directly to target location
                    scp_put = ["scp"] + (["-P", str(self.terminal.port)] if self.terminal.port else []) + [local_tmp_path, f"{remote}:{file_path}"]
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