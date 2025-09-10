from flask import Flask, send_from_directory
import os

app = Flask(__name__, static_folder='static', template_folder='webapp')

@app.route('/')
def index():
    return send_from_directory('webapp', 'index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)