from flask import Flask, request, jsonify
import pandas as pd
import os

app = Flask(__name__)

# صفحة بسيطة للتأكد أن السيرفر شغال
@app.route('/', methods=['GET'])
def home():
    return "Trading Bot is Live!"

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        candles = data.get('candles')
        if not candles:
            return jsonify({"error": "No candles data provided"}), 400
            
        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["close"] = df["close"].astype(float)
        
        # RSI calculation
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))
        
        last_row = df.iloc[-1]
        
        return jsonify({
            "signal": "WAIT", # مؤقتاً للتجربة
            "rsi": round(last_row["rsi"], 2) if not pd.isna(last_row["rsi"]) else 0,
            "price": last_row["close"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
