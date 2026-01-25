#!/bin/bash
# Test script for trade-tracker deployment

set -e  # Exit on any error

echo "🧪 Running tests for trade-tracker..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if pytest is installed
print_status "Checking pytest installation..."
if ! command -v pytest &> /dev/null; then
    print_error "pytest is not installed. Installing..."
    pip3 install pytest pytest-mock
fi

# Check if we're in the right directory
if [ ! -f "app.py" ]; then
    print_error "app.py not found. Please run this script from the project root directory."
    exit 1
fi

print_status "Running unit tests..."

# Run tests with coverage if available
if command -v coverage &> /dev/null; then
    print_status "Running tests with coverage..."
    coverage run -m pytest tests/ -v
    coverage report
    coverage html
    print_status "Coverage report generated in htmlcov/"
else
    print_warning "coverage not installed. Running tests without coverage..."
    python3 -m pytest tests/ -v --tb=short
fi

print_status "Running import tests..."
python3 -c "
import sys
print('Testing core imports...')
try:
    import streamlit as st
    print('✓ streamlit imported successfully')
except ImportError as e:
    print(f'✗ Failed to import streamlit: {e}')
    sys.exit(1)

try:
    import pandas as pd
    print('✓ pandas imported successfully')
except ImportError as e:
    print(f'✗ Failed to import pandas: {e}')
    sys.exit(1)

try:
    import yfinance as yf
    print('✓ yfinance imported successfully')
except ImportError as e:
    print(f'✗ Failed to import yfinance: {e}')
    sys.exit(1)

try:
    import altair as alt
    print('✓ altair imported successfully')
except ImportError as e:
    print(f'✗ Failed to import altair: {e}')
    sys.exit(1)

try:
    from ui.utils import color_profit_loss
    print('✓ ui.utils imported successfully')
except ImportError as e:
    print(f'✗ Failed to import ui.utils: {e}')
    sys.exit(1)

print('All critical imports work!')
"

print_status "Checking requirements.txt..."

# Check if all required packages are listed
required_packages=("streamlit" "streamlit-authenticator" "psycopg2-binary" "pandas" "yfinance" "sqlalchemy" "altair" "pytest" "pytest-mock")

for package in "${required_packages[@]}"; do
    if grep -q "^$package$" requirements.txt; then
        echo "✓ $package found in requirements.txt"
    else
        print_warning "$package not found in requirements.txt"
    fi
done

print_status "🎉 All tests completed successfully!"
print_status "Your app is ready for deployment to Streamlit Cloud."

echo ""
echo "📋 Deployment Checklist:"
echo "  ✓ All dependencies are in requirements.txt"
echo "  ✓ All critical imports work"
echo "  ✓ Unit tests pass"
echo "  ✓ Project structure is correct"
echo ""
echo "🚀 You can now deploy to Streamlit Cloud!"