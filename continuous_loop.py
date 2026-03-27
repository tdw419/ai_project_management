#!/usr/bin/env python3
"""
AIPM Continuous Loop - Runs forever processing prompts

This script runs in a continuous loop, processing prompts from the queue
and updating dashboards.

Usage:
    python3 continuous_loop.py                    # Run forever
    python3 continuous_loop.py --interval 30      # Process every 30 seconds
    python3 continuous_loop.py --max 10           # Process max 10 prompts then stop
    python3 continuous_loop.py --project OpenMind # Only process OpenMind prompts
"""

import sys
import asyncio
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add AIPM to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from aipm import AIPM, get_aipm
from aipm.core.simple_bridge import SimpleQueueBridge
from aipm.config import DEFAULT_REASONING_MODEL, DEFAULT_VISION_MODEL


class ContinuousLoop:
    """Continuous prompt processing loop"""
    
    def __init__(
        self,
        interval: int = 60,
        max_prompts: Optional[int] = None,
        project_filter: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.aipm = get_aipm()
        self.bridge = SimpleQueueBridge()
        self.interval = interval
        self.max_prompts = max_prompts
        self.project_filter = project_filter
        self.model = model or DEFAULT_REASONING_MODEL
        self.processed_count = 0
        self.error_count = 0
        self.running = True
        
        # Handle shutdown signals
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)
    
    def _shutdown(self, signum, frame):
        """Handle shutdown signals"""
        print("\n\n🛑 Shutdown signal received...")
        self.running = False
    
    async def check_model(self) -> bool:
        """Check if a model is loaded"""
        loaded = await self.bridge.get_loaded_model()
        if loaded:
            return True
        
        # Try to load the model
        print(f"⚠️  No model loaded. Attempting to load {self.model}...")
        result = await self.bridge.load_model(self.model)
        
        if result["success"]:
            print(f"✅ Model loaded: {self.model}")
            return True
        else:
            print(f"❌ Could not load model: {result['message']}")
            return False
    
    async def process_one(self) -> bool:
        """Process a single prompt. Returns True if successful."""
        # Get next prompt
        prompts = self.aipm.ctrm.dequeue(limit=1)
        
        if not prompts:
            return False
        
        prompt = prompts[0]
        
        # Filter by project if specified
        if self.project_filter:
            # Check multiple ways to match project:
            # 1. project_id in metadata
            # 2. Project name in prompt text
            # 3. Project-related keywords in prompt
            
            metadata = prompt.get('metadata', {}) or {}
            project_id = metadata.get('project_id', '')
            project = self.aipm.projects.get_project(project_id) if project_id else None
            
            prompt_text = prompt.get('prompt', '').lower()
            filter_lower = self.project_filter.lower()
            
            # Check if prompt matches project
            matches_project = (
                (project and filter_lower in project.name.lower()) or
                (f"[{filter_lower}]" in prompt_text) or
                (filter_lower in prompt_text)
            )
            
            if not matches_project:
                # Not a match - skip this prompt
                return False
        
        print(f"\n{'='*70}")
        print(f"🔄 Processing: {prompt['id']}")
        print(f"   Priority: {prompt['priority']}")
        print(f"   Prompt: {prompt['prompt'][:80]}...")
        print(f"{'='*70}")
        
        # Mark as processing
        self.aipm.ctrm.mark_processing(prompt['id'])
        
        # Build context
        system_context = self._build_context(prompt)
        
        # Process with LM Studio
        start_time = time.time()
        result = await self.bridge.process_chat(
            messages=[
                {"role": "system", "content": system_context},
                {"role": "user", "content": prompt['prompt']},
            ],
            model=self.model,
            max_tokens=4096,
            temperature=0.7,
            auto_load=False,  # We already checked
        )
        
        elapsed = time.time() - start_time
        
        if result.success:
            print(f"\n✅ SUCCESS ({result.wait_time_ms}ms)")
            print("-" * 70)
            # Print first 2000 chars of result
            content = result.content or ""
            if len(content) > 2000:
                print(content[:2000])
                print(f"\n... ({len(content) - 2000} more characters)")
            else:
                print(content)
            print("-" * 70)
            
            # Mark as completed
            self.aipm.ctrm.complete(
                prompt['id'],
                result=content,
                verified=True,
                notes=f"Processed via {self.model} in {elapsed:.2f}s"
            )
            
            self.processed_count += 1
            return True
        else:
            print(f"\n❌ FAILED: {result.error}")
            
            self.aipm.ctrm.complete(
                prompt['id'],
                result=f"Error: {result.error}",
                verified=False,
            )
            
            self.error_count += 1
            return False
    
    def _build_context(self, prompt: dict) -> str:
        """Build system context for the prompt"""
        context_parts = [
            "You are an AI assistant helping build software projects.",
            "Provide detailed, actionable responses with code examples when appropriate.",
            "Focus on practical implementation details.",
        ]
        
        # Add project context if available
        metadata = prompt.get('metadata', {}) or {}
        project_id = metadata.get('project_id')
        
        if project_id:
            project = self.aipm.projects.get_project(project_id)
            if project:
                context_parts.append(f"\nCurrent Project: {project.name}")
                context_parts.append(f"Goal: {project.goal}")
                
                if project.path:
                    context_parts.append(f"Location: {project.path}")
        
        return "\n".join(context_parts)
    
    def update_dashboard(self):
        """Update the ASCII dashboard"""
        from pathlib import Path
        
        lines = [
            "╔══════════════════════════════════════════════════════════════════════╗",
            "║                  AIPM CONTINUOUS PROCESSING                           ║",
            f"║                  Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                         ║",
            "╚══════════════════════════════════════════════════════════════════════╝",
            "",
            f"📊 Statistics:",
            f"   Processed: {self.processed_count}",
            f"   Errors: {self.error_count}",
            f"   Model: {self.model}",
            "",
        ]
        
        # Add project status
        projects = self.aipm.list_projects()
        for p in projects[:3]:
            stats = self.aipm.projects.get_project_stats(p.id)
            bar = self._progress_bar(stats['completion_percentage'])
            lines.append(f"📦 {p.name}: [{bar}] {stats['completion_percentage']:.1f}%")
        
        # Add queue status
        stats = self.aipm.get_stats()
        queue = stats['queue']
        lines.append("")
        lines.append(f"📝 Queue: {queue.get('pending_count', 0)} pending | {queue.get('completed_count', 0)} completed")
        
        # Write dashboard
        dashboard_path = Path.home() / ".aipm" / "ascii" / "continuous_loop.ascii"
        dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        dashboard_path.write_text("\n".join(lines))
    
    def _progress_bar(self, percentage: float, width: int = 20) -> str:
        """Create a progress bar"""
        filled = int(percentage / 100 * width)
        return "█" * filled + "░" * (width - filled)
    
    async def run(self):
        """Run the continuous loop"""
        print("╔══════════════════════════════════════════════════════════════════════╗")
        print("║               AIPM CONTINUOUS PROCESSING LOOP                         ║")
        print("╚══════════════════════════════════════════════════════════════════════╝")
        print(f"\n⚙️  Configuration:")
        print(f"   Interval: {self.interval} seconds")
        print(f"   Model: {self.model}")
        if self.max_prompts:
            print(f"   Max prompts: {self.max_prompts}")
        if self.project_filter:
            print(f"   Project filter: {self.project_filter}")
        print(f"\n🚀 Starting loop... (Ctrl+C to stop)\n")
        
        # Initial model check
        if not await self.check_model():
            print("\n❌ No model available. Please load a model in LM Studio first:")
            print(f"   1. Open LM Studio")
            print(f"   2. Load model: {self.model}")
            print(f"   3. Restart this script")
            return
        
        iteration = 0
        
        while self.running:
            iteration += 1
            
            try:
                # Check if we've hit max
                if self.max_prompts and self.processed_count >= self.max_prompts:
                    print(f"\n✅ Reached max prompts ({self.max_prompts}). Stopping.")
                    break
                
                # Try to process a prompt
                processed = await self.process_one()
                
                if processed:
                    # Update dashboard after each successful process
                    self.update_dashboard()
                else:
                    # No prompt available or filtered out
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] No prompts to process, waiting {self.interval}s...")
                
                # Wait for next interval
                if self.running:
                    await asyncio.sleep(self.interval)
            
            except Exception as e:
                print(f"\n❌ Error in loop: {e}")
                self.error_count += 1
                
                # Wait before retrying
                if self.running:
                    await asyncio.sleep(self.interval * 2)
        
        # Final summary
        print("\n" + "=" * 70)
        print("📊 FINAL SUMMARY")
        print("=" * 70)
        print(f"   Iterations: {iteration}")
        print(f"   Processed: {self.processed_count}")
        print(f"   Errors: {self.error_count}")
        print("=" * 70)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="AIPM Continuous Loop")
    parser.add_argument("--interval", "-i", type=int, default=60, help="Interval between prompts (seconds)")
    parser.add_argument("--max", "-m", type=int, default=None, help="Maximum prompts to process")
    parser.add_argument("--project", "-p", type=str, default=None, help="Filter by project name")
    parser.add_argument("--model", type=str, default=None, help="Model to use")
    
    args = parser.parse_args()
    
    loop = ContinuousLoop(
        interval=args.interval,
        max_prompts=args.max,
        project_filter=args.project,
        model=args.model,
    )
    
    asyncio.run(loop.run())


if __name__ == "__main__":
    main()
