import streamlit as st
from scraper import get_stock

st.title("GESTHOR – Vérification Stock")

st.write("Entrez un code article et obtenez le stock disponible.")

username = st.text_input("Utilisateur BC")
password = st.text_input("Mot de passe BC", type="password")
item_code = st.text_input("Code article")

if st.button("Vérifier le stock"):
    if not item_code:
        st.error("Merci de saisir un code article.")
    else:
        try:
            stock = get_stock(item_code, username, password)
            st.success(f"Stock disponible : **{stock}**")
        except Exception as e:
            st.error("Erreur lors du scraping")
            st.code(str(e))
