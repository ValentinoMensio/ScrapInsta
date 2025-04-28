from selenium.webdriver.common.by import By
import time
from config.config import INSTAGRAM_USER, INSTAGRAM_PASSWORD

def login_instagram(driver):
    try:
        driver.get("https://www.instagram.com/accounts/login/")
        time.sleep(1)

        username_field = driver.find_element(By.NAME, "username")
        password_field = driver.find_element(By.NAME, "password")

        username_field.send_keys(INSTAGRAM_USER)
        password_field.send_keys(INSTAGRAM_PASSWORD)

        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_button.click()

        time.sleep(5)
        print("Login successful")
        return driver
    except Exception as e:
        print(f"Login failed: {e}")
        driver.quit()
        return None