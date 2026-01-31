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
from app.services import db_service

# --- Tools with Real DB Logic ---

@tool
def search_knowledge_base(query: str):
    """
    Search the hospital knowledge base (Vector DB) for general information.
    Use this for questions about departments, doctors, policies, location, services, etc.
    """
    logging.info(f"Searching KB for: {query}")
    # Mock responses based on keywords (KB Mock is still valid as KB is separate from SQL DB)
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
def find_doctors(query: str):
    """
    Find doctors by name or department/specialization.
    IMPORTANT: To list ALL doctors, pass an empty string ("") as the query.
    Returns a list of matching doctors with their IDs.
    """
    logging.info(f"Searching doctors with query: {query}")
    results = db_service.search_doctors(query)
    if not results:
        return "No doctors found matching that criteria."
    return json.dumps(results)

@tool
def get_my_appointments(patient_phone: str):
    """
    Get active appointments for a patient using their phone number.
    Use this when a user wants to check their schedule or cancel an appointment.
    """
    logging.info(f"Fetching appointments for: {patient_phone}")
    results = db_service.get_appointments_by_phone(patient_phone)
    if not results:
        return "No active appointments found for this phone number."
    return json.dumps(results)

@tool
def cancel_appointment(appointment_id: int):
    """
    Cancel an appointment by ID.
    Always confirm with the user before calling this.
    """
    logging.info(f"Cancelling appointment ID: {appointment_id}")
    result = db_service.cancel_appointment(appointment_id)
    return json.dumps(result)

@tool
def check_doctor_availability(doctor_id: int, date: str):
    """
    Check available slots for a specific doctor on a given date (YYYY-MM-DD).
    Requires 'doctor_id' (get this from find_doctors if needed).
    Returns a list of available time slots.
    """
    logging.info(f"Checking availability for Doctor ID {doctor_id} on {date}")
    try:
        # Validate date format
        datetime.strptime(date, "%Y-%m-%d")
        
        slots = db_service.get_doctor_availability(doctor_id, date)
        if not slots:
            return f"No available slots found for Doctor ID {doctor_id} on {date}."
        
        return json.dumps(slots)
    except ValueError:
        return "Error: Invalid date format. Please use YYYY-MM-DD."
    except Exception as e:
        return f"Error checking availability: {str(e)}"

@tool
def book_appointment(doctor_id: int, slot_id: int, patient_name: str, patient_phone: str):
    """
    Book an appointment. 
    Can ONLY be called after checking availability and confirming with the user.
    Requires doctor_id and slot_id (from check availability result).
    """
    logging.info(f"Booking slot {slot_id} for {patient_name}")
    result = db_service.book_appointment_slot(patient_name, patient_phone, doctor_id, slot_id)
    return json.dumps(result)

# --- Agent Definition ---

_agent_runner = None

def get_agent_runner():
    global _agent_runner
    if _agent_runner is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
            
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", google_api_key=api_key)
        
        # Added find_doctors and new appointment tools to tools list
        tools = [search_knowledge_base, find_doctors, check_doctor_availability, book_appointment, get_my_appointments, cancel_appointment]
        
        memory = MemorySaver()
        
        # Inject Current Date/Time into System Prompt
        current_time_str = datetime.now().strftime("%A, %Y-%m-%d %H:%M")
        enhanced_system_prompt = f"{SYSTEM_PROMPT}\n\nCURRENT DATE AND TIME: {current_time_str}\nUse this for resolving relative dates like 'tomorrow' or 'next Monday'."

        _agent_runner = create_agent(
            model=llm,
            tools=tools,
            system_prompt=enhanced_system_prompt,
            checkpointer=memory
        )
    return _agent_runner

def run_agent(message_body: str, wa_id: str):
    try:
        agent = get_agent_runner()
        config = {"configurable": {"thread_id": wa_id}}
        
        input_payload = {"messages": [HumanMessage(content=message_body)]}
        
        result = agent.invoke(input_payload, config=config)
        
        return result["messages"][-1].content
    except Exception as e:
        logging.error(f"Agent execution failed: {e}")
        return "I'm having trouble processing your request right now. Please try again."
