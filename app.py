"""Uvicorn entry point for the complete Aether Engine REST API."""

from aether_engine.server import app, my_custom_logic

__all__ = ["app", "my_custom_logic"]
