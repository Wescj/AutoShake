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
    time.sleep(10)
finally:
    driver.quit()
    