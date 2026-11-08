"""Flows the dispatcher runs, by name. Each has `lane`, `prepare(job, job_dir) -> prompt path` and
`check(job, job_dir) -> list of errors`, plus optional `timeout` (minutes), `model` and `then(job, job_dir)`
(jobs to queue next when it passes)."""
from flows.books import BookFlow
from flows.cover import CoverFlow
from flows.highlights import AuditFlow, HighlightFlow
from flows.labels import LabelFlow
from flows.lecture import LectureLinkFlow, TranscribeFlow
from flows.pointers import PointerFlow
from flows.reference import ReferenceFlow

REGISTRY = {"pointers": PointerFlow(), "books": BookFlow(), "transcribe": TranscribeFlow(),
            "lecture_links": LectureLinkFlow(), "cover": CoverFlow(),
            "reference": ReferenceFlow(), "labels": LabelFlow(),
            "highlights": HighlightFlow(), "hl_audit": AuditFlow()}
