"""SDK-neutral command-agent evaluation framework."""

from evaluation.command_framework.models import (
    AgentDescriptor,
    EnvironmentAccess,
    ParameterDiff,
    Variant,
    VariantIdentity,
    compare_variant_identities,
    load_descriptor,
    load_variant,
)
from evaluation.command_framework.runner import AttemptResult, CommandEvaluationRunner

__all__ = [
    "AgentDescriptor",
    "AttemptResult",
    "CommandEvaluationRunner",
    "EnvironmentAccess",
    "ParameterDiff",
    "Variant",
    "VariantIdentity",
    "compare_variant_identities",
    "load_descriptor",
    "load_variant",
]
