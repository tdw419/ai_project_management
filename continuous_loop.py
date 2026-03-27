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
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add AIPM to path (package is at ./aipm/, not ./src/aipm/)
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "vendor"))

from aipm import AIPM, get_aipm
from aipm.core.simple_bridge import SimpleQueueBridge
from aipm.core.extended_providers import PiAgentProvider, PiAgentConfig
from aipm.config import DEFAULT_REASONING_MODEL, DEFAULT_VISION_MODEL, DEFAULT_PI_MODEL

# RAG World Model for grounded context (Phase 1.1)
try:
    from aipm.rag_context import RAGWorldModel
    HAS_RAG = True
except ImportError:
    HAS_RAG = False

# Roadmap Processor for self-improvement (Ouroboros)
try:
    from aipm.roadmap_processor import RoadmapProcessor
    HAS_ROADMAP = True
except ImportError:
    HAS_ROADMAP = False

# Add AutoSpec integration (vendored)
try:
    from autospec.autoresearch.loop import ExperimentLoop, Hypothesis
    HAS_AUTOSPEC = True
except ImportError:
    HAS_AUTOSPEC = False


class ContinuousLoop:
    """Continuous prompt processing loop"""
    
    def __init__(
        self,
        interval: int = 60,
        max_prompts: Optional[int] = None,
        project_filter: Optional[str] = None,
        model: Optional[str] = None,
        use_pi: bool = False,
        pi_model: Optional[str] = None,
    ):
        self.aipm = get_aipm()
        self.bridge = SimpleQueueBridge()
        self.interval = interval
        self.max_prompts = max_prompts
        self.project_filter = project_filter
        self.model = model or DEFAULT_REASONING_MODEL
        self.use_pi = use_pi
        self.pi_model = pi_model or DEFAULT_PI_MODEL
        self.processed_count = 0
        self.error_count = 0
        self.running = True
        
        # Failover logic state (Phase 1.2)
        self.failover_active = False
        self.last_availability_check = 0
        self.check_cooldown = 300  # 5 minutes
        
        # Initialize Pi agent provider if requested
        if self.use_pi:
            self.pi_provider = PiAgentProvider(PiAgentConfig(
                repo_path=Path(__file__).parent,
                default_model=self.pi_model,
            ))
            print(f"✅ Pi Agent initialized with model: {self.pi_model}")
        else:
            self.pi_provider = None
        
        # Add AutoSpec experiment tracking
        if HAS_AUTOSPEC:
            self.experiment_loop = ExperimentLoop(
                project_path=Path(__file__).parent,
                target_file="results.tsv",
                eval_command="pytest tests/ -q"
            )
            print("✅ AutoSpec ExperimentLoop initialized")
        else:
            self.experiment_loop = None
        
        # RAG World Model for context injection (Phase 1.1)
        if HAS_RAG:
            self.rag = RAGWorldModel(Path(__file__).parent, self.aipm.ctrm)
            print("✅ RAG World Model initialized")
        else:
            self.rag = None
        
        # Roadmap Processor for self-improvement (Ouroboros)
        if HAS_ROADMAP:
            roadmap_path = Path(__file__).parent / "docs" / "ROADMAP.md"
            self.roadmap = RoadmapProcessor(roadmap_path, self.aipm.ctrm)
            self.roadmap.parse()
            pending = len(self.roadmap.get_pending_tasks())
            print(f"✅ Roadmap Processor initialized ({pending} pending tasks)")
        else:
            self.roadmap = None
        
        # Handle shutdown signals
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)
    
    def _shutdown(self, signum, frame):
        """Handle shutdown signals"""
        print("\n\n🛑 Shutdown signal received...")
        self.running = False
    
    async def check_availability(self) -> bool:
        """Check if primary LM Studio is available"""
        available = await self.bridge.is_available()
        self.last_availability_check = time.time()
        return available

    async def check_model(self) -> bool:
        """Check if a model is loaded"""
        if not await self.check_availability():
            return False

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
        
        # Failover check: If failover is active, check if LM Studio is back every check_cooldown seconds
        if self.failover_active:
            if time.time() - self.last_availability_check > self.check_cooldown:
                print("🔍 Checking if primary LM Studio has recovered...")
                if await self.check_availability():
                    print("✅ Primary LM Studio RECOVERED. Switching back from failover.")
                    self.failover_active = False
                else:
                    print(f"⌛ Primary LM Studio still unavailable. Remaining in failover for {self.check_cooldown}s.")
        
        # Process with Pi Agent or LM Studio
        start_time = time.time()
        
        # Decide provider based on failover state
        use_pi_now = self.failover_active or self.use_pi
        
        result = None
        if use_pi_now and self.pi_provider:
            # Use Pi agent with zai/glm-5
            failover_notice = " (FAILOVER MODE)" if self.failover_active else ""
            print(f"\n🤖 Using Pi Agent{failover_notice} with model: {self.pi_model}")
            result = await self.pi_provider.execute_task(
                task=f"{system_context}\n\n{prompt['prompt']}",
                model=self.pi_model,
            )
        else:
            # Attempt LM Studio
            try:
                # Use LM Studio
                result = await self.bridge.process_chat(
                    messages=[
                        {"role": "system", "content": system_context},
                        {"role": "user", "content": prompt['prompt']},
                    ],
                    model=self.model,
                    max_tokens=4096,
                    temperature=0.7,
                    auto_load=True,  # Ensure it tries to load if available
                )
                
                # If it failed due to connection, trigger failover
                if not result.success and ("connection" in result.error.lower() or "http" in result.error.lower()):
                    if self.use_pi and self.pi_provider:
                        print(f"⚠️  LM Studio connection FAILED: {result.error}")
                        print("🚨 Triggering FAILOVER to Pi Agent...")
                        self.failover_active = True
                        self.last_availability_check = time.time()
                        
                        # Immediately retry with Pi Agent
                        print(f"\n🤖 Using Pi Agent (FAILOVER MODE) with model: {self.pi_model}")
                        result = await self.pi_provider.execute_task(
                            task=f"{system_context}\n\n{prompt['prompt']}",
                            model=self.pi_model,
                        )
            except Exception as e:
                if self.use_pi and self.pi_provider:
                    print(f"⚠️  LM Studio process error: {e}")
                    print("🚨 Triggering FAILOVER to Pi Agent...")
                    self.failover_active = True
                    self.last_availability_check = time.time()
                    
                    # Retry with Pi Agent
                    result = await self.pi_provider.execute_task(
                        task=f"{system_context}\n\n{prompt['prompt']}",
                        model=self.pi_model,
                    )
                else:
                    # No failover available, wrap exception in result
                    from aipm.core.simple_bridge import PromptResult
                    result = PromptResult(success=False, content=None, provider="lm_studio", error=str(e))
        
        elapsed = time.time() - start_time
        
        if result and result.success:
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
            
            # AutoSpec: Check if response contains H/T/M/B experiment
            if self.experiment_loop and content:
                self._run_autospec_experiment(content, prompt['id'])
            
            # Mark as completed
            self.aipm.ctrm.complete(
                prompt['id'],
                result=content,
                verified=True,
                notes=f"Processed via {self.model} in {elapsed:.2f}s"
            )

            # Ouroboros: mark roadmap tasks as [x] in ROADMAP.md
            metadata = prompt.get('metadata', {}) or {}
            if metadata.get('source') == 'roadmap' and self.roadmap:
                desc = metadata.get('original_description', '')
                if desc and self.roadmap.mark_completed(desc):
                    print(f"  📋 Roadmap updated: [x] {desc[:60]}")

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
    
    def enqueue_roadmap_tasks(self, max_tasks: int = 5, phase_filter: str = None) -> int:
        """Auto-enqueue roadmap tasks when queue is low"""
        if not self.roadmap:
            return 0
        
        try:
            return self.roadmap.enqueue_tasks(phase_filter=phase_filter, max_tasks=max_tasks)
        except Exception as e:
            print(f"⚠️  Failed to enqueue roadmap tasks: {e}")
            return 0
    
    def _build_context(self, prompt: dict) -> str:
        """Build system context for the prompt"""
        context_parts = [
            "You are an AI assistant helping build software projects.",
            "Provide detailed, actionable responses with code examples when appropriate.",
            "Focus on practical implementation details.",
        ]
        
        # Add RAG World Model context (Phase 1.1)
        if self.rag:
            try:
                world_context = self.rag.get_context_for_prompt(max_age_hours=24)
                if world_context:
                    context_parts.append("\n" + world_context)
            except Exception as e:
                pass  # Silently ignore RAG errors
        
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
    
    def _run_autospec_experiment(self, content: str, prompt_id: str):
        """Extract hypothesis and run experiment via AutoSpec."""
        # Simple parsing for H/T/M/B
        lines = content.split('\n')
        h, t, m, b = "", "", "", ""
        for line in lines:
            line = line.strip(' │\t')
            if line.startswith('H:'): h = line[2:].strip()
            elif line.startswith('T:'): t = line[2:].strip()
            elif line.startswith('M:'): m = line[2:].strip()
            elif line.startswith('B:'): b = line[2:].strip()
        
        if h and t:
            # Find code block
            code_match = re.search(r'```python\n(.*?)```', content, re.DOTALL)
            if not code_match:
                code_match = re.search(r'```(?:\w+)?\n(.*?)```', content, re.DOTALL)
                
            code_changes = {t: code_match.group(1).strip()} if code_match else {}
            
            # Hypothesis from autospec
            hyp = Hypothesis(
                task_id=prompt_id,
                description=h,
                expected_improvement=0.1,
                code_changes=code_changes
            )
            
            print(f"\n🚀 Running AutoSpec Experiment: {h}")
            exp_result = self.experiment_loop.run(hyp)
            print(f"📊 AutoSpec Result: {exp_result.status.value} (Metric: {exp_result.metric})")
            
            return exp_result
        return None
    
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
        if self.use_pi:
            print(f"   Pi Agent: ✅ ENABLED (model: {self.pi_model})")
        if self.max_prompts:
            print(f"   Max prompts: {self.max_prompts}")
        if self.project_filter:
            print(f"   Project filter: {self.project_filter}")
        print(f"\n🚀 Starting loop... (Ctrl+C to stop)\n")
        
        # Auto-enqueue roadmap tasks on startup (Ouroboros)
        if self.roadmap:
            pending = len(self.roadmap.get_pending_tasks())
            if pending > 0:
                print(f"📋 Roadmap has {pending} pending tasks")
                # Enqueue up to 5 high-priority roadmap tasks
                enqueued = self.enqueue_roadmap_tasks(max_tasks=5, phase_filter="Phase 1")
                if enqueued > 0:
                    print(f"✅ Enqueued {enqueued} roadmap tasks for autonomous execution")
        
        # Initial model check (skip if using Pi agent)
        if not self.use_pi and not await self.check_model():
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
    parser.add_argument("--model", type=str, default=None, help="Model to use (for LM Studio)")
    parser.add_argument("--pi", action="store_true", help="Use Pi agent instead of LM Studio")
    parser.add_argument("--pi-model", type=str, default=None, help="Model for Pi agent (default: zai/glm-5)")
    
    args = parser.parse_args()
    
    loop = ContinuousLoop(
        interval=args.interval,
        max_prompts=args.max,
        project_filter=args.project,
        model=args.model,
        use_pi=args.pi,
        pi_model=args.pi_model,
    )
    
    asyncio.run(loop.run())


if __name__ == "__main__":
    main()
