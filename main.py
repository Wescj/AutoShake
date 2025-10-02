from dotenv import load_dotenv
import os
import time

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
print(EMAIL, PASSWORD)

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

def apply(href, job_title):
    driver.get(href)
    print("Navigated to first job card:")
    WebDriverWait(driver, 10).until(
    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[data-size='xlarge']")))
    xlarge_links = driver.find_elements(By.CSS_SELECTOR, "a[data-size='xlarge']")
    xlarge_values = [el.get_attribute("aria-label") for el in xlarge_links]
    print("Xlarge links' aria-labels:", xlarge_values)

    return {
        "company": xlarge_values[0],
        "Category": xlarge_values[2] if len(xlarge_values) > 2 else None,
        "job_title": job_title,
        "job_link": href,
    }

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

    #go to job search page
    driver.get("https://cmu.joinhandshake.com/job-search/?query=software&per_page=25&jobType=3&sort=posted_date_desc&page=1")

    WebDriverWait(driver, 20).until(
    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div[data-hook^='job-result-card']"))
    )

    print("✅ Job cards loaded")

    # Find all job cards
    cards = driver.find_elements(By.CSS_SELECTOR, "a[role='button']")
    print(f"Found {len(cards)} job cards.")

    jobs = []
    for card in cards:
        href = card.get_attribute("href")
        job_title = card.get_attribute("aria-label")

        if href and job_title:  # sanity check
            if href.startswith("/"):
                href = "https://cmu.joinhandshake.com" + href
            jobs.append({"href": href, "job_title": job_title})

    # now navigate safely
    for job in jobs:
        print(apply(job["href"], job["job_title"]))
    time.sleep(10)

finally:
    driver.quit()

    