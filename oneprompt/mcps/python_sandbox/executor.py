"""
Safe code execution with timeout and output capture.
"""

from __future__ import annotations

import ast
import io
import signal
import threading
import traceback
from contextlib import redirect_stdout, redirect_stderr
from typing import Any, Dict, Optional

from .config import DEFAULT_TIMEOUT, MAX_TIMEOUT, MAX_OUTPUT_SIZE, ARTIFACT_STORE_URL
from .validator import validate_code
from .sandbox import create_safe_globals, load_data_science_libraries
from .helpers import create_artifact_helpers


def _timeout_handler(signum, frame):
    """Signal handler for execution timeout."""
    raise TimeoutError("Ejecución cancelada: se excedió el tiempo límite")


def _format_result(result: Any) -> Optional[str]:
    """
    Format the result of code execution for display.
    
    Handles special cases like DataFrames and arrays.
    
    Args:
        result: The result value to format
        
    Returns:
        String representation of the result, or None
    """
    if result is None:
        return None
    
    try:
        # Check for pandas types
        import pandas as pd
        import numpy as np
        
        if isinstance(result, pd.DataFrame):
            return (
                f"DataFrame({len(result)} rows, {len(result.columns)} columns):\n"
                f"{result.head(10).to_string()}"
            )
        elif isinstance(result, pd.Series):
            return (
                f"Series({len(result)} items):\n"
                f"{result.head(10).to_string()}"
            )
        elif isinstance(result, np.ndarray):
            shape_str = f"shape={result.shape}"
            content = str(result)[:1000]
            return f"ndarray({shape_str}):\n{content}"
        else:
            return repr(result)[:5000]
    except Exception:
        return str(type(result))


def _clean_traceback(tb: str) -> str:
    """
    Clean up traceback to not expose internal paths.
    
    Args:
        tb: Full traceback string
        
    Returns:
        Cleaned traceback showing only user code lines
    """
    lines = tb.split("\n")
    clean_lines = [
        line for line in lines
        if "<user_code>" in line or not line.strip().startswith("File")
    ]
    return "\n".join(clean_lines)


def execute_code_safely(
    code: str,
    timeout: int = DEFAULT_TIMEOUT,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute Python code in a restricted environment.
    
    Process:
    1. Validate code for security issues
    2. Set up restricted globals with safe builtins
    3. Load data science libraries
    4. Inject artifact store helpers
    5. Execute with timeout
    6. Capture and return output
    
    Args:
        code: Python source code to execute
        timeout: Maximum execution time in seconds
        session_id: Session ID for artifact store access
        run_id: Run ID for artifact path construction
        
    Returns:
        Dict with keys:
        - ok: bool - Whether execution succeeded
        - output: str - Captured stdout/stderr
        - result: str - Last expression value (if any)
        - error: dict - Error details (if ok=False)
    """
    # Step 1: Validate code
    is_valid, errors = validate_code(code)
    if not is_valid:
        return {
            "ok": False,
            "error": {
                "kind": "validation_error",
                "messages": errors,
            }
        }
    
    # Cap timeout
    timeout = min(max(1, timeout), MAX_TIMEOUT)
    
    # Step 2: Prepare execution environment
    safe_globals = create_safe_globals()
    
    # Step 3: Load data science libraries
    try:
        load_data_science_libraries(safe_globals)
    except ImportError as e:
        return {
            "ok": False,
            "error": {
                "kind": "import_error",
                "message": f"Error importando librerías: {e}",
            }
        }
    
    # Step 4: Add artifact store helpers
    safe_globals["ARTIFACT_STORE_URL"] = ARTIFACT_STORE_URL
    safe_globals["_session_id"] = session_id
    safe_globals["_run_id"] = run_id
    
    if session_id:
        helpers = create_artifact_helpers(session_id, run_id)
        safe_globals.update(helpers)
    
    # Step 5: Capture output
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    result_value = None
    
    _use_sigalrm = hasattr(signal, 'SIGALRM') and threading.current_thread() is threading.main_thread()

    def _do_exec():
        nonlocal result_value
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            compiled = compile(code, "<user_code>", "exec")
            exec(compiled, safe_globals)
            try:
                tree = ast.parse(code)
                if tree.body and isinstance(tree.body[-1], ast.Expr):
                    last_expr = ast.Expression(tree.body[-1].value)
                    result_value = eval(
                        compile(last_expr, "<user_code>", "eval"),
                        safe_globals
                    )
            except Exception:
                pass

    try:
        if _use_sigalrm:
            # Main thread: use SIGALRM (precise, kills the thread)
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout)
            try:
                _do_exec()
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            # Non-main thread (Cloud Run async context): run in a daemon sub-thread
            # join() returns after timeout even if thread is still running
            exec_exc: list = []

            def _target():
                try:
                    _do_exec()
                except Exception as _e:
                    exec_exc.append(_e)

            t = threading.Thread(target=_target, daemon=True)
            t.start()
            t.join(timeout=timeout)
            if t.is_alive():
                raise TimeoutError(f"Ejecución cancelada: se excedió el tiempo límite de {timeout}s")
            if exec_exc:
                raise exec_exc[0]

        # Get output
        stdout_output = stdout_capture.getvalue()
        stderr_output = stderr_capture.getvalue()

        combined_output = stdout_output
        if stderr_output:
            combined_output += f"\n[stderr]:\n{stderr_output}"

        if len(combined_output) > MAX_OUTPUT_SIZE:
            combined_output = (
                combined_output[:MAX_OUTPUT_SIZE] +
                f"\n... [output truncado, excede {MAX_OUTPUT_SIZE} bytes]"
            )

        result_str = _format_result(result_value)

        return {
            "ok": True,
            "output": combined_output,
            "result": result_str,
        }

    except TimeoutError as e:
        return {
            "ok": False,
            "output": stdout_capture.getvalue(),
            "error": {
                "kind": "timeout",
                "message": str(e),
            }
        }
    except Exception as e:
        tb = traceback.format_exc()
        clean_tb = _clean_traceback(tb)

        return {
            "ok": False,
            "output": stdout_capture.getvalue(),
            "error": {
                "kind": "execution_error",
                "type": type(e).__name__,
                "message": str(e),
                "traceback": clean_tb,
            }
        }
