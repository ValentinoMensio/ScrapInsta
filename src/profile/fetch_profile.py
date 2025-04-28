import os
import csv
from selenium.webdriver.common.by import By
from utils.parse import parse_number
from utils.undetected import random_sleep
from db.repositories import save_filtered_profile
import json
from pathlib import Path

with open(Path("src/config/keywords.json"), "r", encoding="utf-8") as f:
    keywords = json.load(f)

DOCTOR_KEYWORDS = keywords["doctor_keywords"]
RUBROS = keywords["rubros"]


def fetch_profile(driver, username):
    url = f"https://www.instagram.com/{username}/"
    driver.get(url)
    random_sleep(1.5, 2.5)

    try:
        bio = ""
        try:
            bio_element = driver.find_element(By.XPATH, "//div[@role='button']//span[@dir='auto']")
            bio = bio_element.text
        except Exception:
            pass 

        stats_elements = driver.find_elements(By.XPATH, "//ul/li")
        if len(stats_elements) < 3:
            return None

        posts_raw = stats_elements[0].text.split("\n")[0]
        followers_raw = stats_elements[1].text.split("\n")[0]
        following_raw = stats_elements[2].text.split("\n")[0]

        posts = parse_number(posts_raw)
        followers = parse_number(followers_raw)
        following = parse_number(following_raw)

        return {
            "username": username,
            "bio": bio,
            "followers": followers,
            "following": following,
            "posts": posts,
            "url": url
        }

    except Exception as e:
        print(f"Error fetching profile for {username}: {e}")
        return None

def detect_rubro(username, bio):
    username_lower = username.lower()
    bio_lower = bio.lower()

    if any(username_lower.startswith(key) for key in DOCTOR_KEYWORDS):
        return "Doctor"

    for rubro, keyword_list in RUBROS.items():
        if any(word in bio_lower for word in keyword_list):
            return rubro

    return None

def analyze_profile(driver, db_conn, usernames):
    resultados = []

    for i, username in enumerate(usernames):
        data = fetch_profile(driver, username)
        if not data:
            continue

        rubro = detect_rubro(data["username"], data["bio"])
        if rubro:
            profile_data = {
                "username": data["username"],
                "followers": data["followers"],
                "following": data["following"],
                "posts": data["posts"],
                "bio": data["bio"],
                "rubro": rubro,
                "url": data["url"]
            }
            save_filtered_profile(db_conn, profile_data)

            print(f"[{i+1}/{len(usernames)}] ✔ {data['username']} - {rubro}")
        else:
            print(f"[{i+1}/{len(usernames)}] ✘ {data['username']} - sin coincidencia")

        random_sleep(1.5, 3.0)
