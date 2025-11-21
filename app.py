import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# --- Configuration de la page ---
st.set_page_config(
    page_title="GESTHOR – Gestion Stock",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS Personnalisé pour le look Pro ---
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
    /* Style du titre principal centré */
    .main-header {
        text-align: center;
        margin-bottom: 2rem;
    }
    .main-logo-text {
        font-size: 4rem;
        font-weight: bold;
        color: #0072B5; /* Couleur bleue similaire à ton image */
        margin-bottom: -1rem;
    }
    .main-title-text {
        font-size: 2.5rem;
        font-weight: bold;
    }
    /* Style du pied de page */
    .footer {
        text-align: center;
        margin-top: 3rem;
        padding-top: 1rem;
        border-top: 1px solid #e9ecef;
        color: #6c757d;
    }
    .footer-stars {
        color: #f1c40f; /* Jaune or */
        letter-spacing: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- EN-TÊTE STYLE "DESATHOR" ---
st.markdown("""
    <div class="main-header">
        <p class="main-logo-text">G</p>
        <p class="main-title-text">GESTHOR</p>
        <p style="font-size: 1.2rem; color: grey;">📦 Tableau de bord de gestion de stock et calcul de colis</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# --- Fonction de chargement en cache ---
@st.cache_data
def load_data(file):
    try:
        data = pd.read_excel(file)
        # On s'assure que les colonnes textuelles sont bien des chaînes
        if "N° article." in data.columns:
            data["N° article."] = data["N° article."].astype(str)
        if "Description" in data.columns:
            data["Description"] = data["Description"].astype(str)
        return data
    except Exception as e:
        st.error(f"Erreur de lecture : {e}")
        return None

# --- Sidebar : Upload et Filtres ---
with st.sidebar:
    st.title("GESTHOR")
    st.caption("Rôle: Admin Stock")
    st.divider()
    
    st.header("📂 Données source")
    uploaded_file = st.file_uploader("Charger un fichier Excel (Inventaire)", type=["xlsx"])
    st.info("💡 Le fichier doit contenir : Inventory, Qty. per Sales Unit of Measure, N° article., Description")
    
    st.divider()
    st.header("⚙️ Filtres")
    search_input = st.text_input("🔍 Recherche rapide (Code/Desc)")
    
    st.subheader("Filtrer par statut :")
    filter_rupture = st.checkbox("❌ Ruptures uniquement", value=False)
    filter_faible = st.checkbox("⚠️ Stock faible uniquement", value=False)

# --- Logique Principale ---
if uploaded_file is not None:
    df_original = load_data(uploaded_file)

    if df_original is not None:
        df = df_original.copy()
        # Vérification des colonnes
        required_cols = ["Inventory", "Qty. per Sales Unit of Measure", "N° article.", "Description"]
        missing_cols = [col for col in required_cols if col not in df.columns]

        if missing_cols:
            st.error(f"⚠️ Colonnes manquantes dans le fichier : {', '.join(missing_cols)}")
        else:
            # --- 1. NETTOYAGE ET CALCULS ---
            # Conversion numérique sécurisée
            df["Qty. per Sales Unit of Measure"] = pd.to_numeric(df["Qty. per Sales Unit of Measure"], errors='coerce').fillna(1)
            df["Inventory"] = pd.to_numeric(df["Inventory"], errors='coerce').fillna(0)

            # Calcul du stock colis (éviter division par 0)
            df["Stock en colis"] = df["Inventory"] / df["Qty. per Sales Unit of Measure"].replace(0, 1)
            
            # Définition des statuts (Vectorisé avec Numpy)
            conditions = [
                (df["Inventory"] <= 0),
                (df["Inventory"] < 500)
            ]
            choices = ["❌ Rupture", "⚠️ Faible"]
            df["Statut"] = np.select(conditions, choices, default="✅ OK")

            # --- 2. FILTRAGE DYNAMIQUE ---
            if search_input:
                mask = (
                    df["N° article."].str.contains(search_input, case=False, na=False) | 
                    df["Description"].str.contains(search_input, case=False, na=False)
                )
                df = df[mask]
            
            # Application des checkbox (si les deux sont cochées, on montre les deux)
            status_filters = []
            if filter_rupture: status_filters.append("❌ Rupture")
            if filter_faible: status_filters.append("⚠️ Faible")
            
            if status_filters:
                 df = df[df["Statut"].isin(status_filters)]

            # --- 3. KPIs ---
            st.subheader("📊 Indicateurs Clés")
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            
            with kpi1:
                st.metric("Articles filtrés", len(df))
            with kpi2:
                # Calcul sur le dataframe total (non filtré) pour les alertes globales
                nb_ruptures_total = len(df_original[df_original["Inventory"] <= 0])
                st.metric("Alertes Rupture (Total)", nb_ruptures_total, delta=-nb_ruptures_total, delta_color="inverse")
            with kpi3:
                 # Calcul du stock total sur les données filtrées
                stock_total_filtered = int(df["Inventory"].sum())
                st.metric("Volumétrie visible (Unités)", f"{stock_total_filtered:,}".replace(",", " "))
            with kpi4:
                stock_colis_total = float(df["Stock en colis"].sum())
                st.metric("Estimation Totale Colis", f"{stock_colis_total:,.1f}")

            st.divider()

            # --- 4. GRAPHIQUES (NOUVEAU) ---
            st.subheader("📈 Analyse visuelle")
            col_graph1, col_graph2 = st.columns(2)

            with col_graph1:
                st.markdown("**Répartition des statuts (Sur données filtrées)**")
                if not df.empty:
                    # Compter les statuts
                    status_counts = df["Statut"].value_counts().reset_index()
                    status_counts.columns = ["Statut", "Nombre d'articles"]
                    
                    # Créer le camembert
                    fig_pie = px.pie(
                        status_counts, 
                        values="Nombre d'articles", 
                        names='Statut',
                        color='Statut',
                        color_discrete_map={"✅ OK": "#2ecc71", "⚠️ Faible": "#f1c40f", "❌ Rupture": "#e74c3c"},
                        hole=0.4 # Donut chart
                    )
                    fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.info("Pas de données à afficher.")

            with col_graph2:
                st.markdown("**Top 10 - Plus gros stocks (Unités)**")
                if not df.empty:
                    # Prendre les 10 plus gros stocks
                    top_10_stock = df.nlargest(10, 'Inventory')
                    # Créer le bar chart horizontal
                    fig_bar = px.bar(
                        top_10_stock,
                        x='Inventory',
                        y='N° article.',
                        orientation='h',
                        text_auto='.2s', # Affiche la valeur sur la barre
                        color='Inventory',
                         color_continuous_scale='Blues'
                    )
                    fig_bar.update_layout(
                        margin=dict(t=0, b=0, l=0, r=0), 
                        height=300,
                        xaxis_title=None,
                        yaxis_title=None,
                        coloraxis_showscale=False # Cache la légende de couleur
                    )
                    # Inverser l'axe Y pour avoir le plus grand en haut
                    fig_bar.update_yaxes(autorange="reversed")
                    st.plotly_chart(fig_bar, use_container_width=True)
                else:
                    st.info("Pas de données à afficher.")

            st.divider()

            # --- 5. TABLEAU DE DONNÉES ---
            st.subheader(f"📋 Détail du Stock ({len(df)} articles)")
            
            st.dataframe(
                df[["N° article.", "Description", "Inventory", "Qty. per Sales Unit of Measure", "Stock en colis", "Statut"]],
                use_container_width=True,
                hide_index=True,
                height=500,
                column_config={
                    "N° article.": st.column_config.TextColumn("Code Article", width="medium"),
                    "Description": st.column_config.TextColumn("Description", width="large"),
                    "Inventory": st.column_config.NumberColumn(
                        "Stock (UVC)", 
                        format="%d",
                        help="Unités de vente consommateur"
                    ),
                     "Qty. per Sales Unit of Measure": st.column_config.NumberColumn(
                        "PCB",
                        help="Par Combien (Unités par colis)"
                    ),
                    "Stock en colis": st.column_config.ProgressColumn(
                        "Stock (Colis)", 
                        format="%.1f 📦",
                        min_value=0,
                        # On met le max sur le dataset global pour garder une échelle cohérente
                        max_value=float(df_original["Inventory"].max() / df_original["Qty. per Sales Unit of Measure"].replace(0,1).min()),
                    ),
                    "Statut": st.column_config.TextColumn("État", width="small"),
                }
            )
else:
    # Écran d'accueil si aucun fichier n'est chargé
    st.markdown("""
        <div style='text-align: center; padding: 50px; background-color: #f8f9fa; border-radius: 20px;'>
            <h2>👈 Commencez par charger votre fichier</h2>
            <p style='color: grey;'>Utilisez le menu latéral pour uploader votre inventaire Excel.</p>
            <p style='font-size: 3rem;'>📑 ➡️ 📊</p>
        </div>
    """, unsafe_allow_html=True)


# --- PIED DE PAGE STYLE "DESATHOR" ---
st.markdown("""
    <div class="footer">
        <div class="footer-stars">★★★★★</div>
        <p>Powered by IC - 2025</p>
    </div>
    """, unsafe_allow_html=True)
