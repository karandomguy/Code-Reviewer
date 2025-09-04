import os
import re
import ast
from typing import Dict, List, Optional, Set
from abc import ABC, abstractmethod
from dotenv import load_dotenv
from groq import AsyncGroq
from app.utils.logging import logger

# Load environment variables
load_dotenv()

class BaseAnalyzer(ABC):
    """Enhanced base class for all code analyzers."""
    
    def __init__(self):
        groq_api_key = os.getenv('GROQ_API_KEY')
        self.client = AsyncGroq(api_key=groq_api_key)
        # Use the most capable model available
        self.model = "llama-3.3-70b-versatile" 
        
        # Language mappings - more comprehensive
        self.language_families = {
            'c-like': ['c', 'cpp', 'csharp', 'java', 'javascript', 'typescript', 'go', 'rust', 'kotlin', 'scala', 'swift'],
            'python-like': ['python'],
            'web': ['html', 'css', 'scss', 'javascript', 'typescript', 'react', 'react-typescript'],
            'functional': ['scala', 'kotlin', 'swift'],
            'systems': ['c', 'cpp', 'rust', 'go'],
            'jvm': ['java', 'kotlin', 'scala'],
            'scripting': ['python', 'ruby', 'php', 'bash'],
            'compiled': ['c', 'cpp', 'rust', 'go', 'java', 'csharp', 'swift', 'kotlin', 'scala']
        }
        
        # Comprehensive language support
        self.supported_languages = {
            'python', 'javascript', 'typescript', 'java', 'go', 'rust', 'cpp', 'c', 
            'csharp', 'php', 'ruby', 'swift', 'kotlin', 'scala', 'sql', 'bash',
            'react', 'react-typescript'
        }
    
    def should_analyze_file(self, file_data: Dict) -> bool:
        """Determine if file should be analyzed based on language and content."""
        language = file_data.get("language", "text")
        filename = file_data.get("filename", "")
        
        # Skip non-code files
        skip_languages = {"text", "markdown", "json", "yaml", "xml"}
        if language in skip_languages:
            return False
            
        # Skip certain file types
        skip_extensions = {".md", ".txt", ".json", ".yaml", ".yml", ".xml", ".lock", ".gitignore"}
        if any(filename.lower().endswith(ext) for ext in skip_extensions):
            return False
            
        return True
    
    def extract_changes_from_patch(self, patch: str) -> Dict[str, List[str]]:
        """Extract added and removed lines from git patch."""
        if not patch:
            return {"added": [], "removed": [], "context": []}
        
        added_lines = []
        removed_lines = []
        context_lines = []
        
        for line in patch.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                added_lines.append(line[1:].strip())
            elif line.startswith('-') and not line.startswith('---'):
                removed_lines.append(line[1:].strip())
            elif line.startswith(' '):
                context_lines.append(line[1:].strip())
        
        return {
            "added": added_lines,
            "removed": removed_lines, 
            "context": context_lines
        }
    
    def analyze_removed_dependencies(self, content: str, changes: Dict, language: str) -> List[Dict]:
        """Analyze removed dependencies for any language."""
        issues = []
        removed_lines = changes.get("removed", [])
        
        # Language-agnostic dependency patterns
        dependency_patterns = {
            'python': [r'^\s*(import|from)\s+(\w+)', r'^\s*from\s+(\w+)'],
            'javascript': [r'^\s*(import|require)\s*.*[\'"`](\w+)[\'"`]', r'^\s*const\s+\w+\s*=\s*require\([\'"`](\w+)[\'"`]\)'],
            'typescript': [r'^\s*import\s+.*from\s+[\'"`](\w+)[\'"`]', r'^\s*import\s+[\'"`](\w+)[\'"`]'],
            'java': [r'^\s*import\s+([\w.]+)', r'^\s*package\s+([\w.]+)'],
            'go': [r'^\s*import\s+["`]([^"`]+)["`]', r'^\s*import\s+(\w+)'],
            'rust': [r'^\s*use\s+([\w:]+)', r'^\s*extern\s+crate\s+(\w+)'],
            'cpp': [r'^\s*#include\s*[<"]([^>"]+)[>"]'],
            'c': [r'^\s*#include\s*[<"]([^>"]+)[>"]']
        }
        
        patterns = dependency_patterns.get(language, [])
        if not patterns:
            return issues
        
        # Extract removed dependencies
        removed_deps = set()
        for line in removed_lines:
            for pattern in patterns:
                matches = re.findall(pattern, line.strip())
                for match in matches:
                    if isinstance(match, tuple):
                        removed_deps.add(match[1] if len(match) > 1 else match[0])
                    else:
                        removed_deps.add(match)
        
        # Check if removed dependencies are still referenced in the file
        if removed_deps and content:
            for dep in removed_deps:
                # Simple string search - could be refined per language
                if dep in content and len(dep) > 2:  # Avoid false positives on short names
                    issues.append({
                        "type": self.get_analysis_type(),
                        "filename": "",
                        "line": None,
                        "severity": "critical",
                        "description": f"Removed dependency '{dep}' but it appears to still be referenced in the code",
                        "suggestion": f"Either keep the dependency or remove all references to '{dep}'",
                        "impact": "This may cause compilation/runtime errors",
                        "category": "dependency"
                    })
        
        return issues
    
    def detect_code_duplication(self, changes: Dict) -> List[Dict]:
        """Detect duplicated code in changes."""
        issues = []
        added_lines = changes.get("added", [])
        
        # Remove empty lines and normalize whitespace
        normalized_lines = []
        for line in added_lines:
            cleaned = re.sub(r'\s+', ' ', line.strip())
            if cleaned and not cleaned.startswith('#'):  # Skip comments
                normalized_lines.append(cleaned)
        
        # Check for exact duplicates
        seen_lines = {}
        for i, line in enumerate(normalized_lines):
            if line in seen_lines:
                issues.append({
                    "type": self.get_analysis_type(),
                    "filename": "",
                    "line": None,
                    "severity": "medium",
                    "description": f"Duplicate code detected: '{line[:50]}...'",
                    "suggestion": "Remove duplicate code or extract to a function",
                    "impact": "Code duplication makes maintenance harder",
                    "category": "duplication"
                })
            else:
                seen_lines[line] = i
        
        return issues
    
    def get_language_context(self, language: str) -> str:
        """Get language-specific context for analysis."""
        contexts = {
            'security': {
                'c-like': "Focus on: buffer overflows, null pointer dereferences, memory leaks, unsafe casts, unvalidated input",
                'python-like': "Focus on: SQL injection, pickle/eval usage, subprocess calls, file path traversal, input validation",
                'web': "Focus on: XSS vulnerabilities, CSRF, unsafe DOM manipulation, eval() usage, input sanitization",
                'jvm': "Focus on: deserialization attacks, SQL injection, XML external entities, reflection usage",
                'systems': "Focus on: memory safety, buffer overflows, integer overflows, race conditions, unsafe operations",
                'scripting': "Focus on: command injection, file inclusion, eval usage, input validation, privilege escalation"
            },
            'performance': {
                'c-like': "Focus on: algorithm complexity, memory allocation patterns, loop optimization, cache efficiency",
                'python-like': "Focus on: list comprehensions vs loops, generator usage, numpy vectorization, database query patterns",
                'web': "Focus on: DOM manipulation efficiency, event handling, bundle size, lazy loading, memory leaks",
                'jvm': "Focus on: garbage collection impact, collection sizing, stream API usage, reflection overhead",
                'systems': "Focus on: memory allocation, cache locality, SIMD usage, lock contention",
                'functional': "Focus on: tail recursion, immutable data structures, lazy evaluation, collection operations"
            },
            'style': {
                'c-like': "Check: consistent naming (camelCase/snake_case), proper indentation, clear function signatures, code organization",
                'python-like': "Follow PEP 8: snake_case naming, proper imports, docstrings, type hints, line length (88-100 chars)",
                'web': "Follow JS standards: camelCase naming, const/let usage, arrow functions, JSDoc comments, ES6+ features",
                'jvm': "Follow conventions: PascalCase classes, camelCase methods, proper JavaDoc, exception handling"
            },
            'logic': {
                'c-like': "Check: null pointer checks, array bounds, memory management, type safety, edge cases",
                'python-like': "Check: None checks, exception handling, iterator exhaustion, async/await usage, edge cases",
                'web': "Check: undefined/null checks, async promise handling, type coercion, event cleanup, edge cases",
                'systems': "Check: memory safety, concurrent access, resource cleanup, error propagation"
            }
        }
        
        analysis_type = self.get_analysis_type()
        
        # Find which family this language belongs to
        for family, languages in self.language_families.items():
            if language in languages:
                return contexts.get(analysis_type, {}).get(family, "")
        
        return f"Analyze this {language} code for {analysis_type} issues using best practices."
    
    @abstractmethod
    def get_analysis_type(self) -> str:
        """Return the type of analysis (security, performance, style, logic)."""
        pass
    
    @abstractmethod
    def get_analysis_categories(self) -> List[str]:
        """Return specific categories to analyze."""
        pass
    
    @abstractmethod
    def get_output_format(self) -> str:
        """Return expected output format for the LLM."""
        pass
    
    async def analyze(self, file_data: Dict) -> List[Dict]:
        """Enhanced analyze method focusing on actual changes."""
        try:
            if not self.should_analyze_file(file_data):
                return []
                
            filename = file_data["filename"]
            content = file_data.get("content", "")
            patch = file_data.get("patch", "")
            language = file_data.get("language", "text")
            
            issues = []
            
            # Extract changes from patch
            changes = self.extract_changes_from_patch(patch)
            
            # If no patch but has content, analyze the content (new file)
            if not patch and content:
                code_to_analyze = content
                analysis_focus = "ANALYZING ENTIRE FILE (new file)"
            elif patch:
                # Focus on changes
                added_lines = '\n'.join(changes["added"])
                removed_lines = '\n'.join(changes["removed"])
                context_lines = '\n'.join(changes["context"][:5])  # Limited context
                
                code_to_analyze = f"""ADDED LINES:
{added_lines}

REMOVED LINES:
{removed_lines}

SURROUNDING CONTEXT:
{context_lines}"""
                analysis_focus = "ANALYZING CHANGES (focus on added/removed lines)"
            else:
                return []
            
            # Add language-agnostic static analysis
            static_issues = self.analyze_removed_dependencies(content, changes, language)
            issues.extend(static_issues)
            
            # Add duplication detection for all languages
            duplication_issues = self.detect_code_duplication(changes)
            issues.extend(duplication_issues)
            
            # LLM-based analysis with enhanced prompt
            prompt = self._build_enhanced_prompt(language, analysis_focus)
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"File: {filename}\nLanguage: {language}\n\n{code_to_analyze}"}
                ],
                temperature=0.1,
                max_tokens=3072,  # Increased for more detailed analysis
            )
            
            analysis_text = response.choices[0].message.content
            llm_issues = self._parse_issues(analysis_text, filename)
            issues.extend(llm_issues)
            
            return issues
            
        except Exception as e:
            logger.error(f"{self.get_analysis_type()} analysis failed", filename=filename, error=str(e))
            return []
    
    def _build_enhanced_prompt(self, language: str, analysis_focus: str) -> str:
        """Build enhanced analysis prompt focusing on changes."""
        analysis_type = self.get_analysis_type()
        categories = self.get_analysis_categories()
        output_format = self.get_output_format()
        language_context = self.get_language_context(language)
        
        categories_text = "\n".join([f"{i+1}. {cat}" for i, cat in enumerate(categories)])
        
        prompt = f"""You are a senior {analysis_type} engineer reviewing code changes for a Pull Request.

{analysis_focus}

CRITICAL: Pay special attention to:
- Lines marked as "ADDED" (new code being introduced)
- Lines marked as "REMOVED" (code being deleted)
- Impact of removed code on remaining functionality
- Duplicated code patterns
- Missing error handling in new code
- Security vulnerabilities in new code

Analyze for {analysis_type} issues including:
{categories_text}

Language-specific guidance:
{language_context}

For each issue found, provide:
- Line number (if identifiable)
- Severity (critical, high, medium, low)
- Clear description focusing on the CHANGE impact
- Specific recommendation to fix

IMPORTANT: 
- Focus on issues related to the actual changes being made
- Flag removed imports that might still be used
- Identify any duplicate code being added
- Consider the impact of deletions on existing functionality

{output_format}"""
        
        return prompt
    
    def _parse_issues(self, analysis_text: str, filename: str) -> List[Dict]:
        """Enhanced parsing with better error handling."""
        issues = []
        
        try:
            # Split by multiple possible delimiters
            sections = re.split(r'---+|\n\n\n+', analysis_text)
            
            for section in sections:
                issue_data = self._extract_issue_from_section(section.strip(), filename)
                if issue_data:
                    issues.append(issue_data)
        
        except Exception as e:
            logger.error(f"Failed to parse {self.get_analysis_type()} issues", error=str(e))
        
        return issues
    
    def _extract_issue_from_section(self, section: str, filename: str) -> Optional[Dict]:
        """Enhanced issue extraction with better keyword matching."""
        if not section or len(section.strip()) < 10:
            return None
            
        try:
            lines = section.split("\n")
            
            # More flexible keyword matching
            issue_keywords = ["ISSUE:", "BUG:", "PERF_ISSUE:", "STYLE_ISSUE:", "SECURITY:", "PROBLEM:", "VULNERABILITY:", "WARNING:"]
            fix_keywords = ["FIX:", "SUGGESTION:", "OPTIMIZATION:", "RECOMMENDATION:", "SOLUTION:", "IMPROVE:"]
            
            issue_line = ""
            fix_line = ""
            impact_line = ""
            
            for line in lines:
                line = line.strip()
                if any(keyword in line.upper() for keyword in [k.rstrip(':') for k in issue_keywords]):
                    issue_line = line
                elif any(keyword in line.upper() for keyword in [k.rstrip(':') for k in fix_keywords]):
                    fix_line = line
                elif "IMPACT:" in line.upper():
                    impact_line = line
            
            if not issue_line and not fix_line:
                # Try to extract from unstructured text
                if len(section) > 20 and any(word in section.lower() for word in ['issue', 'problem', 'bug', 'error', 'vulnerability']):
                    issue_line = section[:200] + "..." if len(section) > 200 else section
                    fix_line = "Review and fix the identified issue"
                else:
                    return None
            
            return self._extract_structured_data(issue_line, fix_line, impact_line, filename)
            
        except Exception as e:
            logger.error("Failed to extract issue from section", error=str(e))
            return None
    
    def _extract_structured_data(self, issue_line: str, fix_line: str, impact_line: str, filename: str) -> Dict:
        """Enhanced structured data extraction."""
        # Clean up the lines
        for prefix in ["ISSUE:", "BUG:", "PERF_ISSUE:", "STYLE_ISSUE:", "SECURITY:", "PROBLEM:", "VULNERABILITY:", "WARNING:"]:
            issue_line = issue_line.replace(prefix, "").strip()
            
        for prefix in ["FIX:", "SUGGESTION:", "OPTIMIZATION:", "RECOMMENDATION:", "SOLUTION:", "IMPROVE:"]:
            fix_line = fix_line.replace(prefix, "").strip()
            
        impact = impact_line.replace("IMPACT:", "").strip() if impact_line else ""
        
        # Enhanced severity extraction
        severity = "medium"
        severity_indicators = {
            "critical": ["critical", "severe", "dangerous", "fatal", "security", "vulnerability"],
            "high": ["high", "important", "significant", "major", "error"],
            "medium": ["medium", "moderate", "warning", "issue"],
            "low": ["low", "minor", "style", "formatting", "cosmetic"]
        }
        
        text_to_check = (issue_line + " " + impact).lower()
        for sev, indicators in severity_indicators.items():
            if any(indicator in text_to_check for indicator in indicators):
                severity = sev
                break
        
        # Enhanced line number extraction
        line_number = None
        line_patterns = [
            r'line\s*(\d+)',
            r'@\s*(\d+)',
            r':\s*(\d+)',
            r'#\s*(\d+)'
        ]
        
        for pattern in line_patterns:
            match = re.search(pattern, issue_line, re.IGNORECASE)
            if match:
                line_number = int(match.group(1))
                break
        
        # Clean description
        description = issue_line
        if ":" in description and len(description.split(":", 1)) > 1:
            description = description.split(":", 1)[1].strip()
        
        # Ensure minimum quality
        if len(description.strip()) < 10:
            description = f"Code quality issue detected in {filename}"
        
        return {
            "type": self.get_analysis_type(),
            "filename": filename,
            "line": line_number,
            "severity": severity,
            "description": description.strip(),
            "suggestion": fix_line.strip() if fix_line else "Review and address the identified issue",
            "impact": impact,
            "category": self.get_analysis_type()
        }


# Specific analyzer implementations with enhanced prompts
class SecurityAnalyzer(BaseAnalyzer):
    def get_analysis_type(self) -> str:
        return "security"
    
    def get_analysis_categories(self) -> List[str]:
        return [
            "Injection vulnerabilities (SQL, NoSQL, Command, LDAP)",
            "Cross-Site Scripting (XSS) and input validation",
            "Authentication and authorization bypass",
            "Cryptographic weaknesses and insecure storage", 
            "Information disclosure and data leaks",
            "Insecure dependencies and vulnerable libraries",
            "CSRF and session management flaws",
            "Path traversal and directory attacks",
            "Code injection and unsafe deserialization",
            "Insecure API endpoints and missing access controls"
        ]
    
    def get_output_format(self) -> str:
        return """Format your response as:
SECURITY: [severity] Line [number]: [description]
FIX: [specific security fix]
IMPACT: [potential security impact]
---"""


class PerformanceAnalyzer(BaseAnalyzer):
    def get_analysis_type(self) -> str:
        return "performance"
    
    def get_analysis_categories(self) -> List[str]:
        return [
            "Inefficient algorithms and data structure choices",
            "N+1 query problems and database inefficiencies",
            "Memory leaks and excessive memory allocation",
            "Blocking operations in async/concurrent contexts",
            "Inefficient loops and unnecessary iterations",
            "Large object creation inside loops",
            "Redundant network calls and I/O operations",
            "Missing caching and poor cache strategies",
            "Resource cleanup and connection management",
            "CPU-intensive operations in main thread"
        ]
    
    def get_output_format(self) -> str:
        return """Format your response as:
PERF_ISSUE: [severity] Line [number]: [description]
OPTIMIZATION: [specific performance fix]
IMPACT: [expected performance improvement]
---"""


class StyleAnalyzer(BaseAnalyzer):
    def get_analysis_type(self) -> str:
        return "style"
    
    def get_analysis_categories(self) -> List[str]:
        return [
            "Code formatting and consistent indentation",
            "Naming conventions for variables, functions, classes",
            "Code organization and logical structure",
            "Documentation, comments, and inline explanations",
            "Function/method length and complexity (cognitive load)",
            "Code duplication and DRY principle violations",
            "Error handling patterns and consistency",
            "Import/dependency organization and cleanup",
            "Code readability and maintainability",
            "Language-specific style guide adherence"
        ]
    
    def get_output_format(self) -> str:
        return """Format your response as:
STYLE_ISSUE: [severity] Line [number]: [description]
SUGGESTION: [specific style improvement]
---"""


class LogicAnalyzer(BaseAnalyzer):
    def get_analysis_type(self) -> str:
        return "logic"
    
    def get_analysis_categories(self) -> List[str]:
        return [
            "Null/undefined reference errors and missing checks",
            "Off-by-one errors in loops and array access",
            "Incorrect conditional logic and boolean expressions",
            "Race conditions and concurrency issues",
            "Resource leaks and improper cleanup",
            "Exception handling gaps and error propagation",
            "Edge case handling and boundary conditions",
            "Data type mismatches and conversion errors", 
            "Infinite loop potential and termination conditions",
            "Control flow problems and unreachable code"
        ]
    
    def get_output_format(self) -> str:
        return """Format your response as:
BUG: [severity] Line [number]: [description]
FIX: [specific logic fix]
IMPACT: [potential runtime impact]
---"""


# Updated workflow functions with proper return statements for parallel execution
async def security_review(state: Dict) -> Dict:
    """Perform security analysis on PR files."""
    analyzer = SecurityAnalyzer()
    files_changed = state.get("files_changed", [])
    security_issues = []
    
    logger.info("Starting security analysis", files_count=len(files_changed))
    
    for file_data in files_changed:
        issues = await analyzer.analyze(file_data)
        security_issues.extend(issues)
    
    security_results = {
        "issues": security_issues,
        "summary": {
            "total_issues": len(security_issues),
            "critical_issues": len([i for i in security_issues if i["severity"] == "critical"]),
            "high_issues": len([i for i in security_issues if i["severity"] == "high"]),
        }
    }
    
    logger.info("Security analysis completed", 
               total_issues=len(security_issues),
               critical_issues=security_results["summary"]["critical_issues"])
    
    return {"analysis_results": {"security": security_results}}


async def performance_review(state: Dict) -> Dict:
    """Perform performance analysis on PR files."""
    analyzer = PerformanceAnalyzer()
    files_changed = state.get("files_changed", [])
    performance_issues = []
    
    logger.info("Starting performance analysis", files_count=len(files_changed))
    
    for file_data in files_changed:
        issues = await analyzer.analyze(file_data)
        performance_issues.extend(issues)
    
    performance_results = {
        "issues": performance_issues,
        "summary": {
            "total_issues": len(performance_issues),
            "critical_issues": len([i for i in performance_issues if i["severity"] == "critical"]),
            "high_issues": len([i for i in performance_issues if i["severity"] == "high"]),
        }
    }
    
    logger.info("Performance analysis completed", 
               total_issues=len(performance_issues),
               critical_issues=performance_results["summary"]["critical_issues"])
    
    return {"analysis_results": {"performance": performance_results}}


async def style_review(state: Dict) -> Dict:
    """Perform style analysis on PR files."""
    analyzer = StyleAnalyzer()
    files_changed = state.get("files_changed", [])
    style_issues = []
    
    logger.info("Starting style analysis", files_count=len(files_changed))
    
    for file_data in files_changed:
        issues = await analyzer.analyze(file_data)
        style_issues.extend(issues)
    
    style_results = {
        "issues": style_issues,
        "summary": {
            "total_issues": len(style_issues),
            "high_issues": len([i for i in style_issues if i["severity"] == "high"]),
            "medium_issues": len([i for i in style_issues if i["severity"] == "medium"]),
        }
    }
    
    logger.info("Style analysis completed", 
               total_issues=len(style_issues),
               high_issues=style_results["summary"]["high_issues"])
    
    return {"analysis_results": {"style": style_results}}


async def logic_review(state: Dict) -> Dict:
    """Perform logic analysis on PR files."""
    analyzer = LogicAnalyzer()
    files_changed = state.get("files_changed", [])
    logic_issues = []
    
    logger.info("Starting logic analysis", files_count=len(files_changed))
    
    for file_data in files_changed:
        issues = await analyzer.analyze(file_data)
        logic_issues.extend(issues)
    
    logic_results = {
        "issues": logic_issues,
        "summary": {
            "total_issues": len(logic_issues),
            "critical_issues": len([i for i in logic_issues if i["severity"] == "critical"]),
            "high_issues": len([i for i in logic_issues if i["severity"] == "high"]),
        }
    }
    
    logger.info("Logic analysis completed", 
               total_issues=len(logic_issues),
               critical_issues=logic_results["summary"]["critical_issues"])
    
    return {"analysis_results": {"logic": logic_results}}