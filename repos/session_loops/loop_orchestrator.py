import os
import asyncio
import subprocess
import time
from pathlib import Path
from datetime import datetime

# AIPM loop logic imports (assuming they are in the python path)
# We can use 'hermes' directly as it is the execution layer.

class SessionLoop:
    """
    An autonomous session loop that iterates using local Ollama (via hermes)
    and only 'yields' to the Gemini CLI (Orchestrator) when stuck.
    """

    def __init__(self, workspace_path: str, goal: str, model: str = "qwen3.5-tools"):
        self.workspace = Path(workspace_path)
        self.goal = goal
        self.model = model
        self.log_path = self.workspace.parent / "summary_log.md"
        self.history = []
        self.failures = 0
        self.max_local_failures = 3

    def log(self, message: str):
        """Append to the summary log for the high-level orchestrator."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_path, "a") as f:
            f.write(f"[{timestamp}] {message}\n")
        print(f"[{timestamp}] {message}")

    async def run_step(self, prompt: str):
        """Run a single step using hermes with the local model."""
        cmd = [
            "hermes", "chat", 
            "-m", self.model,
            "-q", prompt,
            "-Q", "--yolo",
            "-t", "terminal,file"
        ]
        
        self.log(f"Running step with {self.model}...")
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        exit_code = proc.returncode
        output = stdout.decode() + stderr.decode()
        
        return exit_code, output

    async def start(self):
        """Main autonomous loop."""
        self.log(f"--- Starting Autonomous Session ---")
        self.log(f"Goal: {self.goal}")
        
        current_prompt = f"Objective: {self.goal}\n\nPlease begin working in the current directory."
        
        while True:
            exit_code, output = await self.run_step(current_prompt)
            
            if exit_code == 0:
                self.failures = 0
                self.log("Step completed successfully.")
                # We can extract a 'next step' or summary from the output if needed.
                # For now, we just ask the model to 'continue until finished'.
                current_prompt = "Excellent. What is the next step to reach the goal? Continue working."
            else:
                self.failures += 1
                self.log(f"Step failed (exit {exit_code}). Failure {self.failures}/{self.max_local_failures}")
                
                if self.failures >= self.max_local_failures:
                    self.log("!!! CRITICAL STALL: Yielding to Orchestrator (Gemini CLI) !!!")
                    # Here we would effectively 'stop' and wait for the Gemini CLI 
                    # main loop to see the summary_log.md and intervene.
                    break
                
                current_prompt = f"The previous step failed with output:\n{output[-1000:]}\n\nPlease diagnose and try a different approach."

            # Heartbeat/Sleep to prevent CPU thrashing
            await asyncio.sleep(2)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python loop_orchestrator.py 'your goal here'")
        sys.exit(1)
        
    goal = sys.argv[1]
    loop = SessionLoop(workspace_path="./repos/session_loops/workspace", goal=goal)
    asyncio.run(loop.start())
