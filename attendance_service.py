from datetime import date, datetime

from database import (
    get_employee_info,
    get_attendance,
    insert_attendance,
    insert_manual_attendance,
    update_present,
    update_absent,
)

from shift_service import get_shift_from_datetime, get_shift_id


# ==========================================================
# CONSTANTS
# ==========================================================

WEB_USER = "Web User"

REASONS = [
    "Oubli badge",
    "Badge défectueux",
    "Erreur de pointage",
    "Formation",
    "Mission",
    "Correction manuelle",
    "Autre"
]


# ==========================================================
# STATUS
# ==========================================================

def compute_status(row):
    """
    Compute attendance status from employechaine row.
    """

    if row["IDEmployeChaine"] is None:
        return "Absent"

    if row["Etat"] == 1:
        return "Présent"

    return "Absent"


def is_manual(row):
    """
    Was this attendance manually modified?
    """

    return bool(row["Saisipar"]) or bool(row["ModifiePar"])


def status_icon(status, manual=False):
    """
    Return pretty status for UI.
    """

    if status == "Présent":

        if manual:
            return "🟡 Présent"

        return "🟢 Présent"

    return "🔴 Absent"


# ==========================================================
# KPI
# ==========================================================

def build_kpis(df):
    """
    Compute dashboard KPIs.
    """

    total = len(df)

    present = (df["Status"] == "Présent").sum()

    absent = total - present

    attendance = 0

    if total > 0:
        attendance = round(
            present / total * 100,
            1
        )

    manual = df["Manual"].sum()

    return {

        "total": total,

        "present": present,

        "absent": absent,

        "attendance": attendance,

        "manual": manual

    }


# ==========================================================
# PRESENT
# ==========================================================

def add_manual_checkin(employee_id, target_date, checkin_time):
    """Append a manual attendance row for an employee absent on the selected day."""
    if target_date != date.today():
        raise ValueError("Le pointage manuel est autorisé uniquement pour aujourd'hui.")

    shift = get_shift_from_datetime(target_date, checkin_time)
    if shift is None:
        raise ValueError(
            "Aucun poste de travail ne correspond à cette heure dans tpstravail."
        )

    checkin_at = datetime.combine(target_date, checkin_time)
    return insert_manual_attendance(
        employee_id,
        target_date,
        shift["IDPosteTravail"],
        checkin_at,
    )


def mark_present(
        employee_id,
        target_date,
        reason
):
    """
    Mark employee present.
    """

    employee = get_employee_info(employee_id)

    if employee is None:
        raise Exception("Employé introuvable")

    attendance = get_attendance(
        employee_id,
        target_date
    )

    now = datetime.now()

    shift_id = get_shift_id(
        target_date,
        now.time()
    )
    print(shift_id)

    if shift_id is None:
        raise Exception(
            "Impossible de déterminer le poste de travail."
        )

    user = f"{WEB_USER} | {reason}"

    # ------------------------------------------------------
    # Existing attendance
    # ------------------------------------------------------

    if attendance:

        values = (

            shift_id,

            employee["IDChaineMontage"],

            now,

            user,

            attendance["IDEmployeChaine"]

        )

        update_present(values)

        return

    # ------------------------------------------------------
    # New attendance
    # ------------------------------------------------------

    values = (

        employee_id,

        target_date,

        shift_id,

        employee["IDChaineMontage"],

        now,

        user

    )

    insert_attendance(values)


# ==========================================================
# ABSENT
# ==========================================================

def mark_absent(
        employee_id,
        target_date,
        reason
):
    """
    Mark employee absent.
    """

    attendance = get_attendance(
        employee_id,
        target_date
    )

    if attendance is None:
        return

    user = f"{WEB_USER} | {reason}"

    values = (

        user,

        employee_id,

        target_date

    )

    update_absent(values)


# ==========================================================
# UI PREPARATION
# ==========================================================

def prepare_employee_dataframe(df):
    """
    Prepare dataframe before displaying
    in Streamlit.
    """

    if df.empty:
        return df

    df = df.copy()

    df["Status"] = df.apply(
        compute_status,
        axis=1
    )

    df["Manual"] = df.apply(
        is_manual,
        axis=1
    )

    df["DisplayStatus"] = df.apply(

        lambda row:

        status_icon(
            row["Status"],
            row["Manual"]
        ),

        axis=1

    )

    return df