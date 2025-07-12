from .utils import infinite_retry_post

# New function to batch fetch rooms for multiple plans using GraphQL aliases
def fetch_rooms_batch(accommodation_id, plan_ids, adult_count):
    if not plan_ids:
        print(f"          No plan IDs to fetch rooms for")
        return {}
    
    print(f"          Fetching rooms for {len(plan_ids)} plans...")
    
    # Build the query string with aliases for each plan
    query_aliases = []
    for idx, plan_id in enumerate(plan_ids):
        alias = f"plan{idx}"
        query_aliases.append(f'''
      {alias}: plan(planId: \"{plan_id}\") {{
        amounts(input: $planAmountsInput, first: $first, offset: $offset) {{
          edges {{
            node {{
              room {{
                roomId
                name
              }}
            }}
          }}
        }}
      }}''')
    query_body = "\n".join(query_aliases)
    query = f'''
    query PlanListBatch($accommodationId: AccommodationIdScalar!, $planAmountsInput: PlanAmountInput! = {{sortItem: \"1\", sortOrder: \"1\"}}, $first: Int! = 99, $offset: Int! = 0) {{
      accommodation(accommodationId: $accommodationId) {{
        {query_body}
      }}
    }}
    '''
    payload = {
        "query": query,
        "variables": {
            "accommodationId": accommodation_id,
            "planAmountsInput": {
                "discount": True,
                "lodgingCount": 1,
                "peopleCount": adult_count,
                "roomCount": 1,
                "searchType": "1",
                "sortItem": "1",
                "sortOrder": "1",
                "currency": "JPY"
            },
            "first": 99,
            "offset": 0
        },
        "operationName": "PlanListBatch"
    }
    
    try:
        response = infinite_retry_post(payload)
        data = response.json().get('data', {}).get('accommodation', {})
        
        # Map plan_id to its room edges
        plan_rooms = {}
        total_rooms = 0
        for idx, plan_id in enumerate(plan_ids):
            alias = f"plan{idx}"
            plan_data = data.get(alias, {})
            room_edges = plan_data.get('amounts', {}).get('edges', [])
            plan_rooms[plan_id] = room_edges
            total_rooms += len(room_edges)
        
        print(f"          Successfully fetched {total_rooms} rooms across {len(plan_ids)} plans")
        return plan_rooms
        
    except Exception as e:
        print(f"          Error in batch room fetch: {e}")
        # Fallback to individual requests if batch fails
        print(f"          Falling back to individual room requests...")
        plan_rooms = {}
        for plan_id in plan_ids:
            try:
                # Simple individual request as fallback
                individual_payload = {
                    "query": """
                    query PlanList($accommodationId: AccommodationIdScalar!, $planId: PlanIdScalar!, $planAmountsInput: PlanAmountInput! = {sortItem: \"1\", sortOrder: \"1\"}, $first: Int! = 99, $offset: Int! = 0) {
                      accommodation(accommodationId: $accommodationId) {
                        plan(planId: $planId) {
                          amounts(input: $planAmountsInput, first: $first, offset: $offset) {
                            edges {
                              node {
                                room {
                                  roomId
                                  name
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                    """,
                    "variables": {
                        "accommodationId": accommodation_id,
                        "planId": plan_id,
                        "planAmountsInput": {
                            "discount": True,
                            "lodgingCount": 1,
                            "peopleCount": adult_count,
                            "roomCount": 1,
                            "searchType": "1",
                            "sortItem": "1",
                            "sortOrder": "1",
                            "currency": "JPY"
                        },
                        "first": 99,
                        "offset": 0
                    },
                    "operationName": "PlanList"
                }
                response = infinite_retry_post(individual_payload)
                roomlist_data = response.json()
                room_edges = roomlist_data.get('data', {}).get('accommodation', {}).get('plan', {}).get('amounts', {}).get('edges', [])
                plan_rooms[plan_id] = room_edges
            except Exception as inner_e:
                print(f"          Error fetching rooms for plan {plan_id}: {inner_e}")
                plan_rooms[plan_id] = []
        return plan_rooms 