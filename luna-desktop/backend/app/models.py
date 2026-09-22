"""
Luna Desktop Backend Models
Pydantic models for API requests and responses
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ModelProvider(str, Enum):
    """Available LLM providers"""
    OLLAMA = "ollama"
    OPENAI = "openai"
    GROK = "grok"
    GEMINI = "gemini"
    CLAUDE = "claude"


class ChatRequest(BaseModel):
    """Chat request model"""
    message: str = Field(..., description="User message")
    conversation_id: str = Field(default="default", description="Conversation ID")
    model: Optional[ModelProvider] = Field(default=ModelProvider.OLLAMA, description="Model to use")
    temperature: Optional[float] = Field(default=0, ge=0, le=1)
    max_tokens: Optional[int] = Field(default=512, ge=1, le=4000)
    system_prompt: Optional[str] = Field(default=None)


class ChatResponse(BaseModel):
    """Chat response model"""
    response: str
    model: ModelProvider
    tokens_used: int
    thinking: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    conversation_id: str


class Message(BaseModel):
    """Message model"""
    id: str
    role: str  # 'user', 'luna', 'system'
    content: str
    timestamp: datetime
    model: Optional[str] = None
    thinking: Optional[str] = None


class CodeAnalysisResult(BaseModel):
    """Code analysis result"""
    filename: str
    language: str
    complexity: float
    issues: List[Dict[str, Any]]
    recommendations: List[str]
    metrics: Dict[str, Any]


class SecurityScanResult(BaseModel):
    """Security scan result"""
    filename: str
    vulnerabilities: List[Dict[str, Any]]
    severity_level: str  # 'low', 'medium', 'high', 'critical'
    recommendations: List[str]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WalletInfo(BaseModel):
    """Solana wallet information"""
    address: str
    balance: float
    network: str
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class Transaction(BaseModel):
    """Blockchain transaction"""
    id: str
    from_address: str
    to_address: str
    amount: float
    status: str  # 'pending', 'confirmed', 'failed'
    timestamp: datetime
    signature: Optional[str] = None


class LunaConfig(BaseModel):
    """Luna configuration"""
    default_model: ModelProvider = ModelProvider.OLLAMA
    temperature: float = 0
    max_tokens: int = 512
    enable_memory: bool = True
    enable_blockchain: bool = True
    enable_security_scan: bool = True
    api_keys: Dict[str, str] = {}


class MemoryEntry(BaseModel):
    """Memory entry"""
    id: str
    content: str
    embedding: Optional[List[float]] = None
    timestamp: datetime
    conversation_id: str
    metadata: Dict[str, Any] = {}


class ProjectAnalysis(BaseModel):
    """Project analysis result"""
    project_path: str
    total_files: int
    total_lines: int
    languages: Dict[str, int]
    complexity_score: float
    issues: List[Dict[str, Any]]
    recommendations: List[str]
    structure: Dict[str, Any]
