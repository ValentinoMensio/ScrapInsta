from selenium.webdriver.common.by import By
from core.utils.undetected import random_sleep
import time

def login_instagram(driver, account):
    try:
        driver.get("https://www.instagram.com/accounts/login/")
        random_sleep(1.0, 2.0)

        username_field = driver.find_element(By.NAME, "username")
        password_field = driver.find_element(By.NAME, "password")

        username_field.send_keys(account['username'])
        password_field.send_keys(account['password'])

        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_button.click()

        time.sleep(5)
        random_sleep(2.0, 3.0)
        print(f"Login successful for {account['username']}")
        return driver
    except Exception as e:
        print(f"Login failed for {account['username']}: {e}")
        driver.quit()
        return None