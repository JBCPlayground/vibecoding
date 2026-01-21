"""URL Shortener module with Flask web API and SQLite storage."""

import hashlib
import sqlite3
import string
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from flask import Flask, redirect, request, jsonify, render_template_string

# Base62 characters for short codes
BASE62_CHARS = string.ascii_letters + string.digits

# Database path
DB_PATH = Path(__file__).parent / "urls.db"

# HTML template for the home page
HOME_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URL Shortener</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 90%;
            max-width: 500px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            text-align: center;
        }
        .subtitle {
            color: #666;
            text-align: center;
            margin-bottom: 30px;
        }
        .input-group {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        input[type="url"] {
            flex: 1;
            padding: 15px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input[type="url"]:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            padding: 15px 25px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        .result {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            display: none;
        }
        .result.show { display: block; }
        .result-label {
            color: #666;
            font-size: 14px;
            margin-bottom: 8px;
        }
        .result-link {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .result-link a {
            color: #667eea;
            font-size: 18px;
            word-break: break-all;
        }
        .copy-btn {
            padding: 8px 15px;
            font-size: 14px;
        }
        .stats {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
            text-align: center;
            color: #666;
        }
        .error {
            color: #e74c3c;
            padding: 10px;
            background: #fdeaea;
            border-radius: 8px;
            margin-bottom: 20px;
            display: none;
        }
        .error.show { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔗 URL Shortener</h1>
        <p class="subtitle">Make your long URLs short and shareable</p>
        
        <div class="error" id="error"></div>
        
        <div class="input-group">
            <input type="url" id="urlInput" placeholder="Paste your long URL here..." required>
            <button onclick="shortenUrl()">Shorten</button>
        </div>
        
        <div class="result" id="result">
            <div class="result-label">Your shortened URL:</div>
            <div class="result-link">
                <a href="#" id="shortUrl" target="_blank"></a>
                <button class="copy-btn" onclick="copyUrl()">Copy</button>
            </div>
        </div>
        
        <div class="stats">
            <p>Total URLs shortened: <strong id="totalUrls">{{ total_urls }}</strong></p>
        </div>
    </div>
    
    <script>
        async function shortenUrl() {
            const urlInput = document.getElementById('urlInput');
            const url = urlInput.value.trim();
            const errorDiv = document.getElementById('error');
            const resultDiv = document.getElementById('result');
            
            errorDiv.classList.remove('show');
            resultDiv.classList.remove('show');
            
            if (!url) {
                errorDiv.textContent = 'Please enter a URL';
                errorDiv.classList.add('show');
                return;
            }
            
            try {
                const response = await fetch('/api/shorten', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    document.getElementById('shortUrl').href = data.short_url;
                    document.getElementById('shortUrl').textContent = data.short_url;
                    resultDiv.classList.add('show');
                    document.getElementById('totalUrls').textContent = data.total_urls;
                } else {
                    errorDiv.textContent = data.error || 'Something went wrong';
                    errorDiv.classList.add('show');
                }
            } catch (err) {
                errorDiv.textContent = 'Network error. Please try again.';
                errorDiv.classList.add('show');
            }
        }
        
        function copyUrl() {
            const shortUrl = document.getElementById('shortUrl').textContent;
            navigator.clipboard.writeText(shortUrl).then(() => {
                const btn = document.querySelector('.copy-btn');
                btn.textContent = 'Copied!';
                setTimeout(() => btn.textContent = 'Copy', 2000);
            });
        }
        
        document.getElementById('urlInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') shortenUrl();
        });
    </script>
</body>
</html>
"""


def init_db():
    """Initialize the SQLite database with the urls table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            short_code TEXT UNIQUE NOT NULL,
            original_url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            clicks INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def generate_short_code(url: str, length: int = 6) -> str:
    """Generate a short code from a URL using hash-based encoding."""
    # Create a hash of the URL
    hash_object = hashlib.md5(url.encode())
    hash_int = int(hash_object.hexdigest(), 16)
    
    # Convert to base62
    code = []
    while hash_int and len(code) < length:
        code.append(BASE62_CHARS[hash_int % 62])
        hash_int //= 62
    
    return ''.join(code) or BASE62_CHARS[0] * length


def is_valid_url(url: str) -> bool:
    """Validate if the given string is a proper URL."""
    try:
        result = urlparse(url)
        return all([result.scheme in ('http', 'https'), result.netloc])
    except Exception:
        return False


def get_url_by_code(short_code: str) -> Optional[str]:
    """Retrieve the original URL by its short code."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT original_url FROM urls WHERE short_code = ?", (short_code,))
    result = cursor.fetchone()
    
    if result:
        # Increment click count
        cursor.execute("UPDATE urls SET clicks = clicks + 1 WHERE short_code = ?", (short_code,))
        conn.commit()
    
    conn.close()
    return result[0] if result else None


def get_existing_short_code(url: str) -> Optional[str]:
    """Check if URL already exists and return its short code."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT short_code FROM urls WHERE original_url = ?", (url,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def save_url(short_code: str, original_url: str) -> bool:
    """Save a new URL mapping to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO urls (short_code, original_url) VALUES (?, ?)",
            (short_code, original_url)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Short code already exists, generate a new one with timestamp
        new_code = generate_short_code(original_url + str(datetime.now()))
        cursor.execute(
            "INSERT INTO urls (short_code, original_url) VALUES (?, ?)",
            (new_code, original_url)
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_total_urls() -> int:
    """Get the total number of shortened URLs."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM urls")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Initialize database on startup
    init_db()
    
    @app.route('/')
    def home():
        """Render the home page with URL shortening form."""
        total_urls = get_total_urls()
        return render_template_string(HOME_TEMPLATE, total_urls=total_urls)
    
    @app.route('/api/shorten', methods=['POST'])
    def shorten_url():
        """API endpoint to shorten a URL."""
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'error': 'URL is required'}), 400
        
        original_url = data['url'].strip()
        
        # Add http:// if no scheme provided
        if not original_url.startswith(('http://', 'https://')):
            original_url = 'https://' + original_url
        
        if not is_valid_url(original_url):
            return jsonify({'error': 'Invalid URL format'}), 400
        
        # Check if URL already exists
        existing_code = get_existing_short_code(original_url)
        if existing_code:
            short_code = existing_code
        else:
            short_code = generate_short_code(original_url)
            save_url(short_code, original_url)
        
        short_url = f"{request.host_url}{short_code}"
        
        return jsonify({
            'short_url': short_url,
            'short_code': short_code,
            'original_url': original_url,
            'total_urls': get_total_urls()
        })
    
    @app.route('/api/stats/<short_code>')
    def get_stats(short_code: str):
        """Get statistics for a shortened URL."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT original_url, created_at, clicks FROM urls WHERE short_code = ?",
            (short_code,)
        )
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return jsonify({'error': 'URL not found'}), 404
        
        return jsonify({
            'short_code': short_code,
            'original_url': result[0],
            'created_at': result[1],
            'clicks': result[2]
        })
    
    @app.route('/<short_code>')
    def redirect_to_url(short_code: str):
        """Redirect short code to original URL."""
        original_url = get_url_by_code(short_code)
        
        if original_url:
            return redirect(original_url)
        
        return jsonify({'error': 'URL not found'}), 404
    
    return app


def run_server(host: str = '0.0.0.0', port: int = 5000, debug: bool = True):
    """Run the URL shortener web server."""
    app = create_app()
    print(f"\n🔗 URL Shortener running at http://localhost:{port}")
    print("   Press Ctrl+C to stop\n")
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    run_server()
