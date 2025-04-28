import os
import time
import csv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from utils.undetected import random_sleep
from db.repositories import save_followings 



def fetch_followings(driver,db_conn, username_origin, max_followings=100):
    url = f"https://www.instagram.com/{username_origin}/"
    driver.get(url)
    random_sleep(2.5, 4.0)

    try:
        following_button = driver.find_element(By.XPATH, "//a[contains(@href, '/following')]")
        following_button.click()

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
        )
        random_sleep(3.5, 5.0)

        usernames = []
        seen = set()
        last_count = 0
        same_count_repeats = 0
        scroll_attempts = 0

        while len(usernames) < max_followings and same_count_repeats < 5:
            links = driver.find_elements(By.XPATH, "//div[@role='dialog']//a[contains(@href, '/') and not(contains(@href, 'explore'))]")

            for link in links:
                name = link.text.strip()
                if name and name not in seen:
                    usernames.append(name)
                    seen.add(name)
                if len(usernames) >= max_followings:
                    break

            if len(usernames) >= max_followings:
                break

            driver.execute_script("""
                const scrollContainers = document.querySelectorAll('div[role="dialog"] div');
                for (const container of scrollContainers) {
                    if (container.scrollHeight > container.clientHeight) {
                        container.scrollTop = container.scrollHeight;
                        break;
                    }
                }
            """)

            random_sleep(1.0, 1.5)

            if len(usernames) == last_count:
                same_count_repeats += 1
            else:
                same_count_repeats = 0
                last_count = len(usernames)

            scroll_attempts += 1

    except Exception as e:
        print(f"Error during scrolling [{scroll_attempts}]: {e}")

    print(f"Total collected: {len(usernames)}")
    print(f"Scrolls performed: {scroll_attempts}")

    save_followings(db_conn, username_origin, usernames)

    return usernames[:max_followings]
