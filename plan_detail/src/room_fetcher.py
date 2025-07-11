from .utils import infinite_retry_post

def fetch_rooms(accommodation_id, plan_id, adult_count):
    payload_roomlist = {
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
                      capacityMax
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
    response_roomlist = infinite_retry_post(payload_roomlist)
    roomlist_data = response_roomlist.json()
    room_edges = roomlist_data.get('data', {}).get('accommodation', {}).get('plan', {}).get('amounts', {}).get('edges', [])
    return room_edges 