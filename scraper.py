from playwright.sync_api import sync_playwright

def get_stock(item_code, username, password):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Ouvrir Business Central
        page.goto("https://bc.suntat.group/Kardesler/?company=BAK%20Kardesler&dc=0")

        # LOGIN
        page.wait_for_selector("#signInName")
        page.fill("#signInName", username)
        page.fill("#password", password)
        page.click("#next")

        # Attendre le chargement complet
        page.wait_for_timeout(6000)

        # Aller à Articles
        page.click("xpath=//span[text()='Articles']")
        page.wait_for_selector("input[aria-label='Rechercher']")

        # Rechercher l'article
        page.fill("input[aria-label='Rechercher']", item_code)
        page.wait_for_timeout(2000)

        # Récupérer le stock (colonne Inventory)
        cell = page.locator("//div[@role='row' and @aria-rowindex='2']//div[@col-id='Inventory']")
        stock = cell.inner_text()

        browser.close()
        return stock
