"""
Evaluation Tools

Compare fusion results against individual model responses
to measure the quality improvement from synthesis.
"""

import asyncio
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .fusion import FusionOrchestrator, FusionResult
from .synthesis import create_comparison_prompt

console = Console()


@dataclass
class EvaluationScores:
    """Scores for a single response."""
    model: str
    factual_accuracy: float  # 1-10
    reasoning_depth: float   # 1-10
    completeness: float      # 1-10
    clarity: float           # 1-10
    
    @property
    def overall(self) -> float:
        """Weighted average score."""
        return (
            self.factual_accuracy * 0.3 +
            self.reasoning_depth * 0.3 +
            self.completeness * 0.2 +
            self.clarity * 0.2
        )


@dataclass
class EvaluationResult:
    """Complete evaluation of a fusion query."""
    prompt: str
    timestamp: str
    pool_name: str
    individual_scores: list[EvaluationScores]
    fused_scores: EvaluationScores
    improvement_pct: float  # How much better is fused vs best individual
    preferred_by_judge: str  # "fused" or model name
    judge_reasoning: str
    latency_ms: float
    

class FusionEvaluator:
    """
    Evaluates fusion quality by having an LLM judge compare
    individual responses against the fused output.
    """
    
    def __init__(self, orchestrator: FusionOrchestrator):
        self.orchestrator = orchestrator
        self.results_dir = Path("tests/benchmarks/results")
        self.results_dir.mkdir(parents=True, exist_ok=True)
    
    async def evaluate(
        self,
        prompt: str,
        pool: str = "general",
        judge_model: str = "deepseek/deepseek-r1:free",
    ) -> EvaluationResult:
        """
        Run a fusion query and evaluate the results.
        
        Args:
            prompt: Query to evaluate
            pool: Model pool to use
            judge_model: Model to use as evaluator
            
        Returns:
            EvaluationResult with scores and analysis
        """
        # Run fusion
        console.print("\n[bold]Running fusion query...[/bold]")
        fusion_result = await self.orchestrator.fuse(prompt, pool=pool)
        
        # Have judge evaluate all responses
        console.print("\n[bold]Evaluating responses...[/bold]")
        evaluation = await self._judge_responses(
            prompt,
            fusion_result,
            judge_model,
        )
        
        return evaluation
    
    async def _judge_responses(
        self,
        prompt: str,
        fusion_result: FusionResult,
        judge_model: str,
    ) -> EvaluationResult:
        """Have the judge model evaluate and compare all responses."""
        
        # Build evaluation prompt
        eval_prompt = self._build_evaluation_prompt(prompt, fusion_result)
        
        # Query judge
        response = await self.orchestrator.client.chat.completions.create(
            model=judge_model,
            messages=[{"role": "user", "content": eval_prompt}],
            max_tokens=4096,
            extra_headers=self.orchestrator.extra_headers,
        )
        
        judge_response = response.choices[0].message.content or ""
        
        # Parse judge response (simplified - in production use structured output)
        scores = self._parse_judge_response(judge_response, fusion_result)
        
        return scores
    
    def _build_evaluation_prompt(
        self,
        prompt: str,
        fusion_result: FusionResult,
    ) -> str:
        """Build the prompt for the judge model."""
        
        responses_text = ""
        for i, resp in enumerate(fusion_result.individual_responses, 1):
            if not resp.error:
                model_name = resp.model.split("/")[-1].replace(":free", "")
                responses_text += f"""
### Response {i} ({model_name}):
{resp.content[:2000]}{"..." if len(resp.content) > 2000 else ""}
"""
        
        responses_text += f"""
### Fused Response:
{fusion_result.fused_response[:2000]}{"..." if len(fusion_result.fused_response) > 2000 else ""}
"""
        
        return f"""You are an expert evaluator comparing AI model responses.

## Original Query
{prompt}

## Responses to Evaluate
{responses_text}

## Evaluation Task

For EACH response (including the fused one), provide scores from 1-10:
1. **Factual Accuracy**: How accurate are the claims?
2. **Reasoning Depth**: How thorough is the logical analysis?
3. **Completeness**: How well does it cover all aspects?
4. **Clarity**: How well structured and explained?

Then answer:
- **Best Overall**: Which response is best? (model name or "Fused")
- **Why**: Brief explanation of your choice

Format your response as JSON:
```json
{{
  "scores": [
    {{"model": "model-name", "factual": 8, "reasoning": 7, "completeness": 8, "clarity": 9}},
    ...
    {{"model": "Fused", "factual": 9, "reasoning": 9, "completeness": 9, "clarity": 9}}
  ],
  "best_overall": "Fused",
  "reasoning": "The fused response combines..."
}}
```"""

    def _parse_judge_response(
        self,
        judge_response: str,
        fusion_result: FusionResult,
    ) -> EvaluationResult:
        """Parse the judge's evaluation response."""
        
        # Try to extract JSON from response
        try:
            # Find JSON block
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', judge_response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                # Try parsing entire response as JSON
                data = json.loads(judge_response)
            
            individual_scores = []
            fused_scores = None
            
            for score_data in data.get("scores", []):
                scores = EvaluationScores(
                    model=score_data.get("model", "unknown"),
                    factual_accuracy=float(score_data.get("factual", 5)),
                    reasoning_depth=float(score_data.get("reasoning", 5)),
                    completeness=float(score_data.get("completeness", 5)),
                    clarity=float(score_data.get("clarity", 5)),
                )
                if scores.model.lower() == "fused":
                    fused_scores = scores
                else:
                    individual_scores.append(scores)
            
            # Calculate improvement
            best_individual = max(s.overall for s in individual_scores) if individual_scores else 5
            fused_overall = fused_scores.overall if fused_scores else 5
            improvement = ((fused_overall - best_individual) / best_individual) * 100
            
            return EvaluationResult(
                prompt=fusion_result.prompt,
                timestamp=datetime.now().isoformat(),
                pool_name=fusion_result.pool_name,
                individual_scores=individual_scores,
                fused_scores=fused_scores or EvaluationScores("Fused", 5, 5, 5, 5),
                improvement_pct=improvement,
                preferred_by_judge=data.get("best_overall", "unknown"),
                judge_reasoning=data.get("reasoning", ""),
                latency_ms=fusion_result.total_latency_ms,
            )
            
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            console.print(f"[yellow]Warning: Could not parse judge response: {e}[/yellow]")
            # Return default scores
            return EvaluationResult(
                prompt=fusion_result.prompt,
                timestamp=datetime.now().isoformat(),
                pool_name=fusion_result.pool_name,
                individual_scores=[],
                fused_scores=EvaluationScores("Fused", 5, 5, 5, 5),
                improvement_pct=0,
                preferred_by_judge="unknown",
                judge_reasoning=judge_response[:500],
                latency_ms=fusion_result.total_latency_ms,
            )
    
    def display_results(self, result: EvaluationResult):
        """Display evaluation results in a nice table."""
        
        # Scores table
        table = Table(title="Evaluation Scores")
        table.add_column("Model", style="cyan")
        table.add_column("Factual", justify="center")
        table.add_column("Reasoning", justify="center")
        table.add_column("Completeness", justify="center")
        table.add_column("Clarity", justify="center")
        table.add_column("Overall", justify="center", style="bold")
        
        for scores in result.individual_scores:
            table.add_row(
                scores.model,
                f"{scores.factual_accuracy:.1f}",
                f"{scores.reasoning_depth:.1f}",
                f"{scores.completeness:.1f}",
                f"{scores.clarity:.1f}",
                f"{scores.overall:.1f}",
            )
        
        # Add fused row with highlighting
        table.add_row(
            "[bold green]Fused[/bold green]",
            f"[green]{result.fused_scores.factual_accuracy:.1f}[/green]",
            f"[green]{result.fused_scores.reasoning_depth:.1f}[/green]",
            f"[green]{result.fused_scores.completeness:.1f}[/green]",
            f"[green]{result.fused_scores.clarity:.1f}[/green]",
            f"[bold green]{result.fused_scores.overall:.1f}[/bold green]",
        )
        
        console.print(table)
        
        # Summary
        improvement_color = "green" if result.improvement_pct > 0 else "red"
        console.print(f"\n[bold]Improvement over best individual:[/bold] [{improvement_color}]{result.improvement_pct:+.1f}%[/{improvement_color}]")
        console.print(f"[bold]Judge preferred:[/bold] {result.preferred_by_judge}")
        console.print(Panel(result.judge_reasoning, title="Judge Reasoning"))
    
    def save_result(self, result: EvaluationResult, filename: Optional[str] = None):
        """Save evaluation result to JSON file."""
        if filename is None:
            filename = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = self.results_dir / filename
        
        # Convert to dict for JSON serialization
        data = {
            "prompt": result.prompt,
            "timestamp": result.timestamp,
            "pool_name": result.pool_name,
            "individual_scores": [asdict(s) for s in result.individual_scores],
            "fused_scores": asdict(result.fused_scores),
            "improvement_pct": result.improvement_pct,
            "preferred_by_judge": result.preferred_by_judge,
            "judge_reasoning": result.judge_reasoning,
            "latency_ms": result.latency_ms,
        }
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        
        console.print(f"\n[dim]Results saved to {filepath}[/dim]")


async def main():
    """CLI entry point for evaluation."""
    import sys
    import os
    
    if len(sys.argv) < 2:
        console.print("[red]Usage:[/red] python -m src.evaluation \"Your query\" [pool_name]")
        sys.exit(1)
    
    prompt = sys.argv[1]
    pool = sys.argv[2] if len(sys.argv) > 2 else "general"
    
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        console.print("[red]Error:[/red] Set OPENROUTER_API_KEY environment variable")
        sys.exit(1)
    
    orchestrator = FusionOrchestrator(api_key=api_key)
    evaluator = FusionEvaluator(orchestrator)
    
    result = await evaluator.evaluate(prompt, pool=pool)
    evaluator.display_results(result)
    evaluator.save_result(result)


if __name__ == "__main__":
    asyncio.run(main())
