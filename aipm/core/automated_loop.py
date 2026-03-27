#!/usr/bin/env python3
"""
Automated Prompt Loop - Self-Sustaining Prompt Management

The complete automation cycle:
1. PRIORITIZE - Score all pending prompts
2. SELECT - Get highest-scored prompt
3. PROCESS - Execute via LLM
4. GENERATE - Create follow-up prompts from result
5. ENQUEUE - Add new prompts to queue
6. REPEAT
"""

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

# Add AutoSpec integration (vendored)
try:
    from autospec.autoresearch.loop import ExperimentLoop, Hypothesis
    HAS_AUTOSPEC = True
except ImportError:
    HAS_AUTOSPEC = False

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "vendor"))

from aipm.core.ctrm_prompt_manager import CTRMPromptManager, CTRM_DB
from aipm.core.prompt_prioritizer import PromptPrioritizer, PromptGenerator


class AutomatedPromptLoop:
    """
    Self-sustaining prompt management loop.
    
    Usage:
        loop = AutomatedPromptLoop()
        
        # Run once
        await loop.run_once()
        
        # Run continuously
        await loop.run_forever(interval_seconds=60)
    """
    
    def __init__(self, db_path: Path = CTRM_DB):
        self.db_path = db_path
        self.manager = CTRMPromptManager(db_path)
        self.prioritizer = PromptPrioritizer(db_path)
        self.generator = PromptGenerator(db_path)
        
        # Add AutoSpec experiment tracking
        if HAS_AUTOSPEC:
            self.experiment_loop = ExperimentLoop(
                project_path=Path(__file__).parent.parent.parent.parent,
                target_file="results.tsv",
                eval_command="pytest tests/ -q"
            )
            print("✅ AutoSpec ExperimentLoop initialized")
        else:
            self.experiment_loop = None
            
        self.stats = {
            'processed': 0,
            'generated': 0,
            'errors': 0
        }
    
    async def run_once(self, dry_run: bool = False) -> Optional[Dict]:
        """
        Run one cycle of the loop.
        
        Args:
            dry_run: If True, don't actually process (just show what would happen)
        
        Returns:
            Result dict or None if no prompts pending
        """
        # 1. PRIORITIZE - Get highest-scored prompt
        next_result = self.prioritizer.get_next_one()
        
        if not next_result:
            print("📭 No pending prompts")
            return None
        
        prompt, score = next_result
        prompt_id = prompt['id']
        prompt_text = prompt['prompt']
        
        print(f"\n{'='*60}")
        print(f"🎯 PROCESSING PROMPT (Score: {score:.2f})")
        print(f"{'='*60}")
        print(f"ID: {prompt_id}")
        print(f"Priority: {prompt['priority']}")
        print(f"Confidence: {prompt.get('ctrm_confidence', 0):.2f}")
        print(f"\nPrompt: {prompt_text[:200]}...")
        
        if dry_run:
            print("\n⚠️  DRY RUN - Would process this prompt")
            return {'prompt': prompt, 'score': score, 'dry_run': True}
        
        # 2. MARK AS PROCESSING
        self.manager.mark_processing(prompt_id)
        
        try:
            # 3. PROCESS - Execute via queue bridge
            # (In production, this would call the actual LLM)
            print("\n⏳ Processing via LLM...")
            
            # Simulate result for now
            result = await self._process_prompt(prompt_text)
            
            # AutoSpec: Check if response contains H/T/M/B experiment
            if self.experiment_loop and result.get('content'):
                self._run_autospec_experiment(result.get('content', ''), prompt_id)
            
            # 4. COMPLETE - Store result
            self.manager.complete(
                prompt_id,
                result=result.get('content', ''),
                verified=result.get('success', False),
                notes=f"Processed at {datetime.now().isoformat()}"
            )
            
            self.stats['processed'] += 1
            print(f"\n✅ Completed: {prompt_id}")
            
            # 5. ANALYZE - Analyze response quality
            from aipm.core.response_analyzer import PromptResponseAnalyzer
            analyzer = PromptResponseAnalyzer()
            analysis = analyzer.analyze_response(prompt_id)
            
            if analysis:
                print(f"\n📊 Quality: {analysis.quality.value.upper()} ({analysis.confidence:.0%})")
                if analysis.needs_followup:
                    print(f"   ⚠️  {analysis.followup_reason}")
                
                # Store analysis
                analyzer.store_analysis(analysis)
            
            # 6. GENERATE - Create follow-up prompts
            new_prompts = self.generator.generate_from_results(
                prompt_text,
                result.get('content', '')
            )
            
            # Add intelligent follow-ups from analyzer
            if analysis and analysis.suggested_prompts:
                new_prompts.extend(analysis.suggested_prompts[:3])
            
            # Also check for gaps
            gap_prompts = self.generator.generate_from_gaps()
            new_prompts.extend(gap_prompts[:2])  # Limit gap prompts
            
            # 7. ENQUEUE - Add new prompts
            for new_prompt in new_prompts:
                self.manager.enqueue(
                    new_prompt,
                    priority=prompt['priority'] + 1,  # Lower priority than parent
                    source=f"auto:followup:{prompt_id}"
                )
                self.stats['generated'] += 1
            
            if new_prompts:
                print(f"\n📝 Generated {len(new_prompts)} follow-up prompts")
            
            return {
                'prompt': prompt,
                'score': score,
                'result': result,
                'analysis': analysis,
                'new_prompts': new_prompts
            }
            
        except Exception as e:
            self.stats['errors'] += 1
            print(f"\n❌ Error: {e}")
            
            # Mark as failed
            self.manager.complete(
                prompt_id,
                result=f"Error: {str(e)}",
                verified=False,
                notes="Processing failed"
            )
            
            return {'prompt': prompt, 'error': str(e)}
    
    async def _process_prompt(self, prompt_text: str) -> Dict:
        """
        Process a prompt via LLM.
        
        In production, this would use the queue bridge.
        For now, returns a simulated result.
        """
        # TODO: Wire up to actual LLM via queue_bridge
        # result = await self.bridge.process_prompt_async(prompt_text)
        
        # Simulate processing delay
        await asyncio.sleep(0.5)
        
        # Simulate result
        return {
            'success': True,
            'content': f"Processed: {prompt_text[:100]}...\n\nResult: Analysis complete. TODO: Add implementation details."
        }
    
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
    
    async def run_forever(self, 
                          interval_seconds: int = 60,
                          max_iterations: int = 100):
        """
        Run the loop continuously.
        
        Args:
            interval_seconds: Wait time between iterations
            max_iterations: Maximum iterations before stopping
        """
        print(f"\n🔄 Starting Automated Prompt Loop")
        print(f"   Interval: {interval_seconds}s")
        print(f"   Max iterations: {max_iterations}")
        print(f"   Press Ctrl+C to stop\n")
        
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            print(f"\n{'─'*60}")
            print(f"Iteration {iteration}/{max_iterations} | {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'─'*60}")
            
            try:
                result = await self.run_once()
                
                if result is None:
                    print("No more prompts to process")
                    break
                
            except KeyboardInterrupt:
                print("\n\n⏹️  Stopped by user")
                break
            except Exception as e:
                print(f"\n❌ Iteration failed: {e}")
            
            # Show stats
            print(f"\n📊 Stats: {self.stats['processed']} processed, "
                  f"{self.stats['generated']} generated, "
                  f"{self.stats['errors']} errors")
            
            # Wait for next iteration
            if iteration < max_iterations:
                print(f"\n⏳ Waiting {interval_seconds}s for next iteration...")
                await asyncio.sleep(interval_seconds)
        
        print(f"\n{'='*60}")
        print(f"LOOP COMPLETE")
        print(f"{'='*60}")
        print(f"Total processed: {self.stats['processed']}")
        print(f"Total generated: {self.stats['generated']}")
        print(f"Total errors: {self.stats['errors']}")
    
    def show_next_n(self, n: int = 10):
        """Show the next N prompts to process."""
        scored = self.prioritizer.get_next_prompt(limit=n)
        
        print(f"\n{'='*70}")
        print(f"NEXT {n} PROMPTS TO PROCESS")
        print(f"{'='*70}\n")
        
        for i, (prompt, score) in enumerate(scored, 1):
            text = prompt['prompt'][:60]
            priority = prompt['priority']
            confidence = prompt.get('ctrm_confidence', 0)
            
            print(f"{i:2}. [Score: {score:.2f}] [P{priority}] [Conf: {confidence:.2f}]")
            print(f"    {text}...")
            print()
    
    def get_stats(self) -> Dict:
        """Get loop statistics."""
        queue_stats = self.manager.get_stats()
        
        return {
            'loop': self.stats,
            'queue': queue_stats
        }


# === CLI ===

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Automated Prompt Loop")
    parser.add_argument("command", choices=["once", "forever", "next", "stats"])
    parser.add_argument("--dry-run", action="store_true", help="Don't actually process")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between iterations")
    parser.add_argument("--max", type=int, default=100, help="Max iterations")
    parser.add_argument("--limit", type=int, default=10, help="Limit for 'next'")
    
    args = parser.parse_args()
    
    loop = AutomatedPromptLoop()
    
    if args.command == "once":
        asyncio.run(loop.run_once(dry_run=args.dry_run))
    
    elif args.command == "forever":
        asyncio.run(loop.run_forever(
            interval_seconds=args.interval,
            max_iterations=args.max
        ))
    
    elif args.command == "next":
        loop.show_next_n(args.limit)
    
    elif args.command == "stats":
        stats = loop.get_stats()
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
