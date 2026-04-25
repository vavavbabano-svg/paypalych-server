from flask import Flask, request, jsonify
import logging
import json
import os
import requests
from datetime import datetime

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
TON_SEED = os.environ.get("TON_SEED", "")
ADMIN_TG_ID = os.environ.get("ADMIN_TG_ID", "1444520038")
ENOT_SHOP_ID = os.environ.get("ENOT_SHOP_ID", "c2d5e47109ad1d1bccaacdde76130c892a7b5a47")
ENOT_SECRET_KEY = os.environ.get("ENOT_SECRET_KEY", "1bc606d038c11a6380d65872e9946e3a00504337")
ENOT_API_URL = "https://api.enot.io"

# Fragment API
try:
    from fragment_api_lib.client import FragmentAPIClient
    fragment = FragmentAPIClient()
    FRAGMENT_READY = True
    logger.info("✅ Fragment API готов")
except Exception as e:
    FRAGMENT_READY = False
    logger.warning(f"⚠️ Fragment API не загружен: {e}")


def buy_stars_for_user(username: str, stars: int) -> bool:
    if not FRAGMENT_READY or not TON_SEED:
        logger.error("❌ Fragment API не доступен")
        return False
    
    try:
        clean_username = username.replace("@", "")
        logger.info(f"🛒 Покупаю {stars} звёзд для @{clean_username}")
        result = fragment.buy_stars_without_kyc(
            username=clean_username,
            amount=stars,
            seed=TON_SEED
        )
        logger.info(f"✅ Звёзды куплены: {result}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка покупки звёзд: {e}")
        return False


def send_telegram_notification(text: str):
    bot_token = os.environ.get("BOT_TOKEN", "")
    if not bot_token:
        return
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, json={"chat_id": ADMIN_TG_ID, "text": text}, timeout=5)
    except:
        pass


@app.route("/create-invoice", methods=["POST"])
def create_invoice():
    """Создание счёта через Enot API"""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Нет данных"}), 400
    
    stars = data.get("stars")
    amount = data.get("amount")
    currency = data.get("currency", "RUB")
    username = data.get("username", "unknown")
    
    if not stars or not amount:
        return jsonify({"error": "Не хватает данных"}), 400
    
    payload = {
        "shopId": ENOT_SHOP_ID,
        "amount": str(amount),
        "orderId": f"stars-{stars}-{int(datetime.now().timestamp())}",
        "currency": currency,
        "hookUrl": "https://paypalych-server.onrender.com/paypalych/result",
        "successUrl": "https://telegram-mini-app.vavavbabano.workers.dev/success.html",
        "failUrl": "https://telegram-mini-app.vavavbabano.workers.dev/fail.html",
        "customFields": {
            "username": username,
            "stars": str(stars)
        }
    }
    
    headers = {
        "x-api-key": ENOT_SECRET_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        logger.info(f"📤 Создаю счёт в Enot: {json.dumps(payload, indent=2)}")
        response = requests.post(f"{ENOT_API_URL}/invoice/create", json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        invoice_data = response.json()
        logger.info(f"✅ Счёт создан: {invoice_data}")
        
        if invoice_data.get("url"):
            return jsonify({"url": invoice_data["url"]}), 200
        else:
            return jsonify({"error": "Не получена ссылка на оплату"}), 500
    
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка Enot API: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/paypalych/result", methods=["POST"])
def paypalych_result():
    """Обработка результата платежа от Enot"""
    
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    
    logger.info(f"📥 Result URL: {json.dumps(data, indent=2, ensure_ascii=False)}")
    
    order_id = data.get("orderId") or data.get("order_id") or data.get("order")
    amount = data.get("amount") or data.get("Amount") or data.get("sum")
    status = data.get("status") or data.get("Status") or data.get("payment_status")
    
    # Enot передаёт customFields
    custom_fields = data.get("customFields", {})
    if isinstance(custom_fields, str):
        try:
            custom_fields = json.loads(custom_fields)
        except:
            custom_fields = {}
    
    username = custom_fields.get("username") or data.get("username")
    stars = custom_fields.get("stars") or data.get("stars")
    
    if status in ["success", "paid", "completed", "1", "ok"]:
        logger.info(f"✅ Заказ #{order_id} оплачен: {amount}")
        
        if username and stars:
            stars_int = int(stars) if stars else 0
            if stars_int > 0:
                success = buy_stars_for_user(username, stars_int)
                if success:
                    send_telegram_notification(
                        f"✅ Автопокупка звёзд\n"
                        f"Заказ: #{order_id}\n"
                        f"Кому: @{username}\n"
                        f"Звёзд: {stars_int}\n"
                        f"Сумма: {amount}"
                    )
    
    elif status in ["fail", "failed", "error", "0", "cancelled"]:
        logger.warning(f"❌ Заказ #{order_id} не оплачен: {status}")
    
    return "OK", 200


@app.route("/paypalych/refund", methods=["POST"])
def paypalych_refund():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    logger.info(f"💰 Refund: {json.dumps(data, indent=2, ensure_ascii=False)}")
    return "OK", 200


@app.route("/paypalych/chargeback", methods=["POST"])
def paypalych_chargeback():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    logger.warning(f"⚠️ Chargeback: {json.dumps(data, indent=2, ensure_ascii=False)}")
    send_telegram_notification(f"🚨 ЧАРДЖБЭК!\n{json.dumps(data, indent=2)}")
    return "OK", 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "fragment": "ready" if FRAGMENT_READY else "not_loaded",
        "enot": "configured" if ENOT_SHOP_ID else "not_configured",
        "timestamp": datetime.now().isoformat()
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
