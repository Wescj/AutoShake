from dotenv import load_dotenv 
import os
import time
import csv
from datetime import datetime

from selenium import webdriver 
from selenium.webdriver.common.by import By 
from selenium.webdriver.common.keys import Keys 
from selenium.webdriver.chrome.service import Service 
from webdriver_manager.chrome import ChromeDriverManager 
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.support import expected_conditions as EC 

from url_builder import HandshakeURLBuilder


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

                # Wait for the Submit Application button to appear
                submit_btn = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Submit Application')]"))
                )
                if not submit_btn.get_attribute("disabled"):
                    submit_btn.click()
                    applied = True
                    print("✅ Applied!")
                    time.sleep(0.5) # so I can see it lmao
                else:
                    print("⚠️ Submit button is disabled — additional info required.")
            except Exception as e:
                print("❌ Could not find Submit Application button:")

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
            }

        # Add date to row
        result["date"] = today_str  

        # Append row to CSV
        with open(filename, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow(result)

    time.sleep(10)
    print(f"✅ Results saved to {filename}")

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

        cmu_login()
    else:
        print("Manual mode, imagine not being in CMU lol.")
        manual_login()
    
    #go to job search page
    for i in range(page_start, page_end + 1):
        url = builder.build(page=i)
        print(f"Scraping page {i}: {url}")
        jobs = scrape_jobs(url)
        apply_and_save_all(jobs)

finally:
    driver.quit()

    