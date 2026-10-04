"""prompt-forge: versioned prompt templates + rubric evaluation for LLM apps."""

from .template import PromptTemplate, MissingVariableError
from .registry import PromptRegistry
from .models import MockModel, OpenAICompatibleModel, get_model
from .evaluate import Rubric, Check, EvalSuite, run_suite

__all__ = [
    "PromptTemplate",
    "MissingVariableError",
    "PromptRegistry",
    "MockModel",
    "OpenAICompatibleModel",
    "get_model",
    "Rubric",
    "Check",
    "EvalSuite",
    "run_suite",
]
__version__ = "0.1.0"
