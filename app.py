from flask import Flask, request, jsonify
import logging
import json
import os
import requests
from datetime import datetime, date

app = Flask(__name__)

# CORS вручную (без flask-cors)
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, x-api-key"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ ====================
TON_SEED = os.environ.get("TON_SEED", "")
ADMIN_TG_ID = os.environ.get("ADMIN_TG_ID", "1444520038")
ENOT_SHOP_ID = os.environ.get("ENOT_SHOP_ID", "")
ENOT_SECRET_KEY = os.environ.get("ENOT_SECRET_KEY", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ENOT_API_URL = "https://api.enot.io"

# ==================== ХРАНИЛИЩА ====================
orders = []                # Все заказы
processed_orders = set()   # Защита от повторов (anti-replay)

# ==================== FRAGMENT API ====================
try:
    from fragment_api_lib.client import FragmentAPIClient
    fragment = FragmentAPIClient()
    FRAGMENT_READY = True
    logger.info("✅ Fragment API готов")
except Exception as e:
    FRAGMENT_READY = False
    logger.warning(f"⚠️ Fragment API не загружен: {e}")


# ==================== ФУНКЦИИ ====================

def buy_stars_for_user(username: str, stars: int) -> bool:
    """Покупка звёзд через Fragment API"""
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
    """Отправка уведомления в Telegram"""
    if not BOT_TOKEN:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": ADMIN_TG_ID, "text": text}, timeout=5)
    except:
        pass


# ==================== API ЭНДПОИНТЫ ====================

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
        "hookUrl": "https://paypalych-server.onrender.com/enot/result",
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
        response = requests.post(f"{ENOT_API_URL}/invoice/create", json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        invoice_data = response.json()
        if invoice_data.get("url"):
            return jsonify({"url": invoice_data["url"]}), 200
        else:
            return jsonify({"error": "Не получена ссылка на оплату"}), 500
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка Enot API: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/enot/result", methods=["POST"])
def enot_result():
    """Обработка результата платежа от ENOT"""
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    
    logger.info(f"📥 Result URL: {json.dumps(data, indent=2, ensure_ascii=False)}")
    
    order_id = data.get("orderId") or data.get("order_id") or data.get("order")
    amount = data.get("amount") or data.get("Amount") or data.get("sum")
    status = data.get("status") or data.get("Status") or data.get("payment_status")
    
    # Защита от повторов
    if order_id in processed_orders:
        logger.warning(f"⚠️ Повторный запрос для заказа #{order_id}")
        return "OK", 200
    processed_orders.add(order_id)
    
    # Разбираем customFields
    custom_fields = data.get("customFields", {})
    if isinstance(custom_fields, str):
        try:
            custom_fields = json.loads(custom_fields)
        except:
            custom_fields = {}
    
    username = custom_fields.get("username") or data.get("username")
    stars = custom_fields.get("stars") or data.get("stars")
    
    # Сохраняем заказ
    order = {
        "order_id": order_id,
        "amount": amount,
        "status": status,
        "username": username,
        "stars": stars,
        "time": datetime.now().isoformat()
    }
    orders.append(order)
    
    # Обработка успешного платежа
    if status in ["success", "paid", "completed", "1", "ok"]:
        logger.info(f"✅ Заказ #{order_id} оплачен: {amount}")
        if username and stars:
            stars_int = int(stars) if stars else 0
            if stars_int > 0:
                success = buy_stars_for_user(username, stars_int)
                order["stars_bought"] = success
                if success:
                    send_telegram_notification(
                        f"✅ Автопокупка звёзд\n"
                        f"Заказ: #{order_id}\n"
                        f"Кому: @{username}\n"
                        f"Звёзд: {stars_int}\n"
                        f"Сумма: {amount}"
                    )
                else:
                    send_telegram_notification(
                        f"⚠️ Оплата прошла, но звёзды не куплены\n"
                        f"Заказ: #{order_id}\n"
                        f"Кому: @{username}\n"
                        f"Звёзд: {stars_int}"
                    )
    
    elif status in ["fail", "failed", "error", "0", "cancelled"]:
        logger.warning(f"❌ Заказ #{order_id} не оплачен")
    
    return "OK", 200


@app.route("/enot/refund", methods=["POST"])
def enot_refund():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    logger.info(f"💰 Refund: {json.dumps(data, indent=2, ensure_ascii=False)}")
    return "OK", 200


@app.route("/enot/chargeback", methods=["POST"])
def enot_chargeback():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    logger.warning(f"⚠️ Chargeback: {json.dumps(data, indent=2, ensure_ascii=False)}")
    send_telegram_notification(f"🚨 ЧАРДЖБЭК!\n{json.dumps(data, indent=2)}")
    return "OK", 200


@app.route("/admin/stats", methods=["GET"])
def admin_stats():
    """Статистика для админки"""
    today = date.today().isoformat()
    today_orders = [o for o in orders if o.get("time", "").startswith(today)]
    today_success = [o for o in today_orders if o.get("status") in ["success", "paid", "completed", "1", "ok"]]
    
    all_success = [o for o in orders if o.get("status") in ["success", "paid", "completed", "1", "ok"]]
    
    return jsonify({
        "today": {
            "count": len(today_success),
            "amount": round(sum(float(o.get("amount", 0)) for o in today_success), 2),
            "stars": sum(int(o.get("stars", 0)) for o in today_success)
        },
        "all": {
            "count": len(all_success),
            "amount": round(sum(float(o.get("amount", 0)) for o in all_success), 2),
            "stars": sum(int(o.get("stars", 0)) for o in all_success)
        },
        "fragment_ready": FRAGMENT_READY,
        "enot_configured": bool(ENOT_SHOP_ID)
    }), 200


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
