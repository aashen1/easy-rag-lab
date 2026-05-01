import random
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from src.exceptions import ConfigurationError, ParsingError


@dataclass
class SamplingConfig:
    """Configuration for sampling PDF files.

    Args:
        mode: Sampling mode - "count" (by number of PDFs),
              "pages" (by total page count), or "ratio" (by fraction of documents).
        value: The sampling threshold value.
               - count mode: integer number of PDFs to sample
               - pages mode: integer target total page count
               - ratio mode: float between 0.0 and 1.0

    Raises:
        ValueError: If mode is not one of "count", "pages", "ratio",
                    or if value is invalid for the given mode.
    """

    mode: str
    value: int | float

    def __post_init__(self) -> None:
        valid_modes = {"count", "pages", "ratio"}
        if self.mode not in valid_modes:
            raise ConfigurationError(
                f"Invalid sampling mode '{self.mode}', must be one of {valid_modes}"
            )

        if self.mode in ("count", "pages") and (
            not isinstance(self.value, int) or self.value <= 0
        ):
            raise ConfigurationError(
                f"Value for mode '{self.mode}' must be a positive integer, got {self.value}"
            )

        if self.mode == "ratio" and (
            not isinstance(self.value, int | float) or not (0.0 < self.value <= 1.0)
        ):
            raise ConfigurationError(
                f"Value for mode 'ratio' must be a float in (0.0, 1.0], got {self.value}"
            )


def count_pdf_pages(pdf_path: Path) -> int:
    """Count the number of pages in a PDF file.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Number of pages in the PDF.

    Raises:
        Exception: If the PDF cannot be opened or read.
    """
    try:
        import fitz

        with fitz.open(str(pdf_path)) as doc:
            return len(doc)
    except Exception as e:
        error_msg = f"Failed to count pages in {pdf_path}: {str(e)}"
        logger.error(error_msg)
        raise ParsingError(error_msg) from e


def determine_sample(pdf_files: list[Path], config: SamplingConfig) -> list[Path]:
    """Determine which PDF files to sample based on the sampling configuration.

    Args:
        pdf_files: List of all available PDF file paths.
        config: Sampling configuration specifying mode and threshold.

    Returns:
        List of sampled PDF file paths.

    Raises:
        ValueError: If pdf_files is empty.
    """
    if not pdf_files:
        raise ConfigurationError("Cannot sample from an empty list of PDF files")

    total = len(pdf_files)
    logger.info(
        f"Sampling from {total} PDF files (mode={config.mode}, value={config.value})"
    )

    if config.mode == "count":
        count = min(config.value, total)
        sampled = random.sample(pdf_files, count)
        logger.info(f"Sampled {len(sampled)} PDFs by count (requested {config.value})")
        return sampled

    if config.mode == "pages":
        pdf_page_counts: list[tuple] = []
        for pdf_file in pdf_files:
            try:
                pages = count_pdf_pages(pdf_file)
                pdf_page_counts.append((pdf_file, pages))
            except Exception as e:
                logger.warning(f"Skipping {pdf_file} due to page count error: {str(e)}")

        if not pdf_page_counts:
            logger.warning("No PDFs could be read for page-based sampling")
            return []

        random.shuffle(pdf_page_counts)

        sampled = []
        accumulated_pages = 0
        for pdf_file, pages in pdf_page_counts:
            sampled.append(pdf_file)
            accumulated_pages += pages
            if accumulated_pages >= config.value:
                break

        logger.info(
            f"Sampled {len(sampled)} PDFs by pages "
            f"(target {config.value}, actual {accumulated_pages} pages)"
        )
        return sampled

    if config.mode == "ratio":
        import math

        count = math.ceil(config.value * total)
        count = max(1, min(count, total))
        sampled = random.sample(pdf_files, count)
        logger.info(
            f"Sampled {len(sampled)} PDFs by ratio "
            f"(ratio {config.value}, {total} total)"
        )
        return sampled

    return pdf_files
