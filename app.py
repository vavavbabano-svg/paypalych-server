from flask import Flask, request, jsonify
import logging
import json
import os

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route("/paypalych/result", methods=["POST"])
def paypalych_result():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    
    logger.info(f"📥 Result URL: {json.dumps(data, indent=2, ensure_ascii=False)}")
    
    order_id = data.get("order_id") or data.get("OrderId") or data.get("order")
    amount = data.get("amount") or data.get("Amount") or data.get("sum")
    status = data.get("status") or data.get("Status") or data.get("payment_status")
    
    if status in ["success", "paid", "completed", "1", "ok"]:
        logger.info(f"✅ Заказ #{order_id} оплачен: {amount}")
    elif status in ["fail", "failed", "error", "0", "cancelled"]:
        logger.warning(f"❌ Заказ #{order_id} не оплачен")
    
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
    return "OK", 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
