#!/usr/bin/env python
"""
Debug script for Chrome and ChromeDriver in GitHub Actions
"""

import os
import sys
import platform
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def get_chrome_version():
    """Get the Chrome version using different methods based on platform"""
    try:
        if platform.system() == "Windows":
            output = subprocess.check_output(
                r'reg query "HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon" /v version',
                shell=True
            ).decode('utf-8')
            version = output.strip().split()[-1]
        elif platform.system() == "Linux":
            output = subprocess.check_output(['google-chrome', '--version']).decode('utf-8')
            version = output.strip().split()[-1]
        elif platform.system() == "Darwin":  # macOS
            output = subprocess.check_output(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version']).decode('utf-8')
            version = output.strip().split()[-1]
        else:
            version = "Unknown platform"
        
        return version
    except Exception as e:
        return f"Error getting Chrome version: {e}"

def main():
    """Main debug function"""
    print("\n=== Chrome and ChromeDriver Debug Info ===\n")
    
    # System Information
    print(f"Python version: {sys.version}")
    print(f"Platform: {platform.platform()}")
    print(f"System: {platform.system()}")
    print(f"Machine: {platform.machine()}")
    print(f"Working directory: {os.getcwd()}")
    
    # Chrome Version
    chrome_version = get_chrome_version()
    print(f"Chrome version: {chrome_version}")
    
    # Environment Variables
    print("\nEnvironment variables:")
    is_github = os.environ.get('GITHUB_ACTIONS', False)
    is_ci = os.environ.get('CI', False)
    print(f"Running in GitHub Actions: {is_github}")
    print(f"Running in CI: {is_ci}")
    
    # ChromeDriver Installation
    print("\nInstalling ChromeDriver...")
    try:
        # Try to get a compatible ChromeDriver version 
        chrome_major_version = chrome_version.split('.')[0] if chrome_version and not chrome_version.startswith("Error") else None
        print(f"Chrome major version: {chrome_major_version}")
        
        if chrome_major_version == "135":
            # Use a known good version for Chrome 135
            print("Using known compatible ChromeDriver version for Chrome 135")
            driver_path = ChromeDriverManager(version="135.0.7049.0").install()
        else:
            # Let webdriver-manager choose the best version
            driver_path = ChromeDriverManager().install()
            
        print(f"ChromeDriver path: {driver_path}")
    except Exception as e:
        print(f"ChromeDriver installation failed: {e}")
    
    # Try initializing Chrome
    print("\nInitializing Chrome...")
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        print("Chrome successfully initialized!")
        
        # Get ChromeDriver version
        chrome_info = driver.capabilities
        print(f"\nChrome capabilities: {chrome_info}")
        
        # Try a simple navigation
        driver.get("https://www.google.com")
        print(f"Page title: {driver.title}")
        
        driver.quit()
    except Exception as e:
        print(f"Chrome initialization failed: {e}")
    
    print("\n=== Debug Info Complete ===\n")

if __name__ == "__main__":
    main() 