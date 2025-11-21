import streamlit as st
import pandas as pd
import numpy as np
import pdfplumber
import re

# --- Config ---
st.set_page_config(page_title="GESTHOR – Master", page_icon="📦", layout="wide")

# --- CSS ---
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; }
    /* Style KPI */
    div[data-testid="stMetric"] {
        background-color: #fff; border: 1px solid #ddd; border-radius: 8px;
        padding: 10px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    /* Taux de service couleurs */
    .success-kpi { color: #28a745; font-weight: bold; font-size: 1.2rem; }
    .error-kpi { color: #dc3545; font-weight: bold; font-size: 1.2rem; }
    .footer { text-align: center; margin-top: 4rem; color: #888; font-size: 0.8rem; border-top: 1px solid #eee; padding-top: 1rem;}
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

# --- FONCTIONS ---

@st.cache_data
def load_stock(file):
    try:
        df = pd.read_excel(file)
        col_map = {c: c.strip() for c in df.columns}
        df = df.rename(columns=col_map)
        
        # Conversion Texte OBLIGATOIRE
        if "N° article." in df.columns:
            df["N° article."] = df["N° article."].astype(str).str.strip()
        if "Description" in df.columns:
            df["Description"] = df["Description"].astype(str).str.strip()
        
        # Conversion Nombres
        df["Inventory"] = pd.to_numeric(df["Inventory"], errors='coerce').fillna(0)
        df["Qty. per Sales Unit of Measure"] = pd.to_numeric(df["Qty. per Sales Unit of Measure"], errors='coerce').fillna(1)
        
        # Calcul Colis
        df["Stock Colis"] = df["Inventory"] / df["Qty. per Sales Unit of Measure"].replace(0, 1)
        
        # Statut
        conditions = [(df["Inventory"] <= 0), (df["Inventory"] < 500)]
        choices = ["Rupture", "Faible"]
        df["Statut"] = np.select(conditions, choices, default="OK")
        
        return df
    except Exception as e:
        st.error(f"Erreur Excel : {e}")
        return None

def extract_pdf_force(pdf_file):
    """ Lecture Bulletozer, adaptée aux sauts de ligne internes du PDF fourni. """
    orders = []
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() + "\n"
            
            # --- 1. Extraction des Numéros de Commande ---
            # Liste des commandes dans le document
            cde_nums = re.findall(r"Commande\s*n°(\d+)", full_text)
            if not cde_nums:
                 return pd.DataFrame() # Stop si pas de commande trouvée
            
            # --- 2. Extraction des Lignes de Produits ---
            # Pattern: "N\n","REF\n",...,"QTY\n","PCB\n","EUR\n"
            # On cherche: Réf (Groupe 1) et Qté Commandée (Groupe 2)
            # Le .*? en mode DOTALL permet de sauter les multiples champs et les sauts de ligne internes
            item_pattern = re.compile(r'"\d+\n","(\d+)\n",.*?"(\d+)\n",".*?","(EUR\n)"', re.DOTALL)
            
            item_matches = item_pattern.finditer(full_text)
            
            # On utilise les numéros de commande trouvés pour attribuer les lignes
            current_cde_index = 0
            
            for match in item_matches:
                ref = match.group(1).strip()
                qty = match.group(2).strip()
                
                # Attribuer la commande la plus récente ou la suivante
                if current_cde_index < len(cde_nums):
                    cde_id = cde_nums[current_cde_index]
                else:
                    cde_id = cde_nums[-1] # Si on déborde (plus de lignes que de commandes), on reste sur la dernière

                # HACK : Après la première commande, on passe à la suivante quand la page change ou le Récapitulatif est vu.
                # Ici, on va simplement basculer d'ID à chaque fois qu'on voit le récapitulatif
                if "Récapitulatif" in full_text[:match.start()] and cde_id == cde_nums[current_cde_index] and current_cde_index < len(cde_nums) - 1:
                     current_cde_index += 1
                     cde_id = cde_nums[current_cde_index]

                orders.append({
                    "Commande": cde_id,
                    "Ref": ref,
                    "Qte_Cde": int(qty)
                })

        return pd.DataFrame(orders)
    except Exception as e:
        st.error(f"Erreur PDF : {e}")
        return pd.DataFrame()

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Stock (Excel)")
    f_stock = st.file_uploader("Fichier Inventory.xlsx", type=["xlsx"])
    
    st.header("2. Commandes (PDF)")
    f_pdf = st.file_uploader("Fichier Commandes.pdf", type=["pdf"])
    
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

    # --- INDICATEURS DE STOCK (Restaurés) ---
    st.markdown("### 📊 Indicateurs de Stock")
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Articles trouvés", len(df))
    k2.metric("❌ En Rupture", len(df[df["Statut"] == "Rupture"]), delta_color="inverse")
    k3.metric("⚠️ Stock Faible", len(df[df["Statut"] == "Faible"]), delta_color="normal")
    
    st.divider()

    # --- CRÉATION DES ONGLETS ---
    t_noms = []
    if f_pdf: t_noms.append("🚀 Analyse Commandes")
    t_noms.extend(["❌ Ruptures", "⚠️ Stock Faible", "✅ Stock OK", "📁 Tout"])
    
    tabs = st.tabs(t_noms)
    
    # --- 1. LOGIQUE ANALYSE COMMANDES (Si PDF) ---
    if f_pdf:
        with tabs[0]:
            st.subheader("Résultat de l'analyse des Commandes")
            df_cde = extract_pdf_force(f_pdf)
            
            if df_cde.empty:
                st.warning("⚠️ Aucune commande trouvée. Le format de votre PDF semble très inhabituel, mais le code est optimisé pour votre exemple. Rechargez le PDF ou vérifiez le contenu.")
            else:
                # Moteur de calcul (Simule l'épuisement du stock)
                stock_live = df_stock.set_index("N° article.")["Inventory"].to_dict()
                desc_live = df_stock.set_index("N° article.")["Description"].to_dict()
                
                analyse = []
                
                # On groupe par commande pour calculer le taux de service
                for num_cde, data_cde in df_cde.groupby("Commande"):
                    tot_demande, tot_servi = 0, 0
                    lignes_ko = []
                    
                    for _, row in data_cde.iterrows():
                        ref, qte = row["Ref"], row["Qte_Cde"]
                        stock_dispo = stock_live.get(ref, 0)
                        
                        tot_demande += qte
                        
                        servi = min(qte, stock_dispo)
                        tot_servi += servi
                        stock_live[ref] = max(0, stock_dispo - qte) # Déduction immédiate
                        
                        if servi < qte:
                            manque = qte - servi
                            lignes_ko.append({
                                "Ref": ref,
                                "Article": desc_live.get(ref, f"Article {ref} (Non trouvé en stock)"),
                                "Commandé": qte,
                                "Manquant": manque
                            })
                    
                    taux = (tot_servi / tot_demande * 100) if tot_demande > 0 else 0
                    analyse.append({
                        "Commande": num_cde, "Taux": taux, 
                        "Demande": tot_demande, "Servi": tot_servi, 
                        "Alertes": lignes_ko
                    })
                
                df_ana = pd.DataFrame(analyse)
                
                # --- INDICATEURS ANALYSE PDF ---
                taux_global = df_ana["Servi"].sum() / df_ana["Demande"].sum() * 100
                manquants_total = df_ana["Demande"].sum() - df_ana["Servi"].sum()
                
                k1_a, k2_a, k3_a = st.columns(3)
                k1_a.metric("Commandes analysées", len(df_ana))
                k2_a.metric("Taux de Service Moyen", f"{taux_global:.1f}%", delta="Global")
                k3_a.metric("Pièces non livrables", int(manquants_total), delta_color="inverse")
                
                st.markdown("---")
                
                # Affichage détaillé par commande
                for idx, row in df_ana.iterrows():
                    titre = f"Commande {row['Commande']} — Taux: {row['Taux']:.1f}% ({int(row['Servi'])}/{int(row['Demande'])})"
                    icon = "✅" if row["Taux"] == 100 else "⚠️" if row["Taux"] >= 95 else "❌"
                        
                    with st.expander(f"{icon} {titre}"):
                        if row["Alertes"]:
                            st.error(f"🛑 {len(row['Alertes'])} références en rupture sur cette commande :")
                            st.dataframe(pd.DataFrame(row["Alertes"]), hide_index=True)
                        else:
                            st.success("Commande complète. Stock suffisant pour l'intégralité.")

    # --- 2. LOGIQUE ONGLETS STOCK ---
    
    # Index de départ pour les onglets de stock
    start_idx = 1 if f_pdf else 0
    
    def show_tab(filtre, idx):
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
                    d.head(top_n)[["N° article.", "Description", "Inventory", "Stock Colis", "Statut"]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Inventory": st.column_config.NumberColumn("Stock (UVC)", format="%d"),
                        "Stock Colis": st.column_config.NumberColumn("Colis (Est.)", format="%.1f"), # Plus de barre
                    }
                )

    # Appel des onglets de stock
    if "❌ Ruptures" in t_noms:
        show_tab("Rupture", t_noms.index("❌ Ruptures"))
    if "⚠️ Stock Faible" in t_noms:
        show_tab("Faible", t_noms.index("⚠️ Stock Faible"))
    if "✅ Stock OK" in t_noms:
        show_tab("OK", t_noms.index("✅ Stock OK"))
    if "📁 Tout" in t_noms:
        show_tab("Tout", t_noms.index("📁 Tout"))


else:
    st.info("👈 En attente du fichier Stock Excel...")

# --- FOOTER ---
st.markdown("""<div class="footer">Powered by IC - 2025 ★★★★★</div>""", unsafe_allow_html=True)
