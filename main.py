import scrapy
from scrapy.http import FormRequest
import re
import base64
import requests
import time
from datetime import datetime
from twisted.internet import threads
import logging
import json


class RiversideCourtSpider(scrapy.Spider):
    name = 'riverside_court_spider'
    allowed_domains = ['epublic-access.riverside.courts.ca.gov']

    LOGIN_URL = 'https://epublic-access.riverside.courts.ca.gov/public-portal/?q=user/login&destination=node/379'
    SEARCH_URL = 'https://epublic-access.riverside.courts.ca.gov/public-portal/?q=node/379'

    USERNAME = 'valovalovalo2299@gmail.com'                   # Replace with your username
    PASSWORD = 'YsVxCk%z)S89QU&'                              # Replace with your password
    CAPTCHA_API_KEY = 'fdcb4f6dd8ba689240223120308fbf1b'      # Replace with your 2Captcha API key

    CASE_NUMBERS = ['PRMC2400654']                            # Add more cases to get results accordingly

    custom_settings = {
        'CONCURRENT_REQUESTS': 1,
        'DOWNLOAD_DELAY': 2,
        'COOKIES_ENABLED': True,
        'RETRY_TIMES': 3,
        'FEEDS': {
            'output.csv': {
                'format': 'csv',
                'encoding': 'utf8',
                'store_empty': False,
                'fields': [
                    'case_number',
                    'filed_date',
                    'case_status',
                    'case_type',
                    'case_name',
                    'party1_name',
                    'party1_type',
                    'party2_name',
                    'party2_type'
                ],
            }
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_case_index = 0

    def start_requests(self):
        self.logger.info('Starting Riverside court spider...')
        yield scrapy.Request(
            url=self.LOGIN_URL,
            callback=self.parse_login_page,
            dont_filter=True
        )

    def parse_login_page(self, response):
        """Handle login page and detect CAPTCHA."""
        captcha_src = response.xpath('//img[contains(@src, "image_captcha")]/@src').get()
        if captcha_src:
            captcha_url = response.urljoin(captcha_src)
            self.logger.info('Login page contains CAPTCHA, sending for solving...')
            yield scrapy.Request(
                url=captcha_url,
                callback=self.solve_login_captcha,
                meta={'login_response': response},
                dont_filter=True
            )
        else:
            yield from self.submit_login(response)

    def solve_login_captcha(self, response):
        """Send CAPTCHA image to 2Captcha asynchronously."""
        login_response = response.meta['login_response']
        image_data = response.body
        deferred = threads.deferToThread(
            self.solve_with_2captcha,
            image_data,
            self.CAPTCHA_API_KEY
        )
        deferred.addCallback(lambda result: self.handle_captcha_solution(result, login_response))
        deferred.addErrback(self.handle_captcha_error)
        return deferred

    def handle_captcha_solution(self, solution, login_response):
        if solution:
            self.logger.info(f'CAPTCHA solved successfully: {solution}')
            return self.submit_login(login_response, solution)
        else:
            self.logger.error('Failed to solve CAPTCHA.')
            return []

    def submit_login(self, response, captcha_solution=None):
        """Submit login credentials and optional CAPTCHA solution."""
        formdata = {
            'name': self.USERNAME,
            'pass': self.PASSWORD,
            'form_id': 'user_login',
            'op': 'Log in'
        }
        if captcha_solution:
            formdata['captcha_response'] = captcha_solution

        self.logger.info('Submitting login form...')
        yield FormRequest.from_response(
            response,
            formdata=formdata,
            callback=self.after_login,
            dont_filter=True
        )

    def after_login(self, response):
        """Verify login success."""
        if 'Log out' in response.text or 'node/379' in response.url:
            self.logger.info('Login successful.')
            yield scrapy.Request(
                url=self.SEARCH_URL,
                callback=self.parse_search_page,
                dont_filter=True
            )
        else:
            self.logger.error('Login failed. Check credentials or CAPTCHA handling.')

    def parse_search_page(self, response):
        """Handle case search and solve math CAPTCHA."""
        if self.current_case_index >= len(self.CASE_NUMBERS):
            self.logger.info('All cases processed.')
            return

        case_number = self.CASE_NUMBERS[self.current_case_index]
        self.logger.info(f'Searching for case {case_number}...')

        math_captcha_text = response.xpath('//label[contains(text(),"Math question")]/text()').get()
        math_captcha_answer = self.solve_math_captcha(math_captcha_text) if math_captcha_text else None

        if math_captcha_answer is not None:
            self.logger.info(f'Math CAPTCHA answer: {math_captcha_answer}')

        formdata = {
            'case_number': case_number,
            'form_id': 'case_search_form',
            'op': 'Search'
        }
        if math_captcha_answer is not None:
            formdata['captcha_response'] = str(math_captcha_answer)

        yield FormRequest.from_response(
            response,
            formdata=formdata,
            callback=self.parse_search_results,
            meta={'case_number': case_number},
            dont_filter=True
        )

    def solve_math_captcha(self, captcha_text):
        """Evaluate simple arithmetic CAPTCHA expressions."""
        match = re.search(r'(\d+)\s*([+\-*/])\s*(\d+)', captcha_text or '')
        if not match:
            return None
        n1, op, n2 = map(str.strip, match.groups())
        n1, n2 = int(n1), int(n2)
        return {'+': n1 + n2, '-': n1 - n2, '*': n1 * n2, '/': n1 // n2 if n2 else 0}.get(op, 0)

    def parse_search_results(self, response):
        """Extract case detail link from search results."""
        case_number = response.meta['case_number']
        case_link = response.xpath('//table//a[contains(@href, "node/385")]/@href').get()

        if case_link:
            case_url = response.urljoin(case_link)
            self.logger.info(f'Found case link for {case_number}: {case_url}')
            yield scrapy.Request(
                url=case_url,
                callback=self.parse_case_details,
                meta={'case_number': case_number},
                dont_filter=True
            )
        else:
            self.logger.warning(f'Case not found: {case_number}')
            yield self.empty_case_record(case_number)
            self.current_case_index += 1
            yield from self.next_case(response)

    def parse_case_details(self, response):
        """Extract detailed case information."""
        case_number = response.meta['case_number']
        self.logger.info(f'Extracting details for case: {case_number}')

        # Save raw HTML for debugging
        with open(f"case_{case_number}.html", "w", encoding="utf-8") as f:
            f.write(response.text)

        data = {
            'case_number': response.xpath('//div[contains(@class,"field-name-field-case-number")]//div[@class="field-item"]/text()').get(default='').strip(),
            'filed_date': response.xpath('//div[contains(@class,"field-name-field-case-file-date")]//div[@class="field-item"]/text()').get(default='').strip(),
            'case_status': response.xpath('//div[contains(@class,"field-name-field-case-status")]//div[@class="field-item"]/text()').get(default='').strip(),
            'case_type': response.xpath('//div[contains(@class,"field-name-field-case-type")]//div[@class="field-item"]/text()').get(default='').strip(),
            'case_name': response.xpath('//div[contains(@class,"field-name-field-case-title")]//div[@class="field-item"]/text()').get(default='').strip()
        }

        party_rows = response.xpath('//table[contains(@class,"party") or contains(@class,"table")]/tbody/tr')
        data['party1_name'] = party_rows[0].xpath('.//td[1]//text()').get(default='').strip() if len(party_rows) > 0 else ''
        data['party1_type'] = party_rows[0].xpath('.//td[3]//text()').get(default='').strip() if len(party_rows) > 0 else ''
        data['party2_name'] = party_rows[1].xpath('.//td[1]//text()').get(default='').strip() if len(party_rows) > 1 else ''
        data['party2_type'] = party_rows[1].xpath('.//td[3]//text()').get(default='').strip() if len(party_rows) > 1 else ''

        try:
            data['filed_date'] = datetime.strptime(data['filed_date'], '%m/%d/%Y').strftime('%Y-%m-%d')
        except Exception:
            pass

        yield self.clean_case_data(data)

        self.current_case_index += 1
        yield from self.next_case(response)

    def empty_case_record(self, case_number):
        """Return a blank record if no case was found."""
        return {
            'case_number': case_number,
            'filed_date': '',
            'case_status': '',
            'case_type': '',
            'case_name': '',
            'party1_name': '',
            'party1_type': '',
            'party2_name': '',
            'party2_type': ''
        }

    def clean_case_data(self, data):
        """Trim and normalize extracted text fields."""
        for key, value in data.items():
            if isinstance(value, str):
                data[key] = value.strip()
        return data

    def next_case(self, response):
        """Move on to the next case."""
        if self.current_case_index < len(self.CASE_NUMBERS):
            yield scrapy.Request(
                url=self.SEARCH_URL,
                callback=self.parse_search_page,
                dont_filter=True
            )

    def solve_with_2captcha(self, image_content, api_key):
        """Send CAPTCHA to 2Captcha and retrieve solution."""
        try:
            encoded_image = base64.b64encode(image_content).decode('utf-8')
            payload = {'key': api_key, 'method': 'base64', 'body': encoded_image, 'json': 1}
            res = requests.post('http://2captcha.com/in.php', data=payload, timeout=30).json()
            if res.get('status') != 1:
                self.logger.error(f'2Captcha returned error: {res}')
                return None

            captcha_id = res['request']
            for _ in range(30):
                time.sleep(5)
                result = requests.get(
                    f'http://2captcha.com/res.php?key={api_key}&action=get&id={captcha_id}&json=1',
                    timeout=30
                ).json()
                if result.get('status') == 1:
                    return result['request']
                elif result.get('request') != 'CAPCHA_NOT_READY':
                    break

            self.logger.error('CAPTCHA solving timed out.')
            return None
        except Exception as e:
            self.logger.error(f'Error while solving CAPTCHA: {e}')
            return None

    def handle_captcha_error(self, failure):
        self.logger.error(f'Error in CAPTCHA thread: {failure}')
        return []


if __name__ == '__main__':
    from scrapy.crawler import CrawlerProcess
    process = CrawlerProcess()
    process.crawl(RiversideCourtSpider)
    process.start()