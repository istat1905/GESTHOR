from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.firefox.service import Service
import time

def get_stock(item_code, username, password):

    options = webdriver.FirefoxOptions()
    options.add_argument("--headless")

    driver = webdriver.Firefox(
        service=Service(GeckoDriverManager().install()),
        options=options
    )

    driver.get("https://bc.suntat.group/Kardesler/?company=BAK%20Kardesler&dc=0")

    # --- LOGIN ---
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.ID, "signInName"))
    ).send_keys(username)

    driver.find_element(By.ID, "password").send_keys(password)
    driver.find_element(By.ID, "next").click()

    # Temps pour charger BC
    time.sleep(6)

    # --- Aller dans Articles ---
    articles_btn = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.XPATH, "//span[text()='Articles']"))
    )
    articles_btn.click()

    # --- Champ de recherche ---
    search_box = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.XPATH, "//input[@aria-label='Rechercher']"))
    )

    search_box.clear()
    search_box.send_keys(item_code)
    time.sleep(2)

    # --- Lire la colonne Inventory ---
    inventory_cell = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((
            By.XPATH,
            "//div[@role='row' and @aria-rowindex='2']//div[@col-id='Inventory']"
        ))
    )

    stock = inventory_cell.text.strip()
    driver.quit()

    return stock
