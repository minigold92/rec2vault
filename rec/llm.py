"""Text-only calls to subscription CLIs: Codex first, Antigravity (agy) as fallback.

Both run without tool/command permissions: Codex in its read-only sandbox, agy in print mode
(which cannot approve command tools). Prompts carry transcript text only, never file paths.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

from . import config


class LLMError(RuntimeError):
    pass


def _env():
    env = dict(os.environ)
    env["PATH"] = ":".join([os.path.expanduser("~/.local/bin"), "/opt/homebrew/bin", "/usr/local/bin", env.get("PATH", "")])
    return env


def _codex(prompt: str) -> str:
    exe = shutil.which("codex", path=_env()["PATH"])
    if not exe:
        raise LLMError("codex not installed")
    with tempfile.TemporaryDirectory() as d:
        last = os.path.join(d, "last.txt")
        # read-only sandbox alone still lets the model read any file (docs/research/cli-no-tool.md §4).
        # Ignore the user's config/rules and remove the shell, web, app, plugin and image tools.
        r = subprocess.run(
            [exe, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--ephemeral",
             "--ignore-user-config", "--ignore-rules",
             "-c", "features.shell_tool=false", "-c", 'web_search="disabled"',
             "-c", "features.apps=false", "-c", "features.plugins=false", "-c", "features.view_image=false",
             "-c", "features.image_generation=false", "-c", "features.hooks=false",
             "-c", f'model_reasoning_effort="{config.CODEX_EFFORT}"', "-o", last, "-"],
            input=prompt, capture_output=True, text=True, cwd=d, env=_env(), timeout=config.LLM_TIMEOUT_SEC,
        )
        if r.returncode != 0 or not os.path.exists(last):
            raise LLMError(f"codex exit {r.returncode}: {r.stderr[-500:]}")
        return open(last, encoding="utf-8").read()


def _agy(prompt: str) -> str:
    exe = shutil.which("agy", path=_env()["PATH"])
    if not exe:
        raise LLMError("agy not installed")
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run(
            [exe, "-p", prompt, "--model", config.AGY_MODEL, "--print-timeout", f"{config.LLM_TIMEOUT_SEC}s"],
            capture_output=True, text=True, cwd=d, env=_env(), timeout=config.LLM_TIMEOUT_SEC + 30,
        )
        out = r.stdout.strip()
        if r.returncode != 0 or not out or "blocked by Gemini's filters" in out:
            raise LLMError(f"agy exit {r.returncode}: {(r.stderr or out)[-500:]}")
        return out


ENGINES = {"codex": _codex, "agy": _agy}


def complete(prompt: str, validate=None, order=("codex", "codex", "agy")):
    """Return (text, engine). `validate(text)` must return the parsed value or raise ValueError."""
    errors = []
    for name in order:
        try:
            text = ENGINES[name](prompt)
            return (validate(text) if validate else text), name
        except (LLMError, ValueError, subprocess.TimeoutExpired) as e:
            errors.append(f"{name}: {e}")
    raise LLMError(" | ".join(errors))


def json_array(text: str):
    m = re.search(r"\[\s*\{.*\}\s*\]", text, re.S)
    if not m:
        raise ValueError("no JSON array in response")
    return json.loads(m.group(0))
