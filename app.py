from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
import sqlite3
import datetime
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Database setup
DATABASE = 'fraud_history.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with app.app_context():
        conn = get_db_connection()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                amount REAL,
                transaction_type TEXT,
                location TEXT,
                prediction INTEGER,
                probability REAL,
                risk_level TEXT
            )
        ''')
        conn.commit()
        conn.close()

# Dummy ML Model Training (replace with a real model in production)
model = None
training_columns = None # Store the columns used during training for consistent preprocessing

def train_dummy_model():
    global model, training_columns
    data = {
        'amount': [100, 500, 1000, 50, 200, 700, 1200, 80, 300, 600, 1500, 120, 400, 800, 2000],
        'transaction_type': ['online_purchase', 'online_purchase', 'transfer', 'recharge', 'bill_payment', 'transfer', 'online_purchase', 'recharge', 'bill_payment', 'transfer', 'online_purchase', 'recharge', 'bill_payment', 'transfer', 'online_purchase'],
        'location': ['home', 'work', 'other', 'home', 'work', 'other', 'home', 'work', 'other', 'home', 'work', 'other', 'home', 'work', 'other'],
        'is_fraud': [0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1]
    }
    df = pd.DataFrame(data)

    df_encoded = pd.get_dummies(df, columns=['transaction_type', 'location'])

    X = df_encoded.drop('is_fraud', axis=1)
    y = df_encoded['is_fraud']

    training_columns = X.columns.tolist()

    X = X.astype(float)

    model = RandomForestClassifier(random_state=42)
    model.fit(X, y)
    print("Dummy ML model trained successfully.")

# Pre-process input for the dummy model
def preprocess_input(data):
    global training_columns
    if training_columns is None:
        raise RuntimeError("Model not trained or training_columns not set.")

    input_df = pd.DataFrame([data])

    input_df_encoded = pd.get_dummies(input_df, columns=['transaction_type', 'location'])

    processed_input = input_df_encoded.reindex(columns=training_columns, fill_value=0.0)

    return processed_input.astype(float)


@app.route('/api/predict_fraud', methods=['POST'])
def predict_fraud():
    data = request.json
    app.logger.info(f"Received fraud prediction request with data: {data}")

    amount = data.get('amount')
    transaction_type = data.get('transaction_type', 'other')
    location = data.get('location', 'unknown')
    user_id = data.get('user_id', 'guest_user')

    if amount is None:
        return jsonify({"error": "Amount is required"}), 400

    try:
        processed_input = preprocess_input({
            'amount': amount,
            'transaction_type': transaction_type,
            'location': location
        })

        prediction_proba = model.predict_proba(processed_input)[0]
        fraud_probability = prediction_proba[1]
        prediction = 1 if fraud_probability > 0.5 else 0

        risk_level = "LOW"
        if fraud_probability > 0.75:
            risk_level = "HIGH"
        elif fraud_probability > 0.4:
            risk_level = "MEDIUM"

        cnn_confidence = fraud_probability * 0.95
        simple_confidence = fraud_probability * 0.85
        if prediction == 0:
            cnn_confidence = (1 - fraud_probability) * 0.95
            simple_confidence = (1 - fraud_probability) * 0.85

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO history (user_id, amount, transaction_type, location, prediction, probability, risk_level) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, amount, transaction_type, location, prediction, fraud_probability, risk_level)
        )
        conn.commit()
        conn.close()

        app.logger.info(f"Prediction result: {prediction}, probability: {fraud_probability}, risk: {risk_level}")
        return jsonify({
            "prediction": prediction,
            "probability": fraud_probability,
            "risk_level": risk_level,
            "cnn_confidence": cnn_confidence,
            "simple_confidence": simple_confidence
        })
    except Exception as e:
        app.logger.error(f"Error during fraud prediction: {e}", exc_info=True)
        return jsonify({"error": "Internal Server Error during prediction", "details": str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    user_id = request.args.get('user_id', 'guest_user')
    app.logger.info(f"Fetching history for user_id: {user_id}")

    conn = get_db_connection()
    cursor = conn.execute("SELECT * FROM history WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(history)

# Initialize the database and train the dummy model when the app starts
with app.app_context():
    init_db()
    train_dummy_model()

if __name__ == '__main__':
    if os.path.exists(DATABASE):
        os.remove(DATABASE)
    init_db()
    train_dummy_model()

    app.run(debug=True, port=5000)