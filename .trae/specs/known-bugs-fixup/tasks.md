# Tasks

- [x] Task 1: Extract category detection utility function
  - [x] Add `detect_document_category(file_path: str, category_mapping: Optional[Dict[str, str]] = None) -> str` to `src/utils.py`
  - [x] Replace duplicated category detection logic in `src/parser.py` (2 occurrences) with calls to the new utility
  - [x] Replace duplicated category detection logic in `src/chunker.py` (1 occurrence) with calls to the new utility
  - [x] Add unit tests for `detect_document_category` in `tests/test_utils.py`

- [x] Task 2: Implement Embedder show_progress with tqdm
  - [x] Add tqdm import to `src/embedder.py`
  - [x] Implement progress bar in `Embedder._encode_batch()` when `show_progress=True`
  - [x] Thread `show_progress` parameter from `embed_texts()` through to `_encode_batch()`
  - [x] Add unit test for show_progress behavior in `tests/test_embedder.py`

- [x] Task 3: Implement dynamic metric configuration in evaluation
  - [x] Add `metrics_config` parameter to `run_evaluation()` function in `eval/run_eval.py`
  - [x] Make metric calculation conditional based on `metrics_config` (default to all three for backward compatibility)
  - [x] Pass metrics config from experiment config through the CLI path
  - [x] Add unit tests for dynamic metric selection in `tests/test_run_eval.py`

- [x] Task 4: Update review document status
  - [x] Mark issue #1 as ✅ 已修复 (normalize_source already implemented)
  - [x] Mark issue #10 as ✅ 已修复 (after Task 3)
  - [x] Mark issue #11 as ✅ 已修复 (after Task 1)
  - [x] Mark issue #12 as ✅ 已修复 (after Task 2)
  - [x] Update issue #13 status (test files now exist)
  - [x] Add ❌ 不修 status with reasons for issues #6, #7, #8, #9

- [x] Task 5: Commit changes and update TODO.md
  - [x] Commit code changes (Tasks 1-3) with descriptive English commit messages
  - [x] Commit document updates (Task 4)
  - [x] Mark TODO.md line 77 as completed with timestamp (precision to seconds)
  - [x] Commit TODO.md change

# Task Dependencies
- [Task 4] depends on [Task 1, Task 2, Task 3] (document should reflect actual fix status)
- [Task 5] depends on [Task 1, Task 2, Task 3, Task 4] (final commit after all changes)
- [Task 1, Task 2, Task 3] are independent and can be parallelized
