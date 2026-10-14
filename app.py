import hmac
from pathlib import Path
from PIL import Image, ImageChops
import streamlit as st
import pandas as pd
import mysql.connector
from datetime import datetime, date
from config import config
from attendance_service import add_manual_checkin
from streamlit.errors import StreamlitSecretNotFoundError

LOGO_PATH = Path(__file__).with_name("DJO.png")


@st.cache_data
def get_cropped_logo():
    with Image.open(LOGO_PATH) as source:
        logo = source.convert("RGB")
        bounds = ImageChops.difference(
            logo,
            Image.new("RGB", logo.size, "white"),
        ).getbbox()
        if bounds is None:
            return logo

        left, top, right, bottom = bounds
        padding = 12
        return logo.crop(
            (
                max(0, left - padding),
                max(0, top - padding),
                min(logo.width, right + padding),
                min(logo.height, bottom + padding),
            )
        )


# ------------------------------------------------------------
# DATABASE CONNECTION
# ------------------------------------------------------------
def get_connection():
    return mysql.connector.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD

    )


# ------------------------------------------------------------
# QUERIES (with date parameter)
# ------------------------------------------------------------
def get_employees_with_status(target_date):
    conn = get_connection()
    query = """
        SELECT 
            e.IDEmploye AS id,
            e.Nom AS nom,
            e.Prenom AS prenom,
            e.Matricule AS matricule,
            c.ChaineMontage AS chaine_actuelle,
            MAX(CASE WHEN ec.Etat = 1 THEN ec.Affecter_Le END) AS heure_pointage,
            CASE 
                WHEN MAX(CASE WHEN ec.Etat = 1 THEN 1 ELSE 0 END) = 1 THEN 'Oui'
                ELSE 'Non' 
            END AS a_tague
        FROM employe e
        LEFT JOIN chainemontage c ON e.IDChaineMontage = c.IDChaineMontage
        LEFT JOIN employechaine ec 
            ON e.IDEmploye = ec.IDEmploye 
            AND DATE(ec.Date) = %s
        WHERE e.Etat = 1
        GROUP BY e.IDEmploye, e.Nom, e.Prenom, e.Matricule, c.ChaineMontage
    """
    try:
        return pd.read_sql(query, conn, params=(target_date,))
    finally:
        conn.close()


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
    query = """
        SELECT 
            e.IDEmploye AS id,
            COALESCE(c.ChaineMontage, 'Non affecté') AS chaine_nom,
            COALESCE(g.Groupe, 'Sans groupe') AS groupe,
            e.Nom AS nom,
            e.Prenom AS prenom,
            e.Matricule AS matricule,
            MAX(CASE WHEN ec.Etat = 1 THEN ec.IDPosteTravail END) AS poste_travail,
            MAX(CASE WHEN ec.Etat = 1 THEN ec.Affecter_Le END) AS heure_pointage,
            CASE 
                WHEN MAX(CASE WHEN ec.Etat = 1 THEN 1 ELSE 0 END) = 1 THEN 'Présent'
                ELSE 'Absent' 
            END AS statut
        FROM employe e
        LEFT JOIN chainemontage c ON e.IDChaineMontage = c.IDChaineMontage
        LEFT JOIN groupechaine g ON c.IDGroupe = g.IDGroupe
        LEFT JOIN employechaine ec 
            ON e.IDEmploye = ec.IDEmploye 
            AND DATE(ec.Date) = %s
        WHERE e.Etat = 1
        GROUP BY e.IDEmploye, c.ChaineMontage, g.Groupe, e.Nom, e.Prenom, e.Matricule
        ORDER BY c.ChaineMontage, e.Nom
    """
    try:
        return pd.read_sql(query, conn, params=(target_date,))
    finally:
        conn.close()


def get_active_employees():
    conn = get_connection()
    query = """
        SELECT
            e.IDEmploye AS id,
            COALESCE(c.ChaineMontage, 'Non affecté') AS chaine_nom,
            COALESCE(g.Groupe, 'Sans groupe') AS groupe
        FROM employe e
        LEFT JOIN chainemontage c ON e.IDChaineMontage = c.IDChaineMontage
        LEFT JOIN groupechaine g ON c.IDGroupe = g.IDGroupe
        WHERE e.Etat = 1
        ORDER BY g.Groupe, c.ChaineMontage
    """
    try:
        return pd.read_sql(query, conn)
    finally:
        conn.close()


def get_attendance_for_period(start_date, end_date, employee_ids):
    if not employee_ids:
        return pd.DataFrame(
            columns=["id", "date_pointage", "poste_travail", "etat"]
        )

    placeholders = ", ".join(["%s"] * len(employee_ids))
    query = f"""
        SELECT
            IDEmploye AS id,
            DATE(Date) AS date_pointage,
            IDPosteTravail AS poste_travail,
            Etat AS etat
        FROM employechaine
        WHERE Date >= %s
            AND Date < DATE_ADD(%s, INTERVAL 1 DAY)
            AND IDEmploye IN ({placeholders})
    """
    conn = get_connection()
    try:
        return pd.read_sql(
            query,
            conn,
            params=(start_date, end_date, *employee_ids),
        )
    finally:
        conn.close()


def render_manual_checkin(df, target_date, status_column, form_key):
    st.markdown("### Ajouter un pointage manuel")
    if target_date != date.today():
        st.info("Le pointage manuel est disponible uniquement pour aujourd'hui.")
        return

    absent = df[df[status_column].isin(["Non", "Absent"])].copy()
    if absent.empty:
        st.info("Aucun employé absent disponible pour le pointage.")
        return

    labels = {
        int(row.id): (
            f"{row.matricule} — {row.nom} {row.prenom} (ID {int(row.id)})"
            if pd.notna(row.matricule)
            else f"{row.nom} {row.prenom} (ID {int(row.id)})"
        )
        for row in absent.itertuples()
    }

    with st.form(form_key):
        employee_id = st.selectbox(
            "Employé absent",
            options=list(labels),
            format_func=lambda value: labels[value],
        )
        pointage_time = st.time_input(
            "Heure de pointage",
            value=datetime.now().time().replace(second=0, microsecond=0),
        )
        submitted = st.form_submit_button("Enregistrer le pointage")

    if submitted:
        try:
            add_manual_checkin(employee_id, target_date, pointage_time)
            st.session_state["manual_checkin_success"] = True
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except mysql.connector.Error as exc:
            st.error(f"Erreur de base de données : {exc}")


def require_login():
    try:
        credentials = st.secrets["auth"]
        expected_username = credentials["username"]
        expected_password = credentials["password"]
    except (StreamlitSecretNotFoundError, KeyError):
        st.error(
            "Authentification non configurée. Ajoutez [auth], username et password "
            "dans .streamlit/secrets.toml."
        )
        st.stop()

    if not isinstance(expected_username, str) or not expected_username.strip():
        st.error("Le nom d'utilisateur dans .streamlit/secrets.toml est invalide.")
        st.stop()
    if not isinstance(expected_password, str) or not expected_password:
        st.error("Le mot de passe dans .streamlit/secrets.toml est invalide.")
        st.stop()

    if not st.session_state.get("authenticated", False):
        _, login_column, _ = st.columns([1, 1.1, 1])
        with login_column:
            with st.container(border=True):
                _, logo_column, _ = st.columns([1, 2, 1])
                logo_column.image(get_cropped_logo(), use_container_width=True)
                st.markdown(
                    "<h2 style='text-align: center;'>Connexion</h2>", unsafe_allow_html=True
                )

                with st.form("login_form"):
                    username = st.text_input(
                        "Nom d'utilisateur",
                        placeholder="Saisissez votre nom d'utilisateur",
                    )
                    password = st.text_input(
                        "Mot de passe",
                        type="password",
                        placeholder="Saisissez votre mot de passe",
                    )
                    submitted = st.form_submit_button(
                        "Se connecter",
                        type="primary",
                        use_container_width=True,
                    )
                    col1, col2, col3 = st.columns([1, 4, 1])
                    with col2:
                        st.caption("Application réalisée par [DivaSoftware](https://diva-software.com).")

        if submitted:
            username_valid = hmac.compare_digest(
                username.strip(),
                expected_username.strip(),
            )
            password_valid = hmac.compare_digest(password, expected_password)
            if username_valid and password_valid:
                st.session_state["authenticated"] = True
                st.session_state["username"] = expected_username.strip()
                st.rerun()
            st.error("Nom d'utilisateur ou mot de passe incorrect.")

        st.stop()


# ------------------------------------------------------------
# STREAMLIT APP
# ------------------------------------------------------------
def main():
    st.set_page_config(page_title=config.PAGE_TITLE, page_icon=config.PAGE_ICON, layout="wide")
    require_login()
    st.title(f"{config.PAGE_ICON} {config.PAGE_TITLE}")
    if st.session_state.pop("manual_checkin_success", False):
        st.success("Le pointage a été ajouté.")


    menu = ["📈 Dashboard", "📊 Employés", "📋 Chaînes de Montage"]
    st.sidebar.image(get_cropped_logo(), use_container_width=True)
    st.sidebar.markdown("**Djo · Gestion des présences**")
    st.sidebar.caption("Espace de suivi de production")
    st.sidebar.markdown("---")
    st.sidebar.caption("MENU PRINCIPAL")
    choice = st.sidebar.radio("Navigation", menu)

    target_date = None
    if choice != "📈 Dashboard":
        target_date = st.sidebar.date_input("Date d'analyse", value=date.today())

    # ---------------------- Dashboard ----------------------
    if choice == "📈 Dashboard":
        st.subheader("📈 Dashboard de présence")
        today = date.today()
        start_date = st.sidebar.date_input(
            "Du",
            value=today,
            key="dashboard_start_date",
        )
        end_date = st.sidebar.date_input(
            "Au",
            value=today,
            key="dashboard_end_date",
        )
        employees = get_active_employees()

        groups = ["Tous"] + sorted(employees["groupe"].dropna().unique().tolist())
        selected_group = st.sidebar.selectbox("Groupe", groups)
        if selected_group != "Tous":
            employees = employees[employees["groupe"] == selected_group]

        lines = ["Toutes"] + sorted(employees["chaine_nom"].dropna().unique().tolist())
        selected_line = st.sidebar.selectbox("Chaîne de montage", lines)
        if selected_line != "Toutes":
            employees = employees[employees["chaine_nom"] == selected_line]

        post_options = ["Tous", "P1 (6h-14h)", "P2 (14h-22h)", "P3 (22h-6h)"]
        selected_post = st.sidebar.selectbox("Poste de travail", post_options)
        post_ids = {"P1 (6h-14h)": 1, "P2 (14h-22h)": 2, "P3 (22h-6h)": 3}
        selected_post_id = post_ids.get(selected_post)

        if start_date > end_date:
            st.warning("La date de début doit être antérieure ou égale à la date de fin.")
        else:
            st.caption(f"Indicateurs du {start_date} au {end_date}")
            employee_ids = [int(employee_id) for employee_id in employees["id"].tolist()]
            attendance = get_attendance_for_period(
                start_date,
                end_date,
                employee_ids,
            )

            days_count = (end_date - start_date).days + 1
            total_employee_days = len(employee_ids) * days_count
            present_records = attendance[attendance["etat"] == 1].copy()
            if selected_post_id is not None:
                present_records = present_records[
                    present_records["poste_travail"] == selected_post_id
                ]
            present_records = present_records.drop_duplicates(
                subset=["id", "date_pointage"]
            )
            present = len(present_records)
            absent = total_employee_days - present
            attendance_rate = (
                round(present / total_employee_days * 100, 1)
                if total_employee_days
                else 0
            )

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Effectif (employé-jours)", total_employee_days)
            col2.metric("Présences", present)
            col3.metric("Absences", absent)
            col4.metric("Taux de présence", f"{attendance_rate}%")
            st.caption(
                f"{len(employee_ids)} employé(s) actif(s) sur {days_count} jour(s)"
            )

            if employees.empty:
                st.info("Aucun employé ne correspond aux filtres sélectionnés.")
            else:
                st.markdown("### Présence par chaîne de montage")
                employee_counts = employees.groupby("chaine_nom")["id"].nunique()
                present_by_line = (
                    present_records.merge(
                        employees[["id", "chaine_nom"]],
                        on="id",
                        how="inner",
                    )
                    .groupby("chaine_nom")
                    .size()
                )
                present_by_line = present_by_line.reindex(
                    employee_counts.index,
                    fill_value=0,
                )
                line_summary = pd.DataFrame(
                    {
                        "Présences": present_by_line,
                        "Absences": employee_counts * days_count - present_by_line,
                    }
                ).fillna(0).astype(int).sort_index()
                st.bar_chart(line_summary)

        st.markdown("### Rapports")
        download_col1, download_col2 = st.columns(2)
        download_col1.button("Télécharger le rapport CSV", disabled=True, use_container_width=True)
        download_col2.button("Télécharger le rapport PDF", disabled=True, use_container_width=True)
        st.caption("Le téléchargement des rapports sera disponible prochainement.")

    # ---------------------- Employés view ----------------------
    elif choice == "📊 Employés":
        st.subheader("👥 État des employés")
        df = get_employees_with_status(target_date)
        if df.empty:
            st.info("Aucun employé trouvé.")
        else:
            pointage_employees = df.copy()
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
            display_cols += ["chaine_actuelle", "heure_pointage", "Statut"]

            df_display = df[display_cols]
            new_names = ["Nom", "Prénom"]
            if "matricule" in df.columns:
                new_names.append("Matricule")
            new_names += ["Chaîne actuelle", "Heure pointage", "Statut"]
            df_display.columns = new_names

            df_display["Heure pointage"] = df_display["Heure pointage"].apply(
                lambda value: value.strftime("%H:%M:%S") if pd.notnull(value) else ""
            )
            st.dataframe(df_display, width="stretch", hide_index=True)
            st.caption(f"Affichage de {len(df)} employé(s) pour la date {target_date}")
            render_manual_checkin(
                pointage_employees,
                target_date,
                "a_tague",
                "manual_checkin_employees",
            )

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

            pointage_employees = df.copy()

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

            status_filter = st.sidebar.selectbox("Statut", ["Tous", "Présent", "Absent"])
            if status_filter != "Tous":
                df = df[df["statut_recalcule"] == status_filter]

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
                    st.dataframe(display_group, width="stretch", hide_index=True)

            st.caption(f"Affichage de {len(df)} employé(s) pour la date {target_date}")
            render_manual_checkin(
                pointage_employees,
                target_date,
                "statut",
                "manual_checkin_lines",
            )

    st.sidebar.markdown("---")
    st.sidebar.caption("Connecté · Session sécurisée")
    st.sidebar.caption(f"Utilisateur : {st.session_state.get('username', '')}")
    if st.sidebar.button("Se déconnecter", use_container_width=True):
        st.session_state["authenticated"] = False
        st.session_state.pop("username", None)
        st.rerun()
    st.sidebar.caption("Version 0.8.0")
    st.sidebar.markdown("---")

if __name__ == "__main__":
    main()