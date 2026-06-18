"""
Response Synthesis

Creates the synthesis prompt that combines multiple model responses
into a unified output.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .fusion import ModelResponse


SYNTHESIS_SYSTEM_PROMPT = """You are an expert at synthesizing multiple AI model responses into a single, superior answer. Your task is to analyze responses from different models and create a unified response that combines the best elements from each.

Guidelines:
1. Identify the strongest reasoning chains and incorporate them
2. Use facts that are consistent across multiple responses (higher confidence)
3. Fill gaps where one model covered something others missed
4. Resolve contradictions by weighing the quality of evidence/reasoning
5. Maintain a clear, coherent structure
6. Write as a single polished response - never mention the source models or that this is a synthesis
7. If all models agree on something, treat it as high confidence
8. If models strongly disagree, present the strongest argument or note genuine uncertainty

Output only the synthesized response. No meta-commentary."""


def create_synthesis_prompt(
    original_prompt: str,
    responses: list["ModelResponse"],
) -> str:
    """
    Create the prompt for the synthesis model.
    
    Args:
        original_prompt: The user's original query
        responses: List of ModelResponse objects from the model pool
        
    Returns:
        Complete synthesis prompt
    """
    response_sections = []
    
    for i, resp in enumerate(responses, 1):
        # Extract just the model name without provider prefix
        model_name = resp.model.split("/")[-1].replace(":free", "")
        
        response_sections.append(f"""### Response {i} (from {model_name}):
{resp.content}
""")
    
    all_responses = "\n".join(response_sections)
    
    return f"""{SYNTHESIS_SYSTEM_PROMPT}

## Original Query
{original_prompt}

## Model Responses
{all_responses}

## Your Task
Synthesize these responses into a single, superior answer. Combine the strongest reasoning, most accurate facts, and clearest explanations. Output only the final synthesized response."""


def create_comparison_prompt(
    original_prompt: str,
    responses: list["ModelResponse"],
) -> str:
    """
    Create a prompt for comparing responses (for evaluation).
    
    This asks the model to analyze and rank responses rather than synthesize.
    Useful for understanding what each model contributes.
    """
    response_sections = []
    
    for i, resp in enumerate(responses, 1):
        model_name = resp.model.split("/")[-1].replace(":free", "")
        response_sections.append(f"""### Response {i} ({model_name}):
{resp.content}
""")
    
    all_responses = "\n".join(response_sections)
    
    return f"""Analyze these AI model responses to the same query and provide a structured comparison.

## Original Query
{original_prompt}

## Responses
{all_responses}

## Analysis Required
For each response, evaluate:
1. **Factual Accuracy** (1-10): How accurate are the claims?
2. **Reasoning Depth** (1-10): How thorough is the logical analysis?
3. **Completeness** (1-10): How well does it cover all aspects?
4. **Clarity** (1-10): How well structured and explained?
5. **Key Strengths**: What does this response do best?
6. **Key Weaknesses**: What does it miss or get wrong?

Then provide:
- **Best for facts**: Which response?
- **Best for reasoning**: Which response?
- **Best overall**: Which response?
- **Synthesis potential**: What would a combined response gain from each?

Be specific and cite examples from the responses."""
