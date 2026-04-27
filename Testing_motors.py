import RPi.GPIO as GPIO
import time
import gpiod
# -------------------------
# GPIO Pin Definitions
# -------------------------

MOTOR_V1 = 20     # Motor V1 LED

MOTOR_V2 = 21     # Motor V2 LED

MOTOR_V3 = 22     # Motor V3 LED

#MOTOR_V4 = 4    # Motor V4 LED servo vav

DRAIN    = 23      # Drain motor

PUMP     = 24     # Pump motor LED

STIRRER  = 25     # Stirrer motor LED

DOOR     = [5, 6, 13, 12]     # Door motor

# -------------------------
# GPIO Setup
# -------------------------
GPIO.setmode(GPIO.BCM)  # Use BCM pin numbering

GPIO.setwarnings(False) # Ignore warnings if pins were used before

# List of all motor pins for easy setup
motor_pins = [MOTOR_V1, MOTOR_V2, MOTOR_V3, PUMP, STIRRER, DRAIN]
# Set all pins as output and turn them OFF initially
for pin in motor_pins:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)
# -------------------------
# Motor Test Functions
# -------------------------
def test_motor(pin, name, run_time=10):
    """Turn ON a motor for run_time seconds, then turn it OFF."""

    print(f"Testing {name} motor...")
    GPIO.output(pin, GPIO.HIGH)  # Turn ON motor
    time.sleep(run_time)         # Wait
    GPIO.output(pin, GPIO.LOW)   # Turn OFF motor
    print(f"{name} motor test complete.\n")

def test_v1():
    test_motor(MOTOR_V1, "V1")

def test_v2():
    test_motor(MOTOR_V2, "V2")

def test_v3():
    test_motor(MOTOR_V3, "V3")

# def test_v4():
#     test_motor(MOTOR_V4, "V4")

def test_pump():
    test_motor(PUMP, "Pump")

def test_stirrer():
    test_motor(STIRRER, "Stirrer", 2)

#vav stepper motor door code
# ---- Stepper patterns ----
seg_right = [
    [1,0,0,0],
    [1,1,0,0],
    [0,1,0,0],
    [0,1,1,0],
    [0,0,1,0],
    [0,0,1,1],
    [0,0,0,1],
    [1,0,0,1]
]

seg_left = [
    [0,0,0,1],
    [0,0,1,1],
    [0,0,1,0],
    [0,1,1,0],
    [0,1,0,0],
    [1,1,0,0],
    [1,0,0,0],
    [1,0,0,1]
]

def rotate_stepper(lines, steps=280, delay=0.001, direction="left"):
    """Rotate stepper motor in one direction only."""
    seq = seg_left if direction == "left" else seg_right
    for i in range(steps):
        for halfstep in range(8):
            for pin in range(4):
                lines[pin].set_value(seq[halfstep][pin])
            time.sleep(delay)


def open_door(steps=560, delay=0.001):
    """Open the door by rotating stepper in one direction."""
    print("Opening door...")
    chip = gpiod.Chip("gpiochip4")
    lines = [chip.get_line(pin) for pin in DOOR]

    for line in lines:
        line.request("stepper_motor", gpiod.LINE_REQ_DIR_OUT, default_val=0)

    try:
        rotate_stepper(lines, steps, delay, direction="left")
    finally:
        for line in lines:
            line.release()
    print("Door opened.\n")


def close_door(steps=560, delay=0.001):
    """Close the door by rotating stepper in the opposite direction."""
    print("Closing door...")
    chip = gpiod.Chip("gpiochip4")
    lines = [chip.get_line(pin) for pin in DOOR]

    for line in lines:
        line.request("stepper_motor", gpiod.LINE_REQ_DIR_OUT, default_val=0)

    try:
        rotate_stepper(lines, steps, delay, direction="right")
    finally:
        for line in lines:
            line.release()
    print("Door closed.\n")


def test_drain():
    test_motor(DRAIN, "Drain")
# -------------------------
# Menu Loop
# -------------------------
def menu():
    while True:
        print("\n--- Motor Test Menu ---")
        print("1. Test Motor V1")
        print("2. Test Motor V2")
        print("3. Test Motor V3")
        print("4. Test Motor V4 (not connected)")
        print("5. Test Pump Motor")
        print("6. Test Stirrer Motor")
        print("7. Open Door")
        print("8. Close Door")
        print("9. Test Drain Motor")
        print("10. Test ALL Motors")
        print("0. Exit")
        choice = input("Enter choice: ")

        if choice == "1":
            test_v1()
        elif choice == "2":
            test_v2()
        elif choice == "3":
            test_v3()
        #elif choice == "4":
            #test_v4()
        elif choice == "5":
            test_pump()
        elif choice == "6":
            test_stirrer()
        elif choice == "7":
            open_door()
        elif choice == "8":
            close_door()
        elif choice == "9":
            test_drain()
        elif choice == "10":
            #Test all motors
            for func in [test_v1, test_v2, test_v3, test_pump, test_stirrer, open_door, close_door, test_drain]:
                func()
        elif choice == "0":
            print("Exiting program...")
            GPIO.cleanup()  # Reset GPIO state
            break
        else:
            print("Invalid choice, please try again.")
# -------------------------
# Program Entry Point
# -------------------------
if __name__ == "__main__":
    try:
        menu()
    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
        GPIO.cleanup()
    finally:
        GPIO.cleanup()
        print("GPIO cleaned up. Goodbye!")



