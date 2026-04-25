from flask import Flask, request, jsonify, redirect
import requests
import os

app = Flask(__name__)

ENOT_SHOP_ID = os.environ.get("ENOT_SHOP_ID")
ENOT_SECRET_KEY = os.environ.get("ENOT_SECRET_KEY")
ENOT_API_URL = "https://api.enot.io"

@app.route('/create-invoice', methods=['POST'])
def create_invoice():
    data = request.get_json()

    # Проверяем, что все нужные данные пришли из мини-аппа
    if not data or 'stars' not in data or 'amount' not in data or 'currency' not in data:
        return jsonify({"error": "Не хватает данных"}), 400

    # Подготавливаем запрос к Enot API
    payload = {
        'shopId': ENOT_SHOP_ID,
        'amount': str(data['amount']),
        'orderId': str(data['stars']),  # Можно генерировать свой ID
        'currency': data.get('currency', 'RUB'),
        'hookUrl': "https://paypalych-server.onrender.com/paypalych/result",
        'successUrl': "https://telegram-mini-app.vavavbabano.workers.dev/success.html",
        'failUrl': "https://telegram-mini-app.vavavbabano.workers.dev/fail.html",
    }

    headers = {
        'x-api-key': ENOT_SECRET_KEY,
        'Content-Type': 'application/json'
    }

    # Отправляем запрос в Enot
    try:
        response = requests.post(f"{ENOT_API_URL}/invoice/create", json=payload, headers=headers)
        response.raise_for_status()  # Проверяем, нет ли ошибки от API
        invoice_data = response.json()

        # Возвращаем ссылку на оплату в мини-апп
        return jsonify({"url": invoice_data['url']}), 200

    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500
