"""Drawing / PDF comparison with CV + text diff + optional LLM explanations."""
from .pipeline import CompareOptions, compare_pdfs
from .report import write_outputs

__all__ = ["CompareOptions", "compare_pdfs", "write_outputs"]
__version__ = "1.0.0"
