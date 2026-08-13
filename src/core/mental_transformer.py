"""Compatibility shim — re-exports from core.akashic.mental_transformer."""
# This file exists so `from src.core.mental_transformer import X` still works
# after the restructuring to core/. The canonical location is core.akashic.mental_transformer.
from core.akashic.mental_transformer import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.akashic.mental_transformer import (  # noqa: F401
    _TORCH_AVAILABLE,
    _INPUT_DIM,
    _D_MODEL,
    _NHEAD,
    _NUM_LAYERS,
    _SEQ_LEN,
    _CENTROIDS_PATH,
    _MODEL_SAVE_PATH,
    _get_model,
    _build_training_data,
    _genesis_vector_to_sequence,
    _raw_sequence_to_tensor,
)
