"""Luna Desktop Backend App Package"""

# Apply runtime reasoning hardening before luna_engine imports the helpers.
# Stages 1-5 provide command parsing, factual validation, command fidelity,
# quantitative scoring and critical target/tool vetoes. Stage 6 reconciles
# canonical paths/commands across every stage; stage 7 adds strategy-aware
# validation; stage 8 defines operational policy; stage 9 deterministically
# repairs mechanically fixable operator-readiness gaps before display.
from . import reasoning_pipeline as _reasoning_pipeline
from . import reasoning_quality as _reasoning_quality
from . import reasoning_runtime_patch as _stage1
from . import reasoning_runtime_patch_v3 as _stage3
from . import reasoning_runtime_patch_v5 as _stage5
from . import reasoning_runtime_patch_v6 as _stage6
from . import reasoning_runtime_patch_v7 as _stage7
from . import reasoning_runtime_patch_v8 as _stage8
from . import reasoning_runtime_patch_v9 as _stage9
from .command_policy import effective_tool as _effective_tool
from .command_policy import parse_effective_command as _parse_effective_command
from .reasoning_runtime_patch_v6 import action_fingerprint as _patched_action_fingerprint
from .reasoning_runtime_patch_v8 import extract_commands as _patched_extract_commands
from .reasoning_runtime_patch_v9 import (
    build_replan_instruction as _patched_build_replan_instruction,
    validate_model_response as _patched_validate_model_response,
)

# Canonical parser functions replace module-local bindings captured by earlier
# compatibility stages. Validators resolve these globals at call time, keeping
# the complete chain consistent without duplicating parsing logic.
_stage1.extract_commands = _patched_extract_commands
_stage1.action_fingerprint = _patched_action_fingerprint
_stage3.extract_commands = _patched_extract_commands
_stage5.extract_commands = _patched_extract_commands
_stage6.extract_commands = _patched_extract_commands
_stage7.extract_commands = _patched_extract_commands
_stage8.extract_commands = _patched_extract_commands
_reasoning_quality.extract_commands = _patched_extract_commands

# sudo is a policy wrapper, not a different technical tool. Earlier quality,
# critical-veto and strategy stages must evaluate the effective executable.
_stage5._command_tool = _effective_tool
_reasoning_quality._command_tool = _effective_tool
_stage7.parse_command = _parse_effective_command

_reasoning_pipeline.extract_commands = _patched_extract_commands
_reasoning_pipeline.action_fingerprint = _patched_action_fingerprint
_reasoning_pipeline.validate_model_response = _patched_validate_model_response
_reasoning_pipeline.build_replan_instruction = _patched_build_replan_instruction

from .luna_engine import LunaEngine
from .response_attestation import install_response_attestation

# Add UI-safe Q/target/SHA-256 metadata and apply V9 operator-ready transforms.
install_response_attestation(LunaEngine)

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
