"""Request models for the M5 teaching API."""

from typing import Any

from pydantic import BaseModel


class ModelExplanationRequest(BaseModel):
    """Carry a model graph to the teaching core without validating its contents."""

    model_graph: dict[str, Any]


class ErrorSuggestionRequest(BaseModel):
    """Carry an error and optional structured context to the teaching core."""

    error_message: Any
    context: Any = None
