from dotenv import load_dotenv 
import os
import time
import csv
import re
import shutil
from datetime import datetime
from textwrap import wrap

from selenium import webdriver 
from selenium.webdriver.common.by import By 
from selenium.webdriver.common.keys import Keys 
from selenium.webdriver.chrome.service import Service 
from webdriver_manager.chrome import ChromeDriverManager 
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.support import expected_conditions as EC 
from openai import OpenAI
from pypdf import PdfReader
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from url_builder import HandshakeURLBuilder


DEBUG_SINGLE_JOB_MODE = False
DEBUG_JOB_URL = "https://cmu.joinhandshake.com/job-search/10853261?page=1&per_page=25"
RESUME_PDF_PATH = None
AZURE_OPENAI_ENDPOINT = None
AZURE_OPENAI_API_KEY = None
AZURE_OPENAI_MODEL = None
SUPPORTED_REQUIRED_DOCUMENTS = {
    "Attach your transcript",
    "Attach your cover letter",
}


def extract_required_documents():
    requirements = []

    try:
        form = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-hook='apply-modal-content'] form"))
        )
        fieldsets = form.find_elements(By.CSS_SELECTOR, "fieldset")

        for fieldset in fieldsets:
            # Skip requirements that are already satisfied by an attached document.
            if fieldset.find_elements(By.CSS_SELECTOR, "[role='alert'][data-status='positive']"):
                continue

            heading = ""
            heading_elements = fieldset.find_elements(By.CSS_SELECTOR, "legend h5")
            if heading_elements:
                heading = heading_elements[0].text.strip()

            if not heading:
                continue

            requirement = heading
            if heading.lower() == "attach other required documents":
                instruction_elements = fieldset.find_elements(
                    By.XPATH,
                    ".//span[contains(normalize-space(.), 'Instructions from employer:')]/following-sibling::span[1]",
                )
                if instruction_elements:
                    instruction_text = instruction_elements[0].text.strip()
                    if instruction_text:
                        requirement = instruction_text

            requirements.append(requirement)
    except Exception as e:
        print(f"⚠️ Could not extract document requirements: {e}")

    return requirements


def get_unsupported_required_documents(required_documents):
    return [
        requirement
        for requirement in required_documents
        if requirement not in SUPPORTED_REQUIRED_DOCUMENTS
    ]


def upload_file(file_input, file_path):
    if not file_path:
        print("⚠️ No file path provided for upload.")
        return False

    resolved_path = os.path.abspath(os.path.expanduser(file_path))
    if not os.path.isfile(resolved_path):
        print(f"⚠️ File not found for upload: {resolved_path}")
        return False

    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", file_input)
        file_input.send_keys(resolved_path)
        WebDriverWait(driver, 10).until(
            lambda d: bool(file_input.get_attribute("value"))
        )
        print(f"✅ Uploaded file: {os.path.basename(resolved_path)}")
        return True
    except Exception as e:
        print(f"⚠️ Failed to upload file {resolved_path}: {e}")
        return False


def sanitize_filename(value):
    sanitized = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    return sanitized or "document"


def extract_resume_text():
    if not RESUME_PDF_PATH:
        raise ValueError("RESUME_PDF_PATH is not configured.")

    resume_path = os.path.abspath(os.path.expanduser(RESUME_PDF_PATH))
    reader = PdfReader(resume_path)
    pages = [page.extract_text() or "" for page in reader.pages]
    resume_text = "\n".join(pages).strip()
    if not resume_text:
        raise ValueError("Resume PDF did not contain extractable text.")
    return resume_text


def extract_job_description():
    selectors = [
        "[data-hook='job-description']",
        "div[data-testid='job-description']",
        "section[aria-label*='Job description']",
        "main",
    ]

    for selector in selectors:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        for element in elements:
            text = element.text.strip()
            if len(text) > 200:
                return text

    return driver.find_element(By.TAG_NAME, "body").text.strip()


def extract_response_text(response):
    output_text = getattr(response, "output_text", "").strip()
    if output_text:
        return output_text

    response_dict = response.model_dump()
    text_chunks = []
    for output_item in response_dict.get("output", []):
        for content_item in output_item.get("content", []):
            if content_item.get("type") == "output_text":
                text_chunks.append(content_item.get("text", ""))
    return "\n".join(text_chunks).strip()


def generate_cover_letter_text(job_title, company, job_description, resume_text):
    if not AZURE_OPENAI_ENDPOINT:
        raise ValueError("AZURE_OPENAI_ENDPOINT is not configured.")
    if not AZURE_OPENAI_API_KEY:
        raise ValueError("AZURE_OPENAI_API_KEY is not configured.")

    client = OpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        base_url=f"{AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/v1/",
    )

    company_name = company or "the company"
    prompt = f"""
Write a concise, professional cover letter for the following job application.

Requirements:
- Use the candidate resume and job description below.
- Address the hiring team generally; do not invent a recruiter name.
- Keep it to about 250-350 words.
- Do not use placeholders.
- Do not use Em dashes
- Return only the final cover letter text.

Job title: {job_title}
Company: {company_name}

Resume:
{resume_text[:12000]}

Job description:
{job_description[:12000]}
""".strip()

    response = client.responses.create(
        model=AZURE_OPENAI_MODEL,
        input=prompt,
    )
    cover_letter_text = extract_response_text(response)
    if not cover_letter_text:
        raise ValueError("Azure OpenAI returned an empty cover letter.")
    return cover_letter_text


def save_cover_letter_pdf(job_title, company, cover_letter_text):
    os.makedirs("cover_letters", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d")
    company_slug = sanitize_filename(company or "company")
    job_slug = sanitize_filename(job_title)
    filename = f"{timestamp}-{company_slug}-{job_slug}-cover-letter.pdf"
    output_path = os.path.join("cover_letters", filename)

    pdf = canvas.Canvas(output_path, pagesize=LETTER)
    width, height = LETTER
    x_margin = 72
    y_position = height - 72
    line_height = 16

    for paragraph in cover_letter_text.splitlines():
        lines = wrap(paragraph, width=85) if paragraph.strip() else [""]
        for line in lines:
            if y_position <= 72:
                pdf.showPage()
                y_position = height - 72
            pdf.drawString(x_margin, y_position, line)
            y_position -= line_height
        y_position -= 6

    pdf.save()
    return output_path


def prepare_cover_letter_upload_copy(cover_letter_path):
    upload_path = os.path.join(os.path.dirname(cover_letter_path), "Cover_Letter.pdf")
    shutil.copyfile(cover_letter_path, upload_path)
    return upload_path


def select_latest_transcript_if_needed(required_documents):
    if "Attach your transcript" not in required_documents:
        print("No transcript required.")
        return False

    try:
        form = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-hook='apply-modal-content'] form"))
        )
        fieldsets = form.find_elements(By.CSS_SELECTOR, "fieldset")

        for fieldset in fieldsets:
            heading_elements = fieldset.find_elements(By.CSS_SELECTOR, "legend h5")
            if not heading_elements:
                continue

            heading = heading_elements[0].text.strip().lower()
            if heading != "attach your transcript":
                continue

            # Skip if a transcript is already attached in this section.
            if fieldset.find_elements(By.CSS_SELECTOR, "[role='alert'][data-status='positive']"):
                print("Transcript already attached.")
                return False

            transcript_inputs = fieldset.find_elements(By.CSS_SELECTOR, "input[role='combobox']")
            if not transcript_inputs:
                print("⚠️ Could not find transcript selector.")
                return False

            transcript_input = transcript_inputs[0]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", transcript_input)
            transcript_input.click()

            listbox_id = transcript_input.get_attribute("aria-controls")
            if not listbox_id:
                print("⚠️ Transcript selector did not expose a listbox id.")
                return False

            first_option = WebDriverWait(driver, 10).until(
                lambda d: d.find_element(
                    By.CSS_SELECTOR,
                    f"#{listbox_id} div[role='option']",
                )
            )
            first_option_text = first_option.text.strip()
            first_option.click()

            WebDriverWait(driver, 10).until(
                lambda d: transcript_input.get_attribute("value").strip() != ""
            )
            print(f"✅ Selected transcript: {first_option_text}")
            return True
    except Exception as e:
        print(f"⚠️ Could not select transcript: {e}")

    return False


def generate_and_upload_cover_letter_if_needed(required_documents, job_title, company):
    if "Attach your cover letter" not in required_documents:
        print("No cover letter required.")
        return False, ""

    try:
        form = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-hook='apply-modal-content'] form"))
        )
        fieldsets = form.find_elements(By.CSS_SELECTOR, "fieldset")

        for fieldset in fieldsets:
            heading_elements = fieldset.find_elements(By.CSS_SELECTOR, "legend h5")
            if not heading_elements:
                continue

            heading = heading_elements[0].text.strip().lower()
            if heading != "attach your cover letter":
                continue

            if fieldset.find_elements(By.CSS_SELECTOR, "[role='alert'][data-status='positive']"):
                print("Cover letter already attached.")
                return False, ""

            print("Generating cover letter from resume and job description.")
            resume_text = extract_resume_text()
            job_description = extract_job_description()
            cover_letter_text = generate_cover_letter_text(
                job_title=job_title,
                company=company,
                job_description=job_description,
                resume_text=resume_text,
            )
            cover_letter_path = save_cover_letter_pdf(job_title, company, cover_letter_text)

            file_inputs = fieldset.find_elements(By.CSS_SELECTOR, "input[type='file']")
            if not file_inputs:
                print("⚠️ Could not find cover letter upload input.")
                return True, cover_letter_path

            upload_path = prepare_cover_letter_upload_copy(cover_letter_path)
            uploaded = upload_file(file_inputs[0], upload_path)
            if uploaded:
                time.sleep(1)
            return True, cover_letter_path
    except Exception as e:
        print(f"⚠️ Could not generate or upload cover letter: {e}")

    return False, ""


def wait_for_submit_button_ready(timeout=45):
    def submit_button_enabled(driver):
        submit_btn = driver.find_element(By.XPATH, "//button[contains(., 'Submit Application')]")
        disabled_attr = submit_btn.get_attribute("disabled")
        aria_disabled = submit_btn.get_attribute("aria-disabled")
        is_enabled = not disabled_attr and aria_disabled != "true"
        return submit_btn if is_enabled else False

    return WebDriverWait(driver, timeout).until(submit_button_enabled)


def is_application_modal_open():
    return bool(driver.find_elements(By.CSS_SELECTOR, "div[data-hook='apply-modal-content'] form"))


def click_submit_application():
    submit_btn = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Submit Application')]"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
    submit_btn.click()


def ensure_csv_headers(filename, desired_fieldnames):
    if not os.path.isfile(filename):
        with open(filename, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=desired_fieldnames)
            writer.writeheader()
        return desired_fieldnames

    with open(filename, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        existing_fieldnames = reader.fieldnames or []
        existing_rows = list(reader)

    merged_fieldnames = []
    for fieldname in existing_fieldnames + desired_fieldnames:
        if fieldname and fieldname not in merged_fieldnames:
            merged_fieldnames.append(fieldname)

    if merged_fieldnames != existing_fieldnames:
        with open(filename, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=merged_fieldnames)
            writer.writeheader()
            for row in existing_rows:
                writer.writerow({field: row.get(field, "") for field in merged_fieldnames})

    return merged_fieldnames


def get_school_and_query():
    """
    Prompt user for school subdomain and job search query.
    Defaults to 'cmu' and no query if the user presses Enter without typing.
    """
    school = input("Enter school subdomain (default: cmu): ").strip()
    if school == "":
        school = "cmu"

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

def get_user_inputs():
    """
    Prompt user for job search parameters.
    Defaults are used if the user presses Enter without typing.
    """
    query = input("Enter job search query (default: none): ").strip()
    if query == "":
        query = None   # allow null query

    try:
        results_per_page = int(input("Results per page (default: 25): ") or 25)
    except ValueError:
        results_per_page = 25

    try:
        jobType = int(input("Job type (default: 3): ") or 3)
    except ValueError:
        jobType = 3

    try:
        page_start = int(input("Start page (default: 1): ") or 1)
    except ValueError:
        page_start = 1

    try:
        page_end = int(input("End page (default: 10): ") or 10)
    except ValueError:
        page_end = 10

    return query, results_per_page, jobType, page_start, page_end

def apply(href, job_title):
    applied = False
    xlarge_values = []
    required_documents = []
    cover_letter_generated = False
    cover_letter_file = ""
    try:
        # Wait for buttons that contain "Apply"
        driver.get(href)
        print("Navigated to job card:")

        apply_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'Apply')]"))
        )


        time.sleep(1)  # wait for page to stabilize
        xlarge_links = driver.find_elements(By.CSS_SELECTOR, "a[data-size='xlarge']")
        xlarge_values = [el.get_attribute("aria-label") for el in xlarge_links]
        print("Xlarge links' aria-labels:", xlarge_values)



        text = apply_btn.text.strip()
        print("Apply button text:", text)
        if "Apply externally" in text:
            print("⚠️ Found only external apply button. Skipping this job.")
        else:
            apply_btn.click()
            try:
                required_documents = extract_required_documents()
                print("Required documents:", required_documents)
                unsupported_required_documents = get_unsupported_required_documents(required_documents)
                if unsupported_required_documents:
                    print(
                        "⚠️ Skipping job due to unsupported required documents:",
                        unsupported_required_documents,
                    )
                    return {
                        "company": xlarge_values[0] if len(xlarge_values) > 2 else None,
                        "Category": xlarge_values[2] if len(xlarge_values) > 2 else None,
                        "job_title": job_title,
                        "job_link": href,
                        "applied": False,
                        "required_documents_count": len(required_documents),
                        "required_documents": " | ".join(required_documents),
                        "cover_letter_generated": cover_letter_generated,
                        "cover_letter_file": cover_letter_file,
                    }
                click_submit_application()
                time.sleep(1)

                if is_application_modal_open():
                    print("Application still open after initial submit; completing required documents.")
                    select_latest_transcript_if_needed(required_documents)
                    cover_letter_generated, cover_letter_file = generate_and_upload_cover_letter_if_needed(
                        required_documents=required_documents,
                        job_title=job_title,
                        company=xlarge_values[0] if len(xlarge_values) > 2 else None,
                    )

                    # Wait until uploads finish processing and submit becomes enabled again.
                    submit_btn = wait_for_submit_button_ready(timeout=45)
                    submit_btn.click()
                    time.sleep(1)

                if not is_application_modal_open():
                    applied = True
                    print("✅ Applied!")
                    time.sleep(0.5) # so I can see it lmao
                else:
                    print("⚠️ Application modal is still open after submit retry.")
            except Exception as e:
                print(f"❌ Could not submit application: {e}")

    except Exception as e:
        print("❌ Could not find apply button:")

    return {
        "company": xlarge_values[0] if len(xlarge_values) > 2 else None,
        "Category": xlarge_values[2] if len(xlarge_values) > 2 else None,
        "job_title": job_title,
        "job_link": href,
        "applied": applied,
        "required_documents_count": len(required_documents),
        "required_documents": " | ".join(required_documents),
        "cover_letter_generated": cover_letter_generated,
        "cover_letter_file": cover_letter_file,
    }

def cmu_login():
    try:
        # Go to Handshake login
        driver.get("https://cmu.joinhandshake.com/login")
        time.sleep(1)

        # Find button by text
        cmu_login = driver.find_element(By.XPATH, "//span[contains(text(), 'CMU Sign On')]")
        cmu_login.click()
        time.sleep(5)

        #login
        username_box = driver.find_element(By.ID, "username")
        username_box.send_keys(EMAIL)  # from .env

        # Fill password
        password_box = driver.find_element(By.ID, "passwordinput")
        password_box.send_keys(PASSWORD)

        password_box.send_keys(Keys.RETURN)
        print("Waiting for Duo MFA approval...")
        print("Manually approve Duo prompt if needed.")
        WebDriverWait(driver, 60).until(
        EC.url_contains("joinhandshake.com")   # back to Handshake domain
        )
        print("✅ Duo approved and redirected to Handshake")
        print("Now at:", driver.current_url)
        time.sleep(3)
    except Exception as e:
        print("❌ Login failed:", e)

def manual_login():
    """
    Open the Handshake login page and let the user log in manually.
    Waits until the page redirects to a post-login URL before continuing.
    """
    login_url = f"https://{builder.school_domain}.joinhandshake.com/login"
    driver.get(login_url)
    print(f"🔑 Please log in manually at: {login_url}")

    try:
        # Wait until URL contains "joinhandshake.com" but not "/login"
        WebDriverWait(driver, 300).until(
            lambda d: "joinhandshake.com" in d.current_url and "/login" not in d.current_url
        )
        print("✅ Manual login successful. Current URL:", driver.current_url)
    except Exception as e:
        print("❌ Manual login failed or timed out:", e)

def scrape_jobs(url):
    driver.get(url)

    WebDriverWait(driver, 20).until(
    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div[data-hook^='job-result-card']"))
    )
    # Find all job cards
    cards = driver.find_elements(By.CSS_SELECTOR, "a[role='button']")
    print(f"✅ Found {len(cards)} job cards.")

    jobs = []
    for card in cards:
        href = card.get_attribute("href")
        job_title = card.get_attribute("aria-label")

        if href and job_title:  # sanity check
            if job_title.startswith("View "):
                job_title = job_title[5:].strip()
            if href.startswith("/"):
                href = "https://cmu.joinhandshake.com" + href
            jobs.append({"href": href, "job_title": job_title})
    return jobs

def apply_and_save_all(jobs):
    
    # Define headers once
    desired_fieldnames = [
        "date",
        "company",
        "Category",
        "job_title",
        "job_link",
        "applied",
        "required_documents_count",
        "required_documents",
        "cover_letter_generated",
        "cover_letter_file",
    ]
    # Build filename with today's date
    today_str = datetime.now().strftime("%d%b%Y").lower().lstrip("0")  # e.g. "2oct2025"
    # filename = f"{today_str}-shake.csv"
    filename = os.path.join("applied", f"{today_str}-shake.csv")


    fieldnames = ensure_csv_headers(filename, desired_fieldnames)

    # Process jobs one by one and append immediately
    for job in jobs:
        try:
            result = apply(job["href"], job["job_title"])
        except Exception as e:
            print(f"⚠️ Error processing {job['job_title']}: {e}")
            result = {
                "date": today_str,
                "company": None,
                "Category": None,
                "job_title": job["job_title"],
                "job_link": job["href"],
                "applied": False,
                "required_documents_count": 0,
                "required_documents": "",
                "cover_letter_generated": False,
                "cover_letter_file": "",
            }

        # Add date to row
        result["date"] = today_str  

        # Append row to CSV
        with open(filename, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow(result)

    time.sleep(10)
    print(f"✅ Results saved to {filename}")


def debug_apply_single_job(debug_job_url=DEBUG_JOB_URL):
    debug_job = {
        "href": debug_job_url,
        "job_title": "Debug Handshake Job",
    }
    print(f"Running debug apply flow for: {debug_job_url}")
    apply_and_save_all([debug_job])

def build_jobsearch_url(query=None, results_per_page=25, jobType=3, page=1):
    """
    Build a Handshake job search URL with the given parameters.
    If query is None, it uses the simpler base link without ?query.
    """
    if query:  # normal case with search term
        base = "https://cmu.joinhandshake.com/job-search/"
        return (
            f"{base}?query={query}"
            f"&per_page={results_per_page}"
            f"&jobType={jobType}"
            f"&sort=posted_date_desc"
            f"&page={page}"
        )
    else:  # no query
        base = "https://cmu.joinhandshake.com/job-search"
        return (
            f"{base}?page={page}"
            f"&per_page={results_per_page}"
        )


try:
    #Grab values at runtime
    school, query, page_start, page_end = get_school_and_query()
    print(f"Using school: {school}, query: {query}")
    builder = HandshakeURLBuilder(school, query)
    print(builder.build())


    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

    # Spoof timezone to America/New_York
    driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {
        "timezoneId": "America/New_York"
    })

    if school == "cmu":
        print("Using CMU SSO login flow.")

        # Load environment variables from .env file
        load_dotenv()
        EMAIL = os.getenv("HANDSHAKE_EMAIL")
        PASSWORD = os.getenv("HANDSHAKE_PASSWORD")
        RESUME_PDF_PATH = os.getenv("RESUME_PDF_PATH")
        AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
        AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        AZURE_OPENAI_MODEL = os.getenv("AZURE_OPENAI_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4.1-nano"

        cmu_login()
    else:
        print("Manual mode, imagine not being in CMU lol.")
        load_dotenv()
        RESUME_PDF_PATH = os.getenv("RESUME_PDF_PATH")
        AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
        AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        AZURE_OPENAI_MODEL = os.getenv("AZURE_OPENAI_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4.1-nano"
        manual_login()
    
    if DEBUG_SINGLE_JOB_MODE:
        debug_apply_single_job()
    else:
        #go to job search page
        for i in range(page_start, page_end + 1):
            url = builder.build(page=i)
            print(f"Scraping page {i}: {url}")
            jobs = scrape_jobs(url)
            apply_and_save_all(jobs)

finally:
    driver.quit()

    