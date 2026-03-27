"""
Self-Prompting Loop - The AI generates its own prompts

Instead of a fixed goal, the AI:
1. Reads its state (what it's been working on, what worked/didn't)
2. Generates its own prompt about what to explore next
3. Executes that prompt
4. Reflects on results and generates the next prompt
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import json
import anthropic
import os


@dataclass
class SelfPromptState:
    """Persistent state for the self-prompting loop."""
    current_focus: str = "Initialize the system"
    prompts_tried: list = field(default_factory=list)
    insights: list = field(default_factory=list)
    iterations: int = 0
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self):
        return {
            "current_focus": self.current_focus,
            "prompts_tried": self.prompts_tried[-20:],  # Keep last 20
            "insights": self.insights[-10:],  # Keep last 10 insights
            "iterations": self.iterations,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def load(cls, path: Path) -> "SelfPromptState":
        if not path.exists():
            return cls()
        with open(path) as f:
            data = json.load(f)
        return cls(
            current_focus=data.get("current_focus", "Initialize"),
            prompts_tried=data.get("prompts_tried", []),
            insights=data.get("insights", []),
            iterations=data.get("iterations", 0),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
        )

    def save(self, path: Path):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


class SelfPrompter:
    """
    Generates prompts for itself based on past experience.

    The AI reflects on what it's tried and generates its own next prompt.
    """

    REFLECTION_PROMPT = """You are an AI engaged in recursive self-improvement.

## Your Current State
- Focus: {current_focus}
- Iterations completed: {iterations}
- Recent prompts you've tried:
{prompts_history}

## Insights You've Gained
{insights}

## Your Task
Based on your experience, generate your NEXT prompt to yourself.

Guidelines:
1. Be specific about what you want to explore or improve
2. Learn from what worked and what didn't
3. You can pivot to a completely new direction if stuck
4. Keep prompts actionable and measurable

Output format:
```
FOCUS: [What you're focusing on this iteration]
PROMPT: [The actual prompt you'll execute]
EXPECTED: [What success looks like]
```
"""

    def __init__(self, state_path: Path):
        self.state_path = state_path
        self.state = SelfPromptState.load(state_path)
        self.client = anthropic.Anthropic() if os.getenv("ANTHROPIC_API_KEY") else None

    def generate_next_prompt(self) -> dict:
        """Generate the next prompt based on reflection."""

        if not self.client:
            return self._mock_prompt()

        # Format history
        prompts_history = "\n".join(
            f"  - {p}" for p in self.state.prompts_tried[-5:]
        ) or "  (none yet)"

        insights = "\n".join(
            f"  - {i}" for i in self.state.insights[-3:]
        ) or "  (none yet)"

        prompt = self.REFLECTION_PROMPT.format(
            current_focus=self.state.current_focus,
            iterations=self.state.iterations,
            prompts_history=prompts_history,
            insights=insights,
        )

        response = self.client.messages.create(
            model="claude-sonnet-4-6-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._parse_response(response.content[0].text)

    def _parse_response(self, text: str) -> dict:
        """Parse the AI's response into structured prompt."""
        lines = text.split("\n")
        result = {"focus": "", "prompt": "", "expected": ""}

        current = None
        for line in lines:
            if line.startswith("FOCUS:"):
                current = "focus"
                result["focus"] = line.replace("FOCUS:", "").strip()
            elif line.startswith("PROMPT:"):
                current = "prompt"
                result["prompt"] = line.replace("PROMPT:", "").strip()
            elif line.startswith("EXPECTED:"):
                current = "expected"
                result["expected"] = line.replace("EXPECTED:", "").strip()
            elif current and line.strip():
                result[current] += " " + line.strip()

        return result

    def _mock_prompt(self) -> dict:
        """Generate mock prompt when no API key."""
        prompts = [
            {"focus": "Test coverage", "prompt": "Write tests for the core loop module", "expected": "Coverage increases by 10%"},
            {"focus": "Code quality", "prompt": "Refactor the prompt generator for clarity", "expected": "Cyclomatic complexity decreases"},
            {"focus": "Documentation", "prompt": "Add docstrings to all public functions", "expected": "All functions documented"},
            {"focus": "Performance", "prompt": "Optimize the tree traversal algorithm", "expected": "Faster tree operations"},
        ]
        return prompts[self.state.iterations % len(prompts)]

    def record_result(self, prompt: str, result: str, insight: str):
        """Record what happened after executing a prompt."""
        self.state.prompts_tried.append(prompt[:100])
        if insight:
            self.state.insights.append(insight[:200])
        self.state.iterations += 1
        self.state.save(self.state_path)

    def update_focus(self, new_focus: str):
        """Update the current focus area."""
        self.state.current_focus = new_focus
        self.state.save(self.state_path)


def run_self_prompt_loop(state_dir: Path, max_iterations: int = 10):
    """
    Run the self-prompting loop.

    Each iteration:
    1. AI reflects on past experience
    2. AI generates its own next prompt
    3. AI executes that prompt
    4. AI records results and insights
    5. Loop continues
    """
    state_path = state_dir / "self_prompt_state.json"
    self_prompter = SelfPrompter(state_path)

    print("🐍 Self-Prompting Loop Starting")
    print(f"   State: {state_path}")
    print(f"   Current focus: {self_prompter.state.current_focus}")
    print(f"   Iterations so far: {self_prompter.state.iterations}")
    print()

    for i in range(max_iterations):
        print(f"─" * 50)
        print(f"🔄 Iteration {self_prompter.state.iterations + 1}")

        # Generate next prompt
        next_prompt = self_prompter.generate_next_prompt()
        print(f"📍 Focus: {next_prompt['focus']}")
        print(f"📝 Prompt: {next_prompt['prompt'][:80]}...")
        print(f"🎯 Expected: {next_prompt['expected']}")
        print()

        # Here you would execute the prompt
        # For now, we just record it
        result = f"Executed: {next_prompt['prompt'][:50]}"
        insight = f"Learned from focusing on {next_prompt['focus']}"

        self_prompter.record_result(
            prompt=next_prompt['prompt'],
            result=result,
            insight=insight
        )
        self_prompter.update_focus(next_prompt['focus'])

        print(f"✅ Recorded. Total iterations: {self_prompter.state.iterations}")

    print()
    print("🏁 Loop complete. State saved.")
    return self_prompter.state


if __name__ == "__main__":
    import sys
    state_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".ouroboros")
    state_dir.mkdir(exist_ok=True)
    run_self_prompt_loop(state_dir, max_iterations=5)
