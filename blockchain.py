from flask import Flask, request, jsonify, send_file
from pymongo import MongoClient
import hashlib
from datetime import datetime
from prettytable import PrettyTable
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from pymongo.server_api import ServerApi
import os

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
    
    # Perform the transaction
    timestamp = datetime.now()
    new_transaction = {
        'employeeId': sender,
        'timestamp': timestamp,
        'reason': reason,
        'sender': sender,
        'receiver': receiver,
        'amount': amount,
        'balance': sender_balance - amount
    }
    coin_transaction_collection.insert_one(new_transaction)
    
    return jsonify({'success': 'Transaction successful'}), 200

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

@app.route('/download/<filename>', methods=['GET'])
def download_chart(filename):
    chart_path = os.path.join("charts", filename)
    if os.path.exists(chart_path):
        return send_file(chart_path, as_attachment=True)
    else:
        return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    app.run(debug=True)