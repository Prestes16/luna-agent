"""
Security Scanner Service
Identifies security vulnerabilities and compliance issues
"""

import re
import logging
from typing import Dict, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class SecurityScanner:
    """Security scanning service"""
    
    def __init__(self):
        """Initialize security scanner"""
        self.vulnerability_patterns = self._load_patterns()
        logger.info("✅ Security Scanner initialized")
    
    def _load_patterns(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load vulnerability patterns"""
        return {
            "sql_injection": [
                {
                    "pattern": r"execute\s*\(\s*['\"].*\+.*['\"]",
                    "description": "Potential SQL injection vulnerability",
                    "severity": "critical"
                }
            ],
            "xss": [
                {
                    "pattern": r"innerHTML\s*=|dangerouslySetInnerHTML",
                    "description": "Potential XSS vulnerability",
                    "severity": "high"
                }
            ],
            "hardcoded_secrets": [
                {
                    "pattern": r"(password|secret|api.?key|token)\s*[=:]\s*['\"]",
                    "description": "Hardcoded secret found",
                    "severity": "critical"
                }
            ],
            "insecure_crypto": [
                {
                    "pattern": r"md5|sha1|des",
                    "description": "Weak cryptographic algorithm",
                    "severity": "high"
                }
            ],
            "command_injection": [
                {
                    "pattern": r"exec\s*\(|system\s*\(|subprocess\s*\(",
                    "description": "Potential command injection",
                    "severity": "high"
                }
            ]
        }
    
    async def scan(self, content: str, filename: str) -> Dict[str, Any]:
        """Scan file for security vulnerabilities"""
        
        logger.info(f"Scanning file: {filename}")
        
        vulnerabilities = []
        
        # Scan for patterns
        for category, patterns in self.vulnerability_patterns.items():
            for pattern_info in patterns:
                matches = re.finditer(pattern_info["pattern"], content, re.IGNORECASE)
                for match in matches:
                    line_num = content[:match.start()].count('\n') + 1
                    vulnerabilities.append({
                        "category": category,
                        "title": pattern_info["description"],
                        "severity": pattern_info["severity"],
                        "line": line_num,
                        "match": match.group(0)[:50]
                    })
        
        # Determine overall severity
        if vulnerabilities:
            severities = [v["severity"] for v in vulnerabilities]
            if "critical" in severities:
                severity_level = "critical"
            elif "high" in severities:
                severity_level = "high"
            elif "medium" in severities:
                severity_level = "medium"
            else:
                severity_level = "low"
        else:
            severity_level = "none"
        
        # Generate recommendations
        recommendations = self._generate_recommendations(vulnerabilities)
        
        return {
            "filename": filename,
            "vulnerabilities": vulnerabilities,
            "severity_level": severity_level,
            "recommendations": recommendations,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def _generate_recommendations(self, vulnerabilities: List[Dict[str, Any]]) -> List[str]:
        """Generate security recommendations"""
        
        recommendations = []
        
        if not vulnerabilities:
            recommendations.append("✓ No vulnerabilities found")
            return recommendations
        
        categories = set(v["category"] for v in vulnerabilities)
        
        if "sql_injection" in categories:
            recommendations.append("Use parameterized queries or prepared statements")
        
        if "xss" in categories:
            recommendations.append("Sanitize user input and use safe DOM methods")
        
        if "hardcoded_secrets" in categories:
            recommendations.append("Move secrets to environment variables or secure vaults")
        
        if "insecure_crypto" in categories:
            recommendations.append("Use modern cryptographic algorithms (SHA-256, AES-256)")
        
        if "command_injection" in categories:
            recommendations.append("Avoid using shell commands, use safe APIs instead")
        
        recommendations.append("Enable security linting in your development pipeline")
        recommendations.append("Regular security audits and penetration testing")
        
        return recommendations
    
    async def get_status(self) -> Dict[str, Any]:
        """Get scanner status"""
        
        return {
            "status": "active",
            "patterns_loaded": sum(len(p) for p in self.vulnerability_patterns.values()),
            "categories": list(self.vulnerability_patterns.keys()),
            "last_updated": datetime.utcnow().isoformat()
        }
