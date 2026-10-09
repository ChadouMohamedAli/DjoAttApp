import streamlit as st
import pandas as pd
import mysql.connector
from datetime import datetime, date
from config import config


# ------------------------------------------------------------
# DATABASE CONNECTION
# ------------------------------------------------------------
def get_connection():
    return mysql.connector.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        charset=config.DB_CHARSET
    )


# ------------------------------------------------------------
# QUERIES (with date parameter)
# ------------------------------------------------------------
def get_employees_with_status(target_date):
    conn = get_connection()
    query = f"""
        SELECT 
            e.IDEmploye AS id,
            e.Nom AS nom,
            e.Prenom AS prenom,
            e.Matricule AS matricule,
            c.ChaineMontage AS chaine_actuelle,
            CASE 
                WHEN ec.IDEmploye IS NOT NULL THEN 'Oui' 
                ELSE 'Non' 
            END AS a_tague
        FROM employe e
        LEFT JOIN chainemontage c ON e.IDChaineMontage = c.IDChaineMontage
        LEFT JOIN employechaine ec 
            ON e.IDEmploye = ec.IDEmploye 
            AND DATE(ec.Date) = '{target_date}'
        WHERE e.Etat = 1
        GROUP BY e.IDEmploye
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df


def get_employees_with_line_status(target_date):
    """
    Retourne pour chaque employé :
      - sa chaîne affectée
      - son groupe (depuis groupechaine)
      - son matricule
      - le poste (IDPosteTravail) et l'heure (Affecter_Le) du tag du jour (s'il existe)
      - un statut de base (Présent/Absent) basé sur la présence d'un tag ce jour
    """
    conn = get_connection()
    query = f"""
        SELECT 
            COALESCE(c.ChaineMontage, 'Non affecté') AS chaine_nom,
            COALESCE(g.Groupe, 'Sans groupe') AS groupe,
            e.Nom AS nom,
            e.Prenom AS prenom,
            e.Matricule AS matricule,
            ec.IDPosteTravail AS poste_travail,
            ec.Affecter_Le AS heure_pointage,
            CASE 
                WHEN ec.IDEmploye IS NOT NULL THEN 'Présent' 
                ELSE 'Absent' 
            END AS statut
        FROM employe e
        LEFT JOIN chainemontage c ON e.IDChaineMontage = c.IDChaineMontage
        LEFT JOIN groupechaine g ON c.IDGroupe = g.IDGroupe
        LEFT JOIN employechaine ec 
            ON e.IDEmploye = ec.IDEmploye 
            AND DATE(ec.Date) = '{target_date}'
        WHERE e.Etat = 1
        ORDER BY c.ChaineMontage, e.Nom
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df


# ------------------------------------------------------------
# STREAMLIT APP
# ------------------------------------------------------------
def main():
    st.set_page_config(page_title=config.PAGE_TITLE, page_icon=config.PAGE_ICON, layout="wide")
    st.title(f"{config.PAGE_ICON} {config.PAGE_TITLE}")

    menu = ["📊 Employés", "📋 Chaînes de Montage"]
    choice = st.sidebar.radio("Navigation", menu)

    target_date = st.sidebar.date_input("Date d'analyse", value=date.today()).isoformat()

    # ---------------------- Employés view ----------------------
    if choice == "📊 Employés":
        st.subheader("👥 État des employés")
        df = get_employees_with_status(target_date)
        if df.empty:
            st.info("Aucun employé trouvé.")
        else:
            st.sidebar.markdown("### Filtres Employés")
            name_filter = st.sidebar.text_input("Rechercher par Nom/Prénom", "")
            if name_filter:
                df = df[df["nom"].str.contains(name_filter, case=False, na=False) |
                        df["prenom"].str.contains(name_filter, case=False, na=False)]

            if "matricule" in df.columns:
                mat_filter = st.sidebar.text_input("Rechercher par matricule", "")
                if mat_filter:
                    try:
                        mat_int = int(mat_filter)
                        df = df[df["matricule"] == mat_int]
                    except ValueError:
                        st.warning("Veuillez entrer un numéro de matricule valide.")

            status_filter = st.sidebar.selectbox("Statut", ["Tous", "Présent", "Absent"])
            if status_filter == "Présent":
                df = df[df["a_tague"] == "Oui"]
            elif status_filter == "Absent":
                df = df[df["a_tague"] == "Non"]

            df["Statut"] = df["a_tague"].apply(lambda x: "🟢 Présent" if x == "Oui" else "🔴 Absent")
            display_cols = ["nom", "prenom"]
            if "matricule" in df.columns:
                display_cols.append("matricule")
            display_cols += ["chaine_actuelle", "Statut"]

            df_display = df[display_cols]
            new_names = ["Nom", "Prénom"]
            if "matricule" in df.columns:
                new_names.append("Matricule")
            new_names += ["Chaîne actuelle", "Statut"]
            df_display.columns = new_names

            st.dataframe(df_display, width='stretch')
            st.caption(f"Affichage de {len(df)} employé(s) pour la date {target_date}")

    # ---------------------- Chaînes view (BLOCKS) ----------------------
    elif choice == "📋 Chaînes de Montage":
        st.subheader("📋 Employés par chaîne de montage")
        df = get_employees_with_line_status(target_date)
        if df.empty:
            st.info("Aucun employé trouvé.")
        else:
            st.sidebar.markdown("### Filtres Chaînes")

            # Filtre par groupe
            groupes = sorted(df["groupe"].unique().tolist())
            selected_groupe = st.sidebar.selectbox("Filtrer par groupe", ["Tous"] + groupes)
            if selected_groupe != "Tous":
                df = df[df["groupe"] == selected_groupe]

            # Filtre par poste (sélectionne le poste à comparer)
            # Les libellés des postes (P1, P2, P3) correspondent aux IDPosteTravail 1,2,3
            poste_options = ["Tous", "P1 (6h-14h)", "P2 (14h-22h)", "P3 (22h-6h)"]
            selected_poste_label = st.sidebar.selectbox("Filtrer par poste", poste_options)
            poste_map = {"P1 (6h-14h)": 1, "P2 (14h-22h)": 2, "P3 (22h-6h)": 3}
            selected_poste_id = poste_map.get(selected_poste_label, None)  # None si "Tous"

            # Recherche par nom de chaîne
            chain_search = st.sidebar.text_input("Rechercher une chaîne (nom)", "")
            if chain_search:
                df = df[df["chaine_nom"].str.contains(chain_search, case=False, na=False)]

            # --- Recalcul du statut en fonction du poste sélectionné ---
            if selected_poste_id is not None:
                # Nouveau statut : Présent seulement si le tag du jour a le bon IDPosteTravail
                df["statut_recalcule"] = df.apply(
                    lambda row: "Présent" if (row["poste_travail"] == selected_poste_id) else "Absent",
                    axis=1
                )
                # Mais attention : si l'employé n'a pas tagué du tout, poste_travail est NaN
                # Dans ce cas, il est Absent (déjà géré par la condition ci-dessus)
            else:
                # Si aucun poste sélectionné, on garde le statut original (Présent si un tag existe)
                df["statut_recalcule"] = df["statut"]

            # Groupement par chaîne
            grouped = df.groupby("chaine_nom")
            for chaine, group in sorted(grouped, key=lambda x: x[0] if x[0] is not None else ""):
                total = len(group)
                # Compter les présents selon le statut recalculé
                present = group[group["statut_recalcule"] == "Présent"].shape[0]
                with st.expander(f"🏭 {chaine} — {total} employé(s), {present} présent(s)", expanded=True):
                    # Préparation du tableau : afficher le matricule, l'heure de pointage et le statut recalcule
                    display_group = group[["nom", "prenom", "matricule", "heure_pointage", "statut_recalcule"]].copy()
                    # Remplacer le statut par des émojis
                    display_group["statut_recalcule"] = display_group["statut_recalcule"].apply(
                        lambda x: "🟢 Présent" if x == "Présent" else "🔴 Absent"
                    )
                    # Formater l'heure pour n'afficher que l'heure (si non nulle)
                    display_group["heure_pointage"] = display_group["heure_pointage"].apply(
                        lambda x: x.strftime("%H:%M:%S") if pd.notnull(x) else ""
                    )
                    # Renommer les colonnes
                    display_group = display_group.rename(columns={
                        "nom": "Nom",
                        "prenom": "Prénom",
                        "matricule": "Matricule",
                        "heure_pointage": "Heure pointage",
                        "statut_recalcule": "Statut"
                    })
                    st.dataframe(display_group, width='stretch')

            st.caption(f"Affichage de {len(df)} employé(s) pour la date {target_date}")

    st.sidebar.markdown("---")
    st.sidebar.caption("Version 0.7.0 – filtre poste avec statut conditionnel")


if __name__ == "__main__":
    main()