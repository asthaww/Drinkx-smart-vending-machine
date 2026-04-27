

#!/usr/bin/env python3
#vav v 1.5.4
import time
import sys
import RPi.GPIO as GPIO
import serial
# ============================================================================
# GLOBAL CONFIGURATION - MODIFY THESE VALUES TO CUSTOMIZE BEHAVIOR
# ============================================================================
# Serial Communication Settings
SERIAL_CONFIG = {
    'port': "/dev/ttyUSB0",
    'baudrate': 115200,
    'timeout': 2
}
# GPIO Pin Assignments
GPIO_PINS = {
    'motor_v1_led': 20,      # Vending motor V1 LED indicator  
    'motor_v2_led': 21,      # Vending motor V2 LED indicator vjc  
    'motor_v3_led': 22,      # Vending motor V3 LED indicator vjc   
    'motor_v4_led': 4,     # Bar Vending motor V4 LED indicator vjc  
    'pump_p_led': 24,        # Pump LED indicator vav   
    'stirrer_led': 25,       # Stirrer LED indicator       
    'motor_s_led':23,         # Sink motor LED indicator vjc (DRAIN)
    'ir_sensor': 27,         # IR sensor input pin
}

MOTOR_SETTINGS = {
    'cup_drop_turns': 50,
    'door_open_turns': 3,
    'door_close_turns': -3,
    'powder_dispense_steps': 1000,
    'x_axis_mid_position': 55,
    'x_axis_stirrer_offset': 50,
    'z_axis_cleaning_down': 300,
    'z_axis_cup_upper_level': 45, #strvav upper cup
    'z_axis_cup_bottom_level': 18, #strvav bottom cup 
    'z_axis_stirrer_level': 120,
    'x_axis_final_position': -64,
    'product_dispense_positions': {
        1: 40,   # Coffee Powder
        2: 70,   # Tea Powder
        3: 100,   # Hot Chocolate
        #4: 120   # Milk Powder
    }
}


# Timing Configuration (seconds)
TIMING_CONFIG = {
    'selection_timeout': 30,     # Time to wait for user selection
    'cup_detection_timeout': 2, # Time to wait for cup detection
    'water_dispense_time': 10,  # Water dispensing duration
    'powder_dispense_time':9,    #powder dispesning duration
    'stirring_cycles': 6,        # Number of stirring cycles
    'stirring_delay': 0.5,       # Delay between stirring directions
    'cup_collection_wait': 5,   # Time to wait for cup collection
    'cup_removal_timeout': 10,   # Time limit for cup removal detection
    'cleaning_delay': 1,         # Delay during cleaning operations
    'motor_action_delay': 0.5,   # LED indicator duration for simulated motors
    'z_step_delay': 0.1,         # Delay between Z-axis steps
    'sensor_check_delay': 0.1,   # Delay for sensor polling
    'cup_removal_check_delay': 0.5  # Delay for cup removal checking
}

# G-code Motor Settings
GCODE_SETTINGS = {
    'steps_per_mm': {
        'X': 160,
        'Y': 160,
        'Z': 800,
        'E': 160                #vav extruder
    },
    'default_feed_rate': 2000,   # Default movement speed (mm/min)
    'motor_timeout': 12000,      # Motor disable timeout (seconds)
    'home_z_height': 100,        # Z height after homing (mm)
    'home_x_offset': 5,         # X offset after homing for "true home" (mm) vjc
    'mm_per_revolution': {
        'cup_motor': 40,         
        'x_motor': 40,           # X-axis motor
        'z_motor': 1             # Z-axis motor (mm per step)
    }
}
#CHANGE
RUN_COUNTER_FILE = '/tmp/vending_run_counter.txt'
RUN_COUNTER_INTERVAL = 2  # change this for testing (e.g. 3)
import os

def _read_run_count():
    """Read the run counter from file. Return 0 if file missing or invalid."""
    try:
        if not os.path.exists(RUN_COUNTER_FILE):
            return 0
        with open(RUN_COUNTER_FILE, 'r') as f:
            return int(f.read().strip() or 0)
    except Exception:
        return 0

def _write_run_count(n):
    """Write the run counter atomically."""
    try:
        tmp = RUN_COUNTER_FILE + '.tmp'
        with open(tmp, 'w') as f:
            f.write(str(int(n)))
        os.replace(tmp, RUN_COUNTER_FILE)
    except Exception as e:
        print(f"⚠️ Could not write run counter: {e}")

def increment_run_count():
    """Increment counter by 1 and return new value."""
    n = _read_run_count() + 1
    _write_run_count(n)
    return n

def is_draining_due(run_count, interval=RUN_COUNTER_INTERVAL):
    """Check if current run should trigger draining instead of cleaning."""
    return (run_count % interval) == 0 if run_count and interval > 0 else False


# ============================================================================
# SERIAL COMMUNICATION CLASS
# ============================================================================
class SerialController:
    """Handles all serial communication with the 3D printer/CNC controller"""
    
    def __init__(self):
        self.ser = None
        self.connected = False
        self._initialize_serial()
    
    def _initialize_serial(self):
        """Initialize serial connection"""
        try:
            self.ser = serial.Serial(
                SERIAL_CONFIG['port'], 
                SERIAL_CONFIG['baudrate'],
                timeout=SERIAL_CONFIG['timeout']
            )
            time.sleep(2)  # Allow connection to stabilize
            self.connected = True
            print(f" Serial connected to {SERIAL_CONFIG['port']}")
        except Exception as e:
            print(f" Could not open serial: {e}")
            self.ser = None
            self.connected = False
    
    def send_gcode(self, cmd):
        """Send G-code command"""
        if not self.connected:
            print(f"Serial not connected. Would send: {cmd}")
            return
        
        print(f"GCODE {cmd}")
        self.ser.write((cmd + "\r\n").encode())
    
    def wait_until_ready(self):
        """Wait for 'Iamready' response from controller"""
        if not self.connected:
            time.sleep(0.5)  # Simulate wait time
            return
        
        response = ""
        while "Iamready" not in response:
            if self.ser.in_waiting:
                byte_data = self.ser.read()
                response += byte_data.decode(errors='ignore')
    
    def close(self):
        """Close serial connection"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("ðŸ”Œ Serial connection closed")

# ============================================================================
# MOTOR CONTROL CLASSES
# ============================================================================

class GCodeMotor:
    """Controls motors via G-code commands"""
    
    def __init__(self, axis, serial_controller, mm_per_rev=None):
        self.axis = axis
        self.serial = serial_controller
        self.mm_per_rev = mm_per_rev or GCODE_SETTINGS['mm_per_revolution'].get(f'{axis.lower()}_motor', 40)
    
    def move(self, distance_mm, speed=None):
        """Move motor by specified distance in mm"""
        speed = speed or GCODE_SETTINGS['default_feed_rate']
        
        # Allow cold extrusion always (important for extruder-as-cup-motor) vav extruder
        if self.axis == "E":
            self.serial.send_gcode("M302 S0")
        
        self.serial.send_gcode("G91")  # Relative positioning
        self.serial.send_gcode(f"G1 {self.axis}{distance_mm} F{speed}")
        self.serial.send_gcode("M400")  # Wait for movement to complete
        self.serial.send_gcode("M118 E1 Iamready")
        self.serial.wait_until_ready()
        self.serial.send_gcode("G90")  # Absolute positioning
        
    # ------------------------
    # New method for cup drop extruder
    # ------------------------
    def drop_cup(self, distance_mm=None):
        """
        Drop a cup using the extruder.
        distance_mm: how much E-axis to move to release one cup.
                     If None, uses default from MOTOR_SETTINGS['cup_drop_turns']
        """
        if distance_mm is None:
            distance_mm = MOTOR_SETTINGS['cup_drop_turns']  
        
        print(f"Extruder (cup_motor) dropping cup by {distance_mm} mm")
        self.move(distance_mm)
    
    def rotate(self, turns=1):
        """Rotate motor by specified number of turns"""
        distance_mm = turns * self.mm_per_rev
        self.move(distance_mm)
    
    def move_steps(self, steps):
        """Move motor by steps (interpreted as mm for compatibility)"""
        self.move(steps)

class ZAxisMotor:
    """Special handling for Z-axis motor with step-based control"""
    
    def __init__(self, serial_controller):
        self.axis = 'Z'
        self.serial = serial_controller
        self.mm_per_step = GCODE_SETTINGS['mm_per_revolution']['z_motor']
    
    def rotate(self, steps, direction=True):
        """Move Z-axis by steps in specified direction"""
        distance_mm = steps * self.mm_per_step
        if not direction:
            distance_mm = -distance_mm
        
        self.serial.send_gcode("G91")  # Relative positioning
        self.serial.send_gcode(f"G1 Z{distance_mm} F{GCODE_SETTINGS['default_feed_rate']}")
        self.serial.send_gcode("M400")
        self.serial.send_gcode("M118 E1 Iamready")
        self.serial.wait_until_ready()
        self.serial.send_gcode("G90")  # Absolute positioning

class SimulatedMotor:
    """Simulates motor actions with LED indicators"""
    
    def __init__(self, name, led_pin):
        self.name = name
        self.led_pin = led_pin
    
    def _indicate_action(self, description):
        """Show LED indicator and print action"""
        print(description)
        GPIO.output(self.led_pin, GPIO.HIGH)
        time.sleep(TIMING_CONFIG['motor_action_delay'])
        GPIO.output(self.led_pin, GPIO.LOW)
    
    def rotate(self, steps=None, turns=None, direction=True):
        """Simulate motor rotation"""
        if steps:
            self._indicate_action(f"{self.name} rotate {steps} steps")
        elif turns:
            dir_str = "CW" if direction else "CCW"
            self._indicate_action(f"{self.name} rotate {turns} turns {dir_str}")
        else:
            self._indicate_action(f"{self.name} rotate")
    
    def run_for(self, seconds):
        """Simulate motor running for specified time"""
        self._indicate_action(f"{self.name} run for {seconds} seconds")

# ============================================================================
# SENSOR CLASSES
# ============================================================================

class IRSensor:
    """Handles IR sensor readings"""
    
    def __init__(self, pin):
        self.pin = pin
    
    def detected(self):
        """Check if object is detected"""
        return GPIO.input(self.pin) == 1

class ButtonSensor:
    """Handles button input (using IR sensor for simulation)"""
    
    def __init__(self, pin):
        self.pin = pin
    
    def pressed(self):
        """Check if button is pressed"""
        return GPIO.input(self.pin) == 1

# ============================================================================
# SYSTEM INITIALIZATION
# ============================================================================

def initialize_system():
    """Initialize all system components"""
    # Initialize serial communication
    serial_controller = SerialController()
    
    # Initialize GPIO
    GPIO.setmode(GPIO.BCM)
    for pin in GPIO_PINS.values():
        if pin != GPIO_PINS['ir_sensor']:
            GPIO.setup(pin, GPIO.OUT)
        else:
            GPIO.setup(pin, GPIO.IN)
    
    # Initialize motors
    motors = {
        'cup_motor': GCodeMotor('E', serial_controller, GCODE_SETTINGS['mm_per_revolution']['cup_motor']), #extruder vav
        'x_motor': GCodeMotor('X', serial_controller, GCODE_SETTINGS['mm_per_revolution']['x_motor']),
        'z_motor': ZAxisMotor(serial_controller),
        'vending_motor': SimulatedMotor("Vending motor V1", GPIO_PINS['motor_v1_led']),
        'pump': SimulatedMotor("Pump", GPIO_PINS['pump_p_led']),
        'stirrer': SimulatedMotor("Stirrer", GPIO_PINS['stirrer_led']),
        #'door_motor': SimulatedMotor("Door motor", GPIO_PINS['motor_d_led']),
        'sink_motor': SimulatedMotor("Sink motor", GPIO_PINS['motor_s_led'])  # Add sink motor here
    }
    
    # Initialize sensors
    sensors = {
        'ir_sensor': IRSensor(GPIO_PINS['ir_sensor']),
        'button1': ButtonSensor(GPIO_PINS['ir_sensor']),
        'button2': ButtonSensor(GPIO_PINS['ir_sensor']),  # Placeholder
        'z_limit': IRSensor(GPIO_PINS['ir_sensor']),
        'cup_detector': IRSensor(GPIO_PINS['ir_sensor']),
        'exit_detector': IRSensor(GPIO_PINS['ir_sensor'])
    }
    
    return serial_controller, motors, sensors
    
#VAV Home

def home_and_prepare_system(serial_controller):
    """Home X and Z axes. After homing, back Z off slightly to avoid limit switch contact."""
    print("Homing and preparing system...")
    # Set steps per mm
    steps_cmd = (
        f"M92 X{GCODE_SETTINGS['steps_per_mm']['X']} "
        #f"Y{GCODE_SETTINGS['steps_per_mm']['Y']} "
        f"Z{GCODE_SETTINGS['steps_per_mm']['Z']} "
        f"E{GCODE_SETTINGS['steps_per_mm']['E']}"
    )
    serial_controller.send_gcode(steps_cmd)
    # Set motor timeout
    serial_controller.send_gcode(f"M84 S{GCODE_SETTINGS['motor_timeout']}")
    # Home X and Z axes
    serial_controller.send_gcode("G28 Z")
    serial_controller.send_gcode("G28 X")
    # Slight Z back-off to avoid stressing limit switch
    serial_controller.send_gcode(f"G1 Z2 F{GCODE_SETTINGS['default_feed_rate']}")  # Back off Z by 2mm
    # Move to true home X offset (still in relative mode)
    serial_controller.send_gcode(f"G1 X{GCODE_SETTINGS['home_x_offset']} F{GCODE_SETTINGS['default_feed_rate']}")
    serial_controller.send_gcode("G90")  # Return to absolute positioning
    # Synchronize and send ready signal
    serial_controller.send_gcode("M400")  # Wait for moves to finish
    serial_controller.send_gcode("M118 E1 Iamready")
    serial_controller.wait_until_ready()
    print("System homed and ready (Z backed off slightly)")

#VAV Stir
def stir_and_home(serial_controller, motors):
    #strvav
    """
    Perform complete stirring sequence with vertical motion,
    then home the Z-axis at the end.
    """
    #spins once clockwise, then anti-clockwise
    print("Stirring...")
    motors['stirrer'].rotate(direction=True)
    time.sleep(2)
    motors['stirrer'].rotate(direction=False)
    time.sleep(2)
    print("Moving stirrer to cup bottom level...")
    motors['z_motor'].rotate(steps=MOTOR_SETTINGS['z_axis_cup_bottom_level'], direction=True)
    time.sleep(TIMING_CONFIG['z_step_delay'])
    print("Stirring...")
    motors['stirrer'].rotate(direction=True)
    time.sleep(2)
    motors['stirrer'].rotate(direction=False)
    time.sleep(2)
    #moves up
    print("Moving stirrer back to upper...")
    motors['z_motor'].rotate(steps=MOTOR_SETTINGS['z_axis_cup_bottom_level'], direction=False)
    time.sleep(TIMING_CONFIG['z_step_delay'])
    #dispense water before sitrring one final time vav
    print("Dispensing water...")
    # Turn on the pump LED (simulating pump activation for 3 seconds)
    GPIO.output(GPIO_PINS['pump_p_led'], GPIO.HIGH)  # Pump LED ON
    print("pump has started")
    time.sleep(5)
    GPIO.output(GPIO_PINS['pump_p_led'], GPIO.LOW)  # Pump LED OFF
    print("pump has stopped")
    #start stirring
    print("Stirring...")
    motors['stirrer'].rotate(direction=True)
    time.sleep(2)
    motors['stirrer'].rotate(direction=False)
    time.sleep(2)

    # --- Home Z after stirring ---
    print("Homing Z axis (stirrer back to home)...")
    serial_controller.send_gcode("G28 Z") 
    serial_controller.send_gcode(f"G1 Z2 F{GCODE_SETTINGS['default_feed_rate']}") #back off by 2mm

def stir_and_home_no_water(serial_controller, motors):
    #strvav
    """
    Perform complete stirring sequence with vertical motion,
    then home the Z-axis at the end.
    """
    #spins once clockwise, then anti-clockwise
    print("Stirring...")
    motors['stirrer'].rotate(direction=True)
    time.sleep(2)
    motors['stirrer'].rotate(direction=False)
    time.sleep(2)
    print("Moving stirrer to cup bottom level...")
    motors['z_motor'].rotate(steps=MOTOR_SETTINGS['z_axis_cup_bottom_level'], direction=True)
    time.sleep(TIMING_CONFIG['z_step_delay'])
    print("Stirring...")
    motors['stirrer'].rotate(direction=True)
    time.sleep(2)
    motors['stirrer'].rotate(direction=False)
    time.sleep(2)
    #moves up
    print("Moving stirrer back to upper...")
    motors['z_motor'].rotate(steps=MOTOR_SETTINGS['z_axis_cup_bottom_level'], direction=False)
    time.sleep(TIMING_CONFIG['z_step_delay'])
    #start stirring
    print("Stirring...")
    motors['stirrer'].rotate(direction=True)
    time.sleep(2)
    motors['stirrer'].rotate(direction=False)
    time.sleep(2)

    # --- Home Z after stirring ---
    print("Homing Z axis (stirrer back to home)...")
    serial_controller.send_gcode("G28 Z") 
    serial_controller.send_gcode(f"G1 Z2 F{GCODE_SETTINGS['default_feed_rate']}") #back off by 2mm

#DOOR VAV
import gpiod

# Stepper Motor Door Pins
DOOR = [5, 6, 13, 12]

# Stepper Patterns
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
    seq = seg_left if direction == "left" else seg_right
    for i in range(steps):
        for halfstep in range(8):
            for pin in range(4):
                lines[pin].set_value(seq[halfstep][pin])
            time.sleep(delay)

def open_door(steps=560, delay=0.001):
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

# ============================================================================
# MAIN VENDING FLOW
# ============================================================================

def run_vending_flow(serial_controller, motors, sensors, run_count=None): #rvf
    """Execute the complete vending machine flow"""
    GPIO.output(GPIO_PINS["pump_p_led"], GPIO.LOW)
    GPIO.output(GPIO_PINS["motor_s_led"], GPIO.LOW)
    GPIO.output(GPIO_PINS["motor_v1_led"], GPIO.LOW) 
    GPIO.output(GPIO_PINS["motor_v2_led"], GPIO.LOW) 
    GPIO.output(GPIO_PINS["motor_v3_led"], GPIO.LOW) 
    #CHANGE
    # Read or increment run counter
    if run_count is None:
        run_count = _read_run_count()  # current run number

    # --- INITIAL DRAINING CHECK ---
    if run_count == 0:
        print("First run detected -> performing initial draining cycle")
        draining_cycle(serial_controller, motors)
        run_count = increment_run_count()  # increment after draining
    else:
        run_count = increment_run_count()  # increment for normal runs
    
    print("Starting vending flow...")
    # Home and prepare system
    home_and_prepare_system(serial_controller)
    # Step 1: Wait for user selection
    print("1. Waiting for user selection...")
    
    # Step 2 & 3: drop cup until detected    
    print("2. Dropping cup...")

    cup_detected = False
    for attempt in range(3):  # try 3 times
        print(f"   Attempt {attempt+1}...")
        motors['cup_motor'].drop_cup()   # rotate once
        time.sleep(TIMING_CONFIG['cup_detection_timeout'])  # small wait for cup to settle
        
        if sensors['cup_detector'].detected():
            cup_detected = True
            break

    if not cup_detected:
        print("The cup holder can be empty - stopping program")
        sys.exit(1)

    print("Cup detected! Continuing...")
    
    # Step 4: Move X to dispensing position (based on product)
    try:
        product_id = int(sys.argv[sys.argv.index('--product') + 1]) if '--product' in sys.argv else 1 #take the product selection or else take default value as 2 vav
    except (ValueError, IndexError):
        product_id = 2                       #takes default if input is invalid

    dispense_position = MOTOR_SETTINGS.get('product_dispense_positions', {}).get(product_id, MOTOR_SETTINGS['x_axis_mid_position']) #takes product id's dispense position if invalid it returns to mid position   
    x_offset = dispense_position 

    print(f"4. Moving to dispensing position for Product {product_id} (X = {dispense_position})...")
    motors['x_motor'].move_steps(dispense_position)
    
    # Step 5: Dispense powder
    print("5. Dispensing powder...")
    # Identify the correct motor based on the selected product
    product_motor_mapping = {
        1: 'motor_v1_led',  # Coffee Powder (Vending motor 1)
        2: 'motor_v2_led',  # Tea Powder (Vending motor 2)
        3: 'motor_v3_led'   # Hot Chocolate (Vending motor 3)
    }
    # Get the selected motor pin for the product or else default to motor v1
    selected_motor_pin = GPIO_PINS.get(product_motor_mapping.get(product_id, 'motor_v1_led'))

    # Turn on the motor LED (simulating motor turning on for 3 seconds)
    if selected_motor_pin:
        print("Vending motor ", selected_motor_pin, " starting")
        GPIO.output(selected_motor_pin, GPIO.HIGH)  # Simulate motor turning on
        time.sleep(TIMING_CONFIG['powder_dispense_time'])  # Wait while powder is dispensed
        GPIO.output(selected_motor_pin, GPIO.LOW)  # Simulate motor turning off

    # Step 6: Move X to stirrer position
    print("6. Moving to stirrer position...")
    stirrer_position = 125  # modified to set stirrer position
    delta_to_stirrer = stirrer_position - x_offset  # ensures x final position is same
    motors['x_motor'].move_steps(delta_to_stirrer)
    
    # Step 7: Lower Z from home to working cup level
    z_steps = MOTOR_SETTINGS.get('z_axis_cup_upper_level', 30)
    print(f"7. Raising stirrer to cup level ({z_steps} steps above Z=0)...")
    motors['z_motor'].rotate(steps=z_steps, direction=True)
    time.sleep(TIMING_CONFIG['z_step_delay'])

    # Step 8: Dispense water
    print("8. Dispensing water...")
   
    #Turn on the pump LED (simulating pump activation for 3 seconds)
    GPIO.output(GPIO_PINS['pump_p_led'], GPIO.HIGH)  # Pump LED ON
    print("pump has started")
    time.sleep(TIMING_CONFIG['water_dispense_time'])  # Wait for 10 seconds while the pump is activated
    #Simulate actual water dispensing
    #motors['pump'].run_for(seconds=TIMING_CONFIG['water_dispense_time'])
    #Turn off the pump LED (simulating pump deactivation)
    GPIO.output(GPIO_PINS['pump_p_led'], GPIO.LOW)  # Pump LED OFF
    print("pump has stopped")

    # Step 9 & 10: Stir & home mixture strvav
    print("9 & 10. Stirring mixture...")
    stir_and_home(serial_controller, motors)
    
    # Step 11: Move X to center
    print("11. Moving to center position...")
    motors['x_motor'].move_steps(-MOTOR_SETTINGS['x_axis_mid_position'])
    
    # Step 12: Open door
    print("12. Opening door...")
    open_door()
    
    #Wait for cup collection
    print(f"â° Waiting {TIMING_CONFIG['cup_collection_wait']} seconds for cup collection...")
    time.sleep(TIMING_CONFIG['cup_collection_wait'])
    
    # Step 13: Check cup removal
    print("13. Checking cup removal...")
    removal_timeout = time.time() + TIMING_CONFIG['cup_removal_timeout']
    while sensors['exit_detector'].detected():
        if time.time() > removal_timeout:
            print("âš ï¸ Cup removal timeout - proceeding with cleanup")
            break
        time.sleep(TIMING_CONFIG['cup_removal_check_delay'])
    
    # Step 14: Close door and clean if cup is collected vavcup
    while True:
        if not sensors['cup_detector'].detected():
            print("14. Closing door and cleaning...")
            close_door()
            
            motors['x_motor'].move_steps(MOTOR_SETTINGS['x_axis_final_position'])  # Final position of the X axis
            #if 10x then draining cycle, if not normal cleaning sequance
            #CHANGE
            if is_draining_due(run_count):
                print(f"Run count {run_count} is multiple of {RUN_COUNTER_INTERVAL} -> running drain cycle")
                draining_cycle(serial_controller, motors)
                break
            else:
                #Cleaning Sequence
                motors['z_motor'].rotate(steps=MOTOR_SETTINGS.get('z_axis_stirrer_level', 70), direction=True) 
                time.sleep(TIMING_CONFIG['cleaning_delay'])
                motors['stirrer'].rotate(direction=True)  # Stirrer action
                time.sleep(TIMING_CONFIG['cleaning_delay'])
                motors['stirrer'].rotate(direction=True)  # Stirrer action again
                time.sleep(TIMING_CONFIG['cleaning_delay'])
                home_z(serial_controller)
                print("Vending cycle complete - System ready for next customer") 
                break 
        else:
            print("Cup still present, please collect")
            time.sleep(2)
        GPIO.output(GPIO_PINS["pump_p_led"], GPIO.LOW)
        GPIO.output(GPIO_PINS["motor_s_led"], GPIO.LOW)
        GPIO.output(GPIO_PINS["motor_v1_led"], GPIO.LOW) 
        GPIO.output(GPIO_PINS["motor_v2_led"], GPIO.LOW) 
        GPIO.output(GPIO_PINS["motor_v3_led"], GPIO.LOW) 

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================
# Define the GPIO pins for ultrasonic sensor
TRIG = 26
ECHO = 19

def measure_distance():
    
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    start_time = time.time()
    stop_time = time.time()

    # Wait for echo start
    while GPIO.input(ECHO) == 0:
        start_time = time.time()

    # Wait for echo end
    while GPIO.input(ECHO) == 1:
        stop_time = time.time()

    # Calculate pulse duration
    pulse_duration = stop_time - start_time
    distance = pulse_duration * 17150  # Speed of sound in cm/s
    return round(distance, 2)

def sensor_only_mode(threshold=10):
    
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(TRIG, GPIO.OUT)
    GPIO.setup(ECHO, GPIO.IN)
    GPIO.output(TRIG, False)
    time.sleep(1)

    try:
        distance = measure_distance()
        print(f"ðŸ“ Distance measured: {distance} cm")
        if distance < threshold:
            print("ðŸ‘€ Object detected within threshold!")
            sys.exit(1)
        else:
            print("âœ… No object detected.")
            sys.exit(0)
    except Exception as e:
        print(f"âŒ Ultrasonic sensor error: {e}")
        sys.exit(2)
    finally:
        GPIO.cleanup()
    

def cleanup_system(serial_controller):
    """Clean up system resources"""
    if serial_controller:
        serial_controller.close()
    GPIO.cleanup()
    print("System cleanup completed")

def show_help():
    """Display help information"""
    print("Vending Machine Controller")
    print("=" * 50)
    print("Usage:")
    print("  python3 controller.py                 - Run full vending flow")
    print("  python3 controller.py --sensor-only  - Check US sensor only")
    print("  python3 controller.py --help         - Show this help")
    print()
    print("Configuration:")
    print("  Edit the GLOBAL CONFIGURATION section at the top of this file")
    print("  to customize timing, motor settings, and GPIO pins.")

#HOMING ONLY MOTORS X & Z

def home_x(serial_controller):
    """Home X axis using the same safe routine as home_and_prepare_system but only for X."""
    print("Homing X axis...")
    # set steps per mm (same as home_and_prepare_system)
    steps_cmd = (
        f"M92 X{GCODE_SETTINGS['steps_per_mm']['X']} "
        f"Z{GCODE_SETTINGS['steps_per_mm']['Z']} "
        f"E{GCODE_SETTINGS['steps_per_mm']['E']}"
    )
    serial_controller.send_gcode(steps_cmd)
    serial_controller.send_gcode(f"M84 S{GCODE_SETTINGS['motor_timeout']}")
    serial_controller.send_gcode("G28 X")  # home X
    # move to true home X offset (mirror of home_and_prepare_system)
    serial_controller.send_gcode(f"G1 X{GCODE_SETTINGS['home_x_offset']} F{GCODE_SETTINGS['default_feed_rate']}")
    serial_controller.send_gcode("M400")
    serial_controller.send_gcode("M118 E1 Iamready")
    serial_controller.wait_until_ready()
    serial_controller.send_gcode("G90")  # absolute positioning back
    print("X axis homed and ready")


def home_z(serial_controller):
    """Home Z axis using the same safe routine as home_and_prepare_system but only for Z."""
    print("Homing Z axis...")
    # set steps per mm (same as home_and_prepare_system)
    steps_cmd = (
        f"M92 X{GCODE_SETTINGS['steps_per_mm']['X']} "
        f"Z{GCODE_SETTINGS['steps_per_mm']['Z']} "
        f"E{GCODE_SETTINGS['steps_per_mm']['E']}"
    )
    serial_controller.send_gcode(steps_cmd)
    serial_controller.send_gcode(f"M84 S{GCODE_SETTINGS['motor_timeout']}")
    serial_controller.send_gcode("G28 Z")  # home Z
    # Slight Z back-off to avoid limit switch stress
    serial_controller.send_gcode(f"G1 Z2 F{GCODE_SETTINGS['default_feed_rate']}")
    serial_controller.send_gcode("M400")
    serial_controller.send_gcode("M118 E1 Iamready")
    serial_controller.wait_until_ready()
    serial_controller.send_gcode("G90")
    print("Z axis homed and ready")

#test drain functioning, drain, pump then stirr vav drain
def draining_cycle(serial_controller, motors):
    #drains water
    pin = GPIO_PINS['motor_s_led']
    GPIO.output(pin, GPIO.HIGH)  # Turn ON motor
    time.sleep(10)         # Wait
    GPIO.output(pin, GPIO.LOW)   # Turn OFF motor
    print("draining complete")
    #pumps water
    motors['z_motor'].rotate(steps=MOTOR_SETTINGS.get('z_axis_stirrer_level', 70), direction=True) 
    print("Dispensing water...")
    GPIO.output(GPIO_PINS['pump_p_led'], GPIO.HIGH)  # Pump LED ON
    print("pump has started")
    time.sleep(10)
    GPIO.output(GPIO_PINS['pump_p_led'], GPIO.LOW) 
    #stirrer washes
    time.sleep(TIMING_CONFIG['cleaning_delay'])
    motors['stirrer'].rotate(direction=True)  # Stirrer action
    time.sleep(TIMING_CONFIG['cleaning_delay'])
    motors['stirrer'].rotate(direction=True)  # Stirrer action again
    time.sleep(TIMING_CONFIG['cleaning_delay'])
    home_z(serial_controller)
    motors['x_motor'].move_steps(MOTOR_SETTINGS['x_axis_final_position'])  # Final position of the X axis

# ============================================================================
# MAIN PROGRAM
# ============================================================================
#VAV NEW TESTING BETTER
def run_step_by_step_mode(serial_controller, motors, sensors): #rsbs
    """Run vending steps one at a time for testing purposes"""
    print("?? Entering Step-by-Step Tester Mode")
    stirrer_position = 125
    def _blink(pin, seconds=10):
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(seconds)
        GPIO.output(pin, GPIO.LOW)

    def show_menu():
        print("\n=== Step-by-Step Tester Steps ===")
        print("  1  Home X/Z")
        print("  2  Cup drop motor (3s)")
        print("  3  Check cup detector (IR)")
        print("  4  Product position 1")
        print("  5  Product position 2")
        print("  6  Product position 3")
        print("  7  Test v1 motor")
        print("  8  Test v2 motor")
        print("  9  Test v3 motor")
        print("  10 Get cup to stirrer position")
        print("  11 Move stirrer down to cup position")
        print("  12 Test pump motor")
        print("  13 Test stirrer motion")
        print("  14 Move stirrer to sink level")
        print("  15 Move cup to door")
        print("  16 Open door motor")
        print("  17 Cup sensor check")
        print("  18 Close door motor")
        print("  19 Home X")
        print("  20 Home Z")
        print("  21 Test Drain cycle (CAUTION: Water)")
        print("  x  Exit step-by-step tester")
        print("===========================")

    steps = {
        "1":  lambda: home_and_prepare_system(serial_controller),
        "2":  lambda: motors['cup_motor'].drop_cup(),
        "3":  lambda: print("Cup detected" if sensors['cup_detector'].detected() else "No cup detected"),
        "4":  lambda: motors['x_motor'].move_steps(MOTOR_SETTINGS['product_dispense_positions'][1]),
        "5":  lambda: motors['x_motor'].move_steps(MOTOR_SETTINGS['product_dispense_positions'][2]),
        "6":  lambda: motors['x_motor'].move_steps(MOTOR_SETTINGS['product_dispense_positions'][3]),
        "7":  lambda: _blink(GPIO_PINS['motor_v1_led']),
        "8":  lambda: _blink(GPIO_PINS['motor_v2_led']),
        "9":  lambda: _blink(GPIO_PINS['motor_v3_led']),
        "10": lambda: motors['x_motor'].move_steps(stirrer_position),
        "11": lambda: (motors['z_motor'].rotate(steps=MOTOR_SETTINGS['z_axis_cup_upper_level'], direction=True)), 
        "12": lambda: motors['pump'].run_for(seconds=TIMING_CONFIG['water_dispense_time']),
        "13": lambda: stir_and_home_no_water(serial_controller, motors),
        "14": lambda: motors['z_motor'].rotate(steps=MOTOR_SETTINGS['z_axis_stirrer_level'], direction=True),
        "15": lambda: motors['x_motor'].move_steps(-MOTOR_SETTINGS['x_axis_mid_position']),
        "16": lambda: open_door(),
        "17": lambda: print("Cup removed" if not sensors['exit_detector'].detected() else "Cup still present"),
        "18": lambda: close_door(),
        "19": lambda: home_x(serial_controller),  # home only X axis
        "20": lambda: home_z(serial_controller), # home only Z axis
        "21": lambda: draining_cycle(serial_controller, motors),
        "x":  lambda: print("Exiting tester mode...")
    }

    # --- Loop ---
    while True:
        show_menu()
        choice = input("Enter step number, please choose from 1-18 or x: ").strip().lower()
        if choice == "x":
            print("Exiting Step-by-Step Tester...")
            break
        action = steps.get(choice)
        if action:
            action()
        else:
            print("Invalid choice, please choose from 1-18 or x...")


def main():
    
    """Main program entry point"""
    serial_controller = None
    
    try:
        # Handle command line arguments
        if len(sys.argv) > 1:
            if "--sensor-only" in sys.argv:
                sensor_only_mode()
                return
            elif "--help" in sys.argv:
                show_help()
                return
            elif "--tester" in sys.argv:
                key = input("Enter tester access key: ").strip()
                if key == "vav":
                    serial_controller, motors, sensors = initialize_system()
                    run_step_by_step_mode(serial_controller, motors, sensors)
                    return
                else:
                    print("Incorrect key. Access denied.")
                    return
        
        # Initialize system
        print("Vending Machine Controller Starting...")
        serial_controller, motors, sensors = initialize_system()
        
        # Run vending flow
        run_vending_flow(serial_controller, motors, sensors)
        
    except KeyboardInterrupt:
        print("System stopped by user")
        GPIO.cleanup()
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        GPIO.cleanup()
        cleanup_system(serial_controller)
        

if __name__ == "__main__":
    main()
 
