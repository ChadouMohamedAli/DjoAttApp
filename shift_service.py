from datetime import datetime, time, timedelta
from database import get_shift_schedule


# ==========================================================
# TIME UTILITIES
# ==========================================================
def _to_time(value):
    """
    Convert MySQL values to datetime.time.

    Supported:
        - datetime.time
        - datetime.datetime
        - datetime.timedelta   <-- MySQL TIME
        - HH:MM
        - HH:MM:SS
    """

    if value is None:
        return None

    if isinstance(value, time):
        return value

    if isinstance(value, datetime):
        return value.time()

    # MySQL TIME is returned as timedelta
    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())

        hours = (total_seconds // 3600) % 24
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        return time(hours, minutes, seconds)

    if isinstance(value, str):

        try:
            return datetime.strptime(value, "%H:%M:%S").time()
        except ValueError:
            return datetime.strptime(value, "%H:%M").time()

    raise TypeError(f"Unsupported time type: {type(value)}")


# ==========================================================
# SHIFT LOGIC
# ==========================================================

def get_shift_from_datetime(target_date, current_time=None):
    """
    Determine the shift (IDPosteTravail)
    for the selected date and current time.

    Parameters
    ----------
    target_date : date
        Date selected in Streamlit.

    current_time : datetime.time
        Defaults to current system time.

    Returns
    -------
    dict

    Example:

    {
        "IDPosteTravail": 2,
        "H1": time(14,0),
        "H4": time(22,0)
    }

    Returns None if no shift matches.
    """

    if current_time is None:
        current_time = datetime.now().time()

    current_time = _to_time(current_time)

    current_minutes = _minutes(current_time)

    shifts = get_shift_schedule(target_date)

    if not shifts:
        return None

    for shift in shifts:

        start = _to_time(shift["H1"])
        end = _to_time(shift["H4"])

        start_minutes = _minutes(start)
        end_minutes = _minutes(end)

        # --------------------------------------------------
        # Normal shift
        # Example:
        # 06:00 -> 14:00
        # --------------------------------------------------

        if start_minutes < end_minutes:

            if start_minutes <= current_minutes < end_minutes:

                return {
                    "IDPosteTravail": int(shift["IDPosteTravail"]),
                    "H1": start,
                    "H4": end
                }

        # --------------------------------------------------
        # Overnight shift
        # Example:
        # 22:00 -> 06:00
        # --------------------------------------------------

        else:

            if (
                current_minutes >= start_minutes
                or current_minutes < end_minutes
            ):

                return {
                    "IDPosteTravail": int(shift["IDPosteTravail"]),
                    "H1": start,
                    "H4": end
                }

    print("Target Date:", target_date)
    shifts = get_shift_schedule(target_date)
    print("****", shifts)
    return None


# ==========================================================
# SIMPLE HELPER
# ==========================================================

def get_shift_id(target_date, current_time=None):
    """
    Returns only IDPosteTravail.

    Example:

    shift_id = get_shift_id(date.today())
    """

    shift = get_shift_from_datetime(
        target_date,
        current_time
    )

    if shift is None:
        return None

    return shift["IDPosteTravail"]


# ==========================================================
# DEBUG
# ==========================================================

if __name__ == "__main__":

    from datetime import date

    today = date.today()

    tests = [

        "07:30",
        "13:59",
        "14:15",
        "18:00",
        "22:30",
        "02:15",
        "05:45"

    ]

    for t in tests:

        result = get_shift_from_datetime(today, t)

        print(f"{t} -> {result}")