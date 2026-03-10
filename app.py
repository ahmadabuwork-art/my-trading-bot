from flask import Flask, request, jsonify
import pandas as pd

app = Flask(__name__)

def calculate_logic(df):
    # RSI
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))
    
    # MACD
    exp12 = df['close'].ewm(span=12, adjust=False).mean()
    exp26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp12 - exp26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    # Moving Averages
    df["ma_short"] = df["close"].rolling(window=10).mean()
    df["ma_long"] = df["close"].rolling(window=50).mean()
    
    # Bollinger Bands
    df["ma_bb"] = df["close"].rolling(window=20).mean()
    df["std_bb"] = df["close"].rolling(window=20).std()
    df["bollinger_upper"] = df["ma_bb"] + (df["std_bb"] * 2)
    df["bollinger_lower"] = df["ma_bb"] - (df["std_bb"] * 2)
    
    return df

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        candles = data.get('candles') 
        
        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["close"] = df["close"].astype(float)
        
        df = calculate_logic(df)
        last_row = df.iloc[-1]
        current_price = last_row["close"]

        signal = "WAIT"
        if (last_row["ma_short"] > last_row["ma_long"] and last_row["rsi"] > 30 and last_row["macd"] > last_row["macd_signal"] and current_price <= last_row["bollinger_lower"]):
            signal = "BUY"
        elif (last_row["ma_short"] < last_row["ma_long"] and last_row["rsi"] < 70 and last_row["macd"] < last_row["macd_signal"] and current_price >= last_row["bollinger_upper"]):
            signal = "SELL"

        return jsonify({
            "signal": signal,
            "rsi": round(last_row["rsi"], 2),
            "price": current_price
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
