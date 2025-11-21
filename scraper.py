from playwright.sync_api import sync_playwright

def get_stock(item_code, username, password):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("Ouverture de la page BC…")
        page.goto("https://bc.suntat.group/Kardesler/?company=BAK%20Kardesler&dc=0")

        # LOGIN
        page.wait_for_selector("#signInName", timeout=60000)
        page.fill("#signInName", username)
        page.fill("#password", password)
        page.click("#next")

        print("Connexion effectuée, attente du chargement…")
        page.wait_for_timeout(8000)

        # Aller à Articles
        page.click("xpath=//span[text()='Articles']")
        page.wait_for_selector("input[aria-label='Rechercher']", timeout=60000)

        # Rechercher l'article
        page.fill("input[aria-label='Rechercher']", item_code)
        page.wait_for_timeout(3000)

        # Récupérer le stock
        cell = page.locator("//div[@role='row' and @aria-rowindex='2']//div[@col-id='Inventory']")
        stock = cell.inner_text(timeout=30000)

        browser.close()
        print(f"Stock trouvé : {stock}")
        return stock
