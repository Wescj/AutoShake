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

# Load environment variables from .env file
load_dotenv()
EMAIL = os.getenv("HANDSHAKE_EMAIL")
PASSWORD = os.getenv("HANDSHAKE_PASSWORD")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

def apply(href, job_title):
    applied = False
    try:
        # Wait for buttons that contain "Apply"
        driver.get(href)
        print("Navigated to job card:")
        apply_btn = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Apply')]"))
        )
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
                # Wait for the Submit Application button to appear
                submit_btn = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Submit Application')]"))
                )
                submit_btn.click()
                applied = True
                print("✅ Applied! ")

            except Exception as e:
                print("❌ Could not find Submit Application button:")

    except Exception as e:
        print("❌ Could not find apply button:")

    return {
        "company": xlarge_values[0] if len(xlarge_values) > 2 else None,
        "Category": xlarge_values[2] if len(xlarge_values) > 2 else None,
        "job_title": job_title,
        "job_link": href,
        "applied": applied
    }

def cmu_login():
    try:
        # Go to Handshake login
        driver.get("https://cmu.joinhandshake.com/login")
        time.sleep(3)

        # Find button by text
        cmu_login = driver.find_element(By.XPATH, "//span[contains(text(), 'CMU Sign On')]")
        cmu_login.click()
        time.sleep(2.5)

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
            if href.startswith("/"):
                href = "https://cmu.joinhandshake.com" + href
            jobs.append({"href": href, "job_title": job_title})
    return jobs

def apply_and_save_all(jobs):
    
    # Define headers once
    fieldnames = ["date", "company", "Category", "job_title", "job_link", "applied"]
    # Build filename with today's date
    today_str = datetime.now().strftime("%d%b%Y").lower().lstrip("0")  # e.g. "2oct2025"
    # filename = f"{today_str}-shake.csv"
    filename = os.path.join("applied", f"{today_str}-shake.csv")


    # Check if file exists already
    file_exists = os.path.isfile(filename)

    # If not, create it with headers
    if not file_exists:
        with open(filename, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

    # Process jobs one by one and append immediately
    for job in jobs:
        result = apply(job["href"], job["job_title"])
        print(result)

        # Add date to row
        result["date"] = today_str  

        # Append row to CSV
        with open(filename, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow(result)

    time.sleep(10)
    print(f"✅ Results saved to {filename}")

try:
    cmu_login()
    #go to job search page
    url = "https://cmu.joinhandshake.com/job-search/?query=software&per_page=25&jobType=3&sort=posted_date_desc&page=4"
    jobs = scrape_jobs(url)
    apply_and_save_all(jobs)

finally:
    driver.quit()

    