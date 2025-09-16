from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from core.utils.parse import parse_number, extract_number
import logging

logger = logging.getLogger(__name__)

def extract_biography(driver) -> str:
    try:
        bio_element = driver.find_element(By.XPATH, "//div[@role='button']//span[@dir='auto']")
        return bio_element.text
    except NoSuchElementException:
        logger.warning("No se pudo encontrar la biografía")
        return ""
    except Exception as e:
        logger.error(f"Error extrayendo biografía: {e}")
        return ""

def extract_basic_stats(driver):
    try:
        stats_elements = driver.find_elements(By.XPATH, "//ul/li")
        if len(stats_elements) < 3:
            logger.warning("No se encontraron suficientes estadísticas")
            return None

        posts_raw = stats_elements[0].text.split("\n")[0]
        followers_raw = stats_elements[1].text.split("\n")[0]
        following_raw = stats_elements[2].text.split("\n")[0]

        posts = parse_number(extract_number(posts_raw))
        followers = parse_number(extract_number(followers_raw))
        following = parse_number(extract_number(following_raw))

        return {
            "posts": posts,
            "followers": followers,
            "following": following
        }
    except Exception as e:
        logger.error(f"Error extrayendo estadísticas básicas: {e}")
        return None
