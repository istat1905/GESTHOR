import streamlit as st
import pandas as pd
import numpy as np
import pdfplumber
import re
import io
import time
from datetime import datetime

# --- Vérification Plotly pour les graphiques ---
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    
# --- Configuration de la page ---
st.set_page_config(page_title="GESTHOR – Master", page_icon="📦", layout="wide")

# --- Base de données utilisateurs simulée (À REMPLACER par une BDD réelle) ---
USERS_DB = {
    "admin": {"password": "admin123", "role": "admin"},
    "user1": {"password": "user123", "role": "user"},
}

def check_password(username, password):
    """Vérifie les identifiants utilisateur"""
    if username in USERS_DB and USERS_DB[username]["password"] == password:
        return True, USERS_DB[username]["role"]
    return False, None

# --- Session State pour l'authentification ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "username" not in st.session_state:
    st.session_state.username = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None

# --- CSS Épuré et Centré ---
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; }
    /* Style KPI */
    div[data-testid="stMetric"] {
        background-color: #fff; border: 1px solid #ddd; border-radius: 8px;
        padding: 10px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .kpi-card {
        background: linear-gradient(135deg, #1f77b4 0%, #4facfe 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .kpi-value {
        font-size: 2.5rem;
        font-weight: bold;
        margin: 0.5rem 0;
    }
    .kpi-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    .footer { text-align: center; margin-top: 4rem; color: #888; font-size: 0.8rem; border-top: 1px solid #eee; padding-top: 1rem;}
    </style>
    """, unsafe_allow_html=True)

# --- HEADER (Logo Centré) ---
c1, c2, c3 = st.columns([1,1,1])
with c2:
    try:
        # Remplacer par un chemin d'accès si l'image est locale
        # st.image("Gesthor.png", use_container_width=True) 
        st.markdown("<h1 style='text-align: center; color: #0072B5;'>GESTHOR</h1>", unsafe_allow_html=True)
    except:
        st.markdown("<h1 style='text-align: center; color: #0072B5;'>GESTHOR</h1>", unsafe_allow_html=True)

st.markdown("<h4 style='text-align: center; color: grey; font-weight: normal;'>Gestion de Stock & Analyse de Commandes</h4>", unsafe_allow_html=True)

# --- PAGE DE CONNEXION ---
if not st.session_state.authenticated:
    st.markdown("---")
    st.markdown("### 🔐 Connexion requise")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("👤 Identifiant")
            password = st.text_input("🔒 Mot de passe", type="password")
            submit = st.form_submit_button("Se connecter", use_container_width=True, type="primary")
            
            if submit:
                is_valid, role = check_password(username, password)
                if is_valid:
                    st.session_state.authenticated = True
                    st.session_state.user_role = role
                    st.session_state.username = username
                    st.success(f"✅ Bienvenue {username} !")
                    st.rerun()
                else:
                    st.error("❌ Identifiant ou mot de passe incorrect")
        
        st.info("💡 **Demo**: user1 / user123")
    st.stop()


# --- FONCTIONS ---

@st.cache_data
def load_stock(file):
    """ Charge et prépare le fichier Excel de stock """
    try:
        df = pd.read_excel(file)
        col_map = {c: c.strip() for c in df.columns}
        df = df.rename(columns=col_map)
        
        if "N° article." in df.columns:
            df["N° article."] = df["N° article."].astype(str).str.strip()
        if "Description" in df.columns:
            df["Description"] = df["Description"].astype(str).str.strip()
        
        df["Inventory"] = pd.to_numeric(df["Inventory"], errors='coerce').fillna(0)
        df["Qty. per Sales Unit of Measure"] = pd.to_numeric(df["Qty. per Sales Unit of Measure"], errors='coerce').fillna(1)
        
        df["Stock Colis"] = df["Inventory"] / df["Qty. per Sales Unit of Measure"].replace(0, 1)
        
        conditions = [(df["Inventory"] <= 0), (df["Inventory"] < 500)]
        choices = ["Rupture", "Faible"]
        df["Statut"] = np.select(conditions, choices, default="OK")
        
        return df
    except Exception as e:
        st.error(f"Erreur Excel : {e}")
        return None

def extract_pdf_force(pdf_file):
    """ Moteur d'extraction double mode pour PDF (CSV entre guillemets ou Tableau fragmenté) """
    orders = []
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() + "\n"
            
            # 1. Trouver toutes les commandes et leur position dans le texte
            cmd_matches = list(re.finditer(r"Commande\s*n[°º]?\s*[:\s-]*?(\d{5,10})", full_text))
            if not cmd_matches: return pd.DataFrame()
            
            cmd_positions = {m.start(): m.group(1) for m in cmd_matches}
            cmd_starts = sorted(cmd_positions.keys())
            
            # --- MODE 1: Format Quoted CSV (le plus structuré) ---
            item_pattern_mode1 = re.compile(
                r'"\d+\n",'                          # Ligne N°
                r'"(\d{4,7})\n",'                      # Group 1: Réf. frn (Article N°)
                r'.*?'                                # Désordre intermédiaire
                r'"(\d+)\n",'                         # Group 2: Qté commandée
                r'"\d+\n","EUR\n"',                   # Ancrage (Pcb et Devise)
                re.DOTALL | re.IGNORECASE
            )
            
            # --- Tenter Mode 1 ---
            for item_match in item_pattern_mode1.finditer(full_text):
                item_pos = item_match.start()
                ref = item_match.group(1).strip()
                qty = item_match.group(2).strip()
                
                # Déterminer la commande associée
                current_cde = cmd_positions[cmd_starts[0]]
                for start in cmd_starts:
                    if start <= item_pos:
                        current_cde = cmd_positions[start]
                    else:
                        break
                        
                orders.append({
                    "Commande": current_cde,
                    "Ref": ref,
                    "Qte_Cde": int(qty)
                })

            if orders:
                st.success(f"✅ Succès de l'extraction (Mode 1: {len(orders)} lignes trouvées).")
                return pd.DataFrame(orders).drop_duplicates()

            # --- MODE 2: Format Tableau Fragmenté (Fallback pour les formats plus bruts) ---
            item_pattern_mode2 = re.compile(
                r'\n\s*\d+\s+'          # Début d'une ligne d'article (ex: "\n 1 ")
                r'(\d{4,7})\s+'         # Group 1: Réf. frn
                r'.*?'                  # Match non gourmand pour tout ce qui est entre
                r'\n\s*(\d+)\s+'        # Group 2: Qté commandée
                r'\d+\s+'               # Pcb
                r'\d+,\d+'              # Prix
                , re.DOTALL 
            )

            # --- Tenter Mode 2 ---
            for item_match in item_pattern_mode2.finditer(full_text):
                item_pos = item_match.start()
                ref = item_match.group(1).strip()
                qty = item_match.group(2).strip()
                
                # Déterminer la commande associée
                current_cde = cmd_positions[cmd_starts[0]]
                for start in cmd_starts:
                    if start <= item_pos:
                        current_cde = cmd_positions[start]
                    else:
                        break
                        
                orders.append({
                    "Commande": current_cde,
                    "Ref": ref,
                    "Qte_Cde": int(qty)
                })

            if orders:
                st.success(f"✅ Succès de l'extraction (Mode 2: {len(orders)} lignes trouvées).")

        return pd.DataFrame(orders).drop_duplicates()
    except Exception as e:
        st.error(f"Erreur fatale de lecture PDF : {e}")
        return pd.DataFrame()

# --- SIDEBAR ---
with st.sidebar:
    st.header(f"👋 {st.session_state.username}")
    st.caption(f"Rôle: {st.session_state.user_role}")
    
    if st.button("🚪 Déconnexion", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_role = None
        st.session_state.username = None
        st.rerun()
        
    st.divider()
    
    st.header("1. Stock (Excel)")
    f_stock = st.file_uploader("Fichier Inventory.xlsx", type=["xlsx"], key="stock_up")
    
    st.header("2. Commandes (PDF)")
    f_pdf = st.file_uploader("Fichier Commandes.pdf", type=["pdf"], key="cde_up")
    
    st.divider()
    search_input = st.text_input("🔍 Recherche article", placeholder="Code ou Libellé...")


# --- MAIN ---
if f_stock:
    df_stock = load_stock(f_stock)
    
    # --- FILTRE RECHERCHE GLOBAL ---
    df = df_stock.copy()
    if search_input:
        mask = (df["N° article."].str.contains(search_input, case=False, na=False) | 
                df["Description"].str.contains(search_input, case=False, na=False))
        df = df[mask]

    # --- INDICATEURS DE STOCK ---
    st.markdown("### 📊 Indicateurs de Stock")
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Articles trouvés", len(df))
    nb_rupt = len(df[df["Statut"] == "Rupture"])
    nb_faible = len(df[df["Statut"] == "Faible"])
    k2.metric("❌ En Rupture", nb_rupt, delta=0 if nb_rupt == 0 else -nb_rupt, delta_color="inverse")
    k3.metric("⚠️ Stock Faible", nb_faible, delta_color="normal")
    
    st.divider()

    # --- CRÉATION DES ONGLETS ---
    t_noms = []
    if f_pdf: t_noms.append("🚀 Analyse Commandes")
    t_noms.extend(["❌ Ruptures", "⚠️ Stock Faible", "✅ Stock OK", "📁 Tout"])
    
    tabs = st.tabs(t_noms)
    
    # --- 1. LOGIQUE ANALYSE COMMANDES (Si PDF) ---
    if f_pdf:
        with tabs[t_noms.index("🚀 Analyse Commandes")]:
            st.subheader("Résultat de l'analyse des Commandes")
            df_cde = extract_pdf_force(f_pdf)
            
            if df_cde.empty or 'Ref' not in df_cde.columns or len(df_cde) < 1:
                st.warning("⚠️ Aucune ligne de commande exploitable trouvée dans le PDF. Veuillez vérifier que le fichier est bien un PDF texte.")
            else:
                # Moteur de calcul (Simule l'épuisement du stock)
                stock_live = df_stock.set_index("N° article.")["Inventory"].to_dict()
                desc_live = df_stock.set_index("N° article.")["Description"].to_dict()
                
                analyse = []
                all_ruptures = [] # Pour le rapport Excel
                
                for num_cde, data_cde in df_cde.groupby("Commande"):
                    tot_demande, tot_servi = 0, 0
                    lignes_ko = []
                    
                    # Tri des lignes pour un traitement prévisible
                    data_cde = data_cde.sort_values("Ref") 
                    
                    for _, row in data_cde.iterrows():
                        ref, qte = row["Ref"], row["Qte_Cde"]
                        stock_dispo = stock_live.get(ref, 0)
                        
                        tot_demande += qte
                        servi = min(qte, stock_dispo)
                        tot_servi += servi
                        
                        # Déduction immédiate du stock
                        stock_live[ref] = max(0, stock_dispo - servi) 
                        
                        if servi < qte:
                            manque = qte - servi
                            rupture_data = {
                                "Commande": num_cde,
                                "Ref": ref,
                                "Article": desc_live.get(ref, f"Article {ref} (Non trouvé en stock)"),
                                "Commandé": qte,
                                "Servi": servi,
                                "Manquant": manque
                            }
                            lignes_ko.append(rupture_data)
                            all_ruptures.append(rupture_data)
                    
                    taux = (tot_servi / tot_demande * 100) if tot_demande > 0 else 0
                    analyse.append({"Commande": num_cde, "Taux": taux, "Demande": tot_demande, "Servi": tot_servi, "Alertes": lignes_ko})
                
                df_ana = pd.DataFrame(analyse)
                df_all_ruptures = pd.DataFrame(all_ruptures)
                
                # --- INDICATEURS ANALYSE PDF ---
                tot_demande_g = df_ana["Demande"].sum()
                tot_servi_g = df_ana["Servi"].sum()
                taux_global = (tot_servi_g / tot_demande_g * 100) if tot_demande_g > 0 else 0
                manquants_total = tot_demande_g - tot_servi_g
                
                col_kpi_1, col_kpi_2, col_kpi_3 = st.columns(3)
                with col_kpi_1:
                    st.markdown(f"""
                    <div class="kpi-card">
                        <div class="kpi-label">Commandes analysées</div>
                        <div class="kpi-value">{len(df_ana)}</div>
                    </div>
                    """, unsafe_allow_html=True)
                with col_kpi_2:
                    st.markdown(f"""
                    <div class="kpi-card" style="background: linear-gradient(135deg, {'#11998e' if taux_global == 100 else '#ffaf00' if taux_global > 90 else '#f5576c'} 0%, {'#38ef7d' if taux_global == 100 else '#f5576c' if taux_global < 90 else '#ffdd6e'} 100%);">
                        <div class="kpi-label">Taux de Service Global</div>
                        <div class="kpi-value">{taux_global:.1f}%</div>
                    </div>
                    """, unsafe_allow_html=True)
                with col_kpi_3:
                    st.markdown(f"""
                    <div class="kpi-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                        <div class="kpi-label">Pièces non livrables</div>
                        <div class="kpi-value">{int(manquants_total)}</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown("---")
                
                # --- GRAPHIQUE TAUX DE SERVICE ---
                if PLOTLY_AVAILABLE:
                    st.markdown("### 📈 Performance par commande")
                    # Triez par Taux pour afficher les plus problématiques en premier
                    df_ana_sorted = df_ana.sort_values("Taux", ascending=True) 

                    fig_service = go.Figure(data=[
                        go.Bar(
                            x=df_ana_sorted['Commande'],
                            y=df_ana_sorted['Taux'],
                            marker=dict(
                                color=df_ana_sorted['Taux'],
                                colorscale=[[0, 'red'], [0.5, 'orange'], [1, 'green']],
                                cmin=0,
                                cmax=100,
                                showscale=False
                            ),
                            text=[f"{v:.1f}%" for v in df_ana_sorted['Taux']],
                            textposition='outside'
                        )
                    ])
                    fig_service.update_layout(
                        title='Taux de service par commande analysée',
                        xaxis_title='N° Commande',
                        yaxis_title='Taux de service (%)',
                        yaxis_range=[0, 110],
                        showlegend=False,
                        xaxis=dict(type='category')
                    )
                    st.plotly_chart(fig_service, use_container_width=True)
                    

[Image of inventory dashboard charts]

                    
                    st.markdown("---")
                
                # Affichage détaillé par commande
                st.markdown("### 📋 Détail des commandes en rupture")
                for idx, row in df_ana.sort_values("Taux", ascending=True).iterrows():
                    titre = f"Commande {row['Commande']} — Taux: {row['Taux']:.1f}% ({int(row['Servi'])}/{int(row['Demande'])})"
                    icon = "✅" if row["Taux"] == 100 else "⚠️" if row["Taux"] >= 95 else "❌"
                    
                    with st.expander(f"{icon} {titre}"):
                        if row["Alertes"]:
                            st.error(f"🛑 {len(row['Alertes'])} références en rupture sur cette commande :")
                            df_alert = pd.DataFrame(row["Alertes"])
                            st.dataframe(
                                df_alert[["Ref", "Article", "Commandé", "Servi", "Manquant"]], 
                                hide_index=True,
                                column_config={
                                    "Commandé": st.column_config.NumberColumn(format="%d"),
                                    "Servi": st.column_config.NumberColumn(format="%d"),
                                    "Manquant": st.column_config.NumberColumn(format="%d"),
                                }
                            )
                        else:
                            st.success("Tout est en stock pour cette commande !")
                            
                st.markdown("---")
                st.markdown("### 📥 Export du Rapport d'Analyse")
                
                # --- Export au format Excel ---
                output = io.BytesIO()
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"Rapport_Rupture_GESTHOR_{timestamp}.xlsx"

                with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                    
                    # Feuille 1: Récapitulatif
                    df_summary = df_ana[["Commande", "Taux", "Demande", "Servi"]].rename(
                        columns={"Demande": "Qté Commandée", "Servi": "Qté Livrable"}
                    )
                    df_summary["Qté Manquante"] = df_summary["Qté Commandée"] - df_summary["Qté Livrable"]
                    df_summary["Taux"] = df_summary["Taux"].round(1)
                    df_summary.to_excel(writer, sheet_name="Récapitulatif", index=False)
                    
                    # Feuille 2: Détail des ruptures
                    if not df_all_ruptures.empty:
                        df_all_ruptures.to_excel(writer, sheet_name="Détail_Ruptures", index=False)
                    else:
                        pd.DataFrame([{"Message": "Aucune rupture constatée."}]).to_excel(writer, sheet_name="Détail_Ruptures", index=False)


                st.download_button(
                    "📥 Télécharger le Rapport de Rupture Excel",
                    data=output.getvalue(),
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                
                # --- Export des données brutes de la commande (utile pour le débogage) ---
                @st.cache_data
                def convert_df_to_csv(df):
                    return df.to_csv(index=False).encode('utf-8')
                    
                csv_cde = convert_df_to_csv(df_cde)
                st.download_button(
                    "💾 Télécharger les lignes extraites du PDF (CSV)",
                    csv_cde,
                    f"Commandes_extraites_{timestamp}.csv",
                    "text/csv",
                    key='download-csv'
                )


    # --- 2. LOGIQUE ONGLETS STOCK ---
    
    def show_tab(filtre, titre_onglet):
        if titre_onglet not in t_noms: return 
        idx = t_noms.index(titre_onglet)
        
        with tabs[idx]:
            if filtre == "Tout":
                d = df
            else:
                d = df[df["Statut"] == filtre]
            
            if d.empty:
                st.info("Rien à afficher ici avec les filtres actuels.")
            else:
                top_n = st.slider(f"Nombre de lignes à afficher ({filtre})", 5, 100, 20, key=f"s_{idx}")
                st.dataframe(
                    d.sort_values("Inventory", ascending=(filtre!="OK")).head(top_n)[["N° article.", "Description", "Inventory", "Stock Colis", "Statut"]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Inventory": st.column_config.NumberColumn("Stock (UVC)", format="%d"),
                        "Stock Colis": st.column_config.NumberColumn("Colis (Est.)", format="%.1f"),
                    }
                )

    # Appel des onglets de stock
    show_tab("Rupture", "❌ Ruptures")
    show_tab("Faible", "⚠️ Stock Faible")
    show_tab("OK", "✅ Stock OK")
    show_tab("Tout", "📁 Tout")

else:
    st.info("👈 En attente du fichier Stock Excel et de votre connexion...")

# --- FOOTER ---
if st.session_state.authenticated:
    st.markdown("""<div class="footer">GESTHOR | Powered by IC - 2025 ★★★★★</div>""", unsafe_allow_html=True)
