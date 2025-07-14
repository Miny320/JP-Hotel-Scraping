from datetime import datetime
from common.utils import infinite_retry_post

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

# Batch fetch calendar/price info for multiple (plan_id, room_id) pairs
# room_plan_args: list of tuples (plan_id, room_id, room_name, plan_name, meal_code, breakfast, lunch, dinner, adult_count)
def fetch_calendars_batch(accommodation_id, room_plan_args, now_date, limit_date):
    if not room_plan_args:
        print(f"          No room-plan pairs to fetch calendars for")
        return {}
    
    print(f"          Fetching calendars for {len(room_plan_args)} room-plan pairs...")
    
    # Limit batch size to prevent very large queries
    BATCH_SIZE_LIMIT = 100
    all_results = {}
    
    # Split into smaller batches if needed
    for i in range(0, len(room_plan_args), BATCH_SIZE_LIMIT):
        batch_args = room_plan_args[i:i + BATCH_SIZE_LIMIT]
        print(f"          Processing batch {i//BATCH_SIZE_LIMIT + 1}/{(len(room_plan_args) + BATCH_SIZE_LIMIT - 1)//BATCH_SIZE_LIMIT} ({len(batch_args)} pairs)")
        
        batch_results = _fetch_calendars_batch_single(accommodation_id, batch_args, now_date, limit_date)
        all_results.update(batch_results)
    
    print(f"          Successfully fetched calendars for {len(all_results)} room-plan pairs")
    return all_results

def _fetch_calendars_batch_single(accommodation_id, room_plan_args, now_date, limit_date):
    """Helper function to fetch calendars for a single batch"""
    query_aliases = []
    variables = {
        "accommodationId": accommodation_id,
        "currency": "JPY"
    }
    # Build aliases and variables for each pair
    for idx, (plan_id, room_id, room_name, plan_name, meal_code, breakfast, lunch, dinner, adult_count) in enumerate(room_plan_args):
        alias = f"cal{idx}"
        query_aliases.append(f'''
      {alias}: roomPlan(roomId: \"{room_id}\", planId: \"{plan_id}\") {{
        calendar(input: {{
          lodgingCount: 1,
          peopleCount: {adult_count},
          roomCount: 1,
          searchType: \"1\",
          discount: true,
          startDate: \"{now_date.strftime('%Y-%m-%d')}\",
          endDate: \"{limit_date.strftime('%Y-%m-%d')}\",
          preview: false
        }}) {{
          date
          discountAmount(currency: $currency)
        }}
      }}''')
    query_body = "\n".join(query_aliases)
    query = f'''
    query BatchedCalendars($accommodationId: AccommodationIdScalar!, $currency: Currency!) {{
      accommodation(accommodationId: $accommodationId) {{
        {query_body}
      }}
    }}
    '''
    payload = {
        "query": query,
        "variables": variables,
        "operationName": "BatchedCalendars"
    }
    
    try:
        response = infinite_retry_post(payload)
        response_json = response.json()
        
        # Check if response is valid
        if not response_json or 'data' not in response_json:
            print(f"          Invalid response structure: {response_json}")
            raise Exception("Invalid response structure")
        
        data = response_json.get('data', {})
        if not data or 'accommodation' not in data:
            print(f"          No accommodation data in response: {data}")
            raise Exception("No accommodation data in response")
        
        accommodation_data = data.get('accommodation', {})
        if not accommodation_data:
            print(f"          Empty accommodation data")
            raise Exception("Empty accommodation data")
        
        # Map (plan_id, room_id) to calendar/prices
        result = {}
        for idx, (plan_id, room_id, room_name, plan_name, meal_code, breakfast, lunch, dinner, adult_count) in enumerate(room_plan_args):
            alias = f"cal{idx}"
            plan_obj = {
                "plan_id": plan_id,
                "room_code": room_id,
                "checked_adult_count": adult_count,
                "plan_name": plan_name,
                "room_name": room_name,
                "breakfast": breakfast,
                "lunch": lunch,
                "dinner": dinner,
                "prices": []
            }
            
            # Get calendar data for this alias, with proper null checks
            cal_data = accommodation_data.get(alias)
            if cal_data is None:
                print(f"\n========== DEBUG: No calendar data for alias {alias} (plan {plan_id}, room {room_id}) ==========")
                # Print the full response for this alias, limited to 1000 chars
                resp_str = str(accommodation_data)
                print(f"          Full response for alias {alias} (truncated): {resp_str[:1000]}{' ...' if len(resp_str) > 1000 else ''}")
                print("========== END DEBUG ==========")
                result[(plan_id, room_id)] = plan_obj
                continue

            calendar = cal_data.get('calendar', []) or []
            if not calendar:
                print(f"\n========== DEBUG: Empty calendar for plan {plan_id}, room {room_id} ==========")
                # Print the full cal_data for this alias, limited to 1000 chars
                cal_str = str(cal_data)
                print(f"          cal_data for alias {alias} (truncated): {cal_str[:1000]}{' ...' if len(cal_str) > 1000 else ''}")
                print("========== END DEBUG ==========")
                result[(plan_id, room_id)] = plan_obj
                continue
            
            for entry in calendar:
                try:
                    entry_date = datetime.strptime(entry.get("date"), "%Y-%m-%d").date()
                    discount_amount = entry.get("discountAmount")
                    if now_date <= entry_date < limit_date and discount_amount is not None and discount_amount != 0:
                        plan_obj["prices"].append({
                            "date": entry.get("date"),
                            "price": discount_amount
                        })
                except Exception as entry_error:
                    print(f"          Error processing calendar entry for plan {plan_id}, room {room_id}: {entry_error}")
                    continue
            
            result[(plan_id, room_id)] = plan_obj
        
        return result
        
    except Exception as e:
        print(f"          Error in batch calendar fetch: {e}")
        # Fallback to individual requests if batch fails
        print(f"          Falling back to individual calendar requests...")
        result = {}
        for plan_id, room_id, room_name, plan_name, meal_code, breakfast, lunch, dinner, adult_count in room_plan_args:
            try:
                # Create a mock room_edge for the individual function
                room_edge = {
                    'node': {
                        'room': {
                            'roomId': room_id,
                            'name': room_name
                        }
                    }
                }
                args = (accommodation_id, plan_id, plan_name, meal_code, breakfast, lunch, dinner,
                       room_edge, now_date, limit_date, adult_count)
                plan_obj = fetch_room_and_calendar(args)
                if plan_obj:
                    result[(plan_id, room_id)] = plan_obj
                else:
                    # Create empty plan_obj if fetch_room_and_calendar returns None
                    result[(plan_id, room_id)] = {
                        "plan_id": plan_id,
                        "room_code": room_id,
                        "checked_adult_count": adult_count,
                        "plan_name": plan_name,
                        "room_name": room_name,
                        "breakfast": breakfast,
                        "lunch": lunch,
                        "dinner": dinner,
                        "prices": []
                    }
            except Exception as inner_e:
                print(f"          Error fetching calendar for plan {plan_id}, room {room_id}: {inner_e}")
                # Create empty plan_obj on error
                result[(plan_id, room_id)] = {
                    "plan_id": plan_id,
                    "room_code": room_id,
                    "checked_adult_count": adult_count,
                    "plan_name": plan_name,
                    "room_name": room_name,
                    "breakfast": breakfast,
                    "lunch": lunch,
                    "dinner": dinner,
                    "prices": []
                }
        return result 