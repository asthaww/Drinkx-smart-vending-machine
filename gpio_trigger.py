import RPi.GPIO as GPIO
import time

# Define the GPIO pin for the IR sensor
IR_SENSOR_PIN = 17  # Change if you're using a different pin

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(IR_SENSOR_PIN, GPIO.IN)

def is_person_detected():
    """
    Returns True if the IR sensor detects an object/person,
    based on digital LOW signal.
    """
    return GPIO.input(IR_SENSOR_PIN) == 1  # Adjust if sensor logic is inverted

def cleanup():
    """
    Call this function at the end to clean GPIO pins.
    """
    GPIO.cleanup()

# Optional: testing this script standalone
if __name__ == "__main__":
    print("🔍 IR Sensor monitoring started (Press Ctrl+C to exit)...")
    try:
        while True:
            if is_person_detected():
                print("👤 Person Detected!")
            else:
                print("🚫 No one there.")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n🧹 Cleaning up GPIO...")
        cleanup()
