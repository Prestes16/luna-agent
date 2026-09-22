"""Luna Desktop Backend App Package"""

# Apply runtime reasoning hardening before luna_engine imports the helpers.
# Stages 1-5 provide command parsing, factual validation, command fidelity,
# quantitative scoring and critical target/tool vetoes.  Stage 6 reconciles
# canonical paths/commands across every stage so parser artifacts cannot create
# false hallucination signals or bypass the final quality gate.
from . import reasoning_pipeline as _reasoning_pipeline
from . import reasoning_quality as _reasoning_quality
from . import reasoning_runtime_patch as _stage1
from . import reasoning_runtime_patch_v3 as _stage3
from . import reasoning_runtime_patch_v5 as _stage5
from .reasoning_runtime_patch_v6 import (
    action_fingerprint as _patched_action_fingerprint,
    build_replan_instruction as _patched_build_replan_instruction,
    extract_commands as _patched_extract_commands,
    validate_model_response as _patched_validate_model_response,
)

# Canonical parser functions must also replace module-local bindings captured by
# earlier compatibility stages.  Their validators resolve these globals at call
# time, so this keeps the entire chain consistent without duplicating logic.
_stage1.extract_commands = _patched_extract_commands
_stage1.action_fingerprint = _patched_action_fingerprint
_stage3.extract_commands = _patched_extract_commands
_stage5.extract_commands = _patched_extract_commands
_reasoning_quality.extract_commands = _patched_extract_commands

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