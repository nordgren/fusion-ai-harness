"""
Model Pool Configuration

Defines predefined combinations of models optimized for different use cases.
All models use OpenRouter's free tier (June 2026).
"""

from dataclasses import dataclass


@dataclass
class ModelPool:
    """Configuration for a model pool."""
    name: str
    description: str
    models: list[str]
    synthesizer: str


# Predefined model pools using OpenRouter free-tier models
POOLS = {
    "reasoning": ModelPool(
        name="reasoning",
        description="Deep analysis and complex reasoning tasks",
        models=[
            "deepseek/deepseek-r1:free",
            "qwen/qwen3-coder-480b-instruct:free",
            "meta-llama/llama-3.3-70b-instruct:free",
        ],
        synthesizer="deepseek/deepseek-r1:free",
    ),
    
    "general": ModelPool(
        name="general",
        description="Balanced quality for most tasks",
        models=[
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemma-2-27b-it:free",
            "deepseek/deepseek-r1:free",
        ],
        synthesizer="deepseek/deepseek-r1:free",
    ),
    
    "technical": ModelPool(
        name="technical",
        description="Code, architecture, and technical documentation",
        models=[
            "qwen/qwen3-coder-480b-instruct:free",
            "deepseek/deepseek-r1:free",
            "meta-llama/llama-3.3-70b-instruct:free",
        ],
        synthesizer="deepseek/deepseek-r1:free",
    ),
    
    "speed": ModelPool(
        name="speed",
        description="Lower latency for faster responses",
        models=[
            "google/gemma-2-9b-it:free",
            "meta-llama/llama-3.1-8b-instruct:free",
            "mistralai/mistral-7b-instruct:free",
        ],
        synthesizer="meta-llama/llama-3.3-70b-instruct:free",
    ),
    
    "minimal": ModelPool(
        name="minimal",
        description="Two-model fusion for quick testing",
        models=[
            "deepseek/deepseek-r1:free",
            "meta-llama/llama-3.3-70b-instruct:free",
        ],
        synthesizer="deepseek/deepseek-r1:free",
    ),
}


def get_pool(name: str) -> ModelPool:
    """
    Get a model pool by name.
    
    Args:
        name: Pool name (reasoning, general, technical, speed, minimal)
        
    Returns:
        ModelPool configuration
        
    Raises:
        ValueError: If pool name is not found
    """
    if name not in POOLS:
        available = ", ".join(POOLS.keys())
        raise ValueError(f"Unknown pool '{name}'. Available: {available}")
    
    return POOLS[name]


def list_pools() -> dict[str, str]:
    """Return dict of pool names to descriptions."""
    return {name: pool.description for name, pool in POOLS.items()}
