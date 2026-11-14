"""Flows the dispatcher runs, by name. Each has `lane`, `prepare(job, job_dir) -> prompt path` and
`check(job, job_dir) -> list of errors`, plus optional `timeout` (minutes), `model` and `then(job, job_dir)`
(jobs to queue next when it passes)."""
from flows.books import BookFlow
from flows.cover import CoverFlow
from flows.highlights import AuditFlow, HighlightFlow
from flows.labels import LabelFlow
from flows.lecture import LectureLinkFlow, PieceFlow, TranscribeFlow
from flows.mcq import MCQFlow
from flows.place import PlaceFlow
from flows.pointers import PointerFlow
from flows.pointers_one import PointerOneFlow
from flows.reference import ReferenceFlow

REGISTRY = {"pointers": PointerFlow(), "pointers_one": PointerOneFlow(), "books": BookFlow(), "transcribe": TranscribeFlow(), "piece": PieceFlow(), "place": PlaceFlow(), "mcq": MCQFlow(),
            "lecture_links": LectureLinkFlow(), "cover": CoverFlow(),
            "reference": ReferenceFlow(), "labels": LabelFlow(),
            "highlights": HighlightFlow(), "hl_audit": AuditFlow()}
