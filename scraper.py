from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import json
import time
import getpass

def debug_screenshot(driver, name):
    """Save screenshot for debugging"""
    driver.save_screenshot(f"{name}.png")
    print(f"📸 Saved debug screenshot: {name}.png")

def get_credentials():
    """Securely get login credentials"""
    print("Enter IITM Student Credentials:")
    username = "24f1001929@ds.study.iitm.ac.in"  # Default username for IITM student
    password = getpass.getpass("Password:")
    return username, password

def login(driver):
    """Handle IITM login process"""
    username, password = get_credentials()
    
    print("🔐 Navigating to login page...")
    driver.get("https://tds.s-anand.net/login")
    time.sleep(2)  # Initial load
    
    try:
        # Wait for IITM-specific login elements
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "username"))
        )
        
        print("🖊️ Filling credentials...")
        email_field = driver.find_element(By.ID, "username")
        email_field.clear()
        email_field.send_keys(username)
        
        password_field = driver.find_element(By.ID, "password")
        password_field.clear()
        password_field.send_keys(password)
        
        debug_screenshot(driver, "before_login")
        
        # Click login button - may need adjustment
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        login_button.click()
        
        # Wait for successful login (adjust URL as needed)
        WebDriverWait(driver, 15).until(
            EC.url_contains("2025-01") or 
            EC.presence_of_element_located((By.CLASS_NAME, "dashboard"))
        )
        debug_screenshot(driver, "after_login")
        return True
        
    except Exception as e:
        debug_screenshot(driver, "login_error")
        print(f"❌ Login failed: {str(e)}")
        print("Please check:")
        print("1. Correct login URL (might be SSO)")
        print("2. Screenshots in your directory")
        return False

def scrape_course():
    # Configure Chrome (run visible for debugging)
    options = Options()
    options.add_argument("--window-size=1200,900")
    # options.add_argument("--headless")  # Disable for debugging
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        if not login(driver):
            return
        
        print("🌐 Loading course content...")
        driver.get("https://tds.s-anand.net/#/2025-01/")
        
        # Debug: Check if content loaded
        debug_screenshot(driver, "course_page")
        
        # Try basic content extraction
        try:
            content = driver.find_element(By.TAG_NAME, "body").text
            with open("raw_content.txt", "w") as f:
                f.write(content)
            print("📝 Saved raw text content to raw_content.txt")
        except Exception as e:
            print(f"⚠️ Couldn't extract text: {str(e)}")
        
    finally:
        driver.quit()
        print("🛑 Browser closed")

if __name__ == "__main__":
    scrape_course()