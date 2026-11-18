# SAML Authentication for Website Crawler

This document explains how to use SAML authentication to crawl websites that require SAML-based single sign-on (SSO) authentication.

## Overview

The website crawler now supports SAML authentication, allowing you to crawl internal websites and portals that are protected by SAML SSO. This is particularly useful for:

- Internal company wikis and documentation sites
- Corporate portals and intranets
- Enterprise applications with SAML-based authentication
- Knowledge bases behind SSO

## How It Works

The SAML authentication process follows these steps:

1. **Initial Request**: The crawler accesses the protected website
2. **SAML Redirect**: The Service Provider (SP) redirects to the Identity Provider (IdP)
3. **Authentication**: The crawler submits credentials to the IdP login form
4. **SAML Response**: The IdP generates a SAML assertion
5. **SP Validation**: The assertion is posted back to the SP
6. **Authenticated Access**: The crawler receives authenticated session cookies
7. **Content Crawling**: The crawler uses these cookies to access protected content

## Configuration

### 1. YAML Configuration

Add a `saml_auth` section to your website crawler configuration:

```yaml
website_crawler:
  urls:
    - "https://internal.company.com"
  
  # SAML Authentication Configuration
  # Note: SAML_USERNAME and SAML_PASSWORD should be defined in secrets.toml
  saml_auth:
    login_url: "https://portal.company.com/login"
    username_field: "username"
    password_field: "password"
    login_failure_string: "Invalid credentials"  # Optional
    extra_form_data:  # Optional
      organization: "your-org"
```

**Configuration Options:**

- `login_url`: The initial URL where SAML authentication begins
- `username_field`: The name of the username input field on the IdP login page
- `password_field`: The name of the password input field on the IdP login page
- `login_failure_string` (optional): String that appears when login fails
- `extra_form_data` (optional): Additional form fields required by the IdP

### 2. Secrets Configuration

Add your SAML credentials to `secrets.toml` using the standardized format:

```toml
[default]
VECTARA_CORPUS_KEY = "your-corpus-key"
VECTARA_API_KEY = "your-api-key"
SAML_USERNAME = "your-saml-username"
SAML_PASSWORD = "your-saml-password"
```

**Important**: Use `SAML_USERNAME` and `SAML_PASSWORD` (all caps) in your secrets.toml file. These will be automatically loaded into the website crawler configuration as `saml_username` and `saml_password`.

## Usage

Run the crawler with your SAML-enabled configuration:

```bash
python ingest.py config/saml-website-example.yaml default
```

## Example Configurations

### Basic SAML Setup

```yaml
website_crawler:
  urls:
    - "https://wiki.company.com"
  
  saml_auth:
    login_url: "https://sso.company.com/login"
    username_field: "email"
    password_field: "password"
```

### Advanced SAML Setup with Form Data

```yaml
website_crawler:
  urls:
    - "https://portal.company.com/docs"
  
  saml_auth:
    login_url: "https://idp.company.com/adfs/ls/"
    username_field: "UserName"
    password_field: "Password"
    login_failure_string: "The user name or password is incorrect"
    extra_form_data:
      AuthMethod: "FormsAuthentication"
      Domain: "COMPANY"
```