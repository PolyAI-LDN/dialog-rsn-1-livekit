"""The Grand Meridian Hotel front desk: instructions and demo bookings.

Everything is in memory and fictional. Changes last until the process exits.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

INSTRUCTIONS = """\
You are the virtual front-desk assistant for the Grand Meridian Hotel, a 420-room city hotel.
You are speaking with a guest over the phone. This is a demo system running on fictional data.

What you can do:
- Look up a reservation by confirmation code (GM followed by 5 digits, for example GM40912)
  or by the guest's last name.
- Change the checkout time of a reservation. The lookup gives each reservation's
  late_checkout_fee_gbp, which applies to any later checkout up to 16:00. Later than 16:00
  always costs 25 GBP. An earlier checkout is free. State the fee before making the change.

You cannot take new bookings, cancel, change room types, take payments, or handle billing.
For those, offer to put the guest through to a colleague at the front desk.

How to behave:
- Be warm, brief and natural. One or two sentences per turn. No lists, no markdown, no emoji.
- Identify the reservation before changing anything. If a last name matches more than one
  booking, ask for the arrival date or first name rather than guessing.
- Before you change a checkout time, say exactly what you are about to do and get an
  explicit yes.
- Never invent reservations, prices, room numbers or policies. If a lookup finds nothing, say
  so and offer the other way of searching.
"""

# check_in and check_out are days from today, turned into dates at each lookup, so the
# bookings stay upcoming however long the agent runs.
RESERVATIONS = {
    "GM40912": {"guest_name": "Amara Okafor", "last_name": "Okafor", "room_type": "Deluxe King",
                "check_in": 3, "check_out": 6, "checkout_time": "11:00",
                "member": True, "status": "confirmed"},
    "GM41055": {"guest_name": "Tom Reid", "last_name": "Reid", "room_type": "Standard Twin",
                "check_in": 0, "check_out": 1, "checkout_time": "11:00",
                "member": False, "status": "confirmed"},
    "GM41182": {"guest_name": "Priya Reid", "last_name": "Reid", "room_type": "Meridian Suite",
                "check_in": 4, "check_out": 9, "checkout_time": "12:00",
                "member": True, "status": "confirmed"},
}

LATE_CHECKOUT_FEE_GBP = 25
FREE_LATE_CHECKOUT_UNTIL = "16:00"
LATEST_CHECKOUT = "18:00"


def look_up_reservation(confirmation_code: str = "", last_name: str = "") -> dict:
    if confirmation_code:
        code = confirmation_code.strip().upper()
        matches = [(code, RESERVATIONS[code])] if code in RESERVATIONS else []
    elif last_name:
        matches = [(code, r) for code, r in RESERVATIONS.items()
                   if r["last_name"].lower() == last_name.strip().lower()]
    else:
        return {"error": "Provide either a confirmation code or a last name."}
    return {"found": len(matches),
            "reservations": [{"confirmation_code": code, **r,
                              "check_in": _day(r["check_in"]), "check_out": _day(r["check_out"]),
                              "late_checkout_fee_gbp": _late_checkout_fee(r)}
                             for code, r in matches]}


def _day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def _late_checkout_fee(reservation: dict) -> int:
    """The fee for a checkout later than usual, up to FREE_LATE_CHECKOUT_UNTIL."""
    free = reservation["member"] or "Suite" in reservation["room_type"]
    return 0 if free else LATE_CHECKOUT_FEE_GBP


def change_checkout_time(confirmation_code: str, new_checkout_time: str) -> dict:
    code = confirmation_code.strip().upper()
    reservation = RESERVATIONS.get(code)
    if not reservation:
        return {"error": f"No reservation found for {code}."}
    try:
        # Normalises "9:30" to "09:30", so the string comparisons below hold.
        new_checkout_time = datetime.strptime(new_checkout_time.strip(), "%H:%M").strftime("%H:%M")
    except ValueError:
        return {"error": "Give the new checkout time as 24-hour HH:MM, for example 14:00."}
    if new_checkout_time > LATEST_CHECKOUT:
        return {"error": f"The latest checkout we can offer is {LATEST_CHECKOUT}."}
    if new_checkout_time <= reservation["checkout_time"]:
        fee = 0
    elif new_checkout_time <= FREE_LATE_CHECKOUT_UNTIL:
        fee = _late_checkout_fee(reservation)
    else:
        fee = LATE_CHECKOUT_FEE_GBP
    previous, reservation["checkout_time"] = reservation["checkout_time"], new_checkout_time
    return {"status": "updated", "confirmation_code": code, "previous_checkout_time": previous,
            "new_checkout_time": new_checkout_time, "fee_gbp": fee}
