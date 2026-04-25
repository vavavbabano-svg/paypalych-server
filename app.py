from flask import Flask, request, jsonify
import logging
import json
import os
from datetime import datetime

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация из переменных окружения
TON_SEED = os.environ.get("TON_SEED", "")  # 24 слова сид-фразы
ADMIN_TG_ID = os.environ.get("ADMIN_TG_ID", "1444520038")  # Твой Telegram ID

# Попробуем импортировать Fragment API
try:
    from fragment_api_lib.client import FragmentAPIClient
    fragment = FragmentAPIClient()
    FRAGMENT_READY = True
    logger.info("✅ Fragment API готов")
except Exception as e:
    FRAGMENT_READY = False
    logger.warning(f"⚠️ Fragment API не загружен: {e}")


def buy_stars_for_user(username: str, stars: int) -> bool:
    """Покупка звёзд через Fragment API"""
    if not FRAGMENT_READY:
        logger.error("❌ Fragment API не доступен")
        return False
    
    if not TON_SEED:
        logger.error("❌ TON_SEED не задан")
        return False
    
    try:
        # Убираем @ если есть
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
    """Отправка уведомления админу в Telegram (опционально)"""
    bot_token = os.environ.get("BOT_TOKEN", "")
    if not bot_token:
        return
    
    try:
        import requests
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, json={
            "chat_id": ADMIN_TG_ID,
            "text": text
        }, timeout=5)
    except:
        pass


@app.route("/paypalych/result", methods=["POST"])
def paypalych_result():
    """Обработка результата платежа от PayPalych"""
    
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    
    logger.info(f"📥 Result URL: {json.dumps(data, indent=2, ensure_ascii=False)}")
    
    # Извлекаем данные (подстроим под реальные поля PayPalych)
    order_id = data.get("order_id") or data.get("OrderId") or data.get("order")
    amount = data.get("amount") or data.get("Amount") or data.get("sum")
    currency = data.get("currency") or data.get("Currency") or "RUB"
    status = data.get("status") or data.get("Status") or data.get("payment_status")
    username = data.get("username") or data.get("Username") or data.get("customer_id")
    stars = data.get("stars") or data.get("Stars") or data.get("custom_param")
    
    if status in ["success", "paid", "completed", "1", "ok"]:
        logger.info(f"✅ Заказ #{order_id} оплачен: {amount} {currency}")
        
        # Покупаем звёзды через Fragment
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
                        f"Сумма: {amount} {currency}"
                    )
                else:
                    send_telegram_notification(
                        f"⚠️ Оплата прошла, но автопокупка не сработала\n"
                        f"Заказ: #{order_id}\n"
                        f"Кому: @{username}\n"
                        f"Звёзд: {stars_int}"
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
        "timestamp": datetime.now().isoformat()
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
