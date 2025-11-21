import streamlit as st
import pandas as pd

st.set_page_config(page_title="GESTHOR – Gestion Stock", layout="wide")
st.title("GESTHOR – Gestion de stock depuis Excel")

# --- Upload et sauvegarde du fichier ---
if "df" not in st.session_state:
    st.session_state.df = None

uploaded_file = st.file_uploader("Choisir un fichier Excel", type=["xlsx"])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        st.session_state.df = df  # Garde le fichier en mémoire
        st.success("Fichier chargé avec succès !")
    except Exception as e:
        st.error(f"Erreur lors de la lecture du fichier Excel : {e}")

# --- Affichage / suppression du fichier ---
if st.session_state.df is not None:
    st.subheader("Aperçu des données importées")
    st.dataframe(st.session_state.df.head())

    if st.button("Supprimer le fichier"):
        st.session_state.df = None
        st.experimental_rerun()

    # --- Vérification des colonnes nécessaires ---
    required_cols = ["Inventory", "Qty. per Sales Unit of Measure", "N° article."]
    missing_cols = [col for col in required_cols if col not in st.session_state.df.columns]
    
    if missing_cols:
        st.warning(f"Le fichier doit contenir les colonnes suivantes : {', '.join(required_cols)}")
    else:
        # Calcul du stock en colis
        df = st.session_state.df.copy()
        df["Stock en colis"] = df["Inventory"] / df["Qty. per Sales Unit of Measure"]

        # --- Recherche article ---
        st.subheader("Rechercher un article")
        search_input = st.text_input("Code article à rechercher (N° article.)")
        if search_input:
            df_filtered = df[df["N° article."].astype(str).str.strip().str.contains(search_input.strip(), case=False)]
        else:
            df_filtered = df

        st.subheader("Stock calculé en colis")
        st.dataframe(df_filtered[["N° article.", "Description", "Inventory", 
                                  "Qty. per Sales Unit of Measure", "Stock en colis"]])
