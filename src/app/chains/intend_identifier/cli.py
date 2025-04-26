"""
Command Line Interface for the Intent Identification System.

This module provides an interactive CLI for testing and demonstrating
the intent identification capabilities. It allows users to:
- Have a conversation with the system
- See real-time intent classification
- Test different types of queries
"""

from langchain_core.messages import HumanMessage
from .chain import IntendIdentifierChain
from .models import RouterOptions

def main():
    """
    Main entry point for the CLI application.
    
    The function:
    1. Initializes the intent identifier
    2. Maintains conversation state
    3. Processes user input
    4. Displays intent classification results
    
    The conversation continues until:
    - User types 'exit', 'quit', or 'bye'
    - System identifies an END intent
    """
    # Initialize the intent identifier
    intent_identifier = IntendIdentifierChain()
    
    # Initialize state
    messages = []
    
    print("Chatbot: Hello! How can I help you today?")
    
    while True:
        # Get user input
        user_input = input("You: ")
        
        if user_input.lower() in ["exit", "quit", "bye"]:
            print("Chatbot: Goodbye!")
            break
        
        # Add user message to state
        messages.append(HumanMessage(content=user_input))
        
        # Identify intent
        intent = intent_identifier.identify_intent(messages)
        
        # Process based on intent
        if intent == RouterOptions.END.value:
            print("Chatbot: Goodbye!")
            break
        else:
            # Here you would typically route to the appropriate agent
            # For now, we'll just print the intent
            print(f"Chatbot: I've identified this as a {intent} query.")

if __name__ == "__main__":
    main() 