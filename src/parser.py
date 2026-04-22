import json
from pathlib import Path

import pymupdf4llm
from loguru import logger

from src.utils import detect_document_category, ensure_dir


def parse_pdf(pdf_path: str, page_chunks: bool = False, **kwargs) -> str | list[dict]:
    """Parse a single PDF file and convert its content to Markdown text.

    Args:
        pdf_path: Path to the PDF file.
        page_chunks: If True, return a list of page-level dicts instead of
            a single Markdown string. Each dict contains the page content
            and metadata (page number, etc.).
        **kwargs: Additional keyword arguments passed to
            ``pymupdf4llm.to_markdown``. Common options include
            ``header``, ``footer``, ``page_separators``,
            ``ignore_images``, and ``write_images``.

    Returns:
        Markdown-formatted string extracted from the PDF when
        ``page_chunks=False``, or a list of page-level dicts when
        ``page_chunks=True``.

    Raises:
        FileNotFoundError: If the PDF file does not exist.
        ValueError: If the file is not a PDF (wrong extension).
        Exception: If the PDF parsing fails for any other reason.
    """
    pdf_file = Path(pdf_path)

    if not pdf_file.exists():
        error_msg = f"PDF file not found: {pdf_path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    if pdf_file.suffix.lower() != ".pdf":
        error_msg = f"File is not a PDF: {pdf_path}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        logger.info(f"Parsing PDF: {pdf_path}")
        result = pymupdf4llm.to_markdown(str(pdf_file), page_chunks=page_chunks, **kwargs)
        if page_chunks:
            logger.success(f"Parsed PDF (page_chunks): {pdf_path} -> {len(result)} pages")
        else:
            logger.success(f"Successfully parsed PDF: {pdf_path}")
        return result
    except Exception as e:
        error_msg = f"Failed to parse PDF {pdf_path}: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg) from e


def parse_all_pdfs(
    input_dir: str,
    output_dir: str,
    category_mapping: dict[str, str] | None = None,
    force: bool = False,
    pdf_files: list[Path] | None = None,
    parser_options: dict[str, any] | None = None,
) -> list[dict[str, str]]:
    """Parse all PDF files in a directory and save their Markdown output.

    Skips files that have already been parsed unless force is True. Each
    parsed result is categorized based on the file path or the provided
    category_mapping.

    When ``parser_options`` contains ``"page_chunks": True``, each PDF is
    parsed into a list of page-level dicts and saved as a ``.pages.json``
    file instead of a ``.md`` file.

    Args:
        input_dir: Directory containing PDF files to parse.
        output_dir: Directory where parsed Markdown files will be saved.
        category_mapping: Optional mapping from path substrings to category
            names. If None, categories are inferred from path keywords.
        force: If True, re-parse files even if output already exists.
        pdf_files: Optional explicit list of PDF paths to parse. If None,
            all PDFs under input_dir are discovered automatically.
        parser_options: Optional dict of keyword arguments passed to
            ``pymupdf4llm.to_markdown`` (e.g. header, footer,
            page_separators, ignore_images, page_chunks).

    Returns:
        List of result dictionaries, each containing source, output,
        category, and status keys (plus error on failure). When
        ``page_chunks=True``, the result dict also includes
        ``"format": "pages_json"``.

    Raises:
        FileNotFoundError: If input_dir does not exist.
    """
    input_path = Path(input_dir)

    if not input_path.exists():
        error_msg = f"Input directory not found: {input_dir}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    output_path = ensure_dir(output_dir)

    if pdf_files is not None:
        logger.info(f"Using provided list of {len(pdf_files)} PDF files")
    else:
        pdf_files = list(input_path.rglob("*.pdf"))

    if not pdf_files:
        logger.warning(f"No PDF files found in {input_dir}")
        return []

    logger.info(f"Found {len(pdf_files)} PDF files to parse")

    use_page_chunks = bool(parser_options and parser_options.get("page_chunks", False))

    results = []

    for pdf_file in pdf_files:
        try:
            relative_path = pdf_file.relative_to(input_path)

            if use_page_chunks:
                output_file = output_path / relative_path.with_suffix(".pages.json")
            else:
                output_file = output_path / relative_path.with_suffix(".md")

            if not force and output_file.exists():
                logger.info(f"Skipping (already parsed): {pdf_file.name}")
                category = detect_document_category(str(pdf_file), category_mapping)

                results.append(
                    {
                        "source": str(pdf_file),
                        "output": str(output_file),
                        "category": category,
                        "status": "skipped",
                    }
                )
                continue

            if use_page_chunks:
                filtered_options = {k: v for k, v in (parser_options or {}).items() if k != "page_chunks"}
                md_text = parse_pdf(str(pdf_file), page_chunks=True, **filtered_options)

                output_file.parent.mkdir(parents=True, exist_ok=True)

                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(md_text, f, ensure_ascii=False, indent=2)

                category = detect_document_category(str(pdf_file), category_mapping)

                results.append(
                    {
                        "source": str(pdf_file),
                        "output": str(output_file),
                        "category": category,
                        "status": "success",
                        "format": "pages_json",
                    }
                )
            else:
                md_text = parse_pdf(str(pdf_file), **(parser_options or {}))

                output_file.parent.mkdir(parents=True, exist_ok=True)

                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(md_text)

                category = detect_document_category(str(pdf_file), category_mapping)

                results.append(
                    {
                        "source": str(pdf_file),
                        "output": str(output_file),
                        "category": category,
                        "status": "success",
                    }
                )

            logger.success(f"Parsed and saved: {pdf_file.name} -> {output_file.name}")

        except Exception as e:
            logger.error(f"Failed to parse {pdf_file}: {str(e)}")
            results.append(
                {
                    "source": str(pdf_file),
                    "output": None,
                    "category": None,
                    "status": "failed",
                    "error": str(e),
                }
            )

    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = sum(1 for r in results if r["status"] == "failed")
    skipped_count = sum(1 for r in results if r["status"] == "skipped")

    logger.info(
        f"Parsing completed: {success_count} succeeded, {skipped_count} skipped, {failed_count} failed out of {len(pdf_files)} total"
    )

    return results


if __name__ == "__main__":
    from src.utils import load_config, setup_logger

    config = load_config()
    setup_logger(config)

    parser_config = config["parser"]
    results = parse_all_pdfs(
        input_dir=parser_config["input_dir"],
        output_dir=parser_config["output_dir"],
        parser_options=parser_config.get("pymupdf4llm"),
    )

    for result in results:
        logger.info(f"Result: {result}")
