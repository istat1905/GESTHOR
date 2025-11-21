import streamlit as st
import pandas as pd
import numpy as np  # Utilisé pour les calculs rapides

# --- Configuration de la page ---
st.set_page_config(
    page_title="GESTHOR – Gestion Stock",
    page_icon="📦",
    layout="wide"
)

# --- CSS Personnalisé (Optionnel pour un look plus pro) ---
st.markdown("""
    <style>
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Titre Principal ---
col_logo, col_title = st.columns([1, 5])
with col_logo:
    st.write("📦") # Ici tu pourrais mettre st.image("logo.png")
with col_title:
    st.title("GESTHOR – Dashboard de Stock")
    st.markdown("Analysez votre inventaire et calculez vos besoins en colis.")
st.divider()

# --- Fonction de chargement en cache (Optimisation Performance) ---
@st.cache_data
def load_data(file):
    try:
        data = pd.read_excel(file)
        return data
    except Exception as e:
        st.error(f"Erreur de lecture : {e}")
        return None

# --- Sidebar : Upload et Filtres ---
with st.sidebar:
    st.header("📂 Données")
    uploaded_file = st.file_uploader("Charger un fichier Excel", type=["xlsx"])
    
    st.divider()
    st.header("⚙️ Filtres")
    search_input = st.text_input("🔍 Recherche (Code ou Description)")
    filter_rupture = st.checkbox("Afficher seulement les ruptures", value=False)

# --- Logique Principale ---
if uploaded_file is not None:
    df = load_data(uploaded_file)

    if df is not None:
        # Vérification des colonnes
        required_cols = ["Inventory", "Qty. per Sales Unit of Measure", "N° article.", "Description"]
        missing_cols = [col for col in required_cols if col not in df.columns]

        if missing_cols:
            st.error(f"⚠️ Colonnes manquantes : {', '.join(missing_cols)}")
        else:
            # 1. Nettoyage et Calculs (Vectorisation avec Numpy pour la vitesse)
            df["Qty. per Sales Unit of Measure"] = pd.to_numeric(df["Qty. per Sales Unit of Measure"], errors='coerce').fillna(1)
            # Éviter la division par zéro
            df["Stock en colis"] = df["Inventory"] / df["Qty. per Sales Unit of Measure"].replace(0, 1)
            
            # Définition des statuts via conditions vectorisées (plus rapide que .apply)
            conditions = [
                (df["Inventory"] <= 0),
                (df["Inventory"] < 500)
            ]
            choices = ["❌ Rupture", "⚠️ Faible"]
            df["Statut"] = np.select(conditions, choices, default="✅ OK")

            # 2. Filtrage Dynamique
            if search_input:
                mask = (
                    df["N° article."].astype(str).str.contains(search_input, case=False) | 
                    df["Description"].astype(str).str.contains(search_input, case=False)
                )
                df = df[mask]
            
            if filter_rupture:
                df = df[df["Statut"] == "❌ Rupture"]

            # 3. Affichage des KPIs (Indicateurs clés)
            st.subheader("📊 Vue d'ensemble")
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            
            with kpi1:
                st.metric("Total Articles", len(df))
            with kpi2:
                stock_global = int(df["Inventory"].sum())
                st.metric("Stock Total (Unités)", f"{stock_global:,}".replace(",", " "))
            with kpi3:
                nb_ruptures = len(df[df["Statut"] == "❌ Rupture"])
                st.metric("Articles en Rupture", nb_ruptures, delta=-nb_ruptures, delta_color="inverse")
            with kpi4:
                nb_faible = len(df[df["Statut"] == "⚠️ Faible"])
                st.metric("Stock Faible", nb_faible, delta_color="off")

            st.divider()

            # 4. Tableau de données amélioré
            st.subheader("📋 Détail du Stock")
            
            # Configuration des colonnes pour un affichage pro
            st.dataframe(
                df[["N° article.", "Description", "Inventory", "Qty. per Sales Unit of Measure", "Stock en colis", "Statut"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "N° article.": st.column_config.TextColumn("Code Article", help="Identifiant unique"),
                    "Inventory": st.column_config.NumberColumn(
                        "Inventaire (Unités)", 
                        format="%d",
                    ),
                    "Stock en colis": st.column_config.ProgressColumn(
                        "Stock (Colis)", 
                        format="%.1f colis",
                        min_value=0,
                        max_value=float(df["Stock en colis"].max()),
                    ),
                    "Statut": st.column_config.TextColumn("État"),
                }
            )

            # Bouton de téléchargement des résultats filtrés
            st.download_button(
                label="📥 Télécharger le rapport filtré (CSV)",
                data=df.to_csv(index=False).encode('utf-8'),
                file_name='stock_gesthor.csv',
                mime='text/csv',
            )

else:
    st.info("👈 Veuillez charger un fichier Excel dans le menu latéral pour commencer.")
