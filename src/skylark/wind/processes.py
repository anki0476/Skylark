"""Launch the owned interpreter directly, including Windows virtual environments."""
import os
import subprocess
import sys


def spawn_python(arguments, **options):
    executable = sys.executable
    environment = dict(options.pop("env", os.environ))
    if os.name == "nt":
        options.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        base = getattr(sys, "_base_executable", executable)
        if os.path.normcase(base) != os.path.normcase(executable):
            # CPython multiprocessing uses the same mechanism to bypass the
            # venv redirector, so Popen owns the interpreter rather than a proxy.
            environment["__PYVENV_LAUNCHER__"] = executable
            executable = base
    return subprocess.Popen([executable, *map(str, arguments)], env=environment, **options)


def stop_process(process, timeout=5):
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)
