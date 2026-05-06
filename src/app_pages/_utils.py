import re
from pathlib import Path


def extract_company_name(rel_path: str) -> str | None:
    parts = Path(rel_path).parts
    if len(parts) < 3:
        return None
    top_level_categories = {"annual_reports", "research_reports"}
    if parts[0] not in top_level_categories:
        return None
    if re.match(r"^\d{4}$", parts[-2]):
        if len(parts) >= 4:
            return parts[-3]
        return None
    if parts[-2] in top_level_categories:
        return None
    return parts[-2]


def make_pdf_label(rel_path: str) -> str:
    file_name = Path(rel_path).name
    company = extract_company_name(rel_path)
    if company:
        return f"{file_name} 🏢 {company}"
    return file_name
