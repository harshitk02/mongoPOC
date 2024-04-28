from flask import Flask, request, jsonify, send_file
from pymongo import MongoClient
import hashlib
from datetime import datetime
from prettytable import PrettyTable
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from pymongo.server_api import ServerApi
import os, requests
import json

app = Flask(__name__)

# MongoDB connection
uri = "mongodb+srv://farhanabidiai:0MbtNrh3bf8VjaEV@guidegurucluster.karofwo.mongodb.net/?retryWrites=true&w=majority&appName=GuideGuruCluster"

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))
db = client['User_Transactions'] 
user_wallet_collection = db['User_Wallet']
coin_transaction_collection = db['Coin_Transactions']

@app.route('/create_wallet', methods=['POST'])
def create_wallet():
    data = request.json
    if 'employeeId' not in data:
        return jsonify({'error': 'employeeId is missing from request body'}), 400
    
    employee_id = data['employeeId']
    
    # Check if wallet already exists
    existing_wallet = user_wallet_collection.find_one({'employeeId': employee_id})
    if existing_wallet:
        return jsonify({'error': 'Wallet already exists for employeeId'}), 400
    
    # Generate hash key
    hash_key = hashlib.sha256(employee_id.encode()).hexdigest()
    
    # Insert wallet into User_Wallet collection
    user_wallet_collection.insert_one({'employeeId': employee_id, 'privateKey': hash_key})
    
    # Add initial transaction
    initial_transaction = {
        'employeeId': employee_id,
        'timestamp': datetime.now(),
        'reason': 'onboarding rewards',
        'sender': 'Admin',
        'receiver': employee_id,
        'amount': 500,
        'balance': 500
    }
    coin_transaction_collection.insert_one(initial_transaction)
    
    return jsonify({'success': 'Wallet created successfully', 'hashKey': hash_key}), 200

@app.route('/transaction', methods=['POST'])
def transaction():
    data = request.json
    required_fields = ['sender', 'privateKey', 'receiver', 'amount', 'reason']
    
    # Check if all required fields are present
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'One or more required fields are missing'}), 400
    
    # Retrieve data from request
    sender = data['sender']
    private_key = data['privateKey']
    receiver = data['receiver']
    amount = data['amount']
    reason = data['reason']
    
    # Check if sender exists and private key matches
    sender_wallet = user_wallet_collection.find_one({'employeeId': sender, 'privateKey': private_key})
    if not sender_wallet:
        return jsonify({'error': 'Invalid sender credentials'}), 401
    
    # Check sender's balance
    sender_balance = coin_transaction_collection.find_one({'employeeId': sender}, sort=[('timestamp', -1)])['balance']
    if sender_balance < amount:
        return jsonify({'error': 'Insufficient balance for the transaction'}), 400
    
    # Deduct the transaction amount from the sender's balance
    sender_new_balance = sender_balance - amount
    
    # Add the transaction amount to the receiver's balance
    receiver_wallet = user_wallet_collection.find_one({'employeeId': receiver})
    if not receiver_wallet:
        return jsonify({'error': 'Receiver does not exist'}), 404
    
    receiver_balance = coin_transaction_collection.find_one({'employeeId': receiver}, sort=[('timestamp', -1)])['balance']
    receiver_new_balance = receiver_balance + amount
    
    # Perform the transaction
    timestamp = datetime.now()
    new_transaction_sender = {
        'employeeId': sender,
        'timestamp': timestamp,
        'reason': reason,
        'sender': sender,
        'receiver': receiver,
        'amount': -amount,  # Negative amount to indicate deduction
        'balance': sender_new_balance
    }
    new_transaction_receiver = {
        'employeeId': receiver,
        'timestamp': timestamp,
        'reason': reason,
        'sender': sender,
        'receiver': receiver,
        'amount': amount,
        'balance': receiver_new_balance
    }
    
    coin_transaction_collection.insert_one(new_transaction_sender)
    coin_transaction_collection.insert_one(new_transaction_receiver)
    
    return jsonify({'success': True}), 200

@app.route('/check_balance', methods=['POST'])
def check_balance():
    data = request.json
    if 'employeeId' not in data:
        return jsonify({'error': 'employeeId is missing from request body'}), 400
    
    employee_id = data['employeeId']
    
    # Check if user exists in User_Wallet collection
    user = user_wallet_collection.find_one({'employeeId': employee_id})
    if not user:
        return jsonify({'error': 'User does not exist'}), 404
    
    # Retrieve all transactions for the user from Coin_Transactions collection
    user_transactions = coin_transaction_collection.find({'employeeId': employee_id})
    
    # Create a PrettyTable to display transactions
    table = PrettyTable()
    table.field_names = ["Timestamp", "Reason", "Sender", "Receiver", "Amount", "Balance"]
    
    # Extract reasons and amounts from the cursor object
    reasons = []
    amounts = []

    for transaction in user_transactions:
        reasons.append(transaction['reason'])
        amounts.append(int(transaction['amount']))

    # Create a dictionary to aggregate amounts by reason
    amounts_by_reason = {}
    for reason, amount in zip(reasons, amounts):
        amounts_by_reason[reason] = amounts_by_reason.get(reason, 0) + amount

    # Plot pie chart
    plt.figure(figsize=(8, 8))
    plt.pie(amounts_by_reason.values(), labels=amounts_by_reason.keys(), autopct='%1.1f%%', startangle=140)
    plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
    plt.title('Transaction Amounts by Reason')
    plt.tight_layout()
    
   # Ensure the "charts" directory exists
    if not os.path.exists("charts"):
        os.makedirs("charts")

    # Save chart to file
    chart_filename = f"{employee_id}_analysis.png"
    chart_path = os.path.join("charts", chart_filename)
    plt.savefig(chart_path)
    
    # Return response with table and link to download the chart
    response = {
        'transactions': table.get_string(),
        'chart_link': f"Download chart: /download/{chart_filename}"
    }
    
    return jsonify(response), 200

    
@app.route('/check_balance_tg', methods=['POST'])
def check_balance_tg():
    data = request.json
    if 'employeeId' not in data:
        return jsonify({'error': 'employeeId is missing from request body'}), 400
    
    employee_id = data['employeeId']
    
    # Check if user exists in User_Wallet collection
    user = user_wallet_collection.find_one({'employeeId': employee_id})
    if not user:
        return jsonify({'error': 'User does not exist'}), 404
    
    # Retrieve all transactions for the user from Coin_Transactions collection
    user_transactions = coin_transaction_collection.find({'employeeId': employee_id}).sort('timestamp', -1)
    
    # Get the last transaction and calculate the final balance
    last_transaction = user_transactions[0]
    final_balance = last_transaction['balance']
    
    # Prepare the response message
    response_message = f"🗓️ <b><u>Last Transaction</u></b>:\n" \
                       f"   <b>- Timestamp:</b> {last_transaction['timestamp'].isoformat()}\n" \
                       f"   <b>- Reason:</b> {last_transaction['reason']}\n" \
                       f"   <b>- Sender:</b> {last_transaction['sender']}\n" \
                       f"   <b>- Receiver:</b> {last_transaction['receiver']}\n" \
                       f"   <b>- Amount:</b> {last_transaction['amount']} 💰\n\n" \
                       f"   <b>Final Balance: {final_balance} 💰</b>"
                           
    # Plot pie charts
    spent_amounts = {}
    received_amounts = {}
    
    for transaction in user_transactions:
        reason = transaction['reason']
        amount = int(transaction['amount'])
        
        # Categorize transactions into spent and received
        if amount < 0:
            spent_amounts[reason] = spent_amounts.get(reason, 0) + abs(amount)
        else:
            received_amounts[reason] = received_amounts.get(reason, 0) + amount
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))

    # Plot spent coins pie chart
    axes[0].pie(spent_amounts.values(), labels=spent_amounts.keys(), autopct='%1.1f%%', startangle=140)
    axes[0].set_title('Spent Coins')

    # Plot received coins pie chart
    axes[1].pie(received_amounts.values(), labels=received_amounts.keys(), autopct='%1.1f%%', startangle=140)
    axes[1].set_title('Received Coins')

    # Ensure the "charts" directory exists
    if not os.path.exists("charts"):
        os.makedirs("charts")

    # Save chart to file
    chart_filename = f"{employee_id}_analysis.png"
    chart_path = os.path.join("charts", chart_filename)
    plt.savefig(chart_path)
    
    # Return response with message and link to download the chart
    response = {
        'message': response_message,
        'chart_link': f"Download chart: /download/{chart_filename}"
    }
    
    return jsonify(response), 200

greeted_users={}

# Define a dictionary to track whether each user has been greeted and their state
user_info = {}

# Define possible states
STATE_INITIAL = 0
STATE_ENTERING_BALANCE = 1
STATE_ENTERING_RECOGNITION_DETAILS = 2

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    update = request.json
    chat_id = update['message']['chat']['id']
    message_text = update['message']['text']

    # Initialize user info if not already present
    if chat_id not in user_info:
        user_info[chat_id] = {'state': STATE_INITIAL}

    # Handle message based on state
    state = user_info[chat_id]['state']

    if state == STATE_INITIAL:
        if message_text.lower() == '/start':
            send_telegram_message(chat_id, "Hello! I'm your Guide Guru bot.")
            send_telegram_message(chat_id, "You can use the following commands:\n"
                                           "/balance - Check your current skill balance!\n"
                                           "/recognize - Send skill coins to someone!\n"
                                           "/aboutus - Learn more about our Guide Guru Bot for Career Development!")
        elif message_text.lower() == '/balance':
            send_telegram_message(chat_id, "Please enter your employee ID to check your balance:")
            user_info[chat_id]['state'] = STATE_ENTERING_BALANCE
        elif message_text.lower() == '/recognize':
            send_telegram_message(chat_id, "To recognize someone, please fill out the following details:")
            send_telegram_message(chat_id, "1. Enter your Employee ID:")
            user_info[chat_id]['state'] = STATE_ENTERING_RECOGNITION_DETAILS
        elif message_text.lower() == '/aboutus':
            # Send the introduction message about the MS Teams Bot
            send_aboutus_message(chat_id)
    elif state == STATE_ENTERING_BALANCE:
        # Call your Flask endpoint to check balance, passing the employee ID
        employee_id = message_text.strip()
        response = requests.post('https://mongopoc.onrender.com/check_balance_tg', json={'employeeId': employee_id})
        if response.status_code == 200:
            balance_data = response.json()
            balance_message = balance_data['message']
            send_telegram_message(chat_id, balance_message)
        else:
            error_message = "Failed to retrieve balance."
            send_telegram_message(chat_id, error_message)
        # Reset state to initial after balance check
        user_info[chat_id]['state'] = STATE_INITIAL
    elif state == STATE_ENTERING_RECOGNITION_DETAILS:
        if 'recognition_details' not in user_info[chat_id]:
            user_info[chat_id]['recognition_details'] = {}
        
        if 'employee_id' not in user_info[chat_id]['recognition_details']:
            user_info[chat_id]['recognition_details']['employee_id'] = message_text.strip()
            send_telegram_message(chat_id, "2. Enter your Private Key:")
        elif 'private_key' not in user_info[chat_id]['recognition_details']:
            user_info[chat_id]['recognition_details']['private_key'] = message_text.strip()
            send_telegram_message(chat_id, "3. Enter Receiver's ID:")
        elif 'receiver_id' not in user_info[chat_id]['recognition_details']:
            user_info[chat_id]['recognition_details']['receiver_id'] = message_text.strip()
            send_telegram_message(chat_id, "4. Enter Skill Coins to transfer:")
        elif 'skill_coins' not in user_info[chat_id]['recognition_details']:
            user_info[chat_id]['recognition_details']['skill_coins'] = int(message_text.strip())
            send_telegram_message(chat_id, "5. Enter Reason of transfer:")
        elif 'reason' not in user_info[chat_id]['recognition_details']:
            user_info[chat_id]['recognition_details']['reason'] = message_text.strip()
            
            # Send confirmation message
            send_telegram_message(chat_id, "Recognition details received!\nPlease wait while we process your transaction...")
                   
            # Construct transaction details JSON
            transaction_details = {
                "sender": str(user_info[chat_id]['recognition_details']['employee_id']),
                "privateKey": user_info[chat_id]['recognition_details']['private_key'],
                "receiver": user_info[chat_id]['recognition_details']['receiver_id'],
                "amount": user_info[chat_id]['recognition_details']['skill_coins'],
                "reason": user_info[chat_id]['recognition_details']['reason']
            }
            
            response = requests.post('https://mongopoc.onrender.com/transaction', json=transaction_details)
            if response.status_code == 200:
                balance_data = response.json()
                recognition_message = "Your recognition has been received. Thank you for your gesture!"
                send_telegram_message(chat_id, recognition_message)
            else:
                balance_data = response.json()
                error_message = balance_data["error"]
                send_telegram_message(chat_id, error_message)
            
            # Reset state to initial after recognizing someone
            user_info[chat_id]['state'] = STATE_INITIAL
            
    return '', 200
    
# Function to send aboutus message
def send_aboutus_message(chat_id):
    introduction = """
    <b>Introducing our Guide Guru Bot for Career Development</b>

    Our innovative MS Teams bot revolutionizes career advancement within your organization. With seamless integration into the Teams platform, employees can effortlessly upload their CVs and unlock a world of personalized career guidance.

    <b>Key Features:</b>

    <b>1. Personalized Career Path Recommendations:</b> Receive tailored recommendations based on available positions and individual career aspirations.

    <b>2. Customized Study Plans:</b> Access curated study plans with comprehensive learning resources, designed to enhance skillsets and propel career growth.

    <b>3. Calendar Blocking for Study Time:</b> Optimize productivity with automated calendar blocking for dedicated study sessions.

    <b>4. Performance Evaluations with Improvement Tips:</b> Receive detailed performance evaluations and actionable improvement tips to continually enhance professional skills.

    <b>5. Interview Preparation Tools:</b> Equip yourself with AI backed interview preparation tools to ace every opportunity.

    <b>6. Position Tracking and Hiring Manager Notifications:</b> Stay informed with position tracking and receive notifications directly to hiring managers.

    <b>7. Augmented Reality Profiles:</b> HR and hiring managers can access candidates' profiles via QR codes in augmented reality, seamlessly integrating LinkedIn, Workday profiles, resumes, course performance data, and introductory videos for comprehensive candidate evaluation.

    Unlock the full potential of your workforce with our MS Teams bot, empowering individuals to chart their career trajectories and enabling organizations to nurture talent effectively.

    """
    send_telegram_message(chat_id, introduction)  
        
TELEGRAM_API_TOKEN = "7137754355:AAFy98A4EGjzWNpkjH2hqNAIVy-6PxxmhAA"

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode':'HTML'
    }
    requests.post(url, json=payload)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
