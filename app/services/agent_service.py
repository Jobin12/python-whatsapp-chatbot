import logging
import os
import json
from datetime import datetime, timedelta
from typing import List

from langchain.agents import create_agent
from langchain.messages import SystemMessage, HumanMessage, RemoveMessage
from langchain_core.messages import BaseMessage
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
def cancel_appointment(appointment_id: str):
    """
    Cancel an appointment by ID.
    Always confirm with the user before calling this.
    """
    logging.info(f"Cancelling appointment ID: {appointment_id}")
    result = db_service.cancel_appointment(appointment_id)
    return json.dumps(result)

@tool
def check_doctor_availability(doctor_id: str, date: str):
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
def book_appointment(doctor_id: str, slot_id: str, patient_name: str, patient_phone: str):
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
_llm_instance = None # Keep reference for summarization

def get_llm():
    global _llm_instance
    if _llm_instance is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        _llm_instance = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", google_api_key=api_key)
    return _llm_instance

def get_agent_runner():
    global _agent_runner
    if _agent_runner is None:
        llm = get_llm()
        
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

def manage_conversation_history(agent_runner, config: dict):
    """
    Checks history. If messages are > 24h old, summarizes and prunes them.
    Returns the list of update operations for the graph.
    """
    try:
        # 1. Fetch current state
        state_snapshot = agent_runner.get_state(config)
        messages: List[BaseMessage] = state_snapshot.values.get("messages", [])
        
        if not messages:
            return
            
        now = datetime.now()
        messages_to_prune = []
        messages_to_summarize = []
        
        # 2. Identify old messages
        # Skip the first message if it's the system prompt (usually handled by create_agent implicitly, 
        # but if explicit SystemMessage matches our prompt, we treat it carefully).
        # We look for 'timestamp' in additional_kwargs.
        
        for msg in messages:
            # Skip SystemMessages to ensure prompt stays
            if isinstance(msg, SystemMessage):
                continue
                
            timestamp_str = msg.additional_kwargs.get("timestamp")
            if timestamp_str:
                msg_time = datetime.fromisoformat(timestamp_str)
                age = now - msg_time
                if age > timedelta(hours=24):
                    messages_to_prune.append(msg)
                    messages_to_summarize.append(msg)
        
        if not messages_to_prune:
            return

        logging.info(f"Summarizing {len(messages_to_prune)} old messages...")
        
        # 3. Generate Summary
        # We use a direct LLM call for this
        llm = get_llm()
        conversation_text = "\n".join([f"{m.type}: {m.content}" for m in messages_to_summarize])
        summary_prompt = f"Summarize the following old conversation history into 2-3 concise sentences. Focus on facts (Patient Name, Appointments booked, Preferences).:\n\n{conversation_text}"
        
        summary_response = llm.invoke(summary_prompt)
        summary_content = summary_response.content
        
        logging.info(f"Generated Summary: {summary_content}")
        
        # 4. Update Graph State
        # We add a new SystemMessage with the summary and remove the old messages.
        
        updates = []
        
        # Add Summary
        summary_msg = SystemMessage(content=f"PREVIOUS CONVERSATION SUMMARY (Older than 24h): {summary_content}")
        updates.append(summary_msg)
        
        # Remove old messages
        for msg in messages_to_prune:
            updates.append(RemoveMessage(id=msg.id))
            
        agent_runner.update_state(config, {"messages": updates})
        
    except Exception as e:
        logging.error(f"Error in memory management: {e}")

def run_agent(message_body: str, wa_id: str):
    try:
        agent = get_agent_runner()
        config = {"configurable": {"thread_id": wa_id}}
        
        # 1. Manage History (Summarize & Prune) BEFORE adding new message
        manage_conversation_history(agent, config)
        
        # 2. Add User Message with Timestamp
        timestamp = datetime.now().isoformat()
        input_message = HumanMessage(content=message_body, additional_kwargs={"timestamp": timestamp})
        
        input_payload = {"messages": [input_message]}
        
        # 3. Invoke Agent
        result = agent.invoke(input_payload, config=config)
        
        return result["messages"][-1].content
    except Exception as e:
        logging.error(f"Agent execution failed: {e}")
        return "I'm having trouble processing your request right now. Please try again."
