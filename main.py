from dotenv import load_dotenv
import os

load_dotenv()
EMAIL = os.getenv("HANDSHAKE_EMAIL")
PASSWORD = os.getenv("HANDSHAKE_PASSWORD")
print(EMAIL, PASSWORD)