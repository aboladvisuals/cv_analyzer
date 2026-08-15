"""
analysis_bundle.py

Home for the AnalysisBundle dataclass. This lives in its own tiny module
rather than inside app.py so that other modules (report_generator.py)
can import the type without creating a circular import — app.py imports
report_generator.py (to offer report export from the CLI), and
report_generator.py needs AnalysisBundle's shape to build a report from
one. If AnalysisBundle lived in app.py, that would be an import cycle.

app.py re-exports AnalysisBundle (`from analysis_bundle import
AnalysisBundle`) so existing code that does `app.AnalysisBundle` keeps
working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from cv_parser import CVParseResult
from similar_jobs import SimilarJobsResult
from frequency_analyser import FrequencyAnalysisResult
from evidence_mapper import EvidenceMatrixResult
from gap_analyser import GapAnalysisResult


@dataclass
class AnalysisBundle:
    cv_result: CVParseResult
    similar_jobs_result: SimilarJobsResult
    frequency_result: FrequencyAnalysisResult
    evidence_matrix: EvidenceMatrixResult
    gap_result: GapAnalysisResult
