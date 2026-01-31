import logging
import os
import json
from datetime import datetime
from typing import List

from langchain.agents import create_agent
from langchain.messages import SystemMessage, HumanMessage
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver

from app.prompts import SYSTEM_PROMPT

# --- Mock Data & Tools ---

@tool
def search_knowledge_base(query: str):
    """
    Search the hospital knowledge base (Vector DB) for general information.
    Use this for questions about departments, doctors, policies, location, services, etc.
    """
    logging.info(f"Searching KB for: {query}")
    # Mock responses based on keywords
    query_lower = query.lower()
    
    if "cardio" in query_lower or "heart" in query_lower:
        return """
        Department: Cardiology
        Head: Dr. Sarah Johnson
        Services: ECG, Echo, Angioplasty
        Location: Building A, 2nd Floor
        Note: Emergency cardiac services are available 24x7.
        """
    elif "appointment" in query_lower or "booking" in query_lower:
        return """
        To book an appointment, please provide:
        - Department or Doctor name
        - Preferred Date
        - Patient Name and Phone (if not provided)
        
        We prioritize emergency cases. For emergencies, visit the ER immediately.
        """
    elif "insurance" in query_lower or "bill" in query_lower:
        return "We accept all major insurance providers including BlueCross, Aetna, and Cigna. Billing desk is open 9 AM - 5 PM."
    else:
        return "Green Valley Multi-Specialty Hospital is located at 123 Health Ave. We are open 24x7. Main reception: +1-555-0199."

@tool
def check_doctor_availability(doctor_name: str, date: str):
    """
    Check available slots for a specific doctor on a given date (YYYY-MM-DD).
    Returns a list of available time slots.
    """
    logging.info(f"Checking availability for {doctor_name} on {date}")
    # Mock logic: returns 3 slots if date is in the future
    try:
        input_date = datetime.strptime(date, "%Y-%m-%d")
        if input_date < datetime.now():
            return "Error: Cannot check availability for past dates."
    except ValueError:
        return "Error: Invalid date format. Please use YYYY-MM-DD."

    return json.dumps([
        {"slot_id": 1, "time": "10:00 AM", "is_booked": False},
        {"slot_id": 2, "time": "02:00 PM", "is_booked": False},
        {"slot_id": 3, "time": "04:30 PM", "is_booked": False}
    ])

@tool
def book_appointment(doctor_name: str, date: str, time: str, patient_name: str, patient_phone: str):
    """
    Book an appointment. 
    Can ONLY be called after checking availability and confirming with the user.
    """
    logging.info(f"Booking: {doctor_name}, {date} {time} for {patient_name}")
    return json.dumps({
        "status": "success",
        "appointment_id": "APT-7890",
        "message": f"Appointment confirmed with {doctor_name} on {date} at {time}."
    })

# --- Agent Definition ---

_agent_runner = None

def get_agent_runner():
    global _agent_runner
    if _agent_runner is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
            
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", google_api_key=api_key)
        
        tools = [search_knowledge_base, check_doctor_availability, book_appointment]
        
        # Using the new create_agent API as requested
        memory = MemorySaver()
        
        _agent_runner = create_agent(
            model=llm,
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
            checkpointer=memory
        )
    return _agent_runner

def run_agent(message_body: str, wa_id: str):
    try:
        agent = get_agent_runner()
        config = {"configurable": {"thread_id": wa_id}}
        
        # The new create_agent returns a graph runnable that accepts a "messages" key
        input_payload = {"messages": [HumanMessage(content=message_body)]}
        
        result = agent.invoke(input_payload, config=config)
        
        # The result state contains the list of messages. We want the last AIMessage content.
        # Note: Depending on the API version, result might include 'messages' key.
        return result["messages"][-1].content
    except Exception as e:
        logging.error(f"Agent execution failed: {e}")
        return "I'm having trouble processing your request right now. Please try again."
