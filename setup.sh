#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status messages
print_status() {
    echo -e "${GREEN}[+]${NC} $1"
}

print_error() {
    echo -e "${RED}[-]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Function to install a package with error handling
install_package() {
    local package=$1
    print_status "Installing $package..."
    if ! brew install $package; then
        print_warning "$package installation failed or already installed, continuing..."
    fi
}

# Function to install a cask with error handling
install_cask() {
    local package=$1
    print_status "Installing $package..."
    if ! brew install --cask $package; then
        print_warning "$package installation failed or already installed, continuing..."
    fi
}

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    print_status "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    print_status "Homebrew is already installed"
fi

# Update Homebrew
print_status "Updating Homebrew..."
brew update

# Install system dependencies
print_status "Installing system dependencies..."

# Regular packages
print_status "Installing regular packages..."
for package in poppler tesseract firefox font-util libmagic fontconfig jpeg; do
    install_package $package
done

# Font packages
print_status "Installing font packages..."
for package in font-noto-color-emoji font-ipafont font-gnu-unifont; do
    install_cask $package
done

# Install wkhtmltopdf directly from source
print_status "Installing wkhtmltopdf..."
if ! command -v wkhtmltopdf &> /dev/null; then
    curl -L https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6-1/wkhtmltox-0.12.6-1.macos-cocoa.pkg -o wkhtmltox.pkg
    sudo installer -pkg wkhtmltox.pkg -target /
    rm wkhtmltox.pkg
else
    print_warning "wkhtmltopdf is already installed"
fi

# Install Python 3.11
print_status "Installing Python 3.11..."
install_package python@3.11

# Link Python 3.11
print_status "Linking Python 3.11..."
brew link python@3.11

# Install SSL certificates for Python
print_status "Installing SSL certificates for Python..."
# Install certifi
pip3.11 install --upgrade certifi

# Install uv
print_status "Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
print_status "Creating virtual environment..."
python3.11 -m venv venv

# Activate virtual environment and install Python packages
print_status "Installing Python packages..."
source venv/bin/activate

# Verify virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    print_error "Failed to activate virtual environment"
    exit 1
fi

# Add environment variables to .env file for persistence
print_status "Setting up environment variables..."
cat << EOF > .env
XDG_RUNTIME_DIR=/tmp
RAY_DEDUP_LOGS=0
CUDA_VISIBLE_DEVICES=
REQUESTS_CA_BUNDLE=/etc/ssl/cert.pem
EOF

# Install packages using uv
print_status "Installing Python packages with uv..."
uv pip install -r requirements.txt

# Install Playwright browsers
print_status "Installing Playwright browsers..."
playwright install --with-deps firefox

# Check if secrets.toml exists, if not create from example
if [ ! -f "secrets.toml" ]; then
    if [ -f "secrets.example.toml" ]; then
        print_status "Creating secrets.toml from example..."
        cp secrets.example.toml secrets.toml
        print_warning "Please edit secrets.toml with your actual credentials"
    else
        print_error "secrets.example.toml not found. Please create secrets.toml manually"
    fi
fi

print_status "Setup completed successfully!"
print_warning "Don't forget to:"
print_warning "1. Edit secrets.toml with your actual credentials"
print_warning "2. Activate the virtual environment with: source venv/bin/activate"
print_warning "3. Source the environment variables with: source .env" 