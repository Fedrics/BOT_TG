import os

API_TOKEN = os.environ.get("API_TOKEN", "")
CRYPTO_PAY_TOKEN = os.environ.get("CRYPTO_PAY_TOKEN", "")
CRYPTO_PAY_API = "https://pay.crypt.bot/api"

from flask import Flask, render_template

app = Flask(__name__, static_folder='../static', template_folder='../webapp')

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(port=8080, debug=True)