# 🤖 AutoShake – Handshake Job Auto-Apply Bot

AutoShake automates logging into [Handshake](https://cmu.joinhandshake.com), navigating job listings, and applying to jobs that use **internal applications** (it skips “Apply Externally”). Each run saves results into a dated CSV file under the `applied/` folder.

## Features
- Automatic login with CMU SSO + Duo MFA (manual approval required)
- Scrapes job cards: title, company, category, and link
- Detects and clicks internal apply buttons, skips external ones
- Saves results into daily CSV logs under `/applied`
- Waits intelligently for job and apply buttons to load

## Requirements
- Python 3.10 or newer (tested on 3.13)
- Google Chrome installed
- Duo MFA enabled for CMU SSO

## Installation
```bash
# Clone the repository
git clone https://github.com/yourusername/autoshake.git
cd autoshake

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Mac/Linux
# OR
.venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt
```
