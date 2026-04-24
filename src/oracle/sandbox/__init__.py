"""Sandboxes for running LLM-generated skill code.

Research (2025 CVEs, JFSA-2025-001434277 smolagents escape, CVE-2025-3248 Langflow):
subprocess+seccomp is NOT safe for LLM-generated Python. Use Docker for v1;
consider E2B (Firecracker microVMs) for production.
"""

from oracle.sandbox.docker_sandbox import DockerSandbox, SandboxResult

__all__ = ["DockerSandbox", "SandboxResult"]
