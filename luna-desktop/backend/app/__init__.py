"""Luna Desktop Backend App Package"""

# Apply the runtime reasoning hardening before luna_engine imports the helpers.
# This keeps ScenarioContext + validator behavior consistent in the active app
# while the compatibility patch is exercised against the real local Ollama flow.
from . import reasoning_pipeline as _reasoning_pipeline
from .reasoning_runtime_patch import (
    action_fingerprint as _patched_action_fingerprint,
    build_replan_instruction as _patched_build_replan_instruction,
    extract_commands as _patched_extract_commands,
    validate_model_response as _patched_validate_model_response,
)

_reasoning_pipeline.extract_commands = _patched_extract_commands
_reasoning_pipeline.action_fingerprint = _patched_action_fingerprint
_reasoning_pipeline.validate_model_response = _patched_validate_model_response
_reasoning_pipeline.build_replan_instruction = _patched_build_replan_instruction

from .luna_engine import LunaEngine
from .models import (
    ChatRequest,
    ChatResponse,
    ModelProvider,
    CodeAnalysisResult,
    SecurityScanResult,
    WalletInfo,
    Transaction,
    LunaConfig
)

__all__ = [
    "LunaEngine",
    "ChatRequest",
    "ChatResponse",
    "ModelProvider",
    "CodeAnalysisResult",
    "SecurityScanResult",
    "WalletInfo",
    "Transaction",
    "LunaConfig"
]
