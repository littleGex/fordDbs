"""Test double for ops.backup.common.Runner (#31): records every command
and answers from a table keyed by command prefix."""
import subprocess

from ops.backup.common import CommandError


class FakeRunner:
    def __init__(self, responses=None):
        self.responses = dict(responses or {})
        self.calls = []

    def _match(self, cmd):
        line = " ".join(cmd)
        keys = [k for k in self.responses if line.startswith(k)]
        return self.responses[max(keys, key=len)] if keys else b""

    def run(self, cmd, *, stdin=None, stdout=None, env=None, check=True):
        kwargs = {"stdin": stdin, "stdout": stdout, "env": env,
                  "check": check}
        self.calls.append((list(cmd), kwargs))
        response = self._match(cmd)
        if callable(response):
            response = response(cmd, kwargs)
        code, out = (response, b"") if isinstance(response, int) \
            else (0, response or b"")
        if code and check:
            raise CommandError(cmd, code, b"fake failure")
        if stdout is not None:
            stdout.write(out)
            out = b""
        return subprocess.CompletedProcess(cmd, code, out, b"")

    def commands(self, prefix=""):
        return [c for c, _ in self.calls if " ".join(c).startswith(prefix)]
