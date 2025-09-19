import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from contextlib import contextmanager

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logging.warning("Playwright not available. Playwright-based SAML auth will be disabled.")

class SAMLAuthManager:
    def __init__(self, config, secrets):
        """
        Initializes the SAML Authentication Manager.
        
        Args:
            config (dict): The 'saml_auth' section from the YAML config.
            secrets (dict): The secrets profile containing 'username' and 'password'.
        """
        self.config = self._validate_config(config)
        self.secrets = self._validate_secrets(secrets)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def _validate_config(self, config):
        """Validate SAML configuration has required fields."""
        if not config:
            raise ValueError("SAML config is required")
        
        required_fields = ['login_url', 'username_field', 'password_field']
        for field in required_fields:
            if not config.get(field):
                raise ValueError(f"SAML config missing required field: {field}")
        
        return config

    def _validate_secrets(self, secrets):
        """Validate secrets have required credentials."""
        if not secrets:
            raise ValueError("SAML secrets are required")
        
        required_fields = ['username', 'password']
        for field in required_fields:
            if not secrets.get(field):
                raise ValueError(f"SAML secrets missing required field: {field}")
        
        return secrets

    def _check_login_failure(self, content):
        """Check if login failed based on failure string."""
        failure_string = self.config.get('login_failure_string')
        if failure_string and failure_string in content:
            raise Exception(f"SAML authentication failed. Found failure string: '{failure_string}'")
        return False

    @contextmanager
    def _playwright_browser(self):
        """Context manager for Playwright browser with automatic cleanup."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright not available for browser-based SAML auth")
        
        playwright = None
        browser = None
        context = None
        page = None
        
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            context = browser.new_context()
            page = context.new_page()
            
            yield page, context
            
        finally:
            # Cleanup in reverse order
            try:
                if page:
                    page.close()
                if context:
                    context.close()
                if browser:
                    browser.close()
                if playwright:
                    playwright.stop()
            except Exception as cleanup_error:
                logging.warning(f"Error during Playwright cleanup: {cleanup_error}")

    def _submit_playwright_form(self, page):
        """Handle form submission with multiple fallback strategies."""
        username_field = self.config.get('username_field', 'username')
        password_field = self.config.get('password_field', 'password')
        
        logging.info(f"Filling credentials in fields: {username_field}, {password_field}")
        
        # Wait for and fill username field
        page.wait_for_selector(f'input[name="{username_field}"]', timeout=10000)
        page.fill(f'input[name="{username_field}"]', self.secrets['username'])
        
        # Wait for and fill password field
        page.wait_for_selector(f'input[name="{password_field}"]', timeout=10000)
        page.fill(f'input[name="{password_field}"]', self.secrets['password'])
        
        # Try multiple submit strategies
        submit_selectors = [
            'input[type="submit"]',
            'button[type="submit"]', 
            'button:has-text("Sign in")',
            'button:has-text("Login")',
            'button:has-text("Submit")',
            'input[value*="Sign"]',
            'input[value*="Login"]'
        ]
        
        submitted = False
        for selector in submit_selectors:
            try:
                if page.locator(selector).count() > 0:
                    logging.info(f"Clicking submit button: {selector}")
                    page.click(selector)
                    submitted = True
                    break
            except Exception as e:
                logging.debug(f"Submit selector {selector} failed: {e}")
                continue
        
        if not submitted:
            # Fallback: press Enter on password field
            logging.info("No submit button found, pressing Enter on password field")
            page.press(f'input[name="{password_field}"]', 'Enter')

    def _wait_for_saml_completion(self, page):
        """Wait for SAML authentication flow to complete."""
        logging.info("Waiting for SAML authentication flow to complete...")
        
        max_wait_time = 30000  # 30 seconds
        
        try:
            # Wait for page to settle after authentication
            page.wait_for_load_state("networkidle", timeout=max_wait_time)
            
            # Check for login failure
            self._check_login_failure(page.content())
            
            logging.info("SAML authentication completed successfully")
            
        except Exception as e:
            # If waiting fails, check current URL for success indicators
            current_url = page.url
            logging.info(f"SAML flow completed, current URL: {current_url}")
            
            # Still check for failure even if timeout occurred
            self._check_login_failure(page.content())

    def _find_form_and_data(self, soup, payload):
        """Finds the login form and extracts its action URL and hidden fields."""
        form = soup.find('form')
        if not form:
            raise Exception("SAML Auth: Could not find login form on IdP page.")
        
        action_url = urljoin(self.current_url, form.get('action'))
        
        # Add all hidden input fields to the payload
        for input_tag in form.find_all('input', {'type': 'hidden'}):
            name = input_tag.get('name')
            value = input_tag.get('value', '')
            if name:
                payload[name] = value
        
        return action_url, payload

    def get_authenticated_session(self):
        """
        Performs the SAML authentication handshake and returns an authenticated session.
        """
        logging.info("Starting SAML authentication process...")

        # Step 1 & 2: Hit the SP to get redirected to the IdP
        logging.info(f"Accessing initial SP URL: {self.config['login_url']}")
        try:
            response = self.session.get(self.config['login_url'], allow_redirects=True)
            response.raise_for_status()
            self.current_url = response.url
            logging.info(f"Redirected to IdP login page: {self.current_url}")
        except requests.RequestException as e:
            logging.error(f"SAML Auth: Failed to reach initial SP/IdP URL: {e}")
            raise

        # Step 3 & 4: Parse the IdP login form
        soup = BeautifulSoup(response.text, 'lxml')
        
        login_payload = {
            self.config['username_field']: self.secrets['username'],
            self.config['password_field']: self.secrets['password'],
        }
        
        # Add any extra form data from config
        if 'extra_form_data' in self.config:
            login_payload.update(self.config['extra_form_data'])
            
        form_action_url, login_payload = self._find_form_and_data(soup, login_payload)
        
        logging.info(f"Found login form. Submitting credentials to: {form_action_url}")

        # Step 5: Submit credentials to the IdP
        try:
            response = self.session.post(form_action_url, data=login_payload)
            response.raise_for_status()
        except requests.RequestException as e:
            logging.error(f"SAML Auth: Failed to POST credentials to IdP: {e}")
            raise

        # Check for login failure
        self._check_login_failure(response.text)

        logging.info("Credentials submitted successfully. Processing SAMLResponse...")
        
        # This is where the logic becomes more complex. The IdP's response after
        # credential submission is not always the final step. It's often an
        # intermediate page with a form that auto-submits the SAMLResponse.
        # A robust solution must handle this by inspecting the response.
        
        self._process_saml_response_page(response)

        logging.info("SAML authentication successful. Session is authenticated.")
        return self.session

    def _process_saml_response_page(self, response):
        """
        Parses a page to find and submit the SAMLResponse form.
        This may be called recursively if there are multiple intermediate steps.
        """
        soup = BeautifulSoup(response.text, 'lxml')
        saml_form = soup.find('form', attrs={'name': 'hiddenform'}) or soup.find(lambda tag: tag.name == 'form' and tag.find('input', {'name': 'SAMLResponse'}))

        if not saml_form:
            # If no SAMLResponse form is found, we assume the session is now authenticated
            # through cookies set in the previous step. This can happen with some IdPs.
            logging.info("No explicit SAMLResponse form found. Assuming authentication is complete.")
            return

        # Step 6: Extract the SAMLResponse
        saml_response_val = saml_form.find('input', {'name': 'SAMLResponse'}).get('value')
        if not saml_response_val:
            raise Exception("SAML Auth: Found SAML form but could not extract SAMLResponse value.")

        relay_state_val = ''
        relay_state_input = saml_form.find('input', {'name': 'RelayState'})
        if relay_state_input:
            relay_state_val = relay_state_input.get('value', '')
            
        acs_url = urljoin(response.url, saml_form.get('action'))
        saml_payload = {
            'SAMLResponse': saml_response_val,
            'RelayState': relay_state_val,
        }
        
        logging.info(f"Found SAMLResponse. Posting assertion to ACS URL: {acs_url}")

        # Step 7: POST the assertion to the SP's ACS
        try:
            final_response = self.session.post(acs_url, data=saml_payload)
            final_response.raise_for_status()
        except requests.RequestException as e:
            logging.error(f"SAML Auth: Failed to POST SAMLResponse to ACS: {e}")
            raise

    def get_authenticated_cookies(self):
        """
        Use Playwright to handle complex SAML authentication flows.
        Returns cookies as a dictionary that can be used with Scrapy or other HTTP clients.
        
        This method is useful for:
        - JavaScript-heavy IdP redirects (Okta/Azure AD/OneLogin)
        - Multi-factor authentication flows
        - Complex SAML responses requiring browser execution
        
        Returns:
            dict: Cookie dictionary with name->value pairs, or None if authentication fails
        """
        logging.info("Starting Playwright-based SAML authentication...")
        
        try:
            with self._playwright_browser() as (page, context):
                # Step 1: Navigate to login URL
                login_url = self.config['login_url']
                logging.info(f"Navigating to SAML login URL: {login_url}")
                
                page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)  # Wait for any redirects
                
                # Step 2: Fill credentials and submit form
                self._submit_playwright_form(page)
                
                # Step 3: Wait for SAML flow to complete
                self._wait_for_saml_completion(page)
                
                # Step 4: Extract and convert cookies
                cookies = context.cookies()
                logging.info(f"Extracted {len(cookies)} cookies from SAML authentication")
                
                cookie_dict = {}
                for cookie in cookies:
                    cookie_dict[cookie['name']] = cookie['value']
                    logging.debug(f"Extracted cookie: {cookie['name']} for domain {cookie.get('domain', 'N/A')}")
                
                logging.info("Playwright-based SAML authentication successful")
                return cookie_dict
                
        except Exception as e:
            logging.error(f"Playwright-based SAML authentication failed: {e}")
            return None