import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

class SAMLAuthManager:
    def __init__(self, config, secrets):
        """
        Initializes the SAML Authentication Manager.
        
        Args:
            config (dict): The 'saml_auth' section from the YAML config.
            secrets (dict): The secrets profile containing 'username' and 'password'.
        """
        self.config = config
        self.secrets = secrets
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

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
        failure_string = self.config.get('login_failure_string')
        if failure_string and failure_string in response.text:
            raise Exception(f"SAML Auth: Login failed. Found failure string: '{failure_string}'")

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