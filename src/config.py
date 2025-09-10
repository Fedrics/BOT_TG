API_TOKEN = '8209554795:AAE_14T4HcfzG-OQaxe0cIEwc3dIOEZdy3Q'
CRYPTO_PAY_TOKEN = '458139:AAgwFIbyAD3b47y3F72NSg3eNfUlKgsXrFz'
CRYPTO_PAY_API = 'https://pay.crypt.bot/api/'

from flask import Flask, render_template

app = Flask(__name__, static_folder='../static', template_folder='../webapp')

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(port=8080, debug=True)