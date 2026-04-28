# Checklist

## Phase 1: Core Infrastructure

- [x] Document segment sampling mechanism implemented and tested
  - [x] `_segment_document` correctly divides documents into configurable segment sizes
  - [x] Segments maintain proper boundaries (not cutting mid-sentence when possible)
  - [x] Segment-to-chunk mapping accurately records chunk IDs

- [x] Quote-based evidence tracking prompt templates created
  - [x] `EVIDENCE_AWARE_PROMPT` template includes all required output fields
  - [x] Question type supplements updated for evidence tracking
  - [x] JSON schema validation works for LLM responses

- [x] Quote verification mechanism implemented
  - [x] Exact quote matching works correctly
  - [x] Fuzzy matching handles minor variations (whitespace, punctuation)
  - [x] Hallucination detection logs warnings appropriately

## Phase 2: Chunk Location Refactoring

- [x] Quote-based chunk location implemented
  - [x] `_locate_chunks_by_quote` accurately identifies chunks containing quotes
  - [x] Multi-hop scenarios correctly identify all relevant chunks
  - [x] Deprecation warning shown for `_locate_answer_chunks`
  - [x] Backward compatibility maintained for existing test sets

## Phase 3: Multi-hop Intelligence

- [x] Intelligent multi-hop segment selection implemented
  - [x] Candidate segment selection provides appropriate diversity
  - [x] LLM autonomously selects semantically relevant segments
  - [x] Segment selection parsing works correctly
  - [x] Invalid selections are handled gracefully

## Phase 4: Integration

- [x] Hybrid strategy integrated into main generation flow
  - [x] `generate_hybrid_questions` method works as expected
  - [x] `generate_document_based_questions` uses hybrid strategy
  - [x] `strategy="hybrid"` option is supported
  - [x] Quality metrics include `quote_verification_rate` and `ground_truth_confidence`

- [x] Configuration and documentation updated
  - [x] `config.yaml` includes hybrid strategy configuration
  - [x] Configuration schema is valid
  - [x] Migration guide is clear and complete

## Phase 5: Testing

- [x] All unit tests pass
  - [x] `_segment_document` tests pass for various document lengths
  - [x] `_select_segments_for_question_type` tests pass for all question types
  - [x] `_verify_quote_in_segment` tests pass for valid and invalid quotes
  - [x] `_locate_chunks_by_quote` accuracy tests pass
  - [x] Hallucination detection tests pass
  - [x] Multi-hop segment selection tests pass

- [x] Integration tests pass
  - [x] `generate_hybrid_questions` end-to-end test passes
  - [x] Backward compatibility test passes

- [x] Code quality checks pass
  - [x] `pixi run lint` passes without errors
  - [x] Type annotations are complete for all new public methods
  - [x] Docstrings are complete for all new public methods

## Acceptance Criteria

- [x] Ground Truth accuracy improved from ~70% to ~95%+ (measured by quote verification)
- [x] Question authenticity maintained (authenticity_pass_rate >= current baseline)
- [x] Long document coverage improved (all segments have chance to be sampled)
- [x] Hallucination detection working (invalid quotes detected and logged)
- [x] No breaking changes to existing test set format
