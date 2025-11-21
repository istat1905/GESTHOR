from playwright.sync_api import sync_playwright
import time

def get_stock(item_code, username, password):

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto("https://bc.suntat.group/Kardesler/?company=BAK%20Kardesler&dc=0")

        # LOGIN
        page.wait_for_selector("#signInName")
        page.fill("#signInName", username)
        page.fill("#password", password)
        page.click("#next")

        page.wait_for_timeout(5000)

        # ARTICLES
        page.click("xpath=//span[text()='Articles']")

        page.wait_for_selector("input[aria-label='Rechercher']")
        page.fill("input[aria-label='Rechercher']", item_code)

        page.wait_for_timeout(2000)

        # STOCK
        cell = page.locator("//div[@role='row' and @aria-rowindex='2']//div[@col-id='Inventory']")
        stock = cell.inner_text()

        browser.close()
        return stock
