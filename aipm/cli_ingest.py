"""
Codebase Ingestion CLI - Analyze and ingest code into AIPM prompt queue
"""
import click
import sys
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aipm.core.codebase_analyzer import CodebaseAnalyzer
from aipm.core.queue import PromptQueue
from aipm.core.engine import Prompt, PromptCategory, PromptStatus
import uuid
import sqlite3

# Use the CTRM database for continuous loop compatibility
CTRM_DB = Path(__file__).parent.parent.parent / "data" / "truths.db"

def _add_to_ctrm_queue(text: str, priority: int, category: str) -> bool:
    """Add prompt directly to CTRM database for continuous loop"""
    prompt_id = f"prompt_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    
    try:
        with sqlite3.connect(CTRM_DB) as conn:
            conn.execute("""
                INSERT INTO prompt_queue 
                (id, prompt, priority, category, status, created_at, updated_at, confidence, impact)
                VALUES (?, ?, ?, ?, 'pending', ?, ?, 0.8, 0.7)
            """, (prompt_id, text, priority, category, now, now))
        return True
    except Exception as e:
        print(f"Error adding to CTRM: {e}")
        return False

def _create_prompt(text: str, priority: int, category: str) -> Prompt:
    """Helper to create a Prompt object"""
    # Map category string to PromptCategory enum
    cat_map = {
        'improvement': PromptCategory.CODE_GEN,
        'bugfix': PromptCategory.DEBUG,
        'refactoring': PromptCategory.REFACTOR,
        'testing': PromptCategory.TEST,
        'documentation': PromptCategory.DOC,
        'performance': PromptCategory.ANALYSIS,
        'code': PromptCategory.CODE_GEN,
    }
    cat = cat_map.get(category.lower(), PromptCategory.CODE_GEN)

    now = datetime.now()
    return Prompt(
        id=f"prompt_{uuid.uuid4().hex[:8]}",
        text=text,
        category=cat,
        priority=priority,
        confidence=0.8,
        impact=0.7,
        status=PromptStatus.PENDING,
        created_at=now,
        updated_at=now,
    )

@click.group()
def ingest():
    """Ingest codebases into AIPM for analysis"""
    pass

@ingest.command()
@click.argument('directory', type=click.Path(exists=True))
@click.option('--tag', '-t', default='CODEBASE', help='Project tag for prompts')
@click.option('--max-files', '-m', default=100, help='Maximum files to analyze')
@click.option('--dry-run', is_flag=True, help='Show prompts without adding to queue')
@click.option('--priority-offset', '-p', default=0, help='Add to priority (negative = higher priority)')
def scan(directory, tag, max_files, dry_run, priority_offset):
    """Scan a directory and generate improvement prompts"""
    
    click.echo(f"🔍 Scanning {directory}...")
    
    analyzer = CodebaseAnalyzer(directory)
    files = analyzer.scan(max_files)
    
    click.echo(analyzer.generate_summary())
    
    prompts = analyzer.generate_prompts(tag)
    
    if dry_run:
        click.echo("\n📝 Generated Prompts (dry run):")
        click.echo("=" * 60)
        for i, p in enumerate(prompts[:30], 1):
            click.echo(f"{i}. [P{p['priority']}] {p['text'][:80]}...")
        click.echo(f"\nTotal: {len(prompts)} prompts")
        return
    
    # Add to CTRM queue (for continuous loop compatibility)
    added = 0
    
    for p in prompts:
        try:
            adjusted_priority = max(1, min(10, p['priority'] + priority_offset))
            if _add_to_ctrm_queue(p['text'], adjusted_priority, p['category']):
                added += 1
        except Exception as e:
            click.echo(f"Error adding prompt: {e}")
    
    click.echo(f"\n✅ Added {added} prompts to queue")

@ingest.command()
@click.argument('directory', type=click.Path(exists=True))
@click.option('--tag', '-t', default='SHADER', help='Project tag for prompts')
@click.option('--dry-run', is_flag=True, help='Show prompts without adding')
def shaders(directory, tag, dry_run):
    """Analyze WGSL shaders specifically"""
    
    directory = Path(directory)
    shader_files = list(directory.rglob('*.wgsl'))
    
    click.echo(f"🎨 Found {len(shader_files)} shader files")
    
    prompts = []
    
    for shader in shader_files:
        content = shader.read_text(encoding='utf-8', errors='ignore')
        lines = content.count('\n') + 1
        
        # Check for common shader issues
        if lines > 500:
            prompts.append({
                'text': f"[{tag}] Large shader {shader.name} ({lines} lines) - consider splitting",
                'priority': 4,
                'category': 'refactoring'
            })
        
        # Check for TODO/FIXME
        todos = content.count('TODO') + content.count('FIXME')
        if todos > 0:
            prompts.append({
                'text': f"[{tag}] {shader.name} has {todos} TODO/FIXME comments to address",
                'priority': 3,
                'category': 'improvement'
            })
        
        # Check for performance hints
        if 'for' in content and content.count('for') > 5:
            prompts.append({
                'text': f"[{tag}] {shader.name} has many loops - verify GPU optimization",
                'priority': 5,
                'category': 'performance'
            })
        
        # Check for compute shader entry points
        if '@compute' in content:
            workgroup_count = content.count('@compute')
            prompts.append({
                'text': f"[{tag}] {shader.name} has {workgroup_count} compute shaders - document workgroup sizes",
                'priority': 6,
                'category': 'documentation'
            })
    
    if dry_run:
        click.echo("\n📝 Generated Shader Prompts:")
        for p in prompts:
            click.echo(f"  [P{p['priority']}] {p['text']}")
        return
    
    added = 0
    for p in prompts:
        try:
            if _add_to_ctrm_queue(p['text'], p['priority'], p['category']):
                added += 1
        except Exception as e:
            click.echo(f"Error: {e}")
    
    click.echo(f"\n✅ Added {added} shader prompts to queue")

@ingest.command()
@click.argument('directory', type=click.Path(exists=True))
@click.option('--tag', '-t', default='DOCS', help='Project tag for prompts')
def docs(directory, tag):
    """Analyze documentation gaps"""
    
    directory = Path(directory)
    
    # Check for missing docs
    has_readme = (directory / 'README.md').exists()
    has_roadmap = (directory / 'ROADMAP.md').exists()
    has_changelog = (directory / 'CHANGELOG.md').exists()
    has_contributing = (directory / 'CONTRIBUTING.md').exists()
    
    prompts = []
    
    if not has_readme:
        prompts.append({
            'text': f"[{tag}] Create README.md for {directory.name}",
            'priority': 2,
            'category': 'documentation'
        })
    
    if not has_roadmap:
        prompts.append({
            'text': f"[{tag}] Create ROADMAP.md to track project direction",
            'priority': 4,
            'category': 'documentation'
        })
    
    # Check Rust files for missing doc comments
    rust_files = list(directory.rglob('*.rs'))[:20]  # Limit
    
    for rs in rust_files:
        content = rs.read_text(encoding='utf-8', errors='ignore')
        
        # Check for public items without docs
        pub_fns = content.count('pub fn')
        doc_comments = content.count('///')
        
        if pub_fns > 3 and doc_comments < pub_fns // 2:
            prompts.append({
                'text': f"[{tag}] {rs.name} has {pub_fns} public functions but few doc comments",
                'priority': 5,
                'category': 'documentation'
            })
    
    added = 0
    for p in prompts:
        try:
            if _add_to_ctrm_queue(p['text'], p['priority'], p['category']):
                added += 1
        except Exception as e:
            click.echo(f"Error: {e}")
    
    click.echo(f"✅ Added {added} documentation prompts")

if __name__ == '__main__':
    ingest()
