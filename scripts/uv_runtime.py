"""Find uv or install a private copy for personal-skills."""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv


def uv_binary():
    search_dirs = [os.environ.get("PATH", os.defpath), str(Path.home() / ".local/bin"), "/opt/homebrew/bin", "/usr/local/bin"]
    installed = shutil.which("uv", path=os.pathsep.join(search_dirs))
    if installed:
        return installed
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    tools = data / "personal-skills" / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    env = tools / "uv"
    binary = env / "bin/uv"
    with (tools / "uv.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not binary.is_file() or not os.access(binary, os.X_OK):
            print("Устанавливаю uv для personal-skills…", file=sys.stderr, flush=True)
            venv.EnvBuilder(with_pip=True).create(env)
            subprocess.run([str(env / "bin/python"), "-m", "pip", "install", "--disable-pip-version-check",
                            "--only-binary=:all:", "uv==0.8.22"], check=True, stdout=sys.stderr)
    return str(binary)
