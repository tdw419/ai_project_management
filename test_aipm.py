#!/usr/bin/env python3
"""
AIPM Test - Process an OpenMind prompt
"""

import asyncio
import httpx
from aipm import AIPM

async def main():
    aipm = AIPM()
    
    # Get the next OpenMind prompt
    prompts = aipm.ctrm.dequeue(limit=1)
    
    if not prompts:
        print("No pending prompts")
        return
    
    prompt = prompts[0]
    print(f"Processing: {prompt['id']}")
    print(f"Priority: {prompt['priority']}")
    print(f"Prompt: {prompt['prompt'][:150]}...")
    print()
    
    # Mark as processing
    aipm.ctrm.mark_processing(prompt['id'])
    
    # Process with LM Studio - use chat completions API
    bridge = SimpleQueueBridge()
    
    # Add context about OpenMind
    messages = [
        {"role": "system", "content": "Please help with the OpenMind project - a neural attention visualization tool. Current State: Phase 1 Complete (1,000 Wikipedia articles, 32 clusters, ~600ms latency. Phase 2 Next: Streaming attention (token-by-token saccade animation). Project Location: ~/zion/projects/openmind. Key Files: bin/inference-engine.py, bin/render-real-saccades.py. cortex/ - 79,946 tiles from distilgpt2. archive/ - 1,000 documents with embeddings."},
    ]
    
    full_prompt = f"""Task: {prompt['prompt']}

Provide a detailed implementation plan with code examples."""
    
    messages.append({"role": "user", "content": full_prompt})
    
    print("Sending to LM Studio (chat mode)...")
    result = await bridge.process_chat(
        messages=messages,
        max_tokens=4096,
        temperature=0.7,
    )
    
    if result.success:
        print(f"\n=== RESULT (via {result.provider}, {result.wait_time_ms}ms) ===\n")
        print(result.content)
        
        # Mark as completed
        aipm.ctrm.complete(
                prompt_id=prompt['id'],
                result=result.content,
                verified=True,
                notes=f"Processed via {result.provider}"
            )
            print(f"\n✓ Prompt completed: {prompt['id']}")
        else:
            print(f"Error: {result.error}")
            aipm.ctrm.complete(
                prompt_id=prompt['id'],
                result=f"Error: {result.error}",
                verified=False,
            )

if __name__ == "__main__":
    asyncio.run(main())
