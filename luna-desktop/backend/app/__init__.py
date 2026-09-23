"""Luna Desktop Backend App Package"""

# Apply runtime reasoning hardening before luna_engine imports the helpers.
# Stages 1-5 provide command parsing, factual validation, command fidelity,
# quantitative scoring and critical target/tool vetoes. Stage 6 reconciles
# canonical paths/commands across every stage; stage 7 adds strategy-aware
# validation; stage 8 defines operational policy; stage 9 deterministically
# repairs mechanically fixable operator-readiness gaps before display; stage 10
# handles factual tool prerequisites; stage 11 adds privacy-routing truthfulness
# and transport-compatibility guards; stage 12 enforces command lifecycle
# sequencing and explicit destructive intent; stage 13 adds malware-specimen
# isolation and ransomware-recovery calibration guards; stage 14 adds fail-closed
# operator host-integrity checks for dangerous or high-impact commands; stage 15
# enforces correct local privacy prerequisite discovery before remote validation;
# stage 16 calibrates strong cyber conclusions against explicit construction/mechanism evidence;
# stage 17 calibrates quantitative and physical conclusions against math/measurement evidence;
# stage 18 enforces exact integer-arithmetic semantics and bounded rounding claims.
from . import reasoning_pipeline as _reasoning_pipeline
from . import reasoning_quality as _reasoning_quality
from . import reasoning_runtime_patch as _stage1
from . import reasoning_runtime_patch_v3 as _stage3
from . import reasoning_runtime_patch_v5 as _stage5
from . import reasoning_runtime_patch_v6 as _stage6
from . import reasoning_runtime_patch_v7 as _stage7
from . import reasoning_runtime_patch_v8 as _stage8
from . import reasoning_runtime_patch_v9 as _stage9
from . import reasoning_runtime_patch_v10 as _stage10
from . import reasoning_runtime_patch_v11 as _stage11
from . import reasoning_runtime_patch_v12 as _stage12
from . import reasoning_runtime_patch_v13 as _stage13
from . import reasoning_runtime_patch_v14 as _stage14
from . import reasoning_runtime_patch_v15 as _stage15
from . import reasoning_runtime_patch_v16 as _stage16
from . import reasoning_runtime_patch_v17 as _stage17
from . import reasoning_runtime_patch_v18 as _stage18
from .command_policy import effective_tool as _effective_tool
from .command_policy import parse_effective_command as _parse_effective_command
from .reasoning_runtime_patch_v6 import action_fingerprint as _patched_action_fingerprint
from .reasoning_runtime_patch_v8 import extract_commands as _patched_extract_commands
from .reasoning_runtime_patch_v18 import (
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
