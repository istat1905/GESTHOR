import requests
import streamlit as st

st.title("GESTHOR – Vérification Stock")

st.write("Entrez un code article pour récupérer le stock depuis Business Central.")

username = st.text_input("Utilisateur BC")
password = st.text_input("Mot de passe BC", type="password")
item_code = st.text_input("Code article")

if st.button("Vérifier le stock"):
    if not (username and password and item_code):
        st.error("Merci de remplir tous les champs.")
    else:
        url = f"http://demaxbc202.suntat.group:7088/Kardesler/ODataV4/Company('BAK%20Kardesler')/EDF_Item_Card?$filter=No eq '{item_code}'"
        try:
            response = requests.get(url, auth=(username, password))
            if response.status_code == 200:
                data = response.json()
                if data['value']:
                    stock = data['value'][0].get('Inventory', 'Non disponible')
                    st.success(f"Stock disponible : {stock}")
                else:
                    st.warning("Article non trouvé.")
            else:
                st.error(f"Erreur API : {response.status_code} - {response.text}")
        except Exception as e:
            st.error(f"Erreur lors de la connexion à l'API : {e}")
