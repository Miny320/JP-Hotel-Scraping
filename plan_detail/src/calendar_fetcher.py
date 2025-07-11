from datetime import datetime
from .utils import infinite_retry_post

def fetch_room_and_calendar(args):
    (accommodation_id, plan_id, plan_name, meal_code, breakfast, lunch, dinner,
     room_edge, now_date, limit_date, adult_count) = args

    node = room_edge.get('node', {})
    room = node.get('room', {})
    room_id = room.get("roomId")
    if not room_id:
        print("          Skipping room with missing roomId")
        return None

    plan_obj = {
        "plan_id": plan_id,
        "room_code": room_id,
        "checked_adult_count": adult_count,
        "plan_name": plan_name,
        "room_name": room.get("name"),
        "breakfast": breakfast,
        "lunch": lunch,
        "dinner": dinner,
        "url": f"https://www.ikyu.com/{accommodation_id}/?accommodation_types=HOTEL,INN,BUSINESS,RESORT_HOTEL&adc=1&lc=1&pln={plan_id}&ppc=2&rc=1&rm={room_id}&si=1&st=1&top=plans",
        "prices": []
    }

    # Fetch calendar
    payload_calendar = {
        "query": """
        query Search($accommodationId: AccommodationIdScalar!, $roomId: RoomIdScalar!, $planId: PlanIdScalar!, $input: RoomPlanCalendarInput!, $currency: Currency!) {
          accommodation(accommodationId: $accommodationId) {
            roomPlan(
              roomId: $roomId
              planId: $planId
            ) {
              calendar(input: $input) {
                date
                discountAmount(currency: $currency)
              }
            }
          }
        }
        """,
        "variables": {
            "accommodationId": accommodation_id,
            "roomId": room_id,
            "planId": plan_id,
            "input": {
                "lodgingCount": 1,
                "peopleCount": adult_count,
                "roomCount": 1,
                "searchType": "1",
                "discount": True,
                "startDate": now_date.strftime("%Y-%m-%d"),
                "endDate": limit_date.strftime("%Y-%m-%d"),
                "preview": False
            },
            "currency": "JPY"
        },
        "operationName": "Search"
    }
    try:
        calendar_data = infinite_retry_post(payload_calendar).json()
        calendar = calendar_data.get('data', {}).get('accommodation', {}).get('roomPlan', {}).get('calendar', []) or []
        for entry in calendar:
            entry_date = datetime.strptime(entry.get("date"), "%Y-%m-%d").date()
            discount_amount = entry.get("discountAmount")
            if now_date <= entry_date < limit_date and discount_amount is not None and discount_amount != 0:
                plan_obj["prices"].append({
                    "date": entry.get("date"),
                    "price": discount_amount
                })
    except Exception as e:
        print(f"          Error extracting prices for room {room_id}: {e}")

    return plan_obj 