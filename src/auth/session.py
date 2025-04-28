import json
import os
import time

DEFAULT_PATH = "data/cookies.json"

def save_cookies(driver, file_path=DEFAULT_PATH):
    """Save browser cookies to a JSON file."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    cookies = driver.get_cookies()
    with open(file_path, "w") as file:
        json.dump(cookies, file, indent=4)
    print(f"Cookies saved to {file_path}")

def has_sessionid(file_path="data/cookies.json"):
    try:
        with open(file_path, "r") as file:
            cookies = json.load(file)
            for cookie in cookies:
                if cookie.get("name") == "sessionid":
                    print(f"Sessionid found: {cookie.get('value')[:10]}...")
                    return True
        print("! sessionid NOT found in cookies.")
        return False
    except Exception as e:
        print(f"! Error checking sessionid: {e}")
        return False

def load_cookies(driver, file_path=DEFAULT_PATH):
    """Load cookies from a JSON file into the browser."""
    try:
        driver.get("https://www.instagram.com/")
        time.sleep(1)
        driver.delete_all_cookies()

        with open(file_path, "r") as file:
            cookies = json.load(file)

        for cookie in cookies:
            if 'instagram.com' not in cookie.get('domain', ''):
                cookie['domain'] = '.instagram.com'
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                print(f"! Error adding cookie {cookie.get('name')}: {e}")

        print(f"Cookies loaded from {file_path}")
        return True

    except FileNotFoundError:
        print(f"! Cookie file not found at {file_path}")
        return False
    except json.JSONDecodeError:
        print(f"! Error decoding JSON file at {file_path}")
        return False
    except Exception as e:
        print(f"! Unexpected error loading cookies: {str(e)}")
        return False
