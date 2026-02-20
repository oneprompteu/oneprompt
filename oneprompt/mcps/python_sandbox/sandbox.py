"""
Safe builtins and globals for code execution.
"""

from __future__ import annotations

from typing import Any, Dict


def create_safe_builtins() -> Dict[str, Any]:
    """
    Create a restricted set of built-in functions.
    
    Only includes safe functions that cannot be used
    for code injection or system access.
    
    Returns:
        Dictionary of safe built-ins
    """
    return {
        # Constants
        "True": True,
        "False": False,
        "None": None,
        
        # Math/numeric functions
        "abs": abs,
        "bin": bin,
        "bool": bool,
        "complex": complex,
        "divmod": divmod,
        "float": float,
        "hex": hex,
        "int": int,
        "oct": oct,
        "pow": pow,
        "round": round,
        
        # Sequence/iteration functions
        "all": all,
        "any": any,
        "enumerate": enumerate,
        "filter": filter,
        "iter": iter,
        "len": len,
        "map": map,
        "max": max,
        "min": min,
        "next": next,
        "range": range,
        "reversed": reversed,
        "sorted": sorted,
        "sum": sum,
        "zip": zip,
        
        # Type constructors
        "bytes": bytes,
        "dict": dict,
        "frozenset": frozenset,
        "list": list,
        "object": object,
        "set": set,
        "slice": slice,
        "str": str,
        "tuple": tuple,
        
        # Type checking
        "callable": callable,
        "isinstance": isinstance,
        "issubclass": issubclass,
        "type": type,
        
        # String/repr functions
        "ascii": ascii,
        "chr": chr,
        "format": format,
        "hash": hash,
        "id": id,
        "ord": ord,
        "repr": repr,
        
        # Output
        "print": print,
        
        # Exception types (for error handling)
        "Exception": Exception,
        "BaseException": BaseException,
        "ValueError": ValueError,
        "TypeError": TypeError,
        "KeyError": KeyError,
        "IndexError": IndexError,
        "AttributeError": AttributeError,
        "RuntimeError": RuntimeError,
        "ZeroDivisionError": ZeroDivisionError,
        "StopIteration": StopIteration,
        "FileNotFoundError": FileNotFoundError,
        "ImportError": ImportError,
        "ModuleNotFoundError": ModuleNotFoundError,
        "NameError": NameError,
        "OverflowError": OverflowError,
        "RecursionError": RecursionError,
        "NotImplementedError": NotImplementedError,
        "AssertionError": AssertionError,
    }


def create_safe_globals() -> Dict[str, Any]:
    """
    Create a restricted globals dict for code execution.
    
    Returns:
        Dictionary with safe builtins and minimal namespace
    """
    return {
        "__builtins__": create_safe_builtins(),
        "__name__": "__main__",
        "__doc__": None,
    }


def load_data_science_libraries(namespace: Dict[str, Any]) -> None:
    """
    Load data science libraries into the execution namespace.
    
    Imports libraries and adds them with their common aliases.
    
    Args:
        namespace: The globals dict to populate
    """
    # Core data science
    import numpy as np
    import pandas as pd
    namespace.update({
        "np": np,
        "numpy": np,
        "pd": pd,
        "pandas": pd,
    })
    
    # Standard library utilities
    import json
    import math
    import statistics
    import datetime as dt_module
    import re as re_module
    import collections
    import itertools
    import functools
    import copy
    import base64
    import hashlib
    import uuid as uuid_module
    import io as io_module
    import csv as csv_module
    import random
    import decimal
    
    namespace.update({
        "json": json,
        "math": math,
        "statistics": statistics,
        "datetime": dt_module,
        "date": dt_module.date,
        "timedelta": dt_module.timedelta,
        "re": re_module,
        "collections": collections,
        "Counter": collections.Counter,
        "defaultdict": collections.defaultdict,
        "OrderedDict": collections.OrderedDict,
        "itertools": itertools,
        "functools": functools,
        "copy": copy,
        "deepcopy": copy.deepcopy,
        "base64": base64,
        "hashlib": hashlib,
        "uuid": uuid_module,
        "io": io_module,
        "StringIO": io_module.StringIO,
        "BytesIO": io_module.BytesIO,
        "csv": csv_module,
        "random": random,
        "Decimal": decimal.Decimal,
    })
    
    # Optional: scipy
    try:
        import scipy
        from scipy import stats as scipy_stats
        namespace.update({
            "scipy": scipy,
            "scipy_stats": scipy_stats,
        })
    except ImportError:
        pass
    
    # Optional: scikit-learn
    try:
        import sklearn
        from sklearn import (
            preprocessing,
            cluster,
            linear_model,
            tree,
            ensemble,
            metrics,
            model_selection,
        )
        namespace.update({
            "sklearn": sklearn,
            "preprocessing": preprocessing,
            "cluster": cluster,
            "linear_model": linear_model,
            "tree": tree,
            "ensemble": ensemble,
            "metrics": metrics,
            "model_selection": model_selection,
            "train_test_split": model_selection.train_test_split,
        })
    except ImportError:
        pass
    
    # Optional: statsmodels
    try:
        import statsmodels
        import statsmodels.api as sm
        namespace.update({
            "statsmodels": statsmodels,
            "sm": sm,
        })
    except ImportError:
        pass
