"""Flows the dispatcher runs, by name. Each has `lane`, `prepare(job, job_dir) -> prompt path` and
`check(job, job_dir) -> list of errors`, plus optional `timeout` (minutes) and `model`."""
from flows.books import BookFlow
from flows.pointers import PointerFlow

REGISTRY = {"pointers": PointerFlow(), "books": BookFlow()}
