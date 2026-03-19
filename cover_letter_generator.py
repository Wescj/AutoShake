import os
import re
from datetime import datetime
from pathlib import Path

from openai import AzureOpenAI


DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_AZURE_API_VERSION = "2024-12-01-preview"


class CoverLetterGenerationError(RuntimeError):
    """Raised when cover letter generation cannot complete."""


def _slugify(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return normalized or fallback


def build_cover_letter_prompt(
    *,
    company: str,
    job_title: str,
    job_link: str,
    job_description: str,
    resume_text: str,
) -> str:
    return f"""Write a professional, concise cover letter tailored to this role.

Requirements:
- Keep it to 3-5 short paragraphs.
- Sound specific to the job description and candidate background.
- Do not invent experience, skills, or achievements not supported by the resume.
- Avoid placeholders like [Company Name].
- Return only the cover letter body with no surrounding commentary.

Job title: {job_title or 'Unknown'}
Company: {company or 'Unknown'}
Job link: {job_link or 'Unknown'}

Job description:
{job_description}

Candidate resume:
{resume_text}
"""


def is_generation_configured() -> bool:
    api_key = os.getenv("OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    deployment_name = os.getenv("OPENAI_MODEL")
    return bool(api_key and azure_endpoint and deployment_name)


def get_deployment_name(model: str | None = None) -> str:
    deployment_name = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    normalized = deployment_name.strip()
    if not normalized:
        raise CoverLetterGenerationError("OPENAI_MODEL is not set.")
    if normalized == "your_azure_deployment_name":
        raise CoverLetterGenerationError(
            "OPENAI_MODEL must be your real Azure deployment name, not the placeholder value."
        )
    return normalized


def build_client():
    api_key = os.getenv("OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION", DEFAULT_AZURE_API_VERSION)

    if not api_key:
        raise CoverLetterGenerationError("OPENAI_API_KEY is not set.")
    if not azure_endpoint:
        raise CoverLetterGenerationError("AZURE_OPENAI_ENDPOINT is not set.")

    return AzureOpenAI(
        api_key=api_key,
        azure_endpoint=azure_endpoint.rstrip("/"),
        api_version=azure_api_version,
    )


def generate_cover_letter(
    *,
    company: str,
    job_title: str,
    job_link: str,
    job_description: str,
    resume_text: str,
    model: str | None = None,
) -> str:
    client = build_client()
    deployment_name = get_deployment_name(model)
    prompt = build_cover_letter_prompt(
        company=company,
        job_title=job_title,
        job_link=job_link,
        job_description=job_description,
        resume_text=resume_text,
    )
    try:
        response = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {
                    "role": "system",
                    "content": "You write truthful, tailored job application cover letters.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
    except Exception as exc:
        raise CoverLetterGenerationError(f"Azure OpenAI request failed: {exc}") from exc

    cover_letter = ""
    if response.choices and response.choices[0].message:
        cover_letter = (response.choices[0].message.content or "").strip()
    if not cover_letter:
        raise CoverLetterGenerationError("Azure OpenAI returned an empty cover letter.")

    return cover_letter


def build_cover_letter_path(
    *,
    output_dir: str,
    company: str,
    job_title: str,
    generated_at: datetime | None = None,
) -> Path:
    generated_at = generated_at or datetime.now()
    filename = (
        f"{generated_at.strftime('%Y%m%d')}-"
        f"{_slugify(company, 'company')}-"
        f"{_slugify(job_title, 'job')}-cover-letter.md"
    )
    return Path(output_dir) / filename


def save_cover_letter(
    *,
    output_dir: str,
    company: str,
    job_title: str,
    job_link: str,
    cover_letter_text: str,
    generated_at: datetime | None = None,
    overwrite: bool = False,
) -> tuple[str, bool]:
    generated_at = generated_at or datetime.now()
    output_path = build_cover_letter_path(
        output_dir=output_dir,
        company=company,
        job_title=job_title,
        generated_at=generated_at,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not overwrite:
        return str(output_path), False

    file_contents = "\n".join(
        [
            "# Cover Letter Draft",
            "",
            f"- Generated: {generated_at.isoformat(timespec='seconds')}",
            f"- Company: {company or 'Unknown'}",
            f"- Job Title: {job_title or 'Unknown'}",
            f"- Source URL: {job_link or 'Unknown'}",
            "",
            "---",
            "",
            cover_letter_text.strip(),
            "",
        ]
    )
    output_path.write_text(file_contents, encoding="utf-8")

    return str(output_path), True
