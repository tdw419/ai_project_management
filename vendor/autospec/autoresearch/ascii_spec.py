"""
ASCII Experiment Spec Parser

Converts ASCII experiment specs to Python objects for AutoResearch.

Layer 0: Minimal 4-line format (H/T/M/B)
Layer 1: Boxed format
Layer 2: Flow diagrams
Layer 3: Full with history
"""

import re
from dataclasses import dataclass, field
from typing import Optional, Dict, List


@dataclass
class ASCIISpec:
    """Parsed ASCII experiment spec."""
    hypothesis: str
    target: str
    metric: str
    budget_minutes: int
    experiment_id: Optional[str] = None
    flow: List[str] = field(default_factory=lambda: ['HYP', 'RUN', 'EVAL', 'DECIDE'])
    history: List[Dict] = field(default_factory=list)
    state: str = 'PENDING'
    raw_text: str = ''
    
    # Derived fields
    metric_operator: str = '<'  # '<', '>', '<=', '>='
    metric_value: float = 0.0
    lower_is_better: bool = True
    
    def __post_init__(self):
        """Parse metric into operator and value."""
        self._parse_metric()
    
    def _parse_metric(self):
        """Extract operator and value from metric string."""
        # Match patterns like "val_bpb < 0.7" or "accuracy > 0.95"
        match = re.match(r'(.+?)\s*([<>=!]+)\s*([\d.]+)', self.metric)
        if match:
            self.metric_name = match.group(1).strip()
            self.metric_operator = match.group(2)
            self.metric_value = float(match.group(3))
            self.lower_is_better = '<' in self.metric_operator
        else:
            # Default: just extract the metric name
            self.metric_name = self.metric
            self.metric_operator = '<'
            self.metric_value = 0.0
            self.lower_is_better = True


class ASCIISpecParser:
    """Parser for ASCII experiment specs."""
    
    # Regex patterns for each layer
    LAYER0_PATTERN = r'[│\s]*([HTMB]):\s*(.+?)\s*[│\n]' 
    BOX_PATTERN = r'┌[─]+┐\n(.+?)\n└[─]+┘'
    FLOW_PATTERN = r'FLOW:\s*(.+)'
    HISTORY_PATTERN = r'Run\s+(\d+):\s+(\w+)=([\d.]+)\s+(\w+)'
    STATE_PATTERN = r'STATE:\s*(\w+)'
    
    def parse(self, spec_text: str) -> ASCIISpec:
        """Parse ASCII spec text into ASCIISpec object.
        
        Auto-detects layer and parses accordingly.
        """
        # Try to extract key-value pairs (works for all layers)
        kv_pairs = self._extract_key_values(spec_text)
        
        # Check for experiment ID
        exp_id = self._extract_experiment_id(spec_text)
        
        # Check for flow
        flow = self._extract_flow(spec_text)
        
        # Check for history
        history = self._extract_history(spec_text)
        
        # Check for state
        state = self._extract_state(spec_text)
        
        # Parse budget (handles "5", "5m", "5 min", etc.)
        budget = self._parse_budget(kv_pairs.get('B', '30'))
        
        return ASCIISpec(
            hypothesis=kv_pairs.get('H', ''),
            target=kv_pairs.get('T', ''),
            metric=kv_pairs.get('M', ''),
            budget_minutes=budget,
            experiment_id=exp_id,
            flow=flow,
            history=history,
            state=state,
            raw_text=spec_text
        )
    
    def _extract_key_values(self, text: str) -> Dict[str, str]:
        """Extract H/T/M/B key-value pairs from text."""
        matches = re.findall(self.LAYER0_PATTERN, text, re.MULTILINE)
        return {k: v.strip() for k, v in matches}
    
    def _extract_experiment_id(self, text: str) -> Optional[str]:
        """Extract experiment ID from header."""
        match = re.search(r'EXPERIMENT:\s*(.+?)(?:\n|├)', text)
        if match:
            return match.group(1).strip()
        match = re.search(r'SUITE:\s*(.+?)(?:\n|├)', text)
        if match:
            return match.group(1).strip()
        return None
    
    def _extract_flow(self, text: str) -> List[str]:
        """Extract flow stages from FLOW line."""
        match = re.search(self.FLOW_PATTERN, text)
        if match:
            flow_text = match.group(1)
            # Split by arrow and clean up
            stages = [s.strip() for s in re.split(r'[→>-]+', flow_text)]
            return stages
        return ['HYP', 'RUN', 'EVAL', 'DECIDE']
    
    def _extract_history(self, text: str) -> List[Dict]:
        """Extract run history from HISTORY section."""
        matches = re.findall(self.HISTORY_PATTERN, text)
        history = []
        for run_num, metric_name, metric_val, action in matches:
            history.append({
                'run': int(run_num),
                'metric_name': metric_name,
                'metric_value': float(metric_val),
                'action': action
            })
        return history
    
    def _extract_state(self, text: str) -> str:
        """Extract current state from STATE line."""
        match = re.search(self.STATE_PATTERN, text)
        if match:
            return match.group(1)
        return 'PENDING'
    
    def _parse_budget(self, budget_str: str) -> int:
        """Parse budget string into minutes.
        
        Examples: "5", "5m", "5 min", "5 minutes"
        """
        # Extract number
        match = re.search(r'(\d+)', budget_str)
        if match:
            return int(match.group(1))
        return 30  # Default


class ASCIISpecRenderer:
    """Renders ASCIISpec objects to ASCII text."""
    
    def render(self, spec: ASCIISpec, layer: int = 3) -> str:
        """Render spec to ASCII at specified layer.
        
        Args:
            spec: The spec to render
            layer: 0=minimal, 1=boxed, 2=flow, 3=full
        """
        if layer == 0:
            return self._render_layer0(spec)
        elif layer == 1:
            return self._render_layer1(spec)
        elif layer == 2:
            return self._render_layer2(spec)
        else:
            return self._render_layer3(spec)
    
    def _render_layer0(self, spec: ASCIISpec) -> str:
        """Minimal 4-line format."""
        return f"""H: {spec.hypothesis}
T: {spec.target}
M: {spec.metric}
B: {spec.budget_minutes}"""
    
    def _render_layer1(self, spec: ASCIISpec) -> str:
        """Boxed format."""
        exp_id = spec.experiment_id or "experiment"
        lines = [
            f"┌{'─' * 40}┐",
            f"│ EXPERIMENT: {exp_id:<28}│",
            f"├{'─' * 40}┤",
            f"│ H: {spec.hypothesis:<35}│",
            f"│ T: {spec.target:<35}│",
            f"│ M: {spec.metric:<35}│",
            f"│ B: {spec.budget_minutes}m{' ' * 35}│",
            f"└{'─' * 40}┘"
        ]
        return '\n'.join(lines)
    
    def _render_layer2(self, spec: ASCIISpec) -> str:
        """Boxed with flow."""
        exp_id = spec.experiment_id or "experiment"
        flow_str = ' → '.join(spec.flow)
        lines = [
            f"┌{'─' * 44}┐",
            f"│ EXPERIMENT: {exp_id:<30}│",
            f"├{'─' * 44}┤",
            f"│ H: {spec.hypothesis:<39}│",
            f"│ T: {spec.target:<39}│",
            f"│ M: {spec.metric:<39}│",
            f"│ B: {spec.budget_minutes}m{' ' * 39}│",
            f"├{'─' * 44}┤",
            f"│ FLOW: {flow_str:<36}│",
            f"└{'─' * 44}┘"
        ]
        return '\n'.join(lines)
    
    def _render_layer3(self, spec: ASCIISpec) -> str:
        """Full format with history."""
        exp_id = spec.experiment_id or "experiment"
        flow_str = ' → '.join(spec.flow)
        
        lines = [
            f"┌{'─' * 48}┐",
            f"│ EXPERIMENT: {exp_id:<34}│",
            f"├{'─' * 48}┤",
            f"│ H: {spec.hypothesis:<43}│",
            f"│ T: {spec.target:<43}│",
            f"│ M: {spec.metric:<43}│",
            f"│ B: {spec.budget_minutes}m{' ' * 43}│",
            f"├{'─' * 48}┤",
            f"│ FLOW: {flow_str:<40}│",
        ]
        
        if spec.history:
            lines.append(f"├{'─' * 48}┤")
            lines.append(f"│ HISTORY:{' ' * 38}│")
            for run in spec.history:
                action_mark = '✓' if run['action'] == 'KEEP' else '✗'
                lines.append(f"│  Run {run['run']}: {run['metric_name']}={run['metric_value']:.2f} {run['action']} {action_mark}{' ' * 16}│")
        
        lines.extend([
            f"├{'─' * 48}┤",
            f"│ STATE: {spec.state:<40}│",
            f"└{'─' * 48}┘"
        ])
        
        return '\n'.join(lines)


def render_result(result, spec: Optional[ASCIISpec] = None) -> str:
    """Render an ExperimentResult to ASCII.
    
    Args:
        result: ExperimentResult object
        spec: Optional original spec for context
    """
    status_mark = '✓' if result.status.value == 'keep' else '✗'
    status_str = result.status.value.upper()
    
    # Determine if it was an improvement
    improved = result.status.value == 'keep'
    
    lines = [
        f"┌{'─' * 44}┐",
        f"│ RESULT: {spec.experiment_id if spec else 'experiment':<34}│",
        f"├{'─' * 44}┤",
        f"│ STATUS: {status_str} {status_mark}{' ' * (35 - len(status_str))}│",
        f"│ METRIC: {result.metric:.4f}{' ' * 34}│",
        f"│ COMMIT: {result.commit_hash[:12]}{' ' * 35}│",
        f"├{'─' * 44}┤",
        f"│ {result.description:<42}│",
        f"└{'─' * 44}┘"
    ]
    
    return '\n'.join(lines)


# Convenience functions

def parse_ascii_spec(spec_text: str) -> ASCIISpec:
    """Parse ASCII spec text into ASCIISpec object."""
    parser = ASCIISpecParser()
    return parser.parse(spec_text)


def render_ascii_spec(spec: ASCIISpec, layer: int = 3) -> str:
    """Render ASCIISpec to ASCII text."""
    renderer = ASCIISpecRenderer()
    return renderer.render(spec, layer)


# Example usage
if __name__ == '__main__':
    # Layer 0 example
    layer0 = """H: Use AdamW optimizer instead of SGD
T: src/train.py
M: val_bpb < 0.7
B: 5"""
    
    spec = parse_ascii_spec(layer0)
    print("=== Layer 0 ===")
    print(f"Hypothesis: {spec.hypothesis}")
    print(f"Target: {spec.target}")
    print(f"Metric: {spec.metric} (operator: {spec.metric_operator}, value: {spec.metric_value})")
    print(f"Budget: {spec.budget_minutes} minutes")
    print(f"Lower is better: {spec.lower_is_better}")
    print()
    
    # Render to layer 3
    print("=== Rendered to Layer 3 ===")
    print(render_ascii_spec(spec, layer=3))
