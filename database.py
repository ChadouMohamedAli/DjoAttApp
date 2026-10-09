import mysql.connector
import pandas as pd
from config import config


# ==========================================================
# DATABASE CONNECTION
# ==========================================================

def get_connection():
    """Create a new MySQL connection."""
    return mysql.connector.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        charset=config.DB_CHARSET,
        autocommit=False
    )


# ==========================================================
# GENERIC HELPERS
# ==========================================================

def fetch_dataframe(query, params=None):
    """Execute a SELECT query and return a Pandas DataFrame."""
    conn = get_connection()
    try:
        return pd.read_sql(query, conn, params=params)
    finally:
        conn.close()


def fetch_one(query, params=None):
    """Return a single row as dictionary."""
    conn = get_connection()

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        row = cursor.fetchone()
        cursor.close()
        return row

    finally:
        conn.close()


def execute(query, params=None):
    """
    Execute INSERT / UPDATE / DELETE.

    Returns:
        affected rows
    """
    conn = get_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(query, params or ())
        conn.commit()

        affected = cursor.rowcount

        cursor.close()

        return affected

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# ==========================================================
# EMPLOYEES
# ==========================================================

def get_employees(target_date):
    """
    Returns all active employees with attendance
    information for the selected date.
    """

    query = """
    SELECT

        e.IDEmploye,
        e.Nom,
        e.Prenom,
        e.Matricule,

        e.IDChaineMontage,

        c.ChaineMontage,

        g.Groupe,

        ec.IDEmployeChaine,
        ec.IDPosteTravail,
        ec.Etat,

        ec.Affecter_Le,
        ec.Saisipar,
        ec.ModifiePar

    FROM employe e

    LEFT JOIN chainemontage c
        ON c.IDChaineMontage = e.IDChaineMontage

    LEFT JOIN groupechaine g
        ON g.IDGroupe = c.IDGroupe

    LEFT JOIN employechaine ec
        ON ec.IDEmploye = e.IDEmploye
        AND DATE(ec.Date) = %s

    WHERE e.Etat = 1

    ORDER BY
        c.ChaineMontage,
        e.Nom,
        e.Prenom
    """

    return fetch_dataframe(query, (target_date,))


def get_employee(employee_id):
    """Return one employee."""

    query = """
    SELECT *

    FROM employe

    WHERE IDEmploye=%s
    """

    return fetch_one(query, (employee_id,))


def get_employee_info(employee_id):
    """
    Returns employee information required
    for manual attendance.
    """

    query = """
    SELECT

        IDEmploye,
        IDChaineMontage,
        Nom,
        Prenom,
        Matricule

    FROM employe

    WHERE
        IDEmploye=%s
        AND Etat=1
    """

    return fetch_one(query, (employee_id,))


# ==========================================================
# ATTENDANCE
# ==========================================================

def get_attendance(employee_id, target_date):
    """
    Return attendance row for one employee.
    """

    query = """
    SELECT *

    FROM employechaine

    WHERE
        IDEmploye=%s
        AND DATE(Date)=%s

    LIMIT 1
    """

    return fetch_one(
        query,
        (
            employee_id,
            target_date
        )
    )


# ==========================================================
# SHIFTS
# ==========================================================

def get_shift_schedule(target_date):

    query = """
    SELECT

        IDTpsTravail,
        IDPosteTravail,
        H1,
        H2,
        H3,
        H4

    FROM tpstravail

    WHERE

        DateDebut <= %s
        AND DateFin >= %s

    ORDER BY IDPosteTravail
    """

    conn = get_connection()

    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        query,
        (
            target_date,
            target_date
        )
    )

    rows = cursor.fetchall()

    cursor.close()

    conn.close()

    return rows


# ==========================================================
# INSERT / UPDATE
# ==========================================================

def insert_attendance(values):
    """
    Insert manual attendance.
    """

    query = """
    INSERT INTO employechaine
    (

        IDEmploye,

        Date,

        IDPosteTravail,

        IDChaineMontage,

        Affecter_Le,

        Etat,

        CreateTime,

        LastChange,

        SaisieLe,

        Saisipar

    )

    VALUES
    (

        %s,
        %s,
        %s,
        %s,
        %s,

        1,

        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,

        CURRENT_TIMESTAMP,

        %s

    )
    """

    return execute(query, values)


def update_present(values):
    """
    Existing employee becomes Present.
    """

    query = """
    UPDATE employechaine

    SET

        Etat=1,

        IDPosteTravail=%s,

        IDChaineMontage=%s,

        Affecter_Le=%s,

        LastChange=CURRENT_TIMESTAMP,

        ModifieLe=CURRENT_TIMESTAMP,

        ModifiePar=%s

    WHERE IDEmployeChaine=%s
    """

    return execute(query, values)


def update_absent(values):
    """
    Existing employee becomes Absent.
    """

    query = """
    UPDATE employechaine

    SET

        Etat=0,

        LastChange=CURRENT_TIMESTAMP,

        ModifieLe=CURRENT_TIMESTAMP,

        ModifiePar=%s

    WHERE
        IDEmploye=%s
        AND DATE(Date)=%s
    """

    return execute(query, values)