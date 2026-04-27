import os
import subprocess
import threading
import time
from flask import Flask, render_template, request, jsonify
import razorpay
from datetime import datetime

app = Flask(__name__)

# --- RAZORPAY CONFIGURATION ---
KEY_ID = 'rzp_test_vh7E1OIHNiInWq'
KEY_SECRET = '0DGZlSSa1dLSZWMqq9rylrDy'
client = razorpay.Client(auth=(KEY_ID, KEY_SECRET))

# --- SYSTEM CONFIGURATION ---
SCRIPT_PATH = "controller.py"
VIDEO_1 = "video2.mp4"  # Idle loop
VIDEO_2 = "video1.mp4"  # Dispense video

# Product Configuration
PRODUCTS = {
    1: {'name': 'Small Shake (20g)', 'price': 7000, 'description': 'A perfect 20g protein boost.'},
    2: {'name': 'Medium Shake (30g)', 'price': 9000, 'description': 'The standard 30g protein serving.'},
    3: {'name': 'Large Shake (40g)', 'price': 13000, 'description': 'A heavy 40g protein dose.'}
}

# State Management
live_payments = []
payment_stats = {'total_payments': 0, 'total_amount': 0, 'last_payment_time': None}
current_video_process = None
system_state = "idle"
sensor_thread = None
stop_sensor_monitoring = threading.Event()
state_lock = threading.Lock()
browser_launched = False  # OPTIMIZATION: Prevents multiple Firefox windows

# --- VIDEO FUNCTIONS ---
def play_video(video_path, loop=False):
    global current_video_process
    stop_current_video()
    try:
        # Optimization: Try hardware accelerated VLC for Pi 3B
        current_video_process = subprocess.Popen([
            'vlc', '--intf', 'dummy', 
            '--loop' if loop else '--play-and-exit', 
            '--fullscreen', '--no-video-title', 
            '--mmal-display', '--avcodec-hw=any', # Critical for RPi 3B
            video_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"🎥 Playing video: {video_path}")
    except Exception as e:
        print(f"❌ Error playing video: {e}")

def stop_current_video():
    global current_video_process
    if current_video_process:
        try:
            current_video_process.terminate()
            current_video_process.wait(timeout=2)
        except:
            current_video_process.kill()
        current_video_process = None

def start_idle_video():
    global system_state
    with state_lock:
        system_state = "idle"
    play_video(VIDEO_1, loop=True)

# --- SENSOR MONITORING ---
def sensor_monitor():
    global system_state, browser_launched
    print("👀 Sensor monitoring active...")
    while not stop_sensor_monitoring.is_set():
        try:
            with state_lock:
                current = system_state
            
            if current == "idle":
                # Check sensor
                res = subprocess.run(['python3', SCRIPT_PATH, '--sensor-only'], 
                                   capture_output=True, text=True, timeout=2)
                
                if res.returncode == 1:
                    with state_lock:
                        if system_state == "idle":
                            print("🚨 Sensor Triggered!")
                            system_state = "payment_mode"
                            stop_current_video()
                            time.sleep(0.5)
                            
                            # OPTIMIZATION: Only launch browser if not already running
                            if not browser_launched:
                                print("🚀 Launching Firefox...")
                                subprocess.Popen(['firefox-esr', '--kiosk', 'http://localhost:5000'])
                                browser_launched = True
        except:
            pass
        time.sleep(1.0)

def start_sensor_monitoring():
    global sensor_thread
    stop_sensor_monitoring.set()
    if sensor_thread: sensor_thread.join(timeout=2)
    stop_sensor_monitoring.clear()
    sensor_thread = threading.Thread(target=sensor_monitor, daemon=True)
    sensor_thread.start()

# --- HARDWARE CONTROL ---
def start_post_payment_sequence(product_id):
    global system_state
    with state_lock:
        system_state = "post_payment"
    
    stop_sensor_monitoring.set()
    play_video(VIDEO_2, loop=False)
    
    def dispense_task():
        print(f"🛠️ Dispensing Product {product_id}...")
        subprocess.run(["python3", SCRIPT_PATH, "--product", str(product_id)], 
                      cwd=os.getcwd())
        
        # After dispense, wait for video then reset
        if current_video_process:
            stop_current_video()
            
        with state_lock:
            # We don't set system_state back to idle here immediately
            # We let the frontend polling detect the change or force it here
            pass
        
        print("🔄 Dispense complete. Resetting...")
        time.sleep(2)
        start_idle_video()
        time.sleep(2)
        start_sensor_monitoring()
        
        # Reset state last so frontend picks it up
        with state_lock:
            global system_state
            system_state = "idle"

    threading.Thread(target=dispense_task, daemon=True).start()

# --- API ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/products')
def get_products():
    return jsonify(PRODUCTS)

@app.route('/api/addons')
def get_addons():
    return jsonify({
        'creatine': {'name': 'Creatine', 'price': 2000},
        'bcaa': {'name': 'BCAA', 'price': 1500},
        'fruits_nuts': {'name': 'Fruits & Nuts', 'price': 3000}
    })

@app.route('/api/system-state')
def get_state():
    with state_lock:
        return jsonify({'state': system_state})

# --- PAYMENT ROUTES ---
@app.route('/api/create-order', methods=['POST'])
def create_order():
    try:
        # TEST MODE: Always charge ₹1.00 (100 paise)
        amount_to_charge = 100 
        
        order = client.order.create({
            "amount": amount_to_charge,
            "currency": "INR",
            "payment_capture": 1
        })
        return jsonify({
            'order_id': order['id'],
            'amount': amount_to_charge,
            'key_id': KEY_ID
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/verify-payment', methods=['POST'])
def verify_payment():
    try:
        data = request.get_json()
        
        # Verify Signature
        client.utility.verify_payment_signature({
            'razorpay_order_id': data['razorpay_order_id'],
            'razorpay_payment_id': data['razorpay_payment_id'],
            'razorpay_signature': data['razorpay_signature']
        })

        # Payment Valid! Start Hardware
        product_id = int(data.get('product_id'))
        
        # Log stats (using REAL value, not the test ₹1 value)
        real_value = data.get('real_value', 0)
        payment_stats['total_payments'] += 1
        payment_stats['total_amount'] += real_value
        
        start_post_payment_sequence(product_id)
        
        return jsonify({'status': 'success'})
    except Exception as e:
        print(f"Payment Verification Failed: {e}")
        return jsonify({'error': 'Invalid Payment'}), 400

if __name__ == '__main__':
    print("🚀 DrinkX Kiosk Started")
    if not os.path.exists(VIDEO_1) or not os.path.exists(VIDEO_2):
        print("⚠️  MISSING VIDEO FILES! Please check naming.")
    
    start_idle_video()
    time.sleep(2)
    start_sensor_monitoring()
    
    app.run(host='0.0.0.0', port=5000, threaded=True)