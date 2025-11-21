import streamlit as st
import pandas as pd
import numpy as np

# --- Configuration de la page ---
st.set_page_config(
    page_title="GESTHOR – Gestion Stock",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS Épuré (Design plus clean) ---
st.markdown("""
    <style>
    /* Centrage du logo et titre */
    .block-container {
        padding-top: 2rem;
    }
    /* Style des KPIs plus léger et équilibré */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #f0f2f6;
        border-radius: 8px;
        padding: 15px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    div[data-testid="stMetricLabel"] {
        justify-content: center;
        font-weight: bold;
        color: #555;
    }
    div[data-testid="stMetricValue"] {
        justify-content: center;
        color: #0072B5;
    }
    /* Pied de page */
    .footer {
        text-align: center;
        margin-top: 4rem;
        padding-top: 1rem;
        border-top: 1px solid #eee;
        color: #888;
        font-size: 0.8rem;
    }
    </style>
    """, unsafe_allow_html=True)

# --- LOGO CENTRÉ (Tout en haut) ---
col_l1, col_l2, col_l3 = st.columns([1, 1, 1])
with col_l2:
    try:
        # Affiche le logo centré
        st.image("Gesthor.png", use_container_width=True) 
    except:
        st.markdown("<h1 style='text-align: center; color: #0072B5;'>GESTHOR</h1>", unsafe_allow_html=True)

st.markdown("<h4 style='text-align: center; color: grey; font-weight: normal; margin-bottom: 30px;'>Tableau de bord de gestion de stock</h4>", unsafe_allow_html=True)

# --- Fonction de chargement robuste ---
@st.cache_data
def load_data(file):
    try:
        data = pd.read_excel(file)
        # Conversion immédiate en TEXTE pour que la recherche fonctionne à 100%
        if "N° article." in data.columns:
            data["N° article."] = data["N° article."].astype(str).str.strip()
        if "Description" in data.columns:
            data["Description"] = data["Description"].astype(str).str.strip()
        return data
    except ImportError:
        st.error("Module Excel manquant. Convertissez votre fichier en CSV.")
        return None
    except Exception as e:
        st.error(f"Erreur : {e}")
        return None

# --- Sidebar (Juste l'upload et la recherche) ---
with st.sidebar:
    st.header("📂 Données")
    uploaded_file = st.file_uploader("Fichier Excel (.xlsx)", type=["xlsx"])
    
    st.divider()
    st.header("🔍 Recherche")
    search_input = st.text_input("Tapez un code ou un nom...", placeholder="Ex: 1024 ou Carton")

# --- Logique Principale ---
if uploaded_file is not None:
    df_original = load_data(uploaded_file)

    if df_original is not None:
        df = df_original.copy()
        
        # 1. CALCULS & NETTOYAGE
        required_cols = ["Inventory", "Qty. per Sales Unit of Measure", "N° article.", "Description"]
        missing_cols = [col for col in required_cols if col not in df.columns]

        if missing_cols:
            st.error(f"Colonnes manquantes : {', '.join(missing_cols)}")
        else:
            # Nettoyage numérique
            df["Qty. per Sales Unit of Measure"] = pd.to_numeric(df["Qty. per Sales Unit of Measure"], errors='coerce').fillna(1)
            df["Inventory"] = pd.to_numeric(df["Inventory"], errors='coerce').fillna(0)
            df["Stock en colis"] = df["Inventory"] / df["Qty. per Sales Unit of Measure"].replace(0, 1)
            
            # Attribution des Statuts
            conditions = [
                (df["Inventory"] <= 0),
                (df["Inventory"] < 500)
            ]
            choices = ["Rupture", "Faible"]
            df["Statut"] = np.select(conditions, choices, default="OK")

            # 2. MOTEUR DE RECHERCHE (CORRIGÉ)
            # On filtre AVANT de faire les onglets pour que la recherche s'applique partout
            if search_input:
                mask = (
                    df["N° article."].str.contains(search_input, case=False, na=False) | 
                    df["Description"].str.contains(search_input, case=False, na=False)
                )
                df = df[mask]

            # 3. INDICATEURS (KPIS) ÉQUILIBRÉS
            k1, k2, k3, k4 = st.columns(4)
            
            # Données globales (après recherche)
            nb_rupt = len(df[df["Statut"] == "Rupture"])
            nb_faible = len(df[df["Statut"] == "Faible"])
            stock_tot = int(df["Inventory"].sum())
            colis_tot = float(df["Stock en colis"].sum())

            k1.metric("Articles trouvés", len(df))
            k2.metric("En Rupture", nb_rupt, delta_color="inverse")
            k3.metric("Stock Faible", nb_faible, delta_color="normal")
            k4.metric("Volume Colis", f"{colis_tot:,.0f}")

            st.divider()

            # 4. GRAPHIQUE UNIQUE (Histogramme répartition)
            st.subheader("📈 Répartition des stocks")
            if not df.empty:
                status_counts = df["Statut"].value_counts()
                st.bar_chart(status_counts)
            
            st.divider()

            # 5. ONGLETS (TABS)
            tab_rupture, tab_faible, tab_ok, tab_tout = st.tabs(["❌ Ruptures", "⚠️ Stock Faible", "✅ Stock OK", "📁 Tout le stock"])

            # Fonction pour afficher le contenu d'un onglet
            def afficher_onglet(dataframe, filtre_statut=None):
                if filtre_statut:
                    data_view = dataframe[dataframe["Statut"] == filtre_statut]
                else:
                    data_view = dataframe
                
                if data_view.empty:
                    st.info("Aucun article dans cette catégorie.")
                else:
                    # Sélecteur de quantité (Slider) local à l'onglet
                    limit = st.slider(f"Nombre d'articles à afficher", 1, 100, 10, key=f"slider_{filtre_statut}")
                    
                    # Affichage du tableau
                    st.dataframe(
                        data_view.head(limit)[["N° article.", "Description", "Inventory", "Stock en colis", "Statut"]],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Inventory": st.column_config.NumberColumn("Unités", format="%d"),
                            "Stock en colis": st.column_config.ProgressColumn("Colis", format="%.1f", max_value=float(df_original["Inventory"].max()/1) if not df_original.empty else 100),
                        }
                    )

            # Remplissage des onglets
            with tab_rupture:
                afficher_onglet(df, "Rupture")
            
            with tab_faible:
                afficher_onglet(df, "Faible")
            
            with tab_ok:
                afficher_onglet(df, "OK")
            
            with tab_tout:
                afficher_onglet(df, None)

else:
    # Message d'accueil simple
    st.info("👈 Veuillez charger votre fichier Excel dans le menu de gauche.")

# --- PIED DE PAGE ---
st.markdown("""
    <div class="footer">
        <p>Powered by IC - 2025 ★★★★★</p>
    </div>
    """, unsafe_allow_html=True)
