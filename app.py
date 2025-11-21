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

# --- CSS Personnalisé ---
st.markdown("""
    <style>
    /* Style des KPIs */
    [data-testid="stMetric"] {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #e9ecef;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    /* Pied de page */
    .footer {
        text-align: center;
        margin-top: 3rem;
        padding-top: 1rem;
        border-top: 1px solid #e9ecef;
        color: #6c757d;
    }
    .footer-stars {
        color: #f1c40f;
        letter-spacing: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- EN-TÊTE AVEC LOGO ---
# On utilise des colonnes pour centrer le logo
col_logo1, col_logo2, col_logo3 = st.columns([1, 2, 1])

with col_logo2:
    # Affiche l'image. "width" ajuste la taille (en pixels).
    # Si le fichier est dans un dossier, mettez "images/Gesthor.png"
    try:
        st.image("Gesthor.png", width=350) 
    except:
        # Fallback au cas où l'image n'est pas trouvée ou nom incorrect
        st.error("Image 'Gesthor.png' introuvable. Vérifiez le nom du fichier sur GitHub.")
        st.title("GESTHOR")

st.markdown("<h3 style='text-align: center; color: grey;'>📦 Tableau de bord de gestion de stock</h3>", unsafe_allow_html=True)
st.markdown("---")

# --- Fonction de chargement ---
@st.cache_data
def load_data(file):
    try:
        data = pd.read_excel(file)
        # Conversion en string pour éviter les bugs
        if "N° article." in data.columns:
            data["N° article."] = data["N° article."].astype(str)
        if "Description" in data.columns:
            data["Description"] = data["Description"].astype(str)
        return data
    except ImportError:
        st.error("🛑 Erreur : Module Excel manquant. Essayez d'enregistrer le fichier en CSV.")
        return None
    except Exception as e:
        st.error(f"Erreur de lecture : {e}")
        return None

# --- Sidebar ---
with st.sidebar:
    # Petit logo aussi dans la sidebar si vous voulez
    # st.image("Gesthor.png", width=100) 
    st.header("GESTHOR")
    st.caption("Version: v4.0 (Logo)")
    st.divider()
    
    st.header("📂 Fichier")
    uploaded_file = st.file_uploader("Charger Excel (.xlsx)", type=["xlsx"])
    
    st.divider()
    st.header("⚙️ Filtres")
    search_input = st.text_input("🔍 Recherche (Code/Desc)")
    
    filter_rupture = st.checkbox("❌ Ruptures uniquement", value=False)
    filter_faible = st.checkbox("⚠️ Stock faible uniquement", value=False)

# --- Logique Principale ---
if uploaded_file is not None:
    df_original = load_data(uploaded_file)

    if df_original is not None:
        df = df_original.copy()
        
        # Vérification colonnes
        required_cols = ["Inventory", "Qty. per Sales Unit of Measure", "N° article.", "Description"]
        missing_cols = [col for col in required_cols if col not in df.columns]

        if missing_cols:
            st.error(f"⚠️ Colonnes manquantes : {', '.join(missing_cols)}")
        else:
            # 1. Calculs
            df["Qty. per Sales Unit of Measure"] = pd.to_numeric(df["Qty. per Sales Unit of Measure"], errors='coerce').fillna(1)
            df["Inventory"] = pd.to_numeric(df["Inventory"], errors='coerce').fillna(0)
            df["Stock en colis"] = df["Inventory"] / df["Qty. per Sales Unit of Measure"].replace(0, 1)
            
            # Statuts
            conditions = [
                (df["Inventory"] <= 0),
                (df["Inventory"] < 500)
            ]
            choices = ["Rupture", "Faible"]
            df["Statut"] = np.select(conditions, choices, default="OK")

            # 2. Filtres
            if search_input:
                mask = (
                    df["N° article."].str.contains(search_input, case=False, na=False) | 
                    df["Description"].str.contains(search_input, case=False, na=False)
                )
                df = df[mask]
            
            status_filters = []
            if filter_rupture: status_filters.append("Rupture")
            if filter_faible: status_filters.append("Faible")
            if status_filters:
                 df = df[df["Statut"].isin(status_filters)]

            # 3. KPIs
            st.subheader("📊 Indicateurs")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Articles", len(df))
            nb_rupt = len(df_original[df_original["Inventory"] <= 0])
            k2.metric("Alertes Rupture (Total)", nb_rupt, delta=-nb_rupt, delta_color="inverse")
            k3.metric("Unités (Visibles)", f"{int(df['Inventory'].sum()):,}".replace(",", " "))
            k4.metric("Colis (Estimés)", f"{float(df['Stock en colis'].sum()):,.1f}")

            st.divider()

            # 4. Graphiques NATIFS
            col_g1, col_g2 = st.columns(2)
            
            with col_g1:
                st.subheader("Répartition")
                if not df.empty:
                    status_counts = df["Statut"].value_counts()
                    st.bar_chart(status_counts, color=["#ff4b4b", "#ffa421", "#21c354"])
                else:
                    st.info("Aucune donnée.")

            with col_g2:
                st.subheader("Top 10 Stocks (Unités)")
                if not df.empty:
                    top_10 = df.nlargest(10, 'Inventory')[["N° article.", "Inventory"]].set_index("N° article.")
                    st.bar_chart(top_10)
                else:
                    st.info("Aucune donnée.")

            st.divider()

            # 5. Tableau
            st.subheader("📋 Détail")
            st.dataframe(
                df[["N° article.", "Description", "Inventory", "Qty. per Sales Unit of Measure", "Stock en colis", "Statut"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Inventory": st.column_config.NumberColumn("Stock (UVC)", format="%d"),
                    "Stock en colis": st.column_config.ProgressColumn(
                        "Stock (Colis)", 
                        format="%.1f",
                        max_value=float(df_original["Inventory"].max()/1) if not df_original.empty else 100,
                    ),
                }
            )

else:
    # Écran d'accueil
    col_center1, col_center2, col_center3 = st.columns([1, 2, 1])
    with col_center2:
        st.info("👈 Veuillez charger un fichier Excel dans le menu latéral pour commencer.")

# --- PIED DE PAGE ---
st.markdown("""
    <div class="footer">
        <div class="footer-stars">★★★★★</div>
        <p>Powered by IC - 2025</p>
    </div>
    """, unsafe_allow_html=True)
