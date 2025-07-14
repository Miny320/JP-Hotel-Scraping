from common.utils import infinite_retry_post

def meal_code_to_flags(meal_code):
    mapping = {
        "000": (False, False, False),
        "001": (True,  False, False),
        "002": (False, False, True),
        "003": (True,  False, True),
        "004": (True,  True,  False),
        "005": (False, True,  False),
        "006": (True,  True,  True),
        "007": (False, True,  True),
    }
    return mapping.get(meal_code, (False, False, False))

def fetch_plans(accommodation_id, adult_count):
    all_plan_edges = []
    plans_first = 10
    plans_offset = 0
    while True:
        payload_plans = {
            "query": """
            query PlansAndRooms($accommodationId: AccommodationIdScalar!, $plansInput: SearchPlansInput! = {}, $plansFirst: Int!, $plansOffset: Int!) {
              accommodation(accommodationId: $accommodationId) {
                searchPlans2(input: $plansInput, first: $plansFirst, offset: $plansOffset) {
                  plans {
                    edges {
                      node {
                        planId
                        name
                        meal { code }
                      }
                    }
                    pageInfo {
                      hasNextPage
                    }
                  }
                }
              }
            }
            """,
            "variables": {
                "accommodationId": accommodation_id,
                "plansInput": {
                    "discount": True,
                    "lodgingCount": 1,
                    "peopleCount": adult_count,
                    "roomCount": 1,
                    "searchType": "1",
                    "sortItem": "1",
                    "sortOrder": "1",
                    "currency": "JPY",
                    "preferBookable": True
                },
                "plansFirst": plans_first,
                "plansOffset": plans_offset
            },
            "operationName": "PlansAndRooms"
        }
        response_plans = infinite_retry_post(payload_plans)
        plans_data = response_plans.json()
        plan_edges = plans_data.get('data', {}).get('accommodation', {}).get('searchPlans2', {}).get('plans', {}).get('edges', [])
        all_plan_edges.extend(plan_edges)
        page_info = plans_data.get('data', {}).get('accommodation', {}).get('searchPlans2', {}).get('plans', {}).get('pageInfo', {})
        has_next_page = page_info.get('hasNextPage', False)
        if not has_next_page or len(plan_edges) == 0:
            break
        plans_offset += plans_first
    return all_plan_edges 