# Riverside Court Case Scraper

This project is a Scrapy-based web crawler designed to automate the retrieval of case information from the **Riverside County Superior Court** public portal.

## Features
- Automated login using stored credentials
- CAPTCHA handling:
  - Image CAPTCHA solved via **2Captcha API**
  - Math CAPTCHA solved programmatically
- Case search and data extraction
- Structured CSV output with case details (number, status, type, parties, etc.)
- Built-in error handling and logging

## Technologies Used
- **Python 3**
- **Scrapy**
- **Requests**
- **Twisted**
- **2Captcha API**

## Output
The spider exports case data into a CSV file named: output.csv

## Usage


## Usage
Install dependencies:
pip install scrapy requests

USERNAME = 'your_email_here@example.com'
PASSWORD = 'your_password_here'
CAPTCHA_API_KEY = 'your_2captcha_api_key'

scrapy runspider riverside_court_spider.py

Example Output
| case_number | filed_date | case_status | case_type | case_name         | party1_name | party1_type | party2_name  | party2_type |
| ----------- | ---------- | ----------- | --------- | ----------------- | ----------- | ----------- | ------------ | ----------- |
| PRMC2400654 | 2024-05-01 | Active      | Probate   | Smith vs. Johnson | John Smith  | Petitioner  | Mary Johnson | Respondent  |

Notes
Ensure that your 2Captcha API key is active and valid.
For debugging, HTML pages for each case are saved locally.

Author: Muhammad Rafay Ali
License: MIT

