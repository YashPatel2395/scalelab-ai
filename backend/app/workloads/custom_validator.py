"""
AST-based validator for user-uploaded Python workload files.

Security model
──────────────
This validator performs static analysis before execution. It is a
best-effort gate that reduces the attack surface for accidental mistakes.

What it checks:
  - Python syntax is valid
  - run(input_size, worker_count) function is defined at module level
  - No blocked imports: os, subprocess, socket, shutil, pathlib, sys,
    ctypes, multiprocessing (use is for user workload logic, not system ops)
  - No dangerous builtins: eval, exec, compile, __import__, open
  - No heavy import-time execution (warns, doesn't block)

What it does NOT guarantee:
  - Full sandboxing — a determined attacker can bypass AST analysis
  - Memory safety — subprocess timeout is the only hard limit
  - Network isolation — the subprocess has normal network access
  - Filesystem isolation — only `open` calls are blocked at AST level

Do not run workloads from unknown/untrusted sources.
For production multi-tenant use, replace the subprocess runner with
a Docker-isolated sandbox or gVisor-based container.
"""

import ast
from dataclasses import dataclass, field


BLOCKED_IMPORTS: frozenset[str] = frozenset({
    "os",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
    "sys",
    "ctypes",
    "pty",
    "atexit",
    "signal",
    "resource",
    "gc",
    "inspect",
    "importlib",
    "runpy",
    "code",
    "codeop",
    "pickle",
    "shelve",
})

BLOCKED_BUILTINS: frozenset[str] = frozenset({
    "eval",
    "exec",
    "compile",
    "__import__",
    "breakpoint",
    "open",
})


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_workload_file(source_code: str) -> ValidationResult:
    """
    Validate a custom workload Python source string.

    Returns a ValidationResult. ``valid`` is True only when there are no errors.
    Warnings do not block acceptance but are surfaced to the user.
    """
    result = ValidationResult(valid=True)

    # ── Step 1: syntax ─────────────────────────────────────────────────────────
    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        return ValidationResult(valid=False, errors=[f"Syntax error at line {exc.lineno}: {exc.msg}"])

    # ── Step 2: required run() function ────────────────────────────────────────
    _check_run_function(tree, result)

    # ── Step 3: blocked imports ─────────────────────────────────────────────────
    _check_imports(tree, result)

    # ── Step 4: blocked builtins ────────────────────────────────────────────────
    _check_dangerous_calls(tree, result)

    # ── Step 5: import-time execution ───────────────────────────────────────────
    _check_module_level_execution(tree, result)

    result.valid = len(result.errors) == 0
    return result


# ── Checkers ──────────────────────────────────────────────────────────────────

def _check_run_function(tree: ast.Module, result: ValidationResult) -> None:
    """Verify a top-level run(input_size, worker_count) function exists."""
    run_fn: ast.FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run":
            run_fn = node
            break

    if run_fn is None:
        result.errors.append(
            "Missing required function: def run(input_size: int, worker_count: int) -> dict. "
            "This function must be defined at the top level of the file."
        )
        return

    args = run_fn.args
    positional = [a.arg for a in args.args]

    if len(positional) < 2:
        result.errors.append(
            f"run() must accept at least 2 parameters (input_size, worker_count). "
            f"Found only: {positional}"
        )
        return

    if positional[0] != "input_size":
        result.warnings.append(
            f"First parameter should be named 'input_size', got '{positional[0]}'. "
            "ScaleLab passes input_size as a positional argument."
        )
    if positional[1] != "worker_count":
        result.warnings.append(
            f"Second parameter should be named 'worker_count', got '{positional[1]}'. "
            "ScaleLab passes worker_count as a positional argument."
        )

    if isinstance(run_fn, ast.AsyncFunctionDef):
        result.errors.append(
            "run() must be a regular (synchronous) function, not async. "
            "ScaleLab calls it with a plain function call."
        )


def _check_imports(tree: ast.Module, result: ValidationResult) -> None:
    """Block imports of potentially dangerous modules."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BLOCKED_IMPORTS:
                    result.errors.append(
                        f"Blocked import '{alias.name}' (line {node.lineno}): "
                        f"module '{root}' is not permitted in custom workloads."
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in BLOCKED_IMPORTS:
                    result.errors.append(
                        f"Blocked import 'from {node.module} ...' (line {node.lineno}): "
                        f"module '{root}' is not permitted in custom workloads."
                    )


def _check_dangerous_calls(tree: ast.Module, result: ValidationResult) -> None:
    """Block dangerous built-in function calls."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name: str | None = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name and func_name in BLOCKED_BUILTINS:
            lineno = getattr(node, "lineno", "?")
            result.errors.append(
                f"Blocked call '{func_name}()' (line {lineno}): "
                "this built-in is not permitted in custom workloads."
            )


def _check_module_level_execution(tree: ast.Module, result: ValidationResult) -> None:
    """
    Warn about non-definition statements at module level.
    Heavy import-time execution can cause runner timeouts.
    """
    _DEFINITION_TYPES = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Import,
        ast.ImportFrom,
        ast.Assign,
        ast.AnnAssign,
        ast.AugAssign,
        ast.If,          # allow if __name__ == '__main__': guard
        ast.Try,
        ast.Pass,
    )

    for node in tree.body:
        # Allow module docstrings
        if isinstance(node, ast.Expr):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                continue
            result.warnings.append(
                f"Line {node.lineno}: module-level expression found. "
                "Avoid running code at import time — place it inside run()."
            )
        elif not isinstance(node, _DEFINITION_TYPES):
            result.warnings.append(
                f"Line {node.lineno}: unexpected top-level statement "
                f"({type(node).__name__}). Consider wrapping it in run()."
            )
