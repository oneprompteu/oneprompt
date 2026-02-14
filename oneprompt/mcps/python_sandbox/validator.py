"""
Code validation and security checks using AST analysis.
"""

from __future__ import annotations

import ast
import re
from typing import List, Set, Tuple

from .config import (
    ALLOWED_IMPORTS,
    BLOCKED_IMPORTS,
    BLOCKED_BUILTINS,
    BLOCKED_ATTRIBUTES,
    DANGEROUS_PATTERNS,
)


class SecurityError(Exception):
    """Raised when code violates security policies."""
    pass


class CodeValidator(ast.NodeVisitor):
    """
    AST visitor that checks for security violations.
    
    Validates:
    - Import statements (whitelist/blacklist)
    - Function calls (blocked builtins)
    - Attribute access (dangerous dunder attributes)
    """
    
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.imports: Set[str] = set()
    
    def visit_Import(self, node: ast.Import) -> None:
        """Check direct imports: import os, import subprocess"""
        for alias in node.names:
            module = alias.name.split(".")[0]
            self.imports.add(module)
            self._check_module(module, alias.name)
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Check from imports: from os import system"""
        if node.module:
            module = node.module.split(".")[0]
            self.imports.add(module)
            self._check_module(module, node.module)
        self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call) -> None:
        """Check function calls for blocked builtins."""
        # Direct function call: eval(), exec()
        if isinstance(node.func, ast.Name):
            if node.func.id in BLOCKED_BUILTINS:
                self.errors.append(
                    f"Función bloqueada: '{node.func.id}()' no está permitida por seguridad"
                )
        
        # Method call: obj.__class__.__subclasses__()
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in BLOCKED_ATTRIBUTES:
                self.errors.append(
                    f"Acceso bloqueado: '.{node.func.attr}' no está permitido por seguridad"
                )
        
        self.generic_visit(node)
    
    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Check attribute access for dangerous patterns."""
        if node.attr in BLOCKED_ATTRIBUTES:
            self.errors.append(
                f"Acceso bloqueado: '.{node.attr}' no está permitido por seguridad"
            )
        self.generic_visit(node)
    
    def _check_module(self, module: str, full_name: str) -> None:
        """Validate a module import."""
        if module in BLOCKED_IMPORTS:
            self.errors.append(
                f"Import bloqueado: '{module}' no está permitido por seguridad"
            )
        elif module not in ALLOWED_IMPORTS and not self._is_submodule_allowed(full_name):
            self.errors.append(
                f"Import no permitido: '{module}'. Solo se permiten librerías de análisis de datos."
            )
    
    def _is_submodule_allowed(self, full_module: str) -> bool:
        """Check if a submodule belongs to an allowed top-level module."""
        parts = full_module.split(".")
        return parts[0] in ALLOWED_IMPORTS


def _check_dangerous_patterns(code: str) -> List[str]:
    """
    Check for dangerous patterns using regex.
    
    This is a defense-in-depth measure to catch patterns
    that might slip through AST analysis.
    """
    errors = []
    for pattern, message in DANGEROUS_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            errors.append(message)
    return errors


def validate_code(code: str) -> Tuple[bool, List[str]]:
    """
    Validate Python code for security issues.
    
    Performs:
    1. Syntax check (parsing)
    2. AST-based security validation
    3. Regex-based pattern matching (defense in depth)
    
    Args:
        code: Python source code to validate
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors: List[str] = []
    
    # Step 1: Parse the code
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, [f"Error de sintaxis en línea {e.lineno}: {e.msg}"]
    
    # Step 2: Run AST validation
    validator = CodeValidator()
    validator.visit(tree)
    errors.extend(validator.errors)
    
    # Step 3: Additional string-based checks (defense in depth)
    errors.extend(_check_dangerous_patterns(code))
    
    return len(errors) == 0, errors
