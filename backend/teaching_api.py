"""FastAPI routes for the M5 teaching core."""

from typing import Any

from fastapi import APIRouter

try:
    from .teaching import (
        explain_model_graph,
        get_error_suggestion,
        get_layer_teaching,
        get_parameter_teaching,
        get_teaching_catalog,
        list_supported_layers,
    )
    from .teaching_schemas import ErrorSuggestionRequest, ModelExplanationRequest
except ImportError:  # pragma: no cover - supports direct module execution.
    from teaching import (
        explain_model_graph,
        get_error_suggestion,
        get_layer_teaching,
        get_parameter_teaching,
        get_teaching_catalog,
        list_supported_layers,
    )
    from teaching_schemas import ErrorSuggestionRequest, ModelExplanationRequest


router = APIRouter(prefix="/teaching", tags=["teaching"])


@router.get("/layers", response_model=dict[str, list[str]])
def get_supported_layers() -> dict[str, list[str]]:
    return {"layers": list_supported_layers()}


@router.get("/layers/{layer_type}/parameters/{parameter}", response_model=dict[str, Any])
def explain_parameter(layer_type: str, parameter: str) -> dict[str, Any]:
    return get_parameter_teaching(layer_type, parameter)


@router.get("/layers/{layer_type}", response_model=dict[str, Any])
def explain_layer(layer_type: str) -> dict[str, Any]:
    return get_layer_teaching(layer_type)


@router.get("/catalog", response_model=dict[str, Any])
def get_catalog() -> dict[str, Any]:
    return get_teaching_catalog()


@router.post("/errors/explain", response_model=dict[str, Any])
def explain_error(request: ErrorSuggestionRequest) -> dict[str, Any]:
    return get_error_suggestion(request.error_message, request.context)


@router.post("/models/explain", response_model=dict[str, Any])
def explain_model(request: ModelExplanationRequest) -> dict[str, Any]:
    return explain_model_graph(request.model_graph)
