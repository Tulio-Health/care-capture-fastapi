# Follow-up Fast Path Verification & Remaining Issue

**Date**: 2026-03-31
**Environment**: Dev
**Deployed commits**: `68e6bcb` (CDA date rules), `04a77bd` (follow-up fast path)
**User**: `f29ef01a-3354-4718-8778-70729cdc8571`

## Follow-up Fast Path: WORKING

Conversation at ~07:46 IST:
1. "What happened in 26 Dec 2019 visit?" → Found 1 match (Physician - Cardiovascula C)
2. "What was the medication?" → `Follow-up: reusing 1 summaries from previous turn` → Answered "dexamethasone" correctly

The fast path correctly:
- Detected follow-up via `_is_followup()`
- Retrieved summary IDs from `lastMatchedSummaryIds` in Redis context
- Skipped query extraction entirely
- Passed full summary data to response LLM which answered correctly

## Remaining Issue: Conversation History Contamination

### Evidence

Same session, next queries:
3. "What happened in 25 April 2025 visit?" (NEW question — different date, no provider mentioned)
   - `_is_followup()` → False (has specific date, not a follow-up pattern)
   - Falls through to Stage 1 query extraction
   - Extracted: `provider_name='Physician - Cardiovascula C'` ← WRONG
   - Found 0 matched summaries

4. "What happened on 25 April 2025 with MDCardio3 P?" (user explicitly names provider)
   - Extracted: `provider_name='MDCardio3 P'` ← Correct
   - Found 2 matched summaries

### Root Cause

`chain.py:390-400` passes `conversation_history` and `conversation_context` to the query extraction LLM for ALL non-followup queries:

```python
query_params = self.query_chain.invoke({
    "text": text,
    "user_profile": json.dumps(user_profile, default=str),
    "enriched_summaries": json.dumps(condensed, default=str),
    "conversation_history": json.dumps(chat_history, default=str),      # ← contaminates
    "conversation_context": json.dumps(conversation_context, default=str),  # ← contaminates
    "query_format": self.query_parser.get_format_instructions(),
})
```

The QUERY_PROMPT says "ONLY set provider_name when the user EXPLICITLY mentions a provider by name" (line 25), but the LLM ignores this rule when it sees `Physician - Cardiovascula C` in conversation_history — it assumes continuity.

### Why This Only Happens After Follow-ups

The contamination requires conversation history containing a previous provider mention. The sequence is:
1. User asks about visit → gets provider in response
2. User asks follow-up → fast path works fine
3. User asks a NEW question (different visit) → extraction LLM sees old provider in conversation history and injects it

### Fix

Since follow-ups are now handled by the fast path (before reaching extraction), conversation history is pure noise for queries reaching Stage 1. Fix: don't pass conversation_history/conversation_context to extraction for non-followup queries.

```python
# Stage 1 extraction should be context-free for new questions
query_params = self.query_chain.invoke({
    "text": text,
    "user_profile": json.dumps(user_profile, default=str),
    "enriched_summaries": json.dumps(condensed, default=str),
    "conversation_history": "[]",           # No history for new questions
    "conversation_context": "{}",           # No context for new questions
    "query_format": self.query_parser.get_format_instructions(),
})
```

### Verification SQL

```sql
-- Check April 2025 appointments for the test user
SELECT a.id, a.appointment_date, a.provider_name
FROM appointments a
WHERE a.user_id = 'f29ef01a-3354-4718-8778-70729cdc8571'
  AND a.appointment_date::text LIKE '2025-04%';
```
