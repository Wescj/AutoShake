````markdown
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
````

Create a `.env` file in the root directory with your credentials:

```
HANDSHAKE_EMAIL=your-andrew-id@andrew.cmu.edu
HANDSHAKE_PASSWORD=yourpassword
```

⚠️ Never commit your `.env` file (make sure it’s in `.gitignore`). Duo push approval must still be done manually.

## Usage

```bash
python main.py
```

Example output:

```
✅ Duo approved and redirected to Handshake
✅ Found 48 job cards
Navigated to job card:
Apply button text: Apply
✅ Applied!
✅ Results saved to applied/2oct2025-shake.csv
```

## Output

CSV logs are saved under the `applied/` folder, one file per day:

```
applied/
  ├── 2oct2025-shake.csv
  ├── 3oct2025-shake.csv
  └── ...
```

Each row contains:

* Date
* Company
* Category
* Job title
* Job link
* Applied (True/False)

## Disclaimer

This project is for **educational purposes only**. Use responsibly and at your own risk — automated submissions may violate Handshake’s Terms of Service.

```

Do you also want me to generate a **ready-to-paste requirements.txt** so the README matches exactly?
```
