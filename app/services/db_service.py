import logging
import os
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from urllib.parse import quote_plus

# Using the credentials provided by the user
DB_USER = "hospital"
DB_PASS = "reality@123"
DB_HOST = os.getenv("DB_HOST", "0.0.0.0") # Use env var, fallback to 0.0.0.0 (local dev)
DB_PORT = "5432"
DB_NAME = "mydb"

# Construct Connection String
# URL-encode credentials to handle special characters like '@' in the password
DATABASE_URL = f"postgresql+psycopg2://{quote_plus(DB_USER)}:{quote_plus(DB_PASS)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

try:
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logging.info("Database engine created successfully.")
except Exception as e:
    logging.error(f"Failed to create database engine: {e}")
    engine = None

def get_db_connection():
    if engine is None:
        raise Exception("Database engine is not initialized.")
    return engine.connect()

def get_doctor_availability(doctor_id: str, date: str):
    """
    Fetch available slots for a doctor on a specific date.
    """
    query = text("""
        SELECT id, start_time, end_time 
        FROM doctor_availability 
        WHERE doctor_id = :doctor_id 
          AND slot_date = :date 
          AND is_booked = FALSE
        ORDER BY start_time;
    """)
    
    try:
        with get_db_connection() as conn:
            result = conn.execute(query, {"doctor_id": doctor_id, "date": date})
            slots = []
            for row in result:
                # Format time objects to string if needed
                start = row.start_time.strftime("%H:%M") if hasattr(row.start_time, 'strftime') else str(row.start_time)
                end = row.end_time.strftime("%H:%M") if hasattr(row.end_time, 'strftime') else str(row.end_time)
                slots.append({
                    "slot_id": str(row.id),
                    "start_time": start,
                    "end_time": end
                })
            return slots
    except Exception as e:
        logging.error(f"Error fetching availability: {e}")
        return []

def book_appointment_slot(patient_name: str, patient_phone: str, doctor_id: str, slot_id: str):
    """
    Book a slot for a patient.
    1. Check if patient exists, create if not.
    2. Check if slot is still available.
    3. Create appointment.
    4. Mark slot as booked.
    """
    try:
        with SessionLocal() as session:
            # 1. Manage Patient
            # Check if patient exists
            check_patient_query = text("SELECT id FROM patients WHERE phone = :phone")
            result = session.execute(check_patient_query, {"phone": patient_phone}).fetchone()
            
            if result:
                patient_id = result[0]
            else:
                # Create new patient
                create_patient_query = text("""
                    INSERT INTO patients (full_name, phone) 
                    VALUES (:name, :phone) 
                    RETURNING id
                """)
                patient_id = session.execute(create_patient_query, {"name": patient_name, "phone": patient_phone}).scalar()
            
            # 2. Check and Lock Slot
            # We use a transaction here
            check_slot_query = text("SELECT is_booked FROM doctor_availability WHERE id = :slot_id FOR UPDATE")
            slot_status = session.execute(check_slot_query, {"slot_id": slot_id}).fetchone()
            
            if not slot_status:
                return {"status": "error", "message": "Slot not found."}
            if slot_status[0]: # is_booked is True
                session.rollback()
                return {"status": "error", "message": "Slot already booked."}
            
            # 3. Create Appointment
            create_appt_query = text("""
                INSERT INTO appointments (doctor_id, patient_id, availability_id, status, created_at)
                VALUES (:doctor_id, :patient_id, :slot_id, 'scheduled', NOW())
                RETURNING id
            """)
            appt_id = session.execute(create_appt_query, {
                "doctor_id": doctor_id,
                "patient_id": patient_id,
                "slot_id": slot_id
            }).scalar()
            
            # 4. Mark Slot as Booked
            update_slot_query = text("UPDATE doctor_availability SET is_booked = TRUE WHERE id = :slot_id")
            session.execute(update_slot_query, {"slot_id": slot_id})
            
            session.commit()
            session.commit()
            return {"status": "success", "appointment_id": str(appt_id)}
            
    except Exception as e:
        logging.error(f"Error booking appointment: {e}")
        return {"status": "error", "message": str(e)}

def search_doctors(query_str: str):
    """
    Find doctors by name or department.
    """
    query = text("""
        SELECT d.id, d.full_name, d.specialization, d.qualification, d.experience_years, d.languages, dept.name as dept_name
        FROM doctors d
        JOIN departments dept ON d.department_id = dept.id
        WHERE d.full_name ILIKE :q OR d.specialization ILIKE :q OR dept.name ILIKE :q
    """)
    
    try:
        with get_db_connection() as conn:
            result = conn.execute(query, {"q": f"%{query_str}%"})
            doctors = []
            for row in result:
                doctors.append({
                    "id": str(row.id),
                    "name": row.full_name,
                    "specialization": row.specialization,
                    "department": row.dept_name,
                    "qualification": row.qualification,
                    "experience": f"{row.experience_years} years",
                    "languages": row.languages
                })
            return doctors
    except Exception as e:
        logging.error(f"Error searching doctors: {e}")
        return []

def get_appointments_by_phone(phone: str):
    """
    Get active appointments for a patient by phone number.
    """
    query = text("""
        SELECT a.id, d.full_name as doctor_name, da.slot_date, da.start_time, a.status
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        JOIN doctor_availability da ON a.availability_id = da.id
        WHERE p.phone = :phone AND a.status = 'scheduled'
        ORDER BY da.slot_date, da.start_time
    """)
    
    try:
        with get_db_connection() as conn:
            result = conn.execute(query, {"phone": phone})
            appointments = []
            for row in result:
                start = row.start_time.strftime("%H:%M") if hasattr(row.start_time, 'strftime') else str(row.start_time)
                appointments.append({
                    "appointment_id": str(row.id),
                    "doctor": row.doctor_name,
                    "date": str(row.slot_date),
                    "time": start,
                    "status": row.status
                })
            return appointments
    except Exception as e:
        logging.error(f"Error fetching appointments: {e}")
        return []

def cancel_appointment(appointment_id: str):
    """
    Cancel an appointment and free the slot.
    """
    try:
        with SessionLocal() as session:
            # Get slot ID to free it
            get_appt_query = text("SELECT availability_id FROM appointments WHERE id = :id AND status = 'scheduled'")
            result = session.execute(get_appt_query, {"id": appointment_id}).fetchone()
            
            if not result:
                return {"status": "error", "message": "Appointment not found or already cancelled."}
            
            slot_id = result[0]
            
            # Update Appointment Status
            update_appt_query = text("UPDATE appointments SET status = 'cancelled' WHERE id = :id")
            session.execute(update_appt_query, {"id": appointment_id})
            
            # Free the slot
            free_slot_query = text("UPDATE doctor_availability SET is_booked = FALSE WHERE id = :slot_id")
            session.execute(free_slot_query, {"slot_id": slot_id})
            
            session.commit()
            return {"status": "success", "message": "Appointment cancelled successfully."}
    except Exception as e:
        logging.error(f"Error cancelling appointment: {e}")
        return {"status": "error", "message": str(e)}
