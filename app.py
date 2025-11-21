import streamlit as st
import pandas as pd

st.title("GESTHOR – Gestion de stock depuis Excel")
st.write("Importez votre fichier Excel contenant vos articles et stock.")

# Upload fichier Excel
uploaded_file = st.file_uploader("Choisir un fichier Excel", type=["xlsx"])

if uploaded_file is not None:
    # Lire le fichier Excel
    try:
        df = pd.read_excel(uploaded_file)
        st.subheader("Aperçu des données importées")
        st.dataframe(df.head())

        # Vérifier que les colonnes nécessaires existent
        if "Inventory" in df.columns and "Qty. per Sales Unit of Measure" in df.columns:
            # Calcul stock en colis
            df["Stock en colis"] = df["Inventory"] / df["Qty. per Sales Unit of Measure"]

            st.subheader("Stock calculé en colis")
            st.dataframe(df[["No", "Inventory", "Qty. per Sales Unit of Measure", "Stock en colis"]])
        else:
            st.error("Le fichier Excel doit contenir les colonnes 'Inventory' et 'Qty. per Sales Unit of Measure'.")
    except Exception as e:
        st.error(f"Erreur lors de la lecture du fichier Excel : {e}")
