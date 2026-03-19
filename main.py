import csv
import os
import time
from datetime import datetime

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from cover_letter_generator import (
    CoverLetterGenerationError,
    build_cover_letter_path,
    generate_cover_letter,
    is_generation_configured,
    save_cover_letter,
)
from resume_loader import ResumeLoadError, load_resume_text
from url_builder import HandshakeURLBuilder


DESCRIPTION_SELECTORS = [
    "div[data-hook='job-description']",
    "section[data-hook='job-description']",
    "[data-testid='job-description']",
    "[data-qa='job-description']",
    "section[class*='description']",
    "div[class*='description']",
]
COVER_LETTER_SIGNAL_XPATHS = [
    "//*[self::label or self::span or self::div or self::p or self::h2 or self::h3]"
    "[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'cover letter')]",
    "//*[@aria-label]"
    "[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'cover letter')]",
    "//*[@placeholder]"
    "[contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'cover letter')]",
    "//*[@name]"
    "[contains(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'cover')"
    " and contains(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'letter')]",
    "//*[@id]"
    "[contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'cover')"
    " and contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'letter')]",
]
COVER_LETTER_DIR = "cover_letters"
MAX_JOB_DESCRIPTION_CHARS = 6000
MAX_RESUME_CHARS = 8000

driver = None
builder = None
EMAIL = None
PASSWORD = None
RESUME_TEXT = None


def normalize_text(value):
    return " ".join((value or "").split())


def truncate_text(value, max_chars):
    value = (value or "").strip()
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def get_school_and_query():
    """
    Prompt user for school subdomain and job search query.
    Defaults to 'cmu' and no query if the user presses Enter without typing.
    """
    school = input("Enter school subdomain (default: cmu): ").strip() or "cmu"

    query = input("Enter job search query (default: none): ").strip()
    if query == "":
        query = None   # allow null query

    try:
        page_start = int(input("Start page (default: 1): ") or 1)
    except ValueError:
        page_start = 1

    try:
        page_end = int(input("End page (default: 10): ") or 10)
    except ValueError:
        page_end = 10

    return school, query, page_start, page_end


def extract_company_and_category():
    about_employer_sections = driver.find_elements(
        By.XPATH,
        "//h3[contains(normalize-space(.), 'About the employer')]/ancestor::div[1]/parent::div",
    )
    for section in about_employer_sections:
        company_candidates = []
        category_candidates = []

        for selector in [
            "h4",
            "a[href*='/e/'] h4",
            "a[aria-label*='Learn more about']",
        ]:
            for element in section.find_elements(By.CSS_SELECTOR, selector):
                text = normalize_text(element.text or element.get_attribute("aria-label"))
                if text and "learn more about" not in text.lower():
                    company_candidates.append(text)

        for selector in [
            "[data-hook='lockup-subheading']",
            "p.subheading",
        ]:
            for element in section.find_elements(By.CSS_SELECTOR, selector):
                text = normalize_text(element.text)
                if text:
                    category_candidates.append(text)

        if company_candidates or category_candidates:
            company = company_candidates[0] if company_candidates else None
            category = category_candidates[0] if category_candidates else None
            print("About employer candidates:", company_candidates, category_candidates)
            return company, category

    xlarge_links = driver.find_elements(By.CSS_SELECTOR, "a[data-size='xlarge']")
    xlarge_values = [normalize_text(el.get_attribute("aria-label")) for el in xlarge_links]
    xlarge_values = [value for value in xlarge_values if value]
    print("Xlarge links' aria-labels:", xlarge_values)

    company = xlarge_values[0] if xlarge_values else None
    category = xlarge_values[2] if len(xlarge_values) > 2 else None
    return company, category


def extract_job_page_title(fallback_title):
    for selector in ["h1", "[data-hook='job-title']", "[data-testid='job-title']"]:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        for element in elements:
            text = normalize_text(element.text)
            if text:
                return text
    return fallback_title


def extract_job_description():
    candidates = []

    for selector in DESCRIPTION_SELECTORS:
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            text = normalize_text(element.text)
            if len(text) >= 120:
                candidates.append(text)

    description_headings = [
        "//*[self::h2 or self::h3 or self::div or self::span]"
        "[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'job description')]",
        "//*[self::h2 or self::h3 or self::div or self::span]"
        "[normalize-space()='Description']",
    ]
    for xpath in description_headings:
        for heading in driver.find_elements(By.XPATH, xpath):
            try:
                parent_text = normalize_text(heading.find_element(By.XPATH, "..").text)
            except Exception:
                parent_text = ""
            if len(parent_text) >= 120:
                candidates.append(parent_text)

    if candidates:
        return truncate_text(max(candidates, key=len), MAX_JOB_DESCRIPTION_CHARS)

    body_text = normalize_text(driver.find_element(By.TAG_NAME, "body").text)
    return truncate_text(body_text, MAX_JOB_DESCRIPTION_CHARS)


def detect_cover_letter_requirement():
    signals = set()

    for xpath in COVER_LETTER_SIGNAL_XPATHS:
        for element in driver.find_elements(By.XPATH, xpath):
            text = normalize_text(
                element.text
                or element.get_attribute("aria-label")
                or element.get_attribute("placeholder")
                or element.get_attribute("name")
                or element.get_attribute("id")
            )
            if text:
                signals.add(text)

    body_text = normalize_text(driver.find_element(By.TAG_NAME, "body").text).lower()
    has_form_controls = bool(
        driver.find_elements(By.XPATH, "//input[@type='file'] | //textarea | //input[@type='text']")
    )
    if "cover letter" in body_text and has_form_controls:
        signals.add("Application form body references cover letter")

    return bool(signals), sorted(signals)


def maybe_load_resume_text():
    resume_pdf_path = os.getenv("RESUME_PDF_PATH")
    if not resume_pdf_path:
        print("ℹ️ RESUME_PDF_PATH is not set. Cover letter generation is disabled.")
        return None

    try:
        resume_text = load_resume_text(resume_pdf_path)
        print(f"✅ Loaded resume text from {os.path.abspath(os.path.expanduser(resume_pdf_path))}")
        return resume_text
    except ResumeLoadError as exc:
        print(f"⚠️ Could not load resume PDF: {exc}")
        print("Cover letter generation is disabled for this run.")
        return None


def generate_cover_letter_for_job(job_result):
    if not RESUME_TEXT:
        print("ℹ️ No resume text available. Skipping cover letter generation.")
        return None, False

    output_path = build_cover_letter_path(
        output_dir=COVER_LETTER_DIR,
        company=job_result["company"],
        job_title=job_result["job_title"],
    )
    if output_path.exists():
        print(f"ℹ️ Cover letter already exists: {output_path}")
        return str(output_path), False

    job_description = job_result.get("job_description")
    if not job_description:
        print("⚠️ Could not extract a job description. Skipping cover letter generation.")
        return None, False

    cover_letter_text = generate_cover_letter(
        company=job_result["company"],
        job_title=job_result["job_title"],
        job_link=job_result["job_link"],
        job_description=truncate_text(job_description, MAX_JOB_DESCRIPTION_CHARS),
        resume_text=truncate_text(RESUME_TEXT, MAX_RESUME_CHARS),
    )
    return save_cover_letter(
        output_dir=COVER_LETTER_DIR,
        company=job_result["company"],
        job_title=job_result["job_title"],
        job_link=job_result["job_link"],
        cover_letter_text=cover_letter_text,
    )


def apply(href, job_title):
    result = {
        "company": None,
        "Category": None,
        "job_title": job_title,
        "job_link": href,
        "applied": False,
        "cover_letter_requested": False,
        "cover_letter_generated": False,
        "cover_letter_file": None,
        "job_description": None,
    }

    try:
        driver.get(href)
        print(f"Navigated to job card: {href}")
        time.sleep(1)

        result["company"], result["Category"] = extract_company_and_category()
        result["job_title"] = extract_job_page_title(job_title)
        result["job_description"] = extract_job_description()

        apply_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'Apply')]"))
        )

        button_text = normalize_text(apply_btn.text or apply_btn.get_attribute("aria-label"))
        print("Apply button text:", button_text)
        if "apply externally" in button_text.lower():
            print("⚠️ Found only external apply button. Skipping this job.")
            return result

        apply_btn.click()
        time.sleep(2)

        cover_letter_requested, cover_letter_signals = detect_cover_letter_requirement()
        result["cover_letter_requested"] = cover_letter_requested
        if cover_letter_requested:
            print("📝 Cover letter requested by application.")
            if cover_letter_signals:
                print("Cover letter signals:", cover_letter_signals[:3])
            try:
                cover_letter_file, created = generate_cover_letter_for_job(result)
                result["cover_letter_file"] = cover_letter_file
                result["cover_letter_generated"] = bool(cover_letter_file)
                if cover_letter_file:
                    print(
                        "✅ Cover letter saved."
                        if created
                        else "ℹ️ Reusing existing cover letter file."
                    )
                    print("Cover letter file:", cover_letter_file)
            except CoverLetterGenerationError as exc:
                print(f"⚠️ Cover letter generation failed: {exc}")

            print("⚠️ Skipping auto-submit because this application asks for a cover letter.")
            return result

        try:
            submit_btn = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Submit Application')]"))
            )
            if not submit_btn.get_attribute("disabled"):
                submit_btn.click()
                result["applied"] = True
                print("✅ Applied!")
                time.sleep(0.5)
            else:
                print("⚠️ Submit button is disabled — additional info required.")
        except Exception:
            print("❌ Could not find Submit Application button.")

    except Exception as exc:
        print(f"❌ Could not process job card: {exc}")

    return result


def cmu_login():
    try:
        driver.get("https://cmu.joinhandshake.com/login")
        time.sleep(1)

        cmu_login_button = driver.find_element(By.XPATH, "//span[contains(text(), 'CMU Sign On')]")
        cmu_login_button.click()
        time.sleep(5)

        username_box = driver.find_element(By.ID, "username")
        username_box.send_keys(EMAIL)

        password_box = driver.find_element(By.ID, "passwordinput")
        password_box.send_keys(PASSWORD)
        password_box.send_keys(Keys.RETURN)

        print("Waiting for Duo MFA approval...")
        print("Manually approve Duo prompt if needed.")
        WebDriverWait(driver, 60).until(EC.url_contains("joinhandshake.com"))
        print("✅ Duo approved and redirected to Handshake")
        print("Now at:", driver.current_url)
        time.sleep(3)
    except Exception as exc:
        print("❌ Login failed:", exc)


def manual_login():
    """
    Open the Handshake login page and let the user log in manually.
    Waits until the page redirects to a post-login URL before continuing.
    """
    login_url = f"https://{builder.school_domain}.joinhandshake.com/login"
    driver.get(login_url)
    print(f"🔑 Please log in manually at: {login_url}")

    try:
        WebDriverWait(driver, 300).until(
            lambda current_driver: "joinhandshake.com" in current_driver.current_url
            and "/login" not in current_driver.current_url
        )
        print("✅ Manual login successful. Current URL:", driver.current_url)
    except Exception as exc:
        print("❌ Manual login failed or timed out:", exc)


def scrape_jobs(url):
    driver.get(url)

    WebDriverWait(driver, 20).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div[data-hook^='job-result-card']"))
    )
    cards = driver.find_elements(By.CSS_SELECTOR, "a[role='button']")
    print(f"✅ Found {len(cards)} job cards.")

    jobs = []
    base_url = f"https://{builder.school_domain}.joinhandshake.com"
    for card in cards:
        href = card.get_attribute("href")
        job_title = card.get_attribute("aria-label")

        if href and job_title:
            if href.startswith("/"):
                href = f"{base_url}{href}"
            jobs.append({"href": href, "job_title": job_title})
    return jobs


def apply_and_save_all(jobs):
    fieldnames = [
        "date",
        "company",
        "Category",
        "job_title",
        "job_link",
        "applied",
        "cover_letter_requested",
        "cover_letter_generated",
        "cover_letter_file",
    ]
    today_str = datetime.now().strftime("%d%b%Y").lower().lstrip("0")
    filename = os.path.join("applied", f"{today_str}-shake.csv")

    os.makedirs("applied", exist_ok=True)
    file_exists = os.path.isfile(filename)

    if not file_exists:
        with open(filename, mode="w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
            writer.writeheader()

    for job in jobs:
        try:
            result = apply(job["href"], job["job_title"])
        except Exception as exc:
            print(f"⚠️ Error processing {job['job_title']}: {exc}")
            result = {
                "date": today_str,
                "company": None,
                "Category": None,
                "job_title": job["job_title"],
                "job_link": job["href"],
                "applied": False,
                "cover_letter_requested": False,
                "cover_letter_generated": False,
                "cover_letter_file": None,
            }

        result["date"] = today_str
        result.pop("job_description", None)

        with open(filename, mode="a", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
            writer.writerow(result)

    time.sleep(10)
    print(f"✅ Results saved to {filename}")


try:
    school, query, page_start, page_end = get_school_and_query()
    print(f"Using school: {school}, query: {query}")
    builder = HandshakeURLBuilder(school, query)
    print(builder.build())

    load_dotenv()
    EMAIL = os.getenv("HANDSHAKE_EMAIL")
    PASSWORD = os.getenv("HANDSHAKE_PASSWORD")
    RESUME_TEXT = maybe_load_resume_text()
    if not is_generation_configured():
        print(
            "ℹ️ Azure OpenAI is not fully configured. "
            "Set OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT to enable cover letter generation."
        )

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId": "America/New_York"})

    if school == "cmu":
        print("Using CMU SSO login flow.")
        cmu_login()
    else:
        print("Manual mode, imagine not being in CMU lol.")
        manual_login()

    for i in range(page_start, page_end + 1):
        url = builder.build(page=i)
        print(f"Scraping page {i}: {url}")
        jobs = scrape_jobs(url)
        apply_and_save_all(jobs)

finally:
    if driver is not None:
        driver.quit()

    