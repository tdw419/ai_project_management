"""
Codebase Analyzer - Scans directories and generates intelligent prompts
"""
import os
import re
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass
import hashlib

@dataclass
class FileInfo:
    path: str
    language: str
    lines: int
    todos: List[str]
    fixmes: List[str]
    imports: List[str]
    functions: List[str]
    complexity_hints: List[str]
    
class CodebaseAnalyzer:
    """Analyzes codebases and generates improvement prompts"""
    
    LANGUAGE_MAP = {
        '.rs': 'Rust',
        '.py': 'Python',
        '.js': 'JavaScript',
        '.ts': 'TypeScript',
        '.go': 'Go',
        '.c': 'C',
        '.cpp': 'C++',
        '.h': 'C Header',
        '.wgsl': 'WGSL Shader',
        '.md': 'Markdown',
        '.sh': 'Shell',
        '.json': 'JSON',
        '.yaml': 'YAML',
        '.yml': 'YAML',
    }
    
    SKIP_DIRS = {'node_modules', '__pycache__', '.git', 'target', 'build', 'dist', '.venv', 'venv'}
    SKIP_FILES = {'.bak', '.log', '.pyc', '.o', '.so', '.dll'}
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path).expanduser()
        self.files: List[FileInfo] = []
        
    def scan(self, max_files: int = 100) -> List[FileInfo]:
        """Scan directory for code files"""
        self.files = []
        
        for root, dirs, files in os.walk(self.base_path):
            # Skip unwanted directories
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            
            for file in files:
                if any(file.endswith(ext) for ext in self.SKIP_FILES):
                    continue
                    
                ext = Path(file).suffix
                if ext not in self.LANGUAGE_MAP:
                    continue
                    
                full_path = Path(root) / file
                try:
                    info = self._analyze_file(full_path)
                    if info:
                        self.files.append(info)
                        if len(self.files) >= max_files:
                            return self.files
                except Exception as e:
                    print(f"Error analyzing {full_path}: {e}")
                    
        return self.files
    
    def _analyze_file(self, path: Path) -> FileInfo:
        """Analyze a single file"""
        ext = path.suffix
        language = self.LANGUAGE_MAP.get(ext, 'Unknown')
        
        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
        except:
            return None
            
        lines = content.count('\n') + 1
        
        # Extract TODOs
        todos = re.findall(r'(?:TODO|todo|Todo)[\s:]+([^\n]+)', content)
        
        # Extract FIXMEs
        fixmes = re.findall(r'(?:FIXME|fixme|FixMe)[\s:]+([^\n]+)', content)
        
        # Extract imports based on language
        imports = self._extract_imports(content, language)
        
        # Extract functions
        functions = self._extract_functions(content, language)
        
        # Detect complexity hints
        complexity_hints = self._detect_complexity(content, language)
        
        return FileInfo(
            path=str(path),
            language=language,
            lines=lines,
            todos=todos,
            fixmes=fixmes,
            imports=imports,
            functions=functions,
            complexity_hints=complexity_hints
        )
    
    def _extract_imports(self, content: str, language: str) -> List[str]:
        """Extract import statements"""
        patterns = {
            'Rust': r'use\s+([\w:]+)',
            'Python': r'(?:import|from)\s+([\w.]+)',
            'JavaScript': r'import.*?from\s+[\'"]([^\'"]+)',
            'TypeScript': r'import.*?from\s+[\'"]([^\'"]+)',
            'Go': r'import\s+[\'"]([^\'"]+)',
        }
        
        pattern = patterns.get(language)
        if pattern:
            return re.findall(pattern, content)[:20]  # Limit to 20
        return []
    
    def _extract_functions(self, content: str, language: str) -> List[str]:
        """Extract function names"""
        patterns = {
            'Rust': r'fn\s+(\w+)',
            'Python': r'def\s+(\w+)',
            'JavaScript': r'function\s+(\w+)',
            'TypeScript': r'function\s+(\w+)',
            'Go': r'func\s+(\w+)',
            'WGSL Shader': r'fn\s+(\w+)',
        }
        
        pattern = patterns.get(language)
        if pattern:
            return re.findall(pattern, content)[:30]  # Limit to 30
        return []
    
    def _detect_complexity(self, content: str, language: str) -> List[str]:
        """Detect potential complexity issues"""
        hints = []
        
        # Large files
        if content.count('\n') > 500:
            hints.append("Large file (>500 lines) - consider refactoring")
            
        # Deep nesting (Rust/JS/TS)
        if language in ['Rust', 'JavaScript', 'TypeScript']:
            nesting = 0
            max_nesting = 0
            for line in content.split('\n'):
                nesting += line.count('{') - line.count('}')
                max_nesting = max(max_nesting, nesting)
            if max_nesting > 5:
                hints.append(f"Deep nesting (level {max_nesting}) - consider extracting functions")
                
        # Long functions (Rust)
        if language == 'Rust':
            fn_blocks = re.split(r'\nfn\s+', content)
            for block in fn_blocks[1:]:  # Skip first (before first fn)
                if block.count('\n') > 50:
                    fn_name = re.match(r'(\w+)', block)
                    if fn_name:
                        hints.append(f"Long function '{fn_name.group(1)}' (>50 lines)")
                        
        # TODO/FIXME density
        todo_count = len(re.findall(r'TODO|FIXME', content, re.IGNORECASE))
        if todo_count > 5:
            hints.append(f"High TODO/FIXME count ({todo_count}) - technical debt")
            
        return hints
    
    def generate_prompts(self, project_tag: str = "CODEBASE") -> List[Dict[str, Any]]:
        """Generate improvement prompts based on analysis"""
        prompts = []
        
        for file in self.files:
            # TODO-based prompts
            for todo in file.todos[:3]:  # Limit to 3 per file
                prompts.append({
                    'text': f"[{project_tag}] {file.language}: In {Path(file.path).name}, address TODO: {todo.strip()}",
                    'priority': 3,
                    'category': 'improvement',
                    'file': file.path
                })
            
            # FIXME-based prompts (higher priority)
            for fixme in file.fixmes[:2]:
                prompts.append({
                    'text': f"[{project_tag}] {file.language}: Fix in {Path(file.path).name}: {fixme.strip()}",
                    'priority': 2,
                    'category': 'bugfix',
                    'file': file.path
                })
            
            # Complexity-based prompts
            for hint in file.complexity_hints:
                prompts.append({
                    'text': f"[{project_tag}] {file.language}: {Path(file.path).name} - {hint}",
                    'priority': 4,
                    'category': 'refactoring',
                    'file': file.path
                })
            
            # Missing tests (for Rust files with functions but no test module)
            if file.language == 'Rust' and file.functions:
                if '#[cfg(test)]' not in open(file.path).read():
                    if len(file.functions) > 3:  # Only if has multiple functions
                        prompts.append({
                            'text': f"[{project_tag}] Rust: Add tests to {Path(file.path).name} (has {len(file.functions)} functions but no test module)",
                            'priority': 5,
                            'category': 'testing',
                            'file': file.path
                        })
        
        return prompts
    
    def generate_summary(self) -> str:
        """Generate a summary of the codebase"""
        by_language = {}
        total_lines = 0
        total_todos = 0
        total_fixmes = 0
        
        for file in self.files:
            lang = file.language
            by_language.setdefault(lang, {'count': 0, 'lines': 0, 'todos': 0, 'fixmes': 0})
            by_language[lang]['count'] += 1
            by_language[lang]['lines'] += file.lines
            by_language[lang]['todos'] += len(file.todos)
            by_language[lang]['fixmes'] += len(file.fixmes)
            total_lines += file.lines
            total_todos += len(file.todos)
            total_fixmes += len(file.fixmes)
        
        summary = f"Codebase Analysis Summary\n"
        summary += f"========================\n\n"
        summary += f"Total files: {len(self.files)}\n"
        summary += f"Total lines: {total_lines:,}\n"
        summary += f"Total TODOs: {total_todos}\n"
        summary += f"Total FIXMEs: {total_fixmes}\n\n"
        
        summary += "By Language:\n"
        for lang, stats in sorted(by_language.items(), key=lambda x: x[1]['lines'], reverse=True):
            summary += f"  {lang}: {stats['count']} files, {stats['lines']:,} lines, {stats['todos']} TODOs, {stats['fixmes']} FIXMEs\n"
            
        return summary


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python codebase_analyzer.py <directory> [project_tag]")
        sys.exit(1)
        
    directory = sys.argv[1]
    project_tag = sys.argv[2] if len(sys.argv) > 2 else "CODEBASE"
    
    analyzer = CodebaseAnalyzer(directory)
    files = analyzer.scan()
    
    print(analyzer.generate_summary())
    print("\nGenerated Prompts:")
    print("==================")
    
    prompts = analyzer.generate_prompts(project_tag)
    for p in prompts[:20]:  # Show first 20
        print(f"[P{p['priority']}] {p['text'][:100]}")
    
    print(f"\nTotal prompts generated: {len(prompts)}")
