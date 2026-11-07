"""Flows the dispatcher runs, by name. Each has `lane`, `prepare(job, job_dir) -> prompt path` and
`check(job, job_dir) -> list of errors`, plus optional `timeout` (minutes) and `model`. Plan tasks 14-18 add them."""
REGISTRY = {}
