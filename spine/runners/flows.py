"""The spine's fleet flows, added to the old dispatcher's registry (`dispatch.py` itself is not touched).

A flow follows the protocol of flows/__init__.py: `lane`, `timeout`, `prepare(job, job_dir) -> prompt path`,
`check(job, job_dir) -> list of errors`, optional `then(job, job_dir)` and `expand(job)`.
Each flow lives with its engine: spine/align/flow.py (sp_align), spine/tg/flow.py (sp_mother).
"""
import importlib

# sp_seg is not a fleet flow any more (fleet retired 2026-11-18): Haiku answers it through `py -m spine seg run --go`.
FLOWS = {"sp_align": ("spine.align.flow", "AlignFlow"),
         "sp_mother": ("spine.tg.flow", "MotherFlow")}


def register(registry):
    """Add every built spine flow to `registry` (flows.REGISTRY). Returns the names added."""
    added = []
    for name, (module, cls) in FLOWS.items():
        try:
            registry[name] = getattr(importlib.import_module(module), cls)()
            added.append(name)
        except ModuleNotFoundError as e:
            if e.name != module:
                raise
    return added
