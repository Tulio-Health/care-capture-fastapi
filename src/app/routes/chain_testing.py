import requests
import json
import time

def run_past_visits_tests():
    TEST_CASES = [
        {"userQuery": "Tell me about the visits with Dr David Levy I've had.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "What appointments have I had with David?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Show me all my visits with Dr. Levy.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Did I see Dave for any check-ups?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "List my appointments with the emergency medicine doctor.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Which visits did I have with Dr. David Levy in 2025?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Tell me about the visits with Dr David Levy I've had. Only the ones that I had on Spring", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Did I see Dr. Levy in March 2025?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Show me my appointments with Dr. Levy at Main Clinic.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "When did I have a routine check-up with Dr. David Levy?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Which scheduled appointments do I have with Dr. Levy?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Do I have any upcoming visits with Dr. David Levy?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "What past appointments have I had with Dr. Levy?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Did I see Dr. David Levy on May 12, 2025?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "List all my appointments with Dr. Levy in 2024 and 2025.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Show me all my annual physicals with Dr. David Levy.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Did I have any morning appointments with Dr. Levy?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Did I ever miss an appointment with Dr. David Levy?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "When did I see Dr. Levy at Cardiology Dept?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Show me my visits with the ER doctor.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "When did Dr. Levy see me for a follow-up?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "List all scheduled annual physicals with Dr. David Levy in 2025.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Did I see Dr. Levy in 2023?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Show me my appointments with Dr. Levy at Downtown Clinic.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Any visits with doctor lev?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        # New test cases for Jeffrey Schwartz
        {"userQuery": "Tell me about my visits with Jeffrey Schwartz.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "What appointments have I had with Dr. Schwartz?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Show me my visits with Jeffrey.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Did I see Dr. Schwartz for any consultations?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "List my appointments with the general surgery doctor.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Which visits did I have with Jeffrey Schwartz in 2025?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Did I see Jeffrey in November 2024?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
    ]
    ENDPOINT = "http://localhost:3000/chatbot-messages"
    responses = []
    for idx, test in enumerate(TEST_CASES, 1):
        print(f"\n[Past Visits Test {idx}] {test['userQuery']}")
        response = requests.post(ENDPOINT, json=test)
        print(f"Response: {response.status_code}")
        try:
            resp_json = response.json()
            print(json.dumps(resp_json, indent=2))
            responses.append({"test": test, "response": resp_json})
        except Exception:
            print(response.text)
            responses.append({"test": test, "response": response.text})
        time.sleep(5)  
    print("\n--- SUMMARY OF ALL RESPONSES ---")
    for idx, item in enumerate(responses, 1):
        print(f"\n[Past Visits Test {idx}] {item['test']['userQuery']}")
        print(json.dumps(item['response'], indent=2) if isinstance(item['response'], dict) else item['response'])

def run_medical_inquiry_tests():
    # Placeholder for future medical inquiry chain tests
    print("[Medical Inquiry Tests] Not implemented yet.")

def run_upcoming_visits_tests():
    # Placeholder for future upcoming visits chain tests
    print("[Upcoming Visits Tests] Not implemented yet.")

if __name__ == "__main__":
    print("Select which chain tests to run:")
    print("1. Past Visits")
    print("2. Medical Inquiry (future)")
    print("3. Upcoming Visits (future)")
    choice = input("Enter number (default 1): ").strip() or "1"
    if choice == "1":
        run_past_visits_tests()
    elif choice == "2":
        run_medical_inquiry_tests()
    elif choice == "3":
        run_upcoming_visits_tests()
    else:
        print("Invalid choice.")
