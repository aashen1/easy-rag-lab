# Hybrid Question Generation Strategy Spec

## Why

当前问题生成系统存在核心矛盾：Document-based 策略的问题真实性强但 Ground Truth 可靠性低（后验推断导致 chunk 定位不准确），Chunk-based 策略 Ground Truth 精确但问题风格死板。需要融合两种策略的优势，实现高可靠性的真实风格问题生成。

## What Changes

- **新增文档分段随机抽样机制**：替代固定截断前 8000 字符，确保长文档各部分都有机会被采样
- **新增原文引用追踪机制**：LLM 生成问题时必须输出原文引用，实现依据可追溯
- **新增引用验证机制**：验证 LLM 输出的引用是否真实存在于选定的文档段落中
- **新增基于引用的 Chunk 定位**：用原文引用反向定位到具体 chunk，提高 Ground Truth 准确率
- **改进多跳问题选段策略**：让 LLM 自主决定哪些选段适合组合，避免机械规则导致的不自然问题
- **保留真实问题风格**：延续 Document-based 的角色扮演 prompt，确保问题口语化、自然

## Impact

- Affected specs: `test_generation` 配置项扩展
- Affected code: `src/test_generator.py` 核心重构
- Affected tests: `tests/test_test_generator.py` 新增测试用例

## ADDED Requirements

### Requirement: Document Segment Sampling

The system SHALL provide a segment-based document sampling mechanism that ensures comprehensive coverage of long documents.

#### Scenario: Long document sampling
- **WHEN** a document exceeds the segment threshold (default 8000 characters)
- **THEN** the system SHALL divide the document into multiple segments
- **AND** randomly select segments based on question type requirements
- **AND** record the chunk IDs associated with each selected segment

#### Scenario: Segment-to-chunk mapping
- **WHEN** segments are selected for question generation
- **THEN** the system SHALL maintain a mapping between segment text and corresponding chunk IDs
- **AND** this mapping SHALL be used for subsequent quote verification

### Requirement: Quote-Based Evidence Tracking

The system SHALL require LLM to output verbatim quotes as evidence when generating questions.

#### Scenario: Quote output in response
- **WHEN** LLM generates a question
- **THEN** the response SHALL include an `evidence` field
- **AND** each evidence entry SHALL contain:
  - `segment_index`: Index of the source segment
  - `quote`: Verbatim text from the segment (must match exactly)
  - `relevance`: Explanation of how the quote supports the answer

#### Scenario: Quote verification
- **WHEN** LLM outputs a quote
- **THEN** the system SHALL verify the quote exists in the selected segments
- **AND** if verification fails, the question SHALL be marked as invalid
- **AND** the system SHALL retry generation up to max_retries

### Requirement: Quote-Based Chunk Location

The system SHALL locate source chunks using verified quotes instead of keyword matching.

#### Scenario: Single quote location
- **WHEN** a verified quote is found in a segment
- **THEN** the system SHALL identify the specific chunk containing the quote
- **AND** set `source_chunks` to the identified chunk ID

#### Scenario: Multi-hop quote location
- **WHEN** multiple quotes from different segments are verified
- **THEN** the system SHALL identify all chunks containing each quote
- **AND** set `source_chunks` to the union of all identified chunk IDs

### Requirement: Intelligent Multi-hop Segment Selection

The system SHALL use LLM-guided segment selection for multi-hop questions instead of mechanical rules.

#### Scenario: Multi-hop segment selection
- **WHEN** generating a multi-hop question (multi_fact, reasoning, comparative)
- **THEN** the system SHALL provide 3-4 candidate segments to LLM
- **AND** LLM SHALL autonomously decide which segments to combine
- **AND** LLM SHALL output the selected segment indices in the response

### Requirement: Question Type to Segment Strategy Mapping

The system SHALL map question types to appropriate segment selection strategies.

| Question Type | Segment Strategy | Ground Truth Source |
|--------------|------------------|---------------------|
| single_fact | Random 1 segment | Segment's chunks |
| multi_fact | LLM selects from 3-4 segments | Selected segments' chunks |
| reasoning | LLM selects from 3-4 segments | Selected segments' chunks |
| comparative | LLM selects from 2 segments with comparable content | Selected segments' chunks |
| missing | Full document sampling | Empty (expected no answer) |
| irrelevant | No document dependency | Empty |

### Requirement: Hallucination Detection

The system SHALL detect LLM hallucinations through quote verification.

#### Scenario: Quote not found in segment
- **WHEN** LLM outputs a quote that does not exist in any selected segment
- **THEN** the system SHALL mark the question as potentially hallucinated
- **AND** discard the question
- **AND** log a warning with the invalid quote

#### Scenario: Quote partially matches
- **WHEN** a quote has minor differences from segment text (whitespace, punctuation)
- **THEN** the system SHALL attempt fuzzy matching with configurable tolerance
- **AND** if match score exceeds threshold, accept the quote

## MODIFIED Requirements

### Requirement: Document-based Question Generation

The `generate_document_based_questions` method SHALL use the new hybrid strategy by default.

**Previous behavior**: Fixed truncation to 8000 characters, keyword-based chunk location.

**New behavior**: Segment-based sampling, quote-based evidence tracking, quote-based chunk location.

### Requirement: Test Set Quality Metrics

The quality metrics calculation SHALL include new metrics for quote verification.

**Added metrics**:
- `quote_verification_rate`: Percentage of questions with verified quotes
- `ground_truth_confidence`: Average confidence score for chunk location

## REMOVED Requirements

### Requirement: Keyword-based Chunk Location

**Reason**: Replaced by quote-based location which provides higher accuracy.

**Migration**: The `_locate_answer_chunks` method is retained for backward compatibility but deprecated. New code should use `_locate_chunks_by_quote`.

### Requirement: Fixed Document Truncation

**Reason**: Replaced by segment-based sampling for better coverage.

**Migration**: `DOCUMENT_TRUNCATE_MAX` constant is retained but only used as segment size reference.
