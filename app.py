from flask import Flask, request, jsonify, session, send_from_directory
import mysql.connector
from openai import OpenAI
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from datetime import timedelta
import logging
import os
app = Flask(__name__)
app.secret_key = 'Your_secret_key'
app.permanent_session_lifetime = timedelta(minutes=30)

# Load configuration from config.py
app.config.from_object('config.Config')

# Set OpenAI API key
client = OpenAI(api_key='YOUR_OPENAI_KEY')

# Twilio client setup
twilio_client = Client(app.config['TWILIO_ACCOUNT_SID'], app.config['TWILIO_AUTH_TOKEN'])

# Set up logging
logging.basicConfig(level=logging.DEBUG)


os.makedirs('/app/screenshots', exist_ok=True)

@app.route('/save_screenshot', methods=['POST'])
def save_screenshot():
    screenshot_data = request.files['screenshot']
    screenshot_path = os.path.join('/app/screenshots', 'report_screenshot.png')
    screenshot_data.save(screenshot_path)
    logging.info(f"Screenshot saved at: {screenshot_path}")
    return jsonify({"message": "Screenshot saved successfully", "path": screenshot_path})

@app.route('/screenshots/<filename>', methods=['GET'])
def get_screenshot(filename):
    return send_from_directory('/app/screenshots', filename)





# Function to get MySQL connection
def get_db_connection():
    return mysql.connector.connect(
        host=app.config['MYSQL_HOST'],
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        database=app.config['MYSQL_DB'],
        charset='utf8',  # Explicitly set character set to utf8
        collation='utf8_general_ci'  # Explicitly set collation
    )

# Route to handle incoming WhatsApp messages
@app.route('/whatsapp', methods=['POST'])
def whatsapp():
    from_number = request.values.get('From')
    message_body = request.values.get('Body')

    logging.debug(f"Received message from: {from_number}")
    logging.debug(f"Message body: {message_body}")

    # Normalize phone number by keeping only numeric characters
    normalized_number = ''.join(filter(str.isdigit, from_number))
    logging.debug(f"Normalized number: {normalized_number}")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Query to get user from customer table
        cursor.execute('SELECT * FROM customer WHERE REPLACE(CCell, "-", "") LIKE %s', (f'%{normalized_number}%',))
        logging.debug(f"SELECT * FROM customer WHERE REPLACE(CCell, '-', '') LIKE %{normalized_number}%")
        user = cursor.fetchone()
        logging.debug(f"User found: {user}")

        if not user:
            response = MessagingResponse()
            response.message("Hi there! We noticed your number isn't registered with us yet. If you already have a DIDX account, you can update your contact information (including your WhatsApp Number as your Cell Number) in your profile for the best support experience.")
            logging.debug("User not found")
            return str(response)

        uid = user['UID']

        # Query to get orders from OrderDue table
        cursor.execute('SELECT * FROM OrderDue WHERE OID = %s', (uid,))
        transactions = cursor.fetchall()
        logging.debug(f"Transactions found: {transactions}")

        # Query to get DIDs from DIDS table where status is 2 and BOID = uid
        cursor.execute('SELECT DIDNumber FROM DIDS WHERE Status = 2 AND BOID = %s', (uid,))
        dids = cursor.fetchall()
        logging.debug(f"DIDs found: {dids}")

        dids_details_list = [
            ', '.join([f"DID: {did['DIDNumber']}" for did in dids])
        ]

        user_details = ', '.join([f"{key}: {value}" for key, value in user.items()])

        # Limit transaction details to the first 3 transactions
        transaction_details_list = [
            ', '.join([f"{key}: {value}" for key, value in transaction.items()])
            for transaction in transactions  # Fetch only the first 3 transactions
        ]
        transaction_details = '\n'.join(transaction_details_list)

        completion_message = (
            f"You are a DIDx Customer Whatsapp Bot. User details: {user_details}. DIDs: {', '.join(dids_details_list)}. Transactions: {transaction_details}"
        )

        try:
            completion = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": completion_message},
                    {"role": "user", "content": message_body}
                ]
            )

            answer = completion.choices[0].message.content
            logging.debug(f"OpenAI response: {answer}")

        except Exception as e:
            logging.error(f"Error generating response from OpenAI: {e}")
            answer = "Sorry, I'm having trouble processing your request."

    except mysql.connector.Error as err:
        logging.error(f"MySQL Error: {err}")
        answer = "Sorry, I encountered a database error."

    finally:
        cursor.close()
        conn.close()

    response = MessagingResponse()
    response.message(answer)
    return str(response)


if __name__ == '__main__':
    # app.run(debug=True, port=8000)
    app.run(port=80,host='0.0.0.0')

