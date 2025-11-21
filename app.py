import streamlit as st
import pandas as pd
import numpy as np
import pdfplumber
import re
import io
from datetime import datetime
import json # Ajout pour la sauvegarde simple de l'historique en JSON

# --- Vérification Plotly pour les graphiques ---
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    
# --- Configuration de la page ---
st.set_page_config(page_title="GESTHOR – Master", page_icon="📦", layout="wide")

# --- Base de données utilisateurs simulée ---
USERS_DB = {
    "admin": {"password": "admin123", "role": "admin"},
    "user1": {"password": "user123", "role": "user"},
}

def check_password(username, password):
    """Vérifie les identifiants utilisateur"""
    if username in USERS_DB and USERS_DB[username]["password"] == password:
        return True, USERS_DB[username]["role"]
    return False, None

# --- Session State pour l'authentification et la persistance (SIMULÉE) ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "username" not in st.session_state:
    st.session_state.username = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None

# --- NOUVEAU: Initialisation de l'historique de commandes en mémoire ---
if "analysis_history" not in st.session_state:
    # Structure de l'historique: [{Commande, Taux, Demande, Servi, Date_Analyse, Full_Detail}]
    st.session_state.analysis_history = [] 


# --- CSS ---
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; }
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

# --- HEADER ---
c1, c2, c3 = st.columns([1,1,1])
with c2:
    st.markdown("<h1 style='text-align: center; color: #0072B5;'>GESTHOR</h1>", unsafe_allow_html=True)

st.markdown("<h4 style='text-align: center; color: grey; font-weight: normal;'>Gestion de Stock & Analyse de Commandes</h4>", unsafe_allow_html=True)

# --- PAGE DE CONNEXION (unchanged) ---
if not st.session_state.authenticated:
    st.markdown("---")
    st.markdown("### 🔐 Connexion requise")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("👤 Identifiant")
            password = st.text_input("🔑 Mot de passe", type="password")
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

# Utilisation de la fonction de l'utilisateur qui fonctionne pour l'extraction PDF
def extract_pdf_improved(pdf_file):
    """Extraction améliorée pour les PDFs de commandes"""
    orders = []
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() + "\n---PAGE---\n"
            
            # Trouver toutes les commandes
            cmd_pattern = re.compile(r"Commande\s+n[°º]?\s*(\d{5,10})", re.IGNORECASE)
            cmd_matches = list(cmd_pattern.finditer(full_text))
            
            if not cmd_matches:
                st.warning("⚠️ Aucune commande trouvée dans le PDF")
                return pd.DataFrame()
            
            # Créer un dictionnaire de positions de commandes
            cmd_positions = {}
            for match in cmd_matches:
                cmd_num = match.group(1)
                cmd_positions[match.start()] = cmd_num
            
            cmd_starts = sorted(cmd_positions.keys())
            
            # Fonction utilitaire pour trouver la commande associée
            def associate_to_order(item_pos, cmd_positions, cmd_starts):
                current_cmd = "INCONNU"
                for start_pos in cmd_starts:
                    if start_pos <= item_pos:
                        current_cmd = cmd_positions[start_pos]
                    else:
                        break
                return current_cmd

            # PATTERN PRINCIPAL (Format EAN complet)
            line_pattern = re.compile(
                r'^\s*(\d{1,3})\s+'          # 1: Ligne
                r'(\d{3,7})\s+'              # 2: Réf fournisseur (celle qui nous intéresse)
                r'(\d{13})\s+'               # 3: Code EAN
                r'(\d{1,4})\s+'              # 4: Nb cartons
                r'(.+?)\s+'                  # 5: Libellé
                r'(\d{1,5})\s+'              # 6: Qté commandée (celle qui nous intéresse)
                r'(\d{1,4})\s+'              # 7: Pcb
                r'(?:EUR|\d+[,\.]\d+)',      # Fin
                re.MULTILINE
            )
            
            for match in line_pattern.finditer(full_text):
                try:
                    pos = match.start()
                    ref = match.group(2).strip()
                    qty = int(match.group(6).strip())
                    
                    current_cmd = associate_to_order(pos, cmd_positions, cmd_starts)
                    
                    orders.append({
                        "Commande": current_cmd,
                        "Ref": ref,
                        "Qte_Cde": qty
                    })
                except Exception as e:
                    # st.warning(f"Erreur d'extraction sur ligne (mode 1): {e}")
                    continue
            
            # PATTERN ALTERNATIF (Format sans EAN visible ou autre)
            if len(orders) < 5 or len(orders) < sum(1 for m in cmd_matches) * 5: 
                
                alt_pattern = re.compile(
                    r'^\s*\d{1,3}\s+'           # Numéro ligne
                    r'(\d{3,7})\s+'             # 1: Réf fournisseur
                    r'\d{13}\s+'                # EAN
                    r'.{10,200}?'               # Description variable
                    r'\s(\d{1,5})\s+'           # 2: Quantité
                    r'\d{1,4}\s+'               # Pcb
                    r'(?:EUR|\d+[,\.]\d+)',     # Fin de ligne
                    re.MULTILINE | re.DOTALL
                )
                
                # Effacer les résultats du mode 1 s'ils étaient trop faibles
                if len(orders) < 5:
                    orders = []

                for match in alt_pattern.finditer(full_text):
                    try:
                        pos = match.start()
                        ref = match.group(1).strip()
                        qty = int(match.group(2).strip())
                        
                        current_cmd = associate_to_order(pos, cmd_positions, cmd_starts)
                        
                        orders.append({
                            "Commande": current_cmd,
                            "Ref": ref,
                            "Qte_Cde": qty
                        })
                    except:
                        continue
            
            if orders:
                df_orders = pd.DataFrame(orders).drop_duplicates()
                st.success(f"✅ {len(df_orders)} lignes extraites de {len(cmd_matches)} commande(s)")
                return df_orders
            else:
                st.error("❌ Aucune ligne de commande extraite. Vérifiez le format du PDF.")
                return pd.DataFrame()
                
    except Exception as e:
        st.error(f"Erreur lors de la lecture du PDF : {str(e)}")
        return pd.DataFrame()


# --- SIDEBAR ---
with st.sidebar:
    st.header(f"👋 {st.session_state.username}")
    st.caption(f"Rôle: {st.session_state.user_role}")
    
    if st.button("🚪 Déconnexion", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_role = None
        st.session_state.username = None
        st.session_state.analysis_history = [] # Effacer l'historique à la déconnexion
        st.rerun()
        
    st.divider()
    
    st.header("1. Stock (Excel)")
    f_stock = st.file_uploader("Fichier Inventory.xlsx", type=["xlsx"], key="stock_up")
    
    st.header("2. Commandes (PDF)")
    f_pdf = st.file_uploader("Fichier Commandes.pdf", type=["pdf"], key="cde_up")
    
    st.divider()
    # Recherche mieux nommée (répond au point 1)
    search_input = st.text_input("🔍 Recherche/Filtre Global", placeholder="Code ou Libellé...")


# --- MAIN ---
if f_stock:
    df_stock = load_stock(f_stock)
    
    # Filtre recherche
    df = df_stock.copy()
    if search_input:
        mask = (df["N° article."].str.contains(search_input, case=False, na=False) | 
                df["Description"].str.contains(search_input, case=False, na=False))
        df = df[mask]

    # Indicateurs de stock
    st.markdown("### 📊 Indicateurs de Stock")
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Articles trouvés", len(df))
    nb_rupt = len(df[df["Statut"] == "Rupture"])
    nb_faible = len(df[df["Statut"] == "Faible"])
    k2.metric("❌ En Rupture", nb_rupt, delta=0 if nb_rupt == 0 else -nb_rupt, delta_color="inverse")
    k3.metric("⚠️ Stock Faible", nb_faible, delta_color="normal")
    
    st.divider()

    # Création des onglets (Ajout de l'historique)
    t_noms = []
    if f_pdf: t_noms.append("🚀 Analyse Commande Récente")
    t_noms.extend(["📜 Historique Analysé", "❌ Ruptures", "⚠️ Stock Faible", "✅ Stock OK", "📋 Tout"])
    
    tabs = st.tabs(t_noms)
    
    # LOGIQUE ANALYSE COMMANDE RÉCENTE
    if f_pdf:
        with tabs[t_noms.index("🚀 Analyse Commande Récente")]:
            st.subheader("Résultat de l'analyse des Commandes PDF")
            df_cde = extract_pdf_improved(f_pdf)
            
            if df_cde.empty or 'Ref' not in df_cde.columns:
                st.warning("⚠️ Aucune donnée exploitable")
            else:
                # Simulation stock
                stock_live = df_stock.set_index("N° article.")["Inventory"].to_dict()
                desc_live = df_stock.set_index("N° article.")["Description"].to_dict()
                
                analyse = []
                # all_ruptures est conservé pour l'export Excel
                all_ruptures = [] 
                
                for num_cde, data_cde in df_cde.groupby("Commande"):
                    tot_demande, tot_servi = 0, 0
                    all_lines_for_cde = [] # NOUVEAU: Pour stocker toutes les lignes
                    
                    # Traitement des lignes
                    for _, row in data_cde.iterrows():
                        ref, qte = row["Ref"], row["Qte_Cde"]
                        stock_dispo = stock_live.get(ref, 0)
                        
                        tot_demande += qte
                        servi = min(qte, stock_dispo)
                        tot_servi += servi
                        
                        # Déduction du stock
                        stock_live[ref] = max(0, stock_dispo - servi)
                        
                        manque = qte - servi
                        line_data = {
                            "Commande": num_cde,
                            "Ref": ref,
                            "Article": desc_live.get(ref, f"Article {ref} (Non trouvé)"),
                            "Commandé": qte,
                            "Servi": servi,
                            "Manquant": manque
                        }
                        
                        all_lines_for_cde.append(line_data)

                        if manque > 0:
                            all_ruptures.append(line_data) # Pour l'export Excel
                    
                    taux = (tot_servi / tot_demande * 100) if tot_demande > 0 else 0
                    analyse.append({
                        "Commande": num_cde, 
                        "Taux": taux, 
                        "Demande": tot_demande, 
                        "Servi": tot_servi, 
                        "Manquant": tot_demande - tot_servi, # Ajout de la qté manquante totale
                        "Date_Analyse": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "Full_Detail": all_lines_for_cde # NOUVEAU: Stockage du détail complet
                    })
                
                df_ana = pd.DataFrame([item for item in analyse if "Taux" in item])
                df_all_ruptures = pd.DataFrame(all_ruptures)
                
                # --- Sauvegarde de l'historique (Point 2) ---
                for item in analyse:
                    # Ajoute uniquement les nouvelles commandes non encore présentes
                    if not any(h['Commande'] == item['Commande'] for h in st.session_state.analysis_history):
                         st.session_state.analysis_history.append(item)


                # KPIs (affichés uniquement pour la dernière analyse)
                tot_demande_g = df_ana["Demande"].sum()
                tot_servi_g = df_ana["Servi"].sum()
                taux_global = (tot_servi_g / tot_demande_g * 100) if tot_demande_g > 0 else 0
                manquants_total = tot_demande_g - tot_servi_g
                
                col_kpi_1, col_kpi_2, col_kpi_3 = st.columns(3)
                # ... (affichage des KPIs inchangé pour la dernière analyse) ...
                with col_kpi_1:
                    st.markdown(f"""
                    <div class="kpi-card">
                        <div class="kpi-label">Commandes analysées</div>
                        <div class="kpi-value">{len(df_ana)}</div>
                    </div>
                    """, unsafe_allow_html=True)
                with col_kpi_2:
                    color = '#11998e' if taux_global == 100 else '#ffaf00' if taux_global > 90 else '#f5576c'
                    st.markdown(f"""
                    <div class="kpi-card" style="background: linear-gradient(135deg, {color} 0%, {color} 100%);">
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
                
                # Détail commandes (Point 3: Affichage complet)
                st.markdown("### 📋 Détail de la Commande Récente")
                for item in analyse:
                    titre = f"Commande {item['Commande']} – Taux: {item['Taux']:.1f}% ({int(item['Servi'])}/{int(item['Demande'])})"
                    icon = "✅" if item["Taux"] == 100 else "⚠️" if item["Taux"] >= 95 else "❌"
                    
                    with st.expander(f"{icon} {titre}"):
                        if item["Manquant"] > 0:
                            st.error(f"🛑 {item['Manquant']} pièces manquantes sur {item['Demande']} commandées.")
                        else:
                            st.success("Toutes les lignes de cette commande sont entièrement livrables.")

                        # Affichage de TOUTES les lignes (livrées et manquantes)
                        df_full_detail = pd.DataFrame(item["Full_Detail"])
                        
                        st.dataframe(
                            df_full_detail.sort_values("Manquant", ascending=False),
                            hide_index=True,
                            use_container_width=True,
                            column_config={
                                "Ref": "Réf. Frn",
                                "Article": "Libellé Article",
                                "Commandé": st.column_config.NumberColumn("Qté Cde", format="%d"),
                                "Servi": st.column_config.NumberColumn("Qté Livrée", format="%d"),
                                "Manquant": st.column_config.NumberColumn("Manquant ❌", format="%d"),
                            }
                        )
                
                st.markdown("---")
                st.markdown("### 📥 Export")
                
                # ... (Export inchangé) ...
                output = io.BytesIO()
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"Rapport_GESTHOR_{timestamp}.xlsx"

                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    df_summary = df_ana[["Commande", "Taux", "Demande", "Servi", "Manquant"]].rename(
                         columns={"Demande": "Qté Commandée", "Servi": "Qté Livrable"}
                    )
                    df_summary.to_excel(writer, sheet_name="Récapitulatif", index=False)
                    
                    if not df_all_ruptures.empty:
                        df_all_ruptures.to_excel(writer, sheet_name="Détail_Ruptures", index=False)
                    else:
                        pd.DataFrame([{"Message": "Aucune rupture constatée lors de cette analyse."}]).to_excel(writer, sheet_name="Détail_Ruptures", index=False)

                st.download_button(
                    "📥 Télécharger Rapport Excel",
                    data=output.getvalue(),
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                
                csv_cde = df_cde.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "💾 Télécharger données CSV brutes du PDF",
                    csv_cde,
                    f"Commandes_extraites_brutes_{timestamp}.csv",
                    "text/csv"
                )

    
    # NOUVEL ONGLE HISTORIQUE ANALYSÉ (Point 2)
    with tabs[t_noms.index("📜 Historique Analysé")]:
        st.header("Historique des Commandes Analysées")
        
        if not st.session_state.analysis_history:
            st.info("Aucune donnée d'historique. Veuillez analyser un fichier PDF d'abord.")
        else:
            df_hist = pd.DataFrame(st.session_state.analysis_history)
            df_hist = df_hist.sort_values("Date_Analyse", ascending=False).drop(columns=['Full_Detail'])
            
            # --- Graphique Historique ---
            if PLOTLY_AVAILABLE:
                st.markdown("### Taux de Service par Commande (Historique)")
                fig_hist = px.bar(
                    df_hist,
                    x="Commande",
                    y="Taux",
                    color="Taux",
                    color_continuous_scale=[(0, 'red'), (0.5, 'orange'), (1, 'green')],
                    text='Taux',
                    labels={'Commande': 'N° Commande', 'Taux': 'Taux de Service (%)'},
                    title="Performance Historique"
                )
                fig_hist.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                fig_hist.update_layout(yaxis_range=[0, 105], uniformtext_minsize=8, uniformtext_mode='hide')
                st.plotly_chart(fig_hist, use_container_width=True)
                st.markdown("---")

            st.markdown("### Récapitulatif Historique")
            st.dataframe(
                df_hist.rename(
                    columns={
                        "Taux": "Taux (%)", 
                        "Demande": "Qté Cde Totale", 
                        "Servi": "Qté Livrable",
                        "Manquant": "Qté Manquante",
                        "Date_Analyse": "Date Analyse"
                    }
                ),
                hide_index=True,
                use_container_width=True
            )
            
            st.warning("⚠️ Cet historique est conservé tant que votre session Streamlit reste active. Pour une persistance définitive, un système de base de données ou de fichier (CSV/JSON) doit être mis en place sur votre serveur.")


    # Onglets stock (inchangés)
    def show_tab(filtre, titre_onglet):
        if titre_onglet not in t_noms:
            return
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
                    d.sort_values("Inventory", ascending=(filtre!="OK")).head(top_n)[
                        ["N° article.", "Description", "Inventory", "Stock Colis", "Statut"]
                    ],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Inventory": st.column_config.NumberColumn("Stock (UVC)", format="%d"),
                        "Stock Colis": st.column_config.NumberColumn("Colis (Est.)", format="%.1f"),
                    }
                )

    show_tab("Rupture", "❌ Ruptures")
    show_tab("Faible", "⚠️ Stock Faible")
    show_tab("OK", "✅ Stock OK")
    show_tab("Tout", "📋 Tout")

else:
    st.info("👈 Veuillez charger le fichier Stock Excel")

# Footer
if st.session_state.authenticated:
    st.markdown("""<div class="footer">GESTHOR | Powered by IC - 2025 (v4.0)</div>""", unsafe_allow_html=True)
