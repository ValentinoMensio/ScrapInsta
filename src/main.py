import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from utils.undetected import random_sleep
from auth.login import login_instagram
from auth.session import save_cookies, load_cookies
from profile.fetch_profile import analyze_profile
from profile.fetch_followings import fetch_followings
import json
from pathlib import Path
from db.connection import get_db_connection
from db.repositories import save_followings, save_filtered_profile


def load_accounts(filepath="src/config/accounts.json"):
    with open(Path(filepath), "r", encoding="utf-8") as f:
        accounts = json.load(f)
    return accounts
    
def initialize_driver(account):
    options = uc.ChromeOptions()

    if account.get("proxy"):
        proxy = account["proxy"]
        options.add_argument(f"--proxy-server=http://{proxy}")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-extensions")
    options.add_argument("--profile-directory=Default")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

    prefs = {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False
    }
    options.add_experimental_option("prefs", prefs)

    return uc.Chrome(options=options, headless=False)

def handle_save_login_info_popup(driver):
    try:
        # Busca cualquier elemento (div, button, etc.) con role="button" y texto 'Not now'
        not_now_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//*[text()='Not now' and @role='button']"))
        )
        not_now_button.click()
        print("Clicked 'Not now' on save login info popup.")
    except Exception as e:
        print(f"No 'Save your login info' popup detected. Reason: {e}")


def is_logged_in(driver):
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//nav"))  # Indicador de login exitoso
        )
        return "accounts/login" not in driver.current_url
    except:
        return False

def main():
    db_conn = get_db_connection()

    accounts = load_accounts()
    for account in accounts:
        driver = initialize_driver(account)
    followings = []

    try:
        print("Starting Instagram session...")

        driver.get("https://www.instagram.com/")
        random_sleep(2, 4)

        cookies_loaded = load_cookies(driver)

        if cookies_loaded:
            print("Cookies loaded, refreshing session...")
            driver.refresh()
            random_sleep(2, 4)

        if is_logged_in(driver):
            print("Session started successfully")
        else:
            print("Attempting manual login...")
            driver = login_instagram(driver)
            handle_save_login_info_popup(driver)
            print(driver)
            if is_logged_in(driver):
                print("Manual login successful")
                save_cookies(driver)
            else:
                raise Exception("Manual login failed")

        username="ginecologa"
        followings = fetch_followings(driver, db_conn, username, max_followings=50)
        print(f"Followings: {followings}")

        analyze_profile(driver, db_conn, followings)

    except Exception as e:
        print(f"Unexpected error: {str(e)}")

    finally:
        input("Presioana Enter para cerrar el navegador...")
        if db_conn:
            db_conn.close()
        driver.quit()
        print("Driver closed")

if __name__ == "__main__":
    main()
