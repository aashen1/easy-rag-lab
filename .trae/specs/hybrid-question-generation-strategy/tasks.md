# Tasks

## Phase 1: Core Infrastructure

- [x] Task 1: Implement document segment sampling mechanism
  - [x] SubTask 1.1: Create `_segment_document` method to divide documents into segments
  - [x] SubTask 1.2: Create `_select_segments_for_question_type` method for type-based segment selection
  - [x] SubTask 1.3: Create `_map_segments_to_chunks` method for segment-to-chunk mapping
  - [x] SubTask 1.4: Add configuration parameters for segment size and sampling strategy

- [x] Task 2: Create quote-based evidence tracking prompt templates
  - [x] SubTask 2.1: Design `EVIDENCE_AWARE_PROMPT` template with quote output requirements
  - [x] SubTask 2.2: Create question type specific prompt supplements for evidence tracking
  - [x] SubTask 2.3: Define JSON output schema with `evidence` field structure

- [x] Task 3: Implement quote verification mechanism
  - [x] SubTask 3.1: Create `_verify_quote_in_segment` method for exact quote matching
  - [x] SubTask 3.2: Create `_fuzzy_match_quote` method for tolerant matching
  - [x] SubTask 3.3: Create `_validate_evidence` method to validate all evidence entries
  - [x] SubTask 3.4: Add hallucination detection and logging

## Phase 2: Chunk Location Refactoring

- [x] Task 4: Implement quote-based chunk location
  - [x] SubTask 4.1: Create `_locate_chunks_by_quote` method using verified quotes
  - [x] SubTask 4.2: Create `_locate_multi_hop_chunks` method for multi-quote scenarios
  - [x] SubTask 4.3: Deprecate `_locate_answer_chunks` with warning
  - [x] SubTask 4.4: Maintain backward compatibility for existing test sets

## Phase 3: Multi-hop Intelligence

- [x] Task 5: Implement intelligent multi-hop segment selection
  - [x] SubTask 5.1: Create `_select_candidate_segments` method for multi-hop questions
  - [x] SubTask 5.2: Update prompt to let LLM select segments autonomously
  - [x] SubTask 5.3: Parse LLM's segment selection from response
  - [x] SubTask 5.4: Validate selected segments have semantic relevance

## Phase 4: Integration

- [x] Task 6: Integrate hybrid strategy into main generation flow
  - [x] SubTask 6.1: Create `generate_hybrid_questions` method as new entry point
  - [x] SubTask 6.2: Update `generate_document_based_questions` to use hybrid strategy
  - [x] SubTask 6.3: Add `strategy="hybrid"` option support
  - [x] SubTask 6.4: Update quality metrics calculation with new metrics

- [x] Task 7: Update configuration and documentation
  - [x] SubTask 7.1: Add hybrid strategy configuration to `config.yaml`
  - [x] SubTask 7.2: Update `test_generation` config schema
  - [x] SubTask 7.3: Create migration guide for existing users

## Phase 5: Testing

- [x] Task 8: Write comprehensive tests for new functionality
  - [x] SubTask 8.1: Test `_segment_document` with various document lengths
  - [x] SubTask 8.2: Test `_select_segments_for_question_type` for all question types
  - [x] SubTask 8.3: Test `_verify_quote_in_segment` with valid and invalid quotes
  - [x] SubTask 8.4: Test `_locate_chunks_by_quote` accuracy
  - [x] SubTask 8.5: Test hallucination detection
  - [x] SubTask 8.6: Test multi-hop segment selection
  - [x] SubTask 8.7: Integration tests for `generate_hybrid_questions`
  - [x] SubTask 8.8: Test backward compatibility

# Task Dependencies

- [Task 2] depends on [Task 1] (need segment structure for prompt design)
- [Task 3] depends on [Task 2] (need prompt output schema for verification)
- [Task 4] depends on [Task 3] (need verified quotes for chunk location)
- [Task 5] depends on [Task 1] (need segment selection for multi-hop)
- [Task 6] depends on [Task 1, Task 2, Task 3, Task 4, Task 5]
- [Task 7] depends on [Task 6]
- [Task 8] depends on [Task 6]

# Parallelizable Work

- Task 1 and Task 2 can be done in parallel
- Task 5 can be done in parallel with Task 2, Task 3, Task 4
- SubTask 8.1-8.6 can be done in parallel with each other
