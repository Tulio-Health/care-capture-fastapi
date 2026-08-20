"""Consolidates duplicate procedure extractions that describe the SAME real-world procedure
event but were extracted from multiple source documents (e.g. a cardiac catheterization
report AND a separate consult note both describing the same cath).

`ProcedureExtractionChain.extract()` produces one `ProcedureSummary` per SOURCE DOCUMENT, not
per real-world procedure EVENT. Left unconsolidated, downstream persistence would create
duplicate patient-facing rows for the same event.

Pipeline (see `ProcedureConsolidator.consolidate`):
1. Zero-cost fast path: <=1 procedure needs no consolidation at all.
2. Cheap heuristic pre-filter (no LLM): candidate-pair two summaries only when
   `procedure_date` matches (or both are null) AND their `procedure_type` strings are similar
   above `_TYPE_SIMILARITY_THRESHOLD`, reusing `chain.py`'s `_normalize` string-cleanup helper
   and the same `difflib.SequenceMatcher` approach already used by `_quote_supported`.
3. ONE batched, structured (Pydantic-output, no free text) LLM call confirming/denying every
   heuristic-flagged pair — never a per-pair call, and never asked to generate new prose, so
   this adds no new fabrication surface on top of extraction itself.
4. Deterministic merge of LLM-confirmed groups (see `_merge_group`) — again, no further LLM
   generation.
"""

import difflib
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from src.app.chains.procedure_extraction.chain import ExtractedProcedure, _normalize
from src.app.common.llm_factory import get_pydantic_ai_model
from src.app.models.procedure_summarization import (
    NOT_DOCUMENTED_FOLLOW_UP,
    ProcedureSummary,
)

logger = logging.getLogger(__name__)

# Starting point per the task spec; tune if real-world extractions show this is too
# loose/tight. Applied to `_normalize`-cleaned (whitespace-collapsed, lowercased)
# procedure_type strings.
_TYPE_SIMILARITY_THRESHOLD = 0.6


@dataclass
class ConsolidatedProcedure:
    """One consolidated procedure: the merged summary plus every source document id that
    contributed to it. `document_ids` has exactly one entry for a procedure that was never
    merged with another (the common case)."""

    summary: ProcedureSummary
    document_ids: List[str]

    @property
    def source_count(self) -> int:
        return len(self.document_ids)


class _PairConfirmation(BaseModel):
    pair_index: int = Field(
        ...,
        description="The SAME pair_index from the corresponding input candidate pair, unchanged.",
    )
    same_procedure: bool = Field(
        ...,
        description=(
            "True ONLY if both summaries describe the SAME real-world procedure event "
            "(e.g. the same cardiac catheterization, documented twice). False if they are two "
            "distinct events that merely look similar in wording (e.g. two separate cardiac "
            "caths performed a week apart)."
        ),
    )


class _ConsolidationResponse(BaseModel):
    confirmations: List[_PairConfirmation] = Field(
        ..., description="One confirmation per input candidate pair, in any order."
    )


_SYSTEM_PROMPT = """You review pairs of procedure summaries that a heuristic has flagged as POSSIBLE
duplicates (same or both-missing date, similar procedure_type wording) and decide whether each pair
truly describes the SAME real-world procedure event, or two distinct events that merely read similarly.

INPUT: a JSON array of pair objects, each with a pair_index and two summaries "a" and "b", each
carrying procedure_type, procedure_date, reason, performed_by, and source_document_title.

OUTPUT: exactly one confirmation object per input pair, each with:
- pair_index: the same pair_index from the input, unchanged.
- same_procedure: true only if "a" and "b" clearly describe ONE SAME procedure event (e.g. the same
  cardiac catheterization documented in two different reports - a procedure note and a discharge
  summary both covering the same operation). false if they could plausibly be two DIFFERENT
  procedures of the same type (e.g. two separate cardiac catheterizations performed weeks apart,
  or performed by different people, or for different documented reasons) - similar wording alone is
  NOT sufficient evidence they are the same event.

When uncertain, prefer false (treat as distinct events) - a missed consolidation just leaves two
rows instead of one; a wrongful merge silently drops a real, distinct procedure from the patient's
record.

Do not generate any new text. Only classify the given pairs."""


class ProcedureConsolidator:
    """See module docstring for the full pipeline."""

    def __init__(self) -> None:
        self._model: Optional[Any] = None
        self._agent: Optional[Agent[None, _ConsolidationResponse]] = None

    @property
    def model(self) -> Any:
        if self._model is None:
            # Cheapest available tier (get_pydantic_ai_model()'s default, GPT_4O_MINI) - this
            # is a cheap yes/no classification task, not free-text generation, so it doesn't
            # need the more capable (and pricier) GPT_4_1_MINI used for extraction itself.
            self._model = get_pydantic_ai_model()
        return self._model

    @property
    def agent(self) -> Agent[None, _ConsolidationResponse]:
        if self._agent is None:
            self._agent = Agent(
                self.model,
                output_type=_ConsolidationResponse,
                system_prompt=_SYSTEM_PROMPT,
                model_settings=ModelSettings(
                    temperature=0.0, timeout=15.0, max_tokens=800
                ),
                retries=1,
            )
        return self._agent

    async def consolidate(
        self, extracted: List[ExtractedProcedure]
    ) -> List[ConsolidatedProcedure]:
        """Consolidate a list of per-document procedure extractions into one entry per
        real-world procedure event. Zero LLM calls when there's nothing to consolidate
        (<=1 procedure, or the heuristic flags no candidate pairs at all)."""
        if len(extracted) <= 1:
            return [self._singleton(e) for e in extracted]

        candidate_pairs = self._find_candidate_pairs(extracted)
        if not candidate_pairs:
            return [self._singleton(e) for e in extracted]

        confirmed_pairs = await self._confirm_pairs(extracted, candidate_pairs)
        groups = self._build_groups(len(extracted), confirmed_pairs)

        consolidated: List[ConsolidatedProcedure] = []
        for group in groups:
            if len(group) == 1:
                consolidated.append(self._singleton(extracted[group[0]]))
            else:
                consolidated.append(self._merge_group([extracted[i] for i in group]))
        return consolidated

    @staticmethod
    def _singleton(item: ExtractedProcedure) -> ConsolidatedProcedure:
        return ConsolidatedProcedure(
            summary=item.summary, document_ids=[item.document_id]
        )

    def _find_candidate_pairs(
        self, extracted: List[ExtractedProcedure]
    ) -> List[Tuple[int, int]]:
        """O(n^2) pairwise heuristic scan - fine for the small (single-digit) number of
        procedure documents typically attached to one appointment."""
        pairs: List[Tuple[int, int]] = []
        for i in range(len(extracted)):
            for j in range(i + 1, len(extracted)):
                a, b = extracted[i].summary, extracted[j].summary
                if a.procedure_date != b.procedure_date:
                    # Covers both "both non-null and equal" (kept) and "both null" (kept) in
                    # one comparison, and rejects any non-null/non-null mismatch or
                    # null/non-null mismatch.
                    continue
                ratio = difflib.SequenceMatcher(
                    None, _normalize(a.procedure_type), _normalize(b.procedure_type)
                ).ratio()
                if ratio >= _TYPE_SIMILARITY_THRESHOLD:
                    pairs.append((i, j))
        return pairs

    async def _confirm_pairs(
        self,
        extracted: List[ExtractedProcedure],
        candidate_pairs: List[Tuple[int, int]],
    ) -> List[Tuple[int, int]]:
        """ONE LLM call for every candidate pair flagged by the heuristic (never one call per
        pair)."""
        payload = [
            {
                "pair_index": idx,
                "a": self._pair_view(extracted[i].summary),
                "b": self._pair_view(extracted[j].summary),
            }
            for idx, (i, j) in enumerate(candidate_pairs)
        ]

        result = await self.agent.run(json.dumps(payload, ensure_ascii=False))
        confirmed_indices = {
            c.pair_index for c in result.output.confirmations if c.same_procedure
        }
        return [
            pair for idx, pair in enumerate(candidate_pairs) if idx in confirmed_indices
        ]

    @staticmethod
    def _pair_view(summary: ProcedureSummary) -> Dict[str, object]:
        return {
            "procedure_type": summary.procedure_type,
            "procedure_date": summary.procedure_date,
            "reason": summary.reason,
            "performed_by": summary.performed_by,
            "source_document_title": summary.source_document_title,
        }

    @staticmethod
    def _build_groups(
        n: int, confirmed_pairs: List[Tuple[int, int]]
    ) -> List[List[int]]:
        """Union-find over the confirmed pairs only (NOT the heuristic candidates) - two
        summaries end up in the same group iff there's a chain of LLM-confirmed
        same-procedure pairs connecting them."""
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        for i, j in confirmed_pairs:
            union(i, j)

        groups: Dict[int, List[int]] = {}
        for i in range(n):
            groups.setdefault(find(i), []).append(i)
        return list(groups.values())

    @staticmethod
    def _merge_group(group: List[ExtractedProcedure]) -> ConsolidatedProcedure:
        """Deterministic merge, no LLM generation - avoids a second fabrication surface on
        top of extraction itself."""
        summaries = [item.summary for item in group]
        document_ids = [item.document_id for item in group]

        # dict.fromkeys de-dupes while preserving first-seen order.
        source_document_title = "; ".join(
            dict.fromkeys(
                s.source_document_title for s in summaries if s.source_document_title
            )
        )
        procedure_type = max((s.procedure_type for s in summaries), key=len)

        distinct_dates = {s.procedure_date for s in summaries if s.procedure_date}
        procedure_date = min(distinct_dates) if distinct_dates else None
        if len(distinct_dates) > 1:
            logger.warning(
                "ProcedureConsolidator merged procedures with differing non-null "
                f"procedure_date values {sorted(distinct_dates)!r} (documents: {document_ids!r}) "
                "- keeping the earliest. This may signal the similarity heuristic over-matched."
            )

        performed_by = list(
            dict.fromkeys(name for s in summaries for name in s.performed_by)
        )

        reason = max((s.reason for s in summaries), key=len)
        procedure_details = max((s.procedure_details for s in summaries), key=len)
        outcome = max((s.outcome for s in summaries), key=len)

        # follow_up and follow_up_source_quote are kept as a matching pair from the SAME
        # source summary - never mixing a quote from one document with follow-up text
        # paraphrased from another.
        real_follow_ups = [
            s for s in summaries if s.follow_up != NOT_DOCUMENTED_FOLLOW_UP
        ]
        if real_follow_ups:
            chosen = max(real_follow_ups, key=lambda s: len(s.follow_up))
            follow_up = chosen.follow_up
            follow_up_source_quote = chosen.follow_up_source_quote
        else:
            follow_up = NOT_DOCUMENTED_FOLLOW_UP
            follow_up_source_quote = None

        merged = ProcedureSummary(
            source_document_title=source_document_title,
            procedure_type=procedure_type,
            procedure_date=procedure_date,
            performed_by=performed_by,
            reason=reason,
            procedure_details=procedure_details,
            outcome=outcome,
            follow_up=follow_up,
            follow_up_source_quote=follow_up_source_quote,
        )
        return ConsolidatedProcedure(summary=merged, document_ids=document_ids)
