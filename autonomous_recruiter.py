#!/usr/bin/env python3
"""
Autonomous Recruiter - Overnight Code Ingestion

Scans ~/zion/projects/ and recruits all code into the Living Museum.
Runs nightly at 2 AM to create a physical city from your entire codebase.
"""

import sys
import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple
import hashlib

# Add AIPM to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from aipm import AIPM, get_aipm

# Paths
PROJECTS_DIR = Path.home() / "zion" / "projects"
GEOMETRY_OS_DIR = PROJECTS_DIR / "geometry_os"
LOG_FILE = Path(__file__).parent / "logs" / "autonomous_recruiter.log"

# Language to district color mapping
LANGUAGE_COLORS = {
    '.py': {'color': 'yellow', 'district': 'Python District'},
    '.rs': {'color': 'blue', 'district': 'Rust District'},
    '.js': {'color': 'green', 'district': 'JavaScript District'},
    '.ts': {'color': 'green', 'district': 'TypeScript District'},
    '.go': {'color': 'cyan', 'district': 'Go District'},
    '.c': {'color': 'orange', 'district': 'C District'},
    '.cpp': {'color': 'orange', 'district': 'C++ District'},
    '.h': {'color': 'orange', 'district': 'Header District'},
    '.md': {'color': 'violet', 'district': 'Speech District'},
}


def log(message: str):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message}"
    
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(entry + "\n")
    
    print(entry)


def scan_codebase() -> List[Tuple[Path, str, Dict]]:
    """Scan all code files and categorize by language"""
    files = []
    
    for ext, meta in LANGUAGE_COLORS.items():
        for filepath in PROJECTS_DIR.rglob(f"*{ext}"):
            # Skip common exclusions
            if any(x in str(filepath) for x in ['node_modules', '__pycache__', '.git', 'target', '.venv']):
                continue
            
            files.append((filepath, ext, meta))
    
    return files


def calculate_tile_requirements(filepath: Path) -> int:
    """
    Calculate how many RISC-V tiles are needed
    
    Complexity scoring:
    - Simple function: 1 tile
    - Class/module: 5-10 tiles
    - Neural layer: 100 tiles
    - Full file: based on line count and complexity
    """
    try:
        content = filepath.read_text()
        lines = len(content.split('\n'))
        
        # Count complexity indicators
        functions = content.count('def ') + content.count('fn ') + content.count('function ')
        classes = content.count('class ')
        imports = content.count('import ') + content.count('use ')
        
        # Base tiles
        base = max(1, lines // 100)
        
        # Add tiles for complexity
        tiles = base + (functions * 2) + (classes * 5) + (imports // 10)
        
        return min(tiles, 1000)  # Cap at 1000 tiles per file
    except:
        return 1


def assign_district_coordinates(index: int, total: int, language_meta: Dict) -> Tuple[int, int]:
    """
    Assign district coordinates on the Infinite Map
    
    Grid layout:
    - Python District: (0-999, 0-999)
    - Rust District: (1000-1999, 0-999)
    - JavaScript District: (0-999, 1000-1999)
    - etc.
    """
    district = language_meta['district']
    
    # Base coordinates for each district
    district_bases = {
        'Python District': (0, 0),
        'Rust District': (1000, 0),
        'JavaScript District': (0, 1000),
        'TypeScript District': (1000, 1000),
        'Go District': (2000, 0),
        'C District': (0, 2000),
        'C++ District': (1000, 2000),
        'Header District': (2000, 1000),
        'Speech District': (2000, 2000),
    }
    
    base_x, base_y = district_bases.get(district, (3000, 3000))
    
    # Spread files within district
    grid_size = int(total ** 0.5) + 1
    row = index // grid_size
    col = index % grid_size
    
    return (base_x + col * 10, base_y + row * 10)


def create_rts_cartridge(filepath: Path, tiles: int, coords: Tuple[int, int], language_meta: Dict) -> Dict:
    """
    Create .rts.png cartridge for the code file
    
    Returns metadata about the cartridge
    """
    content = filepath.read_text()
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    return {
        'filepath': str(filepath),
        'filename': filepath.name,
        'tiles': tiles,
        'coords': coords,
        'district': language_meta['district'],
        'color': language_meta['color'],
        'hash': content_hash,
        'created_at': datetime.now().isoformat(),
    }


def recruit_file(aipm: AIPM, filepath: Path, ext: str, language_meta: Dict, index: int, total: int) -> Dict:
    """Recruit a single file into the Living Museum"""
    
    # Calculate tile requirements
    tiles = calculate_tile_requirements(filepath)
    
    # Assign coordinates
    coords = assign_district_coordinates(index, total, language_meta)
    
    # Create cartridge
    cartridge = create_rts_cartridge(filepath, tiles, coords, language_meta)
    
    # Enqueue deployment prompt
    prompt_id = aipm.enqueue(
        prompt=f"[Recruiter] Deploy {filepath.name} to {language_meta['district']} at coordinates {coords}. "
              f"Requires {tiles} tiles. Convert to .rts.png format and flash to grid.",
        priority=5,
        source="autonomous_recruiter",
        metadata=cartridge,
    )
    
    cartridge['prompt_id'] = prompt_id
    
    return cartridge


def main():
    """Main recruiter function"""
    log("=" * 70)
    log("Autonomous Recruiter - Starting overnight ingestion")
    log("=" * 70)
    
    # Initialize AIPM
    aipm = get_aipm()
    
    # Scan codebase
    log("Scanning codebase...")
    files = scan_codebase()
    log(f"Found {len(files)} code files to recruit")
    
    # Group by language
    by_language = {}
    for filepath, ext, meta in files:
        lang = meta['district']
        if lang not in by_language:
            by_language[lang] = []
        by_language[lang].append((filepath, ext, meta))
    
    log(f"Districts: {list(by_language.keys())}")
    
    # Recruit files
    cartridges = []
    total = len(files)
    
    for lang, lang_files in by_language.items():
        log(f"\nRecruiting {lang} ({len(lang_files)} files)...")
        
        for i, (filepath, ext, meta) in enumerate(lang_files):
            cartridge = recruit_file(aipm, filepath, ext, meta, i, len(lang_files))
            cartridges.append(cartridge)
            
            if i % 10 == 0:
                log(f"  Recruited {i}/{len(lang_files)} files")
    
    # Calculate total tiles
    total_tiles = sum(c['tiles'] for c in cartridges)
    
    # Generate summary
    summary = {
        'timestamp': datetime.now().isoformat(),
        'files_recruited': len(cartridges),
        'total_tiles': total_tiles,
        'districts': {lang: len(files) for lang, files in by_language.items()},
        'cartridges': cartridges[:10],  # First 10 for preview
    }
    
    # Save summary
    summary_file = LOG_FILE.parent / "recruiter_summary.json"
    summary_file.write_text(json.dumps(summary, indent=2))
    
    log("\n" + "=" * 70)
    log("RECRUITMENT COMPLETE")
    log("=" * 70)
    log(f"Files recruited: {len(cartridges)}")
    log(f"Total tiles needed: {total_tiles}")
    log(f"Summary saved: {summary_file}")
    log("=" * 70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
