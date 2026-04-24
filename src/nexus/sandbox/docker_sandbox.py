"""Docker-backed Python sandbox.

Defaults: no network, read-only FS mount, 512MB RAM, 1 CPU, 30s wall,
dropped all capabilities. This is the minimum bar for LLM-generated code.

For production-grade isolation (Firecracker microVM), switch to E2B:
    pip install e2b-code-interpreter

Usage:
    sb = DockerSandbox()
    result = sb.run_python("print('hi')")
    print(result.stdout, result.exit_code)
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SandboxResult:
    ok: bool
    stdout: str
    stderr: str
    exit_code: int
    elapsed_ms: float
    skill_file: str
    timed_out: bool = False


class DockerSandbox:
    """Run untrusted Python code in a locked-down Docker container."""

    DEFAULT_IMAGE = "python:3.12-slim"

    def __init__(
        self,
        *,
        image: str | None = None,
        memory: str = "512m",
        cpus: str = "1",
        network: str = "none",
        timeout_sec: int = 30,
    ):
        self.image = image or self.DEFAULT_IMAGE
        self.memory = memory
        self.cpus = cpus
        self.network = network
        self.timeout_sec = timeout_sec

    def is_available(self) -> bool:
        return shutil.which("docker") is not None

    def run_python(self, code: str, *, extra_files: dict[str, str] | None = None) -> SandboxResult:
        if not self.is_available():
            return SandboxResult(
                ok=False,
                stdout="",
                stderr="docker not found on PATH; install Docker Desktop or use another sandbox",
                exit_code=-1,
                elapsed_ms=0.0,
                skill_file="",
            )

        with tempfile.TemporaryDirectory(prefix="oracle_sandbox_") as td:
            tdp = Path(td)
            skill_file = tdp / "skill.py"
            skill_file.write_text(code, encoding="utf-8")
            for name, body in (extra_files or {}).items():
                (tdp / name).write_text(body, encoding="utf-8")

            container_name = f"oracle-sb-{uuid.uuid4().hex[:8]}"
            cmd = [
                "docker",
                "run",
                "--rm",
                "--name",
                container_name,
                f"--network={self.network}",
                f"--memory={self.memory}",
                f"--cpus={self.cpus}",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=128",
                "--read-only",
                "--tmpfs",
                "/tmp:rw,size=64m,noexec,nosuid,nodev",
                "-v",
                f"{tdp}:/work:ro",
                "-w",
                "/work",
                self.image,
                "python",
                "skill.py",
            ]

            t0 = time.perf_counter()
            timed_out = False
            try:
                p = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_sec,
                )
                stdout, stderr, rc = p.stdout, p.stderr, p.returncode
            except subprocess.TimeoutExpired as e:
                timed_out = True
                # Make sure the runaway container is killed
                subprocess.run(
                    ["docker", "kill", container_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                stdout = e.stdout or ""
                stderr = (e.stderr or "") + "\n[sandbox] killed after timeout"
                rc = -9
            except Exception as ex:
                stdout, stderr, rc = "", f"sandbox error: {ex}", -2

            return SandboxResult(
                ok=(rc == 0 and not timed_out),
                stdout=(stdout or "")[-8000:],
                stderr=(stderr or "")[-4000:],
                exit_code=rc,
                elapsed_ms=(time.perf_counter() - t0) * 1000,
                skill_file=str(skill_file),
                timed_out=timed_out,
            )
