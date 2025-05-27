import requests
import json
import time
import os
from datetime import datetime

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
        {"userQuery": "Do I have any upcoming visits with Dr. David Levy?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "What past appointments have I had with Dr. Levy?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Did I see Levy on May 12, 2025?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "List all my appointments with my cardiologist in 2024 and 2025.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Show me all my annual physicals with Dr. David Levy.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Did I have any morning appointments with Dr. Levy?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Did I ever miss an appointment with Dr. David Levy?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "When did I see Dr. Levy at Cardiology Dept?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Show me my visits with the ER doctor.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "When did Dr. Levy see me for a follow-up?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "List all scheduled annual physicals with Dr. David Levy in 2025.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Show me my appointments with Dr. Levy at Downtown Clinic.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Any visits with  lev?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        # # New test cases for Jeffrey Schwartz
        {"userQuery": "Tell me about my visits with Jeffrey Schwartz.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "What appointments have I had with Schwartz in autumn and winter 2024?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Show me my visits with Jef. in November 2024?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Have I seen Dr. Schwartz for any consultations?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "List my appointments with the general surgery doctor.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "List my appointments with the surgeon in 2024 and 2025.", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Which visits did I have with Dr. J.S. in 2024?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Did I see Jeffry in late 2024?", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
    ]
    ENDPOINT = "http://localhost:3000/chatbot-messages"
    
    # Prepare data structure for JSON output
    test_results = []
    
    for idx, test in enumerate(TEST_CASES, 1):
        try:
            print(f"\n[Past Visits Test {idx}] {test['userQuery']}")
            response = requests.post(ENDPOINT, json=test)
            print(f"Response: {response.status_code}")
            
            resp_json = response.json()
            
            # Extract AI responses
            ai_responses = []
            if 'data' in resp_json and 'aiResponses' in resp_json['data']:
                for ai_response in resp_json['data']['aiResponses']:
                    ai_responses.append(ai_response['content'])
            
            # Store test result with query and AI responses
            test_result = {
                "test_number": idx,
                "query": test['userQuery'],
                "user_id": test['userId'],
                "ai_responses": ai_responses,
                "full_response": resp_json
            }
            print("Test result: ", test_result['ai_responses'])
            test_results.append(test_result)
            
        except Exception as e:
            print(f"Error processing response: {e}")
            test_result = {
                "test_number": idx,
                "query": test['userQuery'],
                "user_id": test['userId'],
                "ai_responses": [],
                "error": str(e),
                "raw_response": response.text
            }
            test_results.append(test_result)
        

    # Save results to JSON file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"past_visits_test_results_{timestamp}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(test_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n--- TEST RESULTS SAVED TO {filename} ---")
    print(f"Total tests run: {len(test_results)}")
    print(f"Successful responses: {len([r for r in test_results if 'error' not in r])}")
    print(f"Errors: {len([r for r in test_results if 'error' in r])}")


def run_health_insights_tests():
    # ------------------------------------------------------------
    # Health-Insights intent tests
    # NOTE: user_id = "0ca4bb1b-6233-48fd-9998-99f556cdc22a"
    # ------------------------------------------------------------
    HEALTH_INSIGHTS_TEST_CASES = [
        # --- general symptom / condition summaries ---
        {"userQuery": "Summarize all the health issues I'm dealing with.", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "What record is there about my knee being bad? What have I been told to do about it?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Remind me which of my problems are acute versus chronic.", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Do I have anything besides that fever noted?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},

        # --- fever phrasing variants ---
        {"userQuery": "Am I still running a temperature?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "How long have I been febrile?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Do the notes mention pyrexia in October?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},

        # --- knee-related (catch synonyms & body part) ---
        {"userQuery": "Any record of patellar inflammation?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "What's going on with my joints lately?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},

        # --- medication look-ups & misspellings ---
        {"userQuery": "Which meds am I on for the fever?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Am I supposed to keep taking Panadols?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},  # plural / casing variant
        {"userQuery": "List my anti-inflammatory drugs.", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Any note of ibuprophen dosage?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},  # misspelling

        # --- time-bounded queries ---
        {"userQuery": "Show my recorded symptoms for Winter 2024-25.", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Is there any log of fever on 25 October 2023?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Any knee flare-ups noted this spring?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},

        # --- negative / absence checks ---
        {"userQuery": "Do I have any recorded allergies?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Have I had any lab tests yet?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},  # priorTesting is empty
        {"userQuery": "What surgeries have I undergone?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},  # surgeriesAndProcedures empty

        # --- vague / conversational ---
        {"userQuery": "Give me the quick rundown of my current health status.", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},

        # --- stress test with pronouns & ellipsis ---
        {"userQuery": "…and what about that thing with my knee again?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Okay, besides fever, what else do I have?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
    
        {"userQuery": "What does my chart say about that knee swelling last month?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Could you recap any musculoskeletal issues on file?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},

        # medication regimen & dosage subtleties
        {"userQuery": "Remind me what medication regimen I'm currently following.", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Do the notes mention my fever breaking after Panadol?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Am I on any OTC anti-pyretics besides Panadol?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Is ibuprofen listed as 'take when needed' or on a schedule?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Do my records show how many milligrams of ibu I should take each time?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},

        # condition classification & missing data checks
        {"userQuery": "Was the knee inflammation marked acute or chronic in my records?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Do I have any imaging results or tests ordered for my knee?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},

        # fever symptom details
        {"userQuery": "When did I last record a normal temperature?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Does it indicate if I've had chills along with the fever?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},

        # combined-symptom exploration
        {"userQuery": "Show any notes that link my joint pain and fever together.", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Any mention of swelling in my other joints?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},

        # activity clearance & chronology
        {"userQuery": "Am I cleared for light exercise with this knee issue?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Which started first according to my notes, the fever or knee pain?", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
    ]
    
    ENDPOINT = "http://localhost:3000/chatbot-messages"
    
    # Prepare data structure for JSON output
    test_results = []
    
    for idx, test in enumerate(HEALTH_INSIGHTS_TEST_CASES, 1):
        try:
            print(f"\n[Health Insights Test {idx}] {test['userQuery']}")
            response = requests.post(ENDPOINT, json=test)
            print(f"Response: {response.status_code}")
        
            resp_json = response.json()
            
            # Extract AI responses
            ai_responses = []
            if 'data' in resp_json and 'aiResponses' in resp_json['data']:
                for ai_response in resp_json['data']['aiResponses']:
                    ai_responses.append(ai_response['content'])
            
            # Extract the intent that was identified
            identified_intent = "unknown"
            if 'data' in resp_json and 'detectedIntent' in resp_json['data']:
                identified_intent = resp_json['data']['detectedIntent']
            
            # Store test result with query and AI responses
            test_result = {
                "test_number": idx,
                "query": test['userQuery'],
                "user_id": test['userId'],
                "ai_responses": ai_responses,
                "full_response": resp_json
            }
            test_results.append(test_result)
            print("Identified intent: ", identified_intent)
            print("AI response: ", test_result['ai_responses'])
            
        except Exception as e:
            print(f"Error processing response: {e}")
            test_result = {
                "test_number": idx,
                "query": test['userQuery'],
                "user_id": test['userId'],
                "ai_responses": [],
                "error": str(e),
                "raw_response": response.text
            }
            test_results.append(test_result)
        

    # Save results to JSON file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"health_insights_test_results_{timestamp}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(test_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n--- TEST RESULTS SAVED TO {filename} ---")
    print(f"Total tests run: {len(test_results)}")
    print(f"Successful responses: {len([r for r in test_results if 'error' not in r])}")
    print(f"Errors: {len([r for r in test_results if 'error' in r])}")

def run_medical_inquiry_tests():
    # Placeholder for future medical inquiry chain tests
    print("[Medical Inquiry Tests] Not implemented yet.")

def run_upcoming_visits_tests():
    # Placeholder for future upcoming visits chain tests
    print("[Upcoming Visits Tests] Not implemented yet.")

def run_intent_regression_tests():
    """
    Regression tests for intent routing fixes based on expert recommendations.
    Tests the specific cases that were failing before the fixes.
    """
    REGRESSION_TEST_CASES = [
        # Medication-focused queries that should be health_insights
        {"userQuery": "Which meds am I on for the fever?", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "List my anti-inflammatory drugs.", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Any note of ibuprophen dosage?", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Am I supposed to keep taking Panadols?", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Which medications am I currently taking for my fever?", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Do I keep taking ibuprofen or switch to something else?", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        
        # Medical terms with typos/synonyms that should still work
        {"userQuery": "Any record of inflammations?", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Do the notes mention anxiety in the year 2024?", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        
        # General medical inquiry (should still work)
        {"userQuery": "What are the side-effects of ibuprofen?", "expected_intent": "not_a_valid_option", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "How do you prevent cancer?", "expected_intent": "not_a_valid_option", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        
        # Personal health questions
        {"userQuery": "How is my health?", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Am I healthy?", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        
        # Past visits
        {"userQuery": "What appointments have I had in 2024?", "expected_intent": "past_visits", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        
        # Upcoming visits
        {"userQuery": "When is my next appointment?", "expected_intent": "upcoming_visits", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        # -- Past / Upcoming visits – Dr. David Levy (userId: 58ae6e54-…) --
        {"userQuery": "Hey, did I ever swing by to see Dr Levy during that freak snow-storm on 14 Feb ’24?", "expected_intent": "past_visits", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Did Dr. David squeeze me in late on New Year’s Eve 2024 for a quick BP check-up?", "expected_intent": "past_visits", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "🤔 Did I ever no-show a 7 a.m. slot with Dr D. Levy?", "expected_intent": "past_visits", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "When exactly is that follow-up with Levy that got bumped twice? It lives somewhere mid-June, right?", "expected_intent": "upcoming_visits", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Got anything in the books with ‘Levee’ next fortnight?", "expected_intent": "upcoming_visits", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Show all my cardio check-ins—but skip anything not at Main Campus.", "expected_intent": "past_visits", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Did Schwartz stitch me up after that skateboard spill last December, or was that someone else?", "expected_intent": "past_visits", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},
        {"userQuery": "Are there *future* appointments tagged “annual review” that clash with public holidays?", "expected_intent": "upcoming_visits", "conversationId": None, "userId": "58ae6e54-c712-4900-bc02-f80a2f2d9e85"},

        {"userQuery": "Remind me what’s up with my “wonky knee” — any legit diagnosis in the notes?", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Can you see if I logged “elevated temps” between the summer and winter solstice last year?", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "List every med I’m supposed to pop at bedtime — typos welcome 😅", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Can you provide details on any C-reactive protein (CRP) labs that were ordered or are pending over the past 18 months?", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Did any note ever flag a “drug fever” even though my temp was normal?", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Check if my left-knee flare-up matched the marathon weekend on 21 Apr 2024.", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "Any mention of me upping ibuprofen to 600 mg tabs instead of 400s?", "expected_intent": "health_insights", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
        {"userQuery": "¿Cuándo fue la última vez que vi al Dr. Levy para un examen físico?", "expected_intent": "past_visits", "conversationId": None, "userId": "0ca4bb1b-6233-48fd-9998-99f556cdc22a"},
    ]
    
    ENDPOINT = "http://localhost:3000/chatbot-messages"
    
    # Prepare data structure for JSON output
    test_results = []
    passed_tests = 0
    failed_tests = 0
    
    print("=== INTENT ROUTING TESTS ===")
    
    for idx, test in enumerate(REGRESSION_TEST_CASES, 1):
        try:
            print(f"\n[Regression Test {idx}] {test['userQuery']}")
            print(f"Expected intent: {test['expected_intent']}")
            
            response = requests.post(ENDPOINT, json=test)
            print(f"Response: {response.status_code}")
        
            resp_json = response.json()
            
            # Extract AI responses like other tests
            ai_responses = []
            if 'data' in resp_json and 'aiResponses' in resp_json['data']:
                for ai_response in resp_json['data']['aiResponses']:
                    ai_responses.append(ai_response['content'])
            
            # Extract the intent that was identified
            identified_intent = "unknown"
            if 'data' in resp_json and 'detectedIntent' in resp_json['data']:
                identified_intent = resp_json['data']['detectedIntent']
            
            # Check if it matches expected
            is_correct = identified_intent == test['expected_intent']
            if is_correct:
                passed_tests += 1
                print(f"✅ PASS - Got: {identified_intent}")
            else:
                failed_tests += 1
                print(f"❌ FAIL - Got: {identified_intent}, Expected: {test['expected_intent']}")
            
            # Store test result with query and AI responses
            test_result = {
                "test_number": idx,
                "query": test['userQuery'],
                "expected_intent": test['expected_intent'],
                "identified_intent": identified_intent,
                "is_correct": is_correct,
                "user_id": test['userId'],
                "ai_responses": ai_responses,
                "full_response": resp_json
            }
            test_results.append(test_result)
            print("AI responses: ", test_result['ai_responses'])
            
        except Exception as e:
            print(f"❌ ERROR processing response: {e}")
            failed_tests += 1
            test_result = {
                "test_number": idx,
                "query": test['userQuery'],
                "expected_intent": test['expected_intent'],
                "identified_intent": "error",
                "is_correct": False,
                "user_id": test['userId'],
                "ai_responses": [],
                "error": str(e),
                "raw_response": response.text
            }
            test_results.append(test_result)
        

    # Save results to JSON file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"intent_regression_test_results_{timestamp}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(test_results, f, indent=2, ensure_ascii=False)
    
    # Print summary with scoring
    total_tests = len(test_results)
    pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    print(f"\n=== INTENT ROUTING TEST SUMMARY ===")
    print(f"Total tests run: {total_tests}")
    print(f"Passed: {passed_tests} ✅")
    print(f"Failed: {failed_tests} ❌")
    print(f"Pass rate: {pass_rate:.1f}%")
    print(f"Results saved to: {filename}")
    
    if pass_rate == 100:
        print("🎉 ALL TESTS PASSED! Intent routing fixes are working correctly.")
    elif pass_rate >= 80:
        print("✅ Good progress! Most intent routing is working correctly.")
    else:
        print("⚠️  Significant issues remain. Check the results file for details.")
    
    return test_results

if __name__ == "__main__":
    print("Select which chain tests to run:")
    print("1. Past Visits")
    print("2. Medical Inquiry (future)")
    print("3. Upcoming Visits (future)")
    print("4. Health Insights")
    print("5. Intent Regression Tests")
    choice = input("Enter number (default 1): ").strip() or "1"
    if choice == "1":
        run_past_visits_tests()
    elif choice == "2":
        run_medical_inquiry_tests()
    elif choice == "3":
        run_upcoming_visits_tests()
    elif choice == "4":
        run_health_insights_tests()
    elif choice == "5":
        run_intent_regression_tests()
    else:
        print("Invalid choice.")
