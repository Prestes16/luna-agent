"""
Advanced Code Analyzer Service
Analyzes code for complexity, security, and optimization opportunities
"""

import os
import re
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class CodeAnalyzer:
    """Advanced code analysis service"""
    
    def __init__(self):
        """Initialize code analyzer"""
        self.supported_languages = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.go': 'go',
            '.rs': 'rust'
        }
        logger.info("✅ Code Analyzer initialized")
    
    async def analyze(self, content: str, filename: str) -> Dict[str, Any]:
        """Analyze a code file"""
        
        logger.info(f"Analyzing file: {filename}")
        
        # Detect language
        ext = Path(filename).suffix
        language = self.supported_languages.get(ext, 'unknown')
        
        # Calculate metrics
        metrics = self._calculate_metrics(content, language)
        
        # Find issues
        issues = self._find_issues(content, language)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(metrics, issues, language)
        
        return {
            "filename": filename,
            "language": language,
            "complexity": metrics["complexity_score"],
            "lines_of_code": metrics["lines_of_code"],
            "functions": metrics["functions"],
            "classes": metrics["classes"],
            "issues": issues,
            "recommendations": recommendations,
            "metrics": metrics
        }
    
    async def analyze_project(self, path: str) -> Dict[str, Any]:
        """Analyze entire project directory"""
        
        logger.info(f"Analyzing project: {path}")
        
        project_path = Path(path)
        if not project_path.exists():
            return {"error": f"Path not found: {path}"}
        
        files = []
        total_lines = 0
        languages_count: Dict[str, int] = {}
        total_issues = []
        
        # Scan all files
        for file_path in project_path.rglob("*"):
            if file_path.is_file():
                ext = file_path.suffix
                if ext in self.supported_languages:
                    try:
                        content = file_path.read_text()
                        total_lines += len(content.split('\n'))
                        
                        language = self.supported_languages[ext]
                        languages_count[language] = languages_count.get(language, 0) + 1
                        
                        analysis = await self.analyze(content, file_path.name)
                        files.append(analysis)
                        total_issues.extend(analysis.get("issues", []))
                    
                    except Exception as e:
                        logger.error(f"Error analyzing {file_path}: {e}")
        
        # Calculate overall complexity
        complexity_scores = [f.get("complexity", 0) for f in files]
        avg_complexity = sum(complexity_scores) / len(complexity_scores) if complexity_scores else 0
        
        return {
            "project_path": path,
            "total_files": len(files),
            "total_lines": total_lines,
            "languages": languages_count,
            "complexity_score": avg_complexity,
            "issues": total_issues[:20],  # Top 20 issues
            "recommendations": self._generate_project_recommendations(files, total_issues),
            "structure": self._analyze_structure(project_path)
        }
    
    def _calculate_metrics(self, content: str, language: str) -> Dict[str, Any]:
        """Calculate code metrics"""
        
        lines = content.split('\n')
        non_empty_lines = [l for l in lines if l.strip()]
        
        # Count functions and classes
        if language == 'python':
            functions = len(re.findall(r'^\s*def\s+\w+', content, re.MULTILINE))
            classes = len(re.findall(r'^\s*class\s+\w+', content, re.MULTILINE))
        elif language in ['javascript', 'typescript']:
            functions = len(re.findall(r'function\s+\w+|const\s+\w+\s*=\s*\(', content))
            classes = len(re.findall(r'class\s+\w+', content))
        else:
            functions = len(re.findall(r'def\s+\w+|function\s+\w+', content))
            classes = len(re.findall(r'class\s+\w+', content))
        
        # Calculate complexity (cyclomatic complexity estimate)
        complexity = self._estimate_complexity(content)
        
        return {
            "lines_of_code": len(non_empty_lines),
            "total_lines": len(lines),
            "functions": functions,
            "classes": classes,
            "complexity_score": complexity,
            "avg_function_length": len(non_empty_lines) / max(functions, 1),
            "comment_ratio": self._calculate_comment_ratio(content)
        }
    
    def _estimate_complexity(self, content: str) -> float:
        """Estimate cyclomatic complexity"""
        
        # Count control flow statements
        if_count = len(re.findall(r'\bif\b', content, re.IGNORECASE))
        for_count = len(re.findall(r'\bfor\b', content, re.IGNORECASE))
        while_count = len(re.findall(r'\bwhile\b', content, re.IGNORECASE))
        case_count = len(re.findall(r'\bcase\b', content, re.IGNORECASE))
        
        complexity = 1 + if_count + for_count + while_count + (case_count / 2)
        return min(complexity / 10, 10.0)  # Normalize to 0-10 scale
    
    def _calculate_comment_ratio(self, content: str) -> float:
        """Calculate comment to code ratio"""
        
        lines = content.split('\n')
        comment_lines = sum(1 for l in lines if l.strip().startswith('#') or l.strip().startswith('//'))
        code_lines = len([l for l in lines if l.strip() and not l.strip().startswith('#')])
        
        return comment_lines / max(code_lines, 1)
    
    def _find_issues(self, content: str, language: str) -> List[Dict[str, Any]]:
        """Find potential issues in code"""
        
        issues = []
        
        # Check for common issues
        if 'TODO' in content or 'FIXME' in content:
            issues.append({
                "title": "Unfinished code",
                "description": "Found TODO or FIXME comments",
                "severity": "low"
            })
        
        if re.search(r'eval\s*\(', content):
            issues.append({
                "title": "Dangerous eval() usage",
                "description": "Using eval() can be a security risk",
                "severity": "high"
            })
        
        if re.search(r'password|secret|api.?key', content, re.IGNORECASE):
            issues.append({
                "title": "Hardcoded secrets",
                "description": "Found potential hardcoded passwords or API keys",
                "severity": "critical"
            })
        
        if re.search(r'except\s*:', content):
            issues.append({
                "title": "Bare except clause",
                "description": "Using bare except: can hide errors",
                "severity": "medium"
            })
        
        if len(content) > 10000 and language == 'python':
            issues.append({
                "title": "Large file",
                "description": "File is quite large, consider breaking it into smaller modules",
                "severity": "low"
            })
        
        return issues
    
    def _generate_recommendations(
        self,
        metrics: Dict[str, Any],
        issues: List[Dict[str, Any]],
        language: str
    ) -> List[str]:
        """Generate recommendations"""
        
        recommendations = []
        
        if metrics["complexity_score"] > 7:
            recommendations.append("Consider refactoring to reduce complexity")
        
        if metrics["avg_function_length"] > 50:
            recommendations.append("Some functions are too long, consider breaking them down")
        
        if metrics["comment_ratio"] < 0.1:
            recommendations.append("Add more comments to explain complex logic")
        
        if any(i["severity"] == "critical" for i in issues):
            recommendations.append("Fix critical security issues immediately")
        
        if language == 'python':
            recommendations.append("Consider adding type hints for better code clarity")
        
        return recommendations
    
    def _generate_project_recommendations(
        self,
        files: List[Dict[str, Any]],
        issues: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate project-wide recommendations"""
        
        recommendations = []
        
        if not files:
            return ["No code files found in project"]
        
        avg_complexity = sum(f.get("complexity", 0) for f in files) / len(files)
        if avg_complexity > 6:
            recommendations.append("Overall project complexity is high, consider refactoring")
        
        critical_issues = [i for i in issues if i.get("severity") == "critical"]
        if critical_issues:
            recommendations.append(f"Fix {len(critical_issues)} critical security issues")
        
        recommendations.append("Add comprehensive unit tests")
        recommendations.append("Set up continuous integration/deployment")
        
        return recommendations
    
    def _analyze_structure(self, path: Path) -> Dict[str, Any]:
        """Analyze project structure"""
        
        structure = {}
        
        for item in path.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                structure[item.name] = {
                    "type": "directory",
                    "files": len(list(item.glob("*")))
                }
            elif item.is_file() and not item.name.startswith('.'):
                structure[item.name] = {
                    "type": "file",
                    "size": item.stat().st_size
                }
        
        return structure
