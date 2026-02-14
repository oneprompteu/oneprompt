"""
Helper functions for artifact store communication.

These functions are injected into the execution namespace
to allow code to read/write data from the artifact store.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

from .config import ARTIFACT_STORE_URL, ARTIFACT_STORE_TOKEN


def create_artifact_helpers(session_id: str | None, run_id: str | None = None) -> Dict[str, Callable[..., Any]]:
    """
    Create artifact store helper functions bound to a specific session and run.
    
    Args:
        session_id: The session ID for artifact store requests
        run_id: The run ID for constructing output paths
        
    Returns:
        Dictionary of helper functions to inject into the execution namespace
    """
    # Import here to avoid circular imports and allow lazy loading
    import requests
    import json as json_module
    import io as io_module
    import pandas as pd
    
    def _build_canonical_path(path: str, artifact_type: str = "results") -> str:
        """
        Build a canonical artifact path.
        
        If path already contains runs/{run_id}/, use it as-is.
        Otherwise, prefix with runs/{run_id}/{artifact_type}/
        """
        if not run_id:
            return path.lstrip("/")
        
        # Check if path already has the canonical structure
        if path.startswith(f"runs/{run_id}/") or path.startswith("runs/"):
            return path.lstrip("/")
        
        # Add canonical prefix
        clean_path = path.lstrip("/")
        return f"runs/{run_id}/{artifact_type}/{clean_path}"
    
    def fetch_artifact(path: str) -> bytes:
        """
        Fetch artifact data from the artifact store.
        
        Args:
            path: Relative path to the artifact (e.g., "runs/{run_id}/data/file.csv")
            
        Returns:
            Raw bytes content of the artifact
            
        Raises:
            RuntimeError: If artifact store is not configured
            requests.HTTPError: If the request fails
        """
        if not ARTIFACT_STORE_URL:
            raise RuntimeError("ARTIFACT_STORE_URL not configured")
        if not session_id:
            raise RuntimeError("No session_id available")
        
        # Don't modify path for fetch - use as provided
        clean_path = path.lstrip("/")
        url = f"{ARTIFACT_STORE_URL.rstrip('/')}/artifacts/{session_id}/{clean_path}"
        headers: Dict[str, str] = {}
        if ARTIFACT_STORE_TOKEN:
            headers["Authorization"] = f"Bearer {ARTIFACT_STORE_TOKEN}"
        
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.content
    
    def fetch_artifact_json(path: str) -> Any:
        """
        Fetch JSON artifact from the artifact store.
        
        Args:
            path: Relative path to the JSON artifact
            
        Returns:
            Parsed JSON data (dict or list)
        """
        data = fetch_artifact(path)
        return json_module.loads(data)
    
    def fetch_artifact_csv(path: str, **kwargs) -> "pd.DataFrame":
        """
        Fetch CSV artifact as a pandas DataFrame.
        
        Args:
            path: Relative path to the CSV artifact
            **kwargs: Additional arguments passed to pd.read_csv
            
        Returns:
            pandas DataFrame with the CSV data
        """
        data = fetch_artifact(path)
        return pd.read_csv(io_module.BytesIO(data), **kwargs)
    
    def upload_artifact(
        path: str,
        data: bytes,
        content_type: str = "application/octet-stream"
    ) -> Dict[str, Any]:
        """
        Upload data to the artifact store.
        
        Args:
            path: Relative path for the artifact (will be prefixed with runs/{run_id}/results/)
            data: Raw bytes to upload
            content_type: MIME type of the data
            
        Returns:
            Response from artifact store (typically includes URL and path)
        """
        if not ARTIFACT_STORE_URL:
            raise RuntimeError("ARTIFACT_STORE_URL not configured")
        if not session_id:
            raise RuntimeError("No session_id available")
        if not run_id:
            raise RuntimeError("No run_id available - cannot determine artifact path")
        
        # Build canonical path: runs/{run_id}/results/{filename}
        canonical_path = _build_canonical_path(path, artifact_type="results")
        url = f"{ARTIFACT_STORE_URL.rstrip('/')}/artifacts/{session_id}/{canonical_path}?upload=true"
        headers: Dict[str, str] = {"Content-Type": content_type}
        if ARTIFACT_STORE_TOKEN:
            headers["Authorization"] = f"Bearer {ARTIFACT_STORE_TOKEN}"
        
        resp = requests.post(url, data=data, headers=headers, timeout=60)
        resp.raise_for_status()
        result = resp.json()
        
        # Enrich response with canonical path info
        if isinstance(result, dict):
            result["canonical_path"] = canonical_path
            result["session_id"] = session_id
            result["run_id"] = run_id
        
        return result
    
    def upload_dataframe(
        path: str,
        df: "pd.DataFrame",
        format: str = "csv"
    ) -> Dict[str, Any]:
        """
        Upload a DataFrame to the artifact store.
        
        Args:
            path: Relative path for the artifact (will be placed in runs/{run_id}/results/)
            df: pandas DataFrame to upload
            format: Output format ("csv" or "json")
            
        Returns:
            Response from artifact store with artifact info
            
        Raises:
            ValueError: If format is not supported
        """
        if format == "csv":
            data = df.to_csv(index=False).encode("utf-8")
            content_type = "text/csv"
        elif format == "json":
            data = df.to_json(orient="records", date_format="iso").encode("utf-8")
            content_type = "application/json"
        else:
            raise ValueError(f"Unsupported format: {format}. Use 'csv' or 'json'.")
        
        return upload_artifact(path, data, content_type)
    
    return {
        "fetch_artifact": fetch_artifact,
        "fetch_artifact_json": fetch_artifact_json,
        "fetch_artifact_csv": fetch_artifact_csv,
        "upload_artifact": upload_artifact,
        "upload_dataframe": upload_dataframe,
        "_build_canonical_path": _build_canonical_path,
        "_session_id": session_id,
        "_run_id": run_id,
    }
