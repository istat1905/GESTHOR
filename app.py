import streamlit as st
import pandas as pd
import numpy as np
import pdfplumber
import re
import io
import json
from datetime import datetime
from pathlib import Path

# --- Vérification Plotly ---
try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# --- Configuration ---
st.set_page_config(page_title="GESTHOR", page_icon="📦", layout="wide")

# --- Fichier de sauvegarde ---
HISTORY_FILE = "gesthor_history.json"

USERS_DB = {
    "admin": {"password": "admin123", "role": "admin"},
    "user1": {"password": "user123", "role": "user"},
}

def check_password(username, password):
    if username in USERS_DB and USERS_DB[username]["password"] == password:
        return True, USERS_DB[username]["role"]
    return False, None

# --- Session State ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "username" not in st.session_state:
    st.session_state.username = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "search_history" not in st.session_state:
    st.session_state.search_history = []
if "current_search" not in st.session_state:
    st.session_state.current_search = ""

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
        padding: 1.5rem; border-radius: 10px; color: white;
        text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .kpi-value { font-size: 2.5rem; font-weight: bold; margin: 0.5rem 0; }
    .kpi-label { font-size: 0.9rem; opacity: 0.9; }
    .footer { text-align: center; margin-top: 4rem; color: #888; 
              font-size: 0.8rem; border-top: 1px solid #eee; padding-top: 1rem;}
    </style>
    """, unsafe_allow_html=True)

# --- HEADER ---
c1, c2, c3 = st.columns([1,1,1])
with c2:
    try:
        st.image("Gesthor.png", use_container_width=True)
    except:
        st.markdown("<h1 style='text-align: center; color: #0072B5;'>GESTHOR</h1>", unsafe_allow_html=True)

st.markdown("<h4 style='text-align: center; color: grey; font-weight: normal;'>Gestion de Stock & Analyse de Commandes</h4>", unsafe_allow_html=True)

# --- CONNEXION ---
if not st.session_state.authenticated:
    st.markdown("---")
    st.markdown("### 🔒 Connexion requise")
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

def load_history():
    try:
        if Path(HISTORY_FILE).exists():
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except:
        return []

def save_history(history):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Erreur sauvegarde : {e}")

def add_to_history(analysis_data):
    history = load_history()
    analysis_data['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    analysis_data['user'] = st.session_state.username
    history.append(analysis_data)
    if len(history) > 50:
        history = history[-50:]
    save_history(history)

@st.cache_data
def load_stock(file):
    try:
        df = pd.read_excel(file)
        col_map = {c: c.strip() for c in df.columns}
        df = df.rename(columns=col_map)
        
        if "N° article." in df.columns:
            df["N° article."] = df["N° article."].astype(str).str.strip()
        if "Description" in df.columns:
            df["Description"] = df["Description"].astype(str).str.strip()
        
        df["Inventory"] = pd.to_numeric(df["Inventory"], errors='coerce').fillna(0)
        df["Qty. per Sales Unit of Measure"] = pd.to_numeric(
            df["Qty. per Sales Unit of Measure"], errors='coerce'
        ).fillna(1)
        
        df["Stock Colis"] = df["Inventory"] / df["Qty. per Sales Unit of Measure"].replace(0, 1)
        
        conditions = [(df["Inventory"] <= 0), (df["Inventory"] < 500)]
        choices = ["Rupture", "Faible"]
        df["Statut"] = np.select(conditions, choices, default="OK")
        
        return df
    except Exception as e:
        st.error(f"Erreur Excel : {e}")
        return None

def extract_pdf_improved(pdf_file):
    orders = []
    try:
        with pdfplumber.open(pdf_file) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() + "\n---PAGE---\n"
            
            cmd_pattern = re.compile(r"Commande\s+n[°º]?\s*(\d{5,10})", re.IGNORECASE)
            cmd_matches = list(cmd_pattern.finditer(full_text))
            
            if not cmd_matches:
                return pd.DataFrame()
            
            cmd_positions = {match.start(): match.group(1) for match in cmd_matches}
            cmd_starts = sorted(cmd_positions.keys())
            
            line_pattern = re.compile(
                r'^\s*(\d{1,3})\s+(\d{3,7})\s+(\d{13})\s+(\d{1,4})\s+(.+?)\s+(\d{1,5})\s+(\d{1,4})\s+(?:EUR|\d+[,\.]\d+)',
                re.MULTILINE
            )
            
            for match in line_pattern.finditer(full_text):
                try:
                    pos = match.start()
                    ref = match.group(2).strip()
                    qty = int(match.group(6).strip())
                    
                    current_cmd = "INCONNU"
                    for start_pos in cmd_starts:
                        if start_pos <= pos:
                            current_cmd = cmd_positions[start_pos]
                        else:
                            break
                    
                    orders.append({"Commande": current_cmd, "Ref": ref, "Qte_Cde": qty})
                except:
                    continue
            
            if len(orders) < 5:
                alt_pattern = re.compile(
                    r'^\s*\d{1,3}\s+(\d{3,7})\s+\d{13}\s+.{10,200}?\s(\d{1,5})\s+\d{1,4}\s+(?:EUR|\d+[,\.]\d+)',
                    re.MULTILINE | re.DOTALL
                )
                
                for match in alt_pattern.finditer(full_text):
                    try:
                        pos = match.start()
                        ref = match.group(1).strip()
                        qty = int(match.group(2).strip())
                        
                        current_cmd = "INCONNU"
                        for start_pos in cmd_starts:
                            if start_pos <= pos:
                                current_cmd = cmd_positions[start_pos]
                            else:
                                break
                        
                        orders.append({"Commande": current_cmd, "Ref": ref, "Qte_Cde": qty})
                    except:
                        continue
            
            if orders:
                return pd.DataFrame(orders).drop_duplicates()
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Erreur PDF : {e}")
        return pd.DataFrame()

# --- SIDEBAR ---
with st.sidebar:
    st.markdown(f"### 👋 {st.session_state.username}")
    st.caption(f"🔑 {st.session_state.user_role}")
    
    if st.button("🚪 Déconnexion", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()
        st.divider()
    # --- NOUVEAU BOUTON IMAGE ---
    # Nous utilisons st.markdown avec la balise <a> pour créer un lien cliquable
    # contenant votre image 'desathor.png'.
    st.markdown("""
        <a href="https://desathor.streamlit.app/" target="_blank" class="external-app-link">
            <img src="desathor.png" alt="Aller à Desathor App" title="Ouvrir l'application Desathor" />
        </a>    
    
    st.divider()
    
    st.markdown("### 📁 Fichiers")
    f_stock = st.file_uploader("📊 Stock Excel", type=["xlsx"])
    f_pdf = st.file_uploader("📄 Commandes PDF", type=["pdf"])
    
    st.divider()
    
    st.markdown("### 🔍 Recherche")
    search_input = st.text_input(
        "Article",
        value=st.session_state.current_search,
        placeholder="Code ou nom..."
    )
    
    if search_input and search_input != st.session_state.current_search:
        st.session_state.current_search = search_input
        if search_input not in st.session_state.search_history:
            st.session_state.search_history.insert(0, search_input)
            st.session_state.search_history = st.session_state.search_history[:10]
    
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        if st.button("🔄 Reset", use_container_width=True):
            st.session_state.current_search = ""
            st.rerun()
    
    if st.session_state.search_history:
        with st.expander("📜 Historique"):
            for i, h in enumerate(st.session_state.search_history[:5]):
                if st.button(f"🔎 {h}", key=f"h_{i}", use_container_width=True):
                    st.session_state.current_search = h
                    st.rerun()
    
    st.divider()
    
    st.markdown("### 📊 Historique")
    history = load_history()
    
    if history:
        nb = st.slider("Afficher", 3, 10, 5)
        for entry in reversed(history[-nb:]):
            with st.expander(f"📅 {entry['timestamp'][:16]}"):
                st.write(f"👤 {entry.get('user', 'N/A')}")
                st.write(f"📦 {entry.get('nb_commandes', 0)} cde")
                st.write(f"✅ {entry.get('taux_global', 0):.1f}%")
    else:
        st.info("Aucun historique")
    
    if st.button("🗑️ Effacer", use_container_width=True):
        save_history([])
        st.success("Effacé")
        st.rerun()

# --- MAIN ---
if f_stock:
    df_stock = load_stock(f_stock)
    
    if df_stock is None:
        st.stop()
    
    df = df_stock.copy()
    if st.session_state.current_search:
        mask = (
            df["N° article."].str.contains(st.session_state.current_search, case=False, na=False) |
            df["Description"].str.contains(st.session_state.current_search, case=False, na=False)
        )
        df = df[mask]
        if not df.empty:
            st.success(f"🎯 {len(df)} résultat(s) pour '{st.session_state.current_search}'")
        else:
            st.warning(f"Aucun résultat")
    
    st.markdown("### 📊 Stock")
    k1, k2, k3, k4 = st.columns(4)
    
    k1.metric("📦 Articles", len(df))
    k2.metric("✅ OK", len(df[df["Statut"] == "OK"]))
    k3.metric("❌ Rupture", len(df[df["Statut"] == "Rupture"]))
    k4.metric("⚠️ Faible", len(df[df["Statut"] == "Faible"]))
    
    st.divider()
    
    tabs_list = []
    if f_pdf:
        tabs_list.append("🚀 Commandes")
    tabs_list.extend(["❌ Ruptures", "⚠️ Faible", "✅ OK", "📋 Tout"])
    
    tabs = st.tabs(tabs_list)
    
    # --- ANALYSE ---
    if f_pdf:
        with tabs[0]:
            st.subheader("📊 Analyse")
            
            df_cde = extract_pdf_improved(f_pdf)
            
            if df_cde.empty:
                st.warning("Aucune donnée PDF")
            else:
                stock_live = df_stock.set_index("N° article.")["Inventory"].to_dict()
                desc_live = df_stock.set_index("N° article.")["Description"].to_dict()
                
                analyse = []
                all_ruptures = []
                all_livres = []
                
                for num_cde, data_cde in df_cde.groupby("Commande"):
                    tot_demande, tot_servi = 0, 0
                    lignes_ko, lignes_ok = [], []
                    
                    for _, row in data_cde.iterrows():
                        ref, qte = row["Ref"], row["Qte_Cde"]
                        stock_dispo = stock_live.get(ref, 0)
                        
                        tot_demande += qte
                        servi = min(qte, stock_dispo)
                        tot_servi += servi
                        stock_live[ref] = max(0, stock_dispo - servi)
                        
                        item = {
                            "Commande": num_cde,
                            "Ref": ref,
                            "Article": desc_live.get(ref, f"Ref {ref}"),
                            "Commandé": qte,
                            "Servi": servi,
                            "Manquant": qte - servi
                        }
                        
                        if servi < qte:
                            lignes_ko.append(item)
                            all_ruptures.append(item)
                        else:
                            lignes_ok.append(item)
                            all_livres.append(item)
                    
                    taux = (tot_servi / tot_demande * 100) if tot_demande > 0 else 0
                    analyse.append({
                        "Commande": num_cde,
                        "Taux": taux,
                        "Demande": tot_demande,
                        "Servi": tot_servi,
                        "Alertes": lignes_ko,
                        "Livres": lignes_ok
                    })
                
                df_ana = pd.DataFrame(analyse)
                
                tot_demande_g = df_ana["Demande"].sum()
                tot_servi_g = df_ana["Servi"].sum()
                taux_global = (tot_servi_g / tot_demande_g * 100) if tot_demande_g > 0 else 0
                
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                
                with kpi1:
                    st.markdown(f"""
                    <div class="kpi-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                        <div class="kpi-label">Commandes</div>
                        <div class="kpi-value">{len(df_ana)}</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with kpi2:
                    color = '#11998e' if taux_global == 100 else '#ffaf00' if taux_global > 90 else '#f5576c'
                    st.markdown(f"""
                    <div class="kpi-card" style="background: linear-gradient(135deg, {color} 0%, {color} 100%);">
                        <div class="kpi-label">Taux</div>
                        <div class="kpi-value">{taux_global:.1f}%</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with kpi3:
                    st.markdown(f"""
                    <div class="kpi-card" style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);">
                        <div class="kpi-label">Livrés</div>
                        <div class="kpi-value">{int(tot_servi_g)}</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with kpi4:
                    st.markdown(f"""
                    <div class="kpi-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                        <div class="kpi-label">Manquants</div>
                        <div class="kpi-value">{int(tot_demande_g - tot_servi_g)}</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                add_to_history({
                    'nb_commandes': len(df_ana),
                    'taux_global': taux_global,
                    'total_demande': int(tot_demande_g),
                    'total_servi': int(tot_servi_g)
                })
                
                st.markdown("---")
                
                if PLOTLY_AVAILABLE:
                    st.markdown("### 📈 Performance")
                    df_plot = df_ana.sort_values("Taux", ascending=True)
                    
                    fig = go.Figure(data=[
                        go.Bar(
                            x=df_plot['Commande'],
                            y=df_plot['Taux'],
                            marker=dict(
                                color=df_plot['Taux'],
                                colorscale=[[0, 'red'], [0.5, 'orange'], [1, 'green']],
                                cmin=0, cmax=100, showscale=False
                            ),
                            text=[f"{v:.1f}%" for v in df_plot['Taux']],
                            textposition='outside'
                        )
                    ])
                    fig.update_layout(
                        xaxis_title='Commande',
                        yaxis_title='Taux (%)',
                        yaxis_range=[0, 110],
                        height=400
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("---")
                st.markdown("### 📋 Détail")
                
                col1, col2 = st.columns(2)
                with col1:
                    mode = st.radio("Vue", ["🔴 Problèmes", "🟢 OK", "📊 Tout"], horizontal=True)
                with col2:
                    sort = st.selectbox("Tri", ["Taux ↑", "Taux ↓", "N° cde"])
                
                if sort == "Taux ↑":
                    df_display = df_ana.sort_values("Taux")
                elif sort == "Taux ↓":
                    df_display = df_ana.sort_values("Taux", ascending=False)
                else:
                    df_display = df_ana.sort_values("Commande")
                
                if mode == "🔴 Problèmes":
                    df_display = df_display[df_display["Taux"] < 100]
                elif mode == "🟢 OK":
                    df_display = df_display[df_display["Taux"] == 100]
                
                for _, row in df_display.iterrows():
                    taux = row['Taux']
                    icon = "✅" if taux == 100 else "⚠️" if taux >= 95 else "❌"
                    
                    with st.expander(f"{icon} Cde {row['Commande']} – {taux:.1f}% ({int(row['Servi'])}/{int(row['Demande'])})", expanded=(taux < 100)):
                        sub = st.tabs([f"🟢 Livrés ({len(row['Livres'])})", f"🔴 Manquants ({len(row['Alertes'])})"])
                        
                        with sub[0]:
                            if row["Livres"]:
                                st.dataframe(
                                    pd.DataFrame(row["Livres"])[["Ref", "Article", "Commandé", "Servi"]],
                                    hide_index=True,
                                    use_container_width=True
                                )
                            else:
                                st.info("Aucun")
                        
                        with sub[1]:
                            if row["Alertes"]:
                                st.dataframe(
                                    pd.DataFrame(row["Alertes"])[["Ref", "Article", "Commandé", "Servi", "Manquant"]],
                                    hide_index=True,
                                    use_container_width=True
                                )
                            else:
                                st.success("✅ RAS")
                
                st.markdown("---")
                st.markdown("### 📥 Export")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    output = io.BytesIO()
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    with pd.ExcelWriter(output, engine="openpyxl") as w:
                        df_recap = df_ana[["Commande", "Taux", "Demande", "Servi"]].copy()
                        df_recap["Manquant"] = df_recap["Demande"] - df_recap["Servi"]
                        df_recap.to_excel(w, sheet_name="Recap", index=False)
                        
                        if all_livres:
                            pd.DataFrame(all_livres).to_excel(w, sheet_name="Livres", index=False)
                        
                        if all_ruptures:
                            pd.DataFrame(all_ruptures).to_excel(w, sheet_name="Ruptures", index=False)
                    
                    st.download_button(
                        "📊 Excel",
                        output.getvalue(),
                        f"GESTHOR_{ts}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                
                with col2:
                    csv = df_cde.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "💾 CSV",
                        csv,
                        f"Data_{ts}.csv",
                        "text/csv",
                        use_container_width=True
                    )
    
    # --- STOCK TABS ---
    def show_tab(filtre, nom):
        if nom not in tabs_list:
            return
        idx = tabs_list.index(nom)
        
        with tabs[idx]:
            if filtre == "Tout":
                d = df
            else:
                d = df[df["Statut"] == filtre]
            
            if d.empty:
                st.info("Aucune donnée")
            else:
                n = st.slider("Lignes", 5, 100, 20, key=f"sl_{idx}")
                st.dataframe(
                    d.sort_values("Inventory", ascending=(filtre!="OK")).head(n)[
                        ["N° article.", "Description", "Inventory", "Stock Colis", "Statut"]
                    ],
                    use_container_width=True,
                    hide_index=True
                )
    
    show_tab("Rupture", "❌ Ruptures")
    show_tab("Faible", "⚠️ Faible")
    show_tab("OK", "✅ OK")
    show_tab("Tout", "📋 Tout")

else:
    st.info("👈 Chargez le fichier stock")

if st.session_state.authenticated:
    st.markdown("""<div class="footer">Powered by IC | 2025 ⭐⭐⭐⭐⭐ </div>""", unsafe_allow_html=True)
