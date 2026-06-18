"""
Core Fusion Orchestrator

Queries multiple models in parallel and synthesizes their outputs
into a unified, superior response.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .models import ModelPool, get_pool
from .synthesis import create_synthesis_prompt

console = Console()


@dataclass
class ModelResponse:
    """Response from a single model."""
    model: str
    content: str
    latency_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    error: Optional[str] = None


@dataclass
class FusionResult:
    """Complete fusion result with all intermediate data."""
    prompt: str
    pool_name: str
    individual_responses: list[ModelResponse] = field(default_factory=list)
    fused_response: str = ""
    synthesis_latency_ms: float = 0
    total_latency_ms: float = 0
    

class FusionOrchestrator:
    """
    Orchestrates multi-model fusion queries.
    
    Usage:
        orchestrator = FusionOrchestrator()
        result = await orchestrator.fuse("Your complex query here", pool="reasoning")
        print(result.fused_response)
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1",
    ):
        """
        Initialize the fusion orchestrator.
        
        Args:
            api_key: OpenRouter API key (or set OPENROUTER_API_KEY env var)
            base_url: API base URL (default: OpenRouter)
        """
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        # Set default headers for OpenRouter
        self.extra_headers = {
            "HTTP-Referer": "https://github.com/nordgren/fusion-ai-harness",
            "X-Title": "Fusion AI Harness",
        }
    
    async def _query_model(
        self,
        model: str,
        prompt: str,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        """Query a single model and return its response."""
        start_time = time.perf_counter()
        
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=self.extra_headers,
            )
            
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            return ModelResponse(
                model=model,
                content=response.choices[0].message.content or "",
                latency_ms=latency_ms,
                tokens_in=response.usage.prompt_tokens if response.usage else 0,
                tokens_out=response.usage.completion_tokens if response.usage else 0,
            )
            
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return ModelResponse(
                model=model,
                content="",
                latency_ms=latency_ms,
                error=str(e),
            )
    
    async def _query_models_parallel(
        self,
        models: list[str],
        prompt: str,
        progress: Optional[Progress] = None,
    ) -> list[ModelResponse]:
        """Query multiple models in parallel."""
        tasks = [self._query_model(model, prompt) for model in models]
        
        if progress:
            task_id = progress.add_task("Querying models...", total=len(models))
        
        responses = []
        for coro in asyncio.as_completed(tasks):
            response = await coro
            responses.append(response)
            if progress:
                progress.advance(task_id)
        
        return responses
    
    async def _synthesize(
        self,
        prompt: str,
        responses: list[ModelResponse],
        synthesizer: str,
    ) -> tuple[str, float]:
        """Synthesize multiple responses into one."""
        # Filter out failed responses
        valid_responses = [r for r in responses if not r.error and r.content]
        
        if len(valid_responses) == 0:
            return "Error: No valid responses to synthesize.", 0
        
        if len(valid_responses) == 1:
            # Only one valid response, return it directly
            return valid_responses[0].content, 0
        
        # Create synthesis prompt
        synthesis_prompt = create_synthesis_prompt(prompt, valid_responses)
        
        # Query synthesizer
        start_time = time.perf_counter()
        
        response = await self.client.chat.completions.create(
            model=synthesizer,
            messages=[{"role": "user", "content": synthesis_prompt}],
            max_tokens=4096,
            extra_headers=self.extra_headers,
        )
        
        latency_ms = (time.perf_counter() - start_time) * 1000
        
        return response.choices[0].message.content or "", latency_ms
    
    async def fuse(
        self,
        prompt: str,
        pool: str = "general",
        show_progress: bool = True,
    ) -> FusionResult:
        """
        Execute a fusion query.
        
        Args:
            prompt: The query to send to all models
            pool: Name of the model pool to use (see configs/model-pools.yaml)
            show_progress: Whether to show progress in console
            
        Returns:
            FusionResult with individual responses and fused output
        """
        start_time = time.perf_counter()
        
        # Get model pool configuration
        model_pool = get_pool(pool)
        
        result = FusionResult(
            prompt=prompt,
            pool_name=pool,
        )
        
        if show_progress:
            console.print(f"\n[bold blue]Fusion Query[/bold blue] using pool: [green]{pool}[/green]")
            console.print(f"Models: {', '.join(model_pool.models)}")
            console.print(f"Synthesizer: {model_pool.synthesizer}\n")
        
        # Stage 1: Parallel model queries
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            disable=not show_progress,
        ) as progress:
            progress.add_task("Stage 1: Querying models in parallel...", total=None)
            result.individual_responses = await self._query_models_parallel(
                model_pool.models, prompt
            )
        
        if show_progress:
            for resp in result.individual_responses:
                status = "[red]FAILED[/red]" if resp.error else f"[green]{resp.latency_ms:.0f}ms[/green]"
                console.print(f"  • {resp.model}: {status}")
        
        # Stage 2 & 3: Synthesis
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            disable=not show_progress,
        ) as progress:
            progress.add_task("Stage 2-3: Analyzing and synthesizing...", total=None)
            result.fused_response, result.synthesis_latency_ms = await self._synthesize(
                prompt,
                result.individual_responses,
                model_pool.synthesizer,
            )
        
        result.total_latency_ms = (time.perf_counter() - start_time) * 1000
        
        if show_progress:
            console.print(f"\n[bold]Synthesis complete[/bold] in {result.synthesis_latency_ms:.0f}ms")
            console.print(f"[dim]Total time: {result.total_latency_ms:.0f}ms[/dim]\n")
        
        return result


async def main():
    """CLI entry point."""
    import sys
    import os
    
    if len(sys.argv) < 2:
        console.print("[red]Usage:[/red] python -m src.fusion \"Your query here\" [pool_name]")
        console.print("\nAvailable pools: reasoning, general, technical, speed")
        sys.exit(1)
    
    prompt = sys.argv[1]
    pool = sys.argv[2] if len(sys.argv) > 2 else "general"
    
    # Check for API key
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        console.print("[red]Error:[/red] Set OPENROUTER_API_KEY environment variable")
        console.print("Get a free key at: https://openrouter.ai/keys")
        sys.exit(1)
    
    orchestrator = FusionOrchestrator(api_key=api_key)
    result = await orchestrator.fuse(prompt, pool=pool)
    
    console.print(Panel(
        result.fused_response,
        title="[bold green]Fused Response[/bold green]",
        border_style="green",
    ))


if __name__ == "__main__":
    asyncio.run(main())
