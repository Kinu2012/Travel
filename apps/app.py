from flask import Flask, request, jsonify, session, send_from_directory, redirect
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import secrets
from flask_mail import Mail, Message
import requests
import json
from typing import Dict, List
import random

from typing import List, Dict, Tuple
from datetime import datetime, timedelta
import math

from functools import wraps

def login_required(f):
    """ログイン必須デコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/'), 401
        return f(*args, **kwargs)
    return decorated_function

# 環境変数の読み込み
load_dotenv()
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# ベースディレクトリ（C:\travel）を取得
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# デバッグ用の出力
import sys
print("="*60, file=sys.stderr)
print(f"🔍 現在のディレクトリ: {CURRENT_DIR}", file=sys.stderr)
print(f"🔍 ベースディレクトリ: {BASE_DIR}", file=sys.stderr)

TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

print(f"🔍 テンプレートディレクトリ: {TEMPLATES_DIR}", file=sys.stderr)
print(f"🔍 存在チェック: {os.path.exists(TEMPLATES_DIR)}", file=sys.stderr)

if os.path.exists(TEMPLATES_DIR):
    print(f"📂 テンプレートファイル:", file=sys.stderr)
    try:
        for file in os.listdir(TEMPLATES_DIR):
            print(f"  - {file}", file=sys.stderr)
    except Exception as e:
        print(f"❌ エラー: {e}", file=sys.stderr)
else:
    print(f"❌ テンプレートディレクトリが見つかりません！", file=sys.stderr)
print("="*60, file=sys.stderr)

app = Flask(__name__, 
    template_folder=TEMPLATES_DIR,
    static_folder=STATIC_DIR
)

# ★★★ これを修正 ★★★
app.secret_key = os.getenv('SECRET_KEY', 'mysecretkey123')  # SECRET_KEY → secret_key
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)

# セッションCookie設定を追加
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # 開発環境用
app.config['SESSION_COOKIE_HTTPONLY'] = True

# CORS設定（1回だけ！）
CORS(app, 
     resources={r"/api/*": {"origins": "*"}},
     supports_credentials=True,
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization"])

# データベース接続設定
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:kashiwa0001@localhost:5432/travel')

def get_db_connection():
    """データベース接続を取得"""
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print(f"データベース接続エラー: {e}")
        return None

def calculate_age(birthdate_str):
    """生年月日から年齢を計算"""
    if not birthdate_str:
        return None
    try:
        birthdate = datetime.strptime(birthdate_str, '%Y-%m-%d')
        today = datetime.now()
        age = today.year - birthdate.year
        if today.month < birthdate.month or (today.month == birthdate.month and today.day < birthdate.day):
            age -= 1
        return age
    except:
        return None

@app.route('/<path:path>')
def serve_static(path):
    """静的ファイルを配信"""
    return send_from_directory(os.path.join(BASE_DIR, 'templates'), path)


@app.route('/')
def index():
    """ログインページを表示"""
    return send_from_directory(os.path.join(BASE_DIR, 'templates'), 'login.html')


@app.route('/api/login', methods=['POST'])
def login():
    """ログイン"""
    print("=== ログインリクエスト受信 ===")
    data = request.get_json()
    # セキュリティ: パスワードはログに出力しない
    print(f"ログイン試行: {data.get('email')}")
    
    email = data.get('email')
    password = data.get('password')
    
    # バリデーション
    if not email or not password:
        return jsonify({'success': False, 'message': 'メールアドレスとパスワードを入力してください'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'データベース接続エラー'}), 500
    
    try:
        cur = conn.cursor()
        
        # ユーザー検索
        cur.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        
        if not user:
            return jsonify({'success': False, 'message': 'メールアドレスまたはパスワードが正しくありません'}), 401
        
        # パスワード検証
        if not check_password_hash(user['password'], password):
            return jsonify({'success': False, 'message': 'メールアドレスまたはパスワードが正しくありません'}), 401
        
        # セッションにユーザー情報を保存
        session.permanent = True
        session['user_id'] = user['id']
        session['user_email'] = user['email']
        
        # 最終ログイン時刻を更新
        cur.execute('UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE id = %s', (user['id'],))
        conn.commit()
        
        print(f"ログイン成功: {user['email']}")
        
        return jsonify({
            'success': True,
            'message': 'ログインに成功しました',
            'user': {
                'id': user['id'],
                'user_id': user['user_id'],
                'name': user['name'],
                'email': user['email'],
                'age': user['age']
            }
        }), 200
        
    except Exception as e:
        print(f"ログインエラー: {e}")
        return jsonify({'success': False, 'message': 'サーバーエラーが発生しました'}), 500
    finally:
        cur.close()
        conn.close()



# API エンドポイント
@app.route('/api/register', methods=['POST'])
def register():
    """ユーザー登録"""
    print("=== 登録リクエスト受信 ===")
    data = request.get_json()
    # セキュリティ: パスワードはログに出力しない
    safe_data = {k: v for k, v in data.items() if k != 'password'}
    print(f"受信データ: {safe_data}")
    
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    fullname = data.get('fullname', username)
    birthdate = data.get('birthdate')
    gender = data.get('gender')
    
    # バリデーション
    if not username or not email or not password:
        return jsonify({'success': False, 'message': '必須項目を入力してください'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'データベース接続エラー'}), 500
    
    try:
        cur = conn.cursor()
        
        # メールアドレスの重複チェック
        cur.execute('SELECT * FROM users WHERE email = %s', (email,))
        if cur.fetchone():
            return jsonify({'success': False, 'message': 'このメールアドレスは既に登録されています'}), 400
        
        # ユーザーIDの重複チェック
        cur.execute('SELECT * FROM users WHERE user_id = %s', (username,))
        if cur.fetchone():
            return jsonify({'success': False, 'message': 'このユーザー名は既に使用されています'}), 400
        
        # パスワードのハッシュ化
        hashed_password = generate_password_hash(password)
        
        # 年齢計算
        age = calculate_age(birthdate)
        
        # ユーザー登録
        cur.execute(
            '''INSERT INTO users (user_id, password, name, email, age, created_at, updated_at) 
               VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) 
               RETURNING id, user_id, name, email, age, created_at''',
            (username, hashed_password, fullname, email, age)
        )
        
        user = cur.fetchone()
        conn.commit()
        
        print(f"登録成功: {user}")
        
        return jsonify({
            'success': True,
            'message': '登録が完了しました',
            'user': {
                'id': user['id'],
                'user_id': user['user_id'],
                'name': user['name'],
                'email': user['email'],
                'age': user['age']
            }
        }), 201
        
    except Exception as e:
        conn.rollback()
        print(f"登録エラー: {e}")
        return jsonify({'success': False, 'message': f'サーバーエラーが発生しました: {str(e)}'}), 500
    finally:
        cur.close()
        conn.close()



#パスワードリセット
########################################################################################################
########################################################################################################

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    """パスワードリセット"""
    print("=== パスワードリセットリクエスト受信 ===")
    data = request.get_json()
    
    token = data.get('token')
    new_password = data.get('newPassword')
    
    # バリデーション
    if not token or not new_password:
        return jsonify({'success': False, 'message': '必須項目を入力してください'}), 400
    
    if len(new_password) < 8:
        return jsonify({'success': False, 'message': 'パスワードは8文字以上で入力してください'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'データベース接続エラー'}), 500
    
    try:
        cur = conn.cursor()
        
        # トークンを検索（有効期限内、未使用）
        cur.execute(
            '''SELECT prt.*, u.email 
               FROM password_reset_tokens prt
               JOIN users u ON prt.user_id = u.id
               WHERE prt.token = %s 
               AND prt.expires_at > CURRENT_TIMESTAMP 
               AND prt.used = FALSE''',
            (token,)
        )
        
        token_data = cur.fetchone()
        
        if not token_data:
            return jsonify({
                'success': False, 
                'message': '無効または期限切れのトークンです'
            }), 400
        
        user_id = token_data['user_id']
        
        # パスワードをハッシュ化
        hashed_password = generate_password_hash(new_password)
        
        # パスワードを更新
        cur.execute(
            'UPDATE users SET password = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s',
            (hashed_password, user_id)
        )
        
        # トークンを使用済みにする
        cur.execute(
            'UPDATE password_reset_tokens SET used = TRUE WHERE token = %s',
            (token,)
        )
        
        conn.commit()
        
        print(f"パスワードリセット成功: {token_data['email']}")
        
        return jsonify({
            'success': True,
            'message': 'パスワードが正常に変更されました'
        }), 200
        
    except Exception as e:
        conn.rollback()
        print(f"パスワードリセットエラー: {e}")
        return jsonify({'success': False, 'message': 'サーバーエラーが発生しました'}), 500
    finally:
        cur.close()
        conn.close()

# forgot-passwordエンドポイント内で使用
@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    """パスワード復元リクエスト"""
    print("=== パスワード復元リクエスト受信 ===")
    data = request.get_json()
    email = data.get('email')
    
    if not email:
        return jsonify({'success': False, 'message': 'メールアドレスを入力してください'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'データベース接続エラー'}), 500
    
    try:
        cur = conn.cursor()
        
        # ユーザー検索
        cur.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        
        if not user:
            print(f"ユーザーが見つかりません: {email}")
            # セキュリティ: ユーザーが存在しなくても成功メッセージを返す
            return jsonify({
                'success': True,
                'message': 'パスワード復元メールを送信しました'
            }), 200
        
        # トークン生成
        reset_token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=1)
        
        # 既存の未使用トークンを無効化
        cur.execute(
            'UPDATE password_reset_tokens SET used = TRUE WHERE user_id = %s AND used = FALSE',
            (user['id'],)
        )
        
        # 新しいトークンを保存
        cur.execute(
            '''INSERT INTO password_reset_tokens (user_id, token, expires_at) 
               VALUES (%s, %s, %s)''',
            (user['id'], reset_token, expires_at)
        )
        
        conn.commit()
        
        # リセットURL生成
        # 本番環境では実際のドメインに変更
        reset_url = f"http://localhost:5000/reset-password.html?token={reset_token}"
        
        # メール送信
        email_sent = send_password_reset_email(
            to_email=email,
            reset_url=reset_url,
            user_name=user.get('name')
        )
        
        if email_sent:
            print(f"パスワードリセットメール送信成功: {email}")
        else:
            print(f"パスワードリセットメール送信失敗: {email}")
            # メール送信失敗でもトークンは生成されているので、
            # 開発環境ではコンソールにURLを出力
            print(f"リセットURL: {reset_url}")
        
        return jsonify({
            'success': True,
            'message': 'パスワード復元メールを送信しました'
        }), 200
        
    except Exception as e:
        conn.rollback()
        print(f"パスワード復元エラー: {e}")
        return jsonify({'success': False, 'message': 'サーバーエラーが発生しました'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/api/verify-reset-token', methods=['POST'])
def verify_reset_token():
    """リセットトークンの有効性を確認"""
    data = request.get_json()
    token = data.get('token')
    
    if not token:
        return jsonify({'success': False, 'message': 'トークンが必要です'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'データベース接続エラー'}), 500
    
    try:
        cur = conn.cursor()
        
        # トークンを検索
        cur.execute(
            '''SELECT * FROM password_reset_tokens 
               WHERE token = %s 
               AND expires_at > CURRENT_TIMESTAMP 
               AND used = FALSE''',
            (token,)
        )
        
        token_data = cur.fetchone()
        
        if token_data:
            return jsonify({'success': True, 'valid': True}), 200
        else:
            return jsonify({'success': True, 'valid': False}), 200
        
    except Exception as e:
        print(f"トークン検証エラー: {e}")
        return jsonify({'success': False, 'message': 'サーバーエラーが発生しました'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/logout', methods=['POST'])
def logout():
    """ログアウト"""
    session.clear()
    return jsonify({'success': True, 'message': 'ログアウトしました'}), 200

@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user_by_id(user_id):
    """指定されたユーザーの情報を取得"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'データベース接続エラー'}), 500
    
    try:
        cur = conn.cursor()
        cur.execute(
            'SELECT id, user_id, name, email, age, created_at FROM users WHERE id = %s',
            (user_id,)
        )
        user = cur.fetchone()
        
        if not user:
            return jsonify({'success': False, 'message': 'ユーザーが見つかりません'}), 404
        
        return jsonify(dict(user)), 200
        
    except Exception as e:
        print(f"ユーザー情報取得エラー: {e}")
        return jsonify({'success': False, 'message': 'サーバーエラーが発生しました'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/api/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    """ユーザー情報を更新"""
    data = request.get_json()
    print(f"=== ユーザー更新リクエスト受信 (ID: {user_id}) ===")
    
    name = data.get('name')
    email = data.get('email')
    age = data.get('age')
    password = data.get('password')  # オプション
    
    # バリデーション
    if not name or not email:
        return jsonify({'success': False, 'error': '名前とメールアドレスは必須です'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'データベース接続エラー'}), 500
    
    try:
        cur = conn.cursor()
        
        # ユーザーの存在確認
        cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
        user = cur.fetchone()
        if not user:
            return jsonify({'success': False, 'error': 'ユーザーが見つかりません'}), 404
        
        # メールアドレスの重複チェック（自分以外）
        cur.execute('SELECT * FROM users WHERE email = %s AND id != %s', (email, user_id))
        if cur.fetchone():
            return jsonify({'success': False, 'error': 'このメールアドレスは既に使用されています'}), 400
        
        # パスワードが指定されている場合はハッシュ化して更新
        if password:
            hashed_password = generate_password_hash(password)
            cur.execute(
                '''UPDATE users 
                   SET name = %s, email = %s, age = %s, password = %s, updated_at = CURRENT_TIMESTAMP 
                   WHERE id = %s''',
                (name, email, age, hashed_password, user_id)
            )
        else:
            # パスワードなしで更新
            cur.execute(
                '''UPDATE users 
                   SET name = %s, email = %s, age = %s, updated_at = CURRENT_TIMESTAMP 
                   WHERE id = %s''',
                (name, email, age, user_id)
            )
        
        conn.commit()
        
        print(f"ユーザー更新成功: {email}")
        
        return jsonify({
            'success': True,
            'message': 'ユーザー情報を更新しました'
        }), 200
        
    except Exception as e:
        conn.rollback()
        print(f"ユーザー更新エラー: {e}")
        return jsonify({'success': False, 'error': f'サーバーエラーが発生しました: {str(e)}'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/user', methods=['GET'])
def get_user():
    """ログイン中のユーザー情報を取得"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '認証が必要です'}), 401
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'データベース接続エラー'}), 500
    
    try:
        cur = conn.cursor()
        cur.execute(
            'SELECT id, user_id, name, email, age, created_at FROM users WHERE id = %s',
            (session['user_id'],)
        )
        user = cur.fetchone()
        
        if not user:
            return jsonify({'success': False, 'message': 'ユーザーが見つかりません'}), 404
        
        return jsonify({
            'success': True,
            'user': dict(user)
        }), 200
        
    except Exception as e:
        print(f"ユーザー情報取得エラー: {e}")
        return jsonify({'success': False, 'message': 'サーバーエラーが発生しました'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/spots', methods=['GET'])
def get_spots():
    """スポットデータを取得"""
    import json
    
    try:
        # dataフォルダからspots.jsonを読み込む
        spots_file = os.path.join(BASE_DIR, 'data', 'spots.json')
        
        if not os.path.exists(spots_file):
            return jsonify({'success': False, 'message': 'スポットデータが見つかりません'}), 404
        
        with open(spots_file, 'r', encoding='utf-8') as f:
            spots_data = json.load(f)
        
        return jsonify({
            'success': True,
            'data': spots_data
        }), 200
        
    except Exception as e:
        print(f"スポットデータ読み込みエラー: {e}")
        return jsonify({'success': False, 'message': 'データの読み込みに失敗しました'}), 500

if __name__ == '__main__':
    # データベース接続確認
    conn = get_db_connection()
    if conn:
        print("データベースに接続しました")
        conn.close()
    else:
        print("データベース接続に失敗しました")
    
    # 本番環境ではdebug=Falseにすること
    is_debug = os.getenv('FLASK_ENV') == 'development'
    app.run(debug=is_debug, host='0.0.0.0', port=5000)

# app.pyの既存の設定部分に追加
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', 'testyuneten@gmail.com')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', 'pqof lmqn nyhm uxob')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'testyuneten@gmail.com')

mail = Mail(app)

# メール送信関数
def send_password_reset_email(to_email, reset_url, user_name=None):
    """パスワードリセットメールを送信"""
    try:
        msg = Message(
            subject='【旅行プランサービス】パスワードリセットのご案内',
            recipients=[to_email]
        )
        
        # HTMLメール
        msg.html = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .container {{
                    background: #f8f9fa;
                    border-radius: 10px;
                    padding: 30px;
                    margin: 20px 0;
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .header h1 {{
                    color: #ff6b6b;
                    margin: 0;
                }}
                .content {{
                    background: white;
                    border-radius: 8px;
                    padding: 25px;
                    margin: 20px 0;
                }}
                .button {{
                    display: inline-block;
                    padding: 15px 30px;
                    background: linear-gradient(135deg, #ff9a44, #ff6b6b);
                    color: white;
                    text-decoration: none;
                    border-radius: 25px;
                    font-weight: bold;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    color: #7f8c8d;
                    font-size: 12px;
                    margin-top: 30px;
                }}
                .warning {{
                    background: #fff3cd;
                    border-left: 4px solid #ffc107;
                    padding: 15px;
                    margin: 20px 0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔒 パスワードリセット</h1>
                </div>
                
                <div class="content">
                    <p>こんにちは{", " + user_name if user_name else ""}様</p>
                    
                    <p>パスワードのリセットリクエストを受け付けました。</p>
                    
                    <p>以下のボタンをクリックして、新しいパスワードを設定してください：</p>
                    
                    <div style="text-align: center;">
                        <a href="{reset_url}" class="button">パスワードをリセット</a>
                    </div>
                    
                    <div class="warning">
                        <strong>⚠️ 注意事項</strong>
                        <ul>
                            <li>このリンクは<strong>1時間</strong>有効です</li>
                            <li>リンクは一度のみ使用できます</li>
                            <li>このメールに心当たりがない場合は、無視してください</li>
                        </ul>
                    </div>
                    
                    <p style="color: #7f8c8d; font-size: 14px;">
                        ボタンが動作しない場合は、以下のURLをブラウザにコピー&ペーストしてください：<br>
                        <a href="{reset_url}" style="color: #3498db;">{reset_url}</a>
                    </p>
                </div>
                
                <div class="footer">
                    <p>このメールは旅行プランサービスから自動送信されています。</p>
                    <p>© 2025 旅行プランサービス</p>
                </div>
            </div>
        </body>
        </html>
        '''
        
        # テキスト版（HTMLが表示できない場合のフォールバック）
        msg.body = f'''
パスワードリセットのご案内

こんにちは{", " + user_name if user_name else ""}様

パスワードのリセットリクエストを受け付けました。

以下のリンクをクリックして、新しいパスワードを設定してください：
{reset_url}

【注意事項】
・このリンクは1時間有効です
・リンクは一度のみ使用できます
・このメールに心当たりがない場合は、無視してください

---
このメールは旅行プランサービスから自動送信されています。
© 2025 旅行プランサービス
        '''
        
        mail.send(msg)
        print(f"パスワードリセットメール送信成功: {to_email}")
        return True
        
    except Exception as e:
        print(f"メール送信エラー: {e}")
        return False
    
#######################################################################################################
#######################################################################################################


    
import re
import requests
from flask import jsonify, request

#API連携、スポット検索
########################################################################################################
########################################################################################################

@app.route('/api/overpass-spots', methods=['GET'])
def get_overpass_spots():
    """Overpass APIから厳選された観光スポットのみを取得"""

    overpass_query = """
    [out:json][timeout:25];
    (
      node["historic"="castle"](33.5,134.5,35.8,136.8);
      way["historic"="castle"](33.5,134.5,35.8,136.8);

      node["amenity"="place_of_worship"]["religion"="buddhist"]["wikidata"](33.5,134.5,35.8,136.8);
      node["amenity"="place_of_worship"]["religion"="shinto"]["wikidata"](33.5,134.5,35.8,136.8);

      node["tourism"="museum"](33.5,134.5,35.8,136.8);
      way["tourism"="museum"](33.5,134.5,35.8,136.8);
      node["tourism"="gallery"](33.5,134.5,35.8,136.8);

      node["tourism"="theme_park"](33.5,134.5,35.8,136.8);
      way["tourism"="theme_park"](33.5,134.5,35.8,136.8);

      node["heritage"="1"](33.5,134.5,35.8,136.8);
      way["heritage"="1"](33.5,134.5,35.8,136.8);
      relation["heritage"="1"](33.5,134.5,35.8,136.8);

      node["leisure"="park"]["operator"~"国"](33.5,134.5,35.8,136.8);

      node["amenity"="theatre"](33.5,134.5,35.8,136.8);

      node["amenity"~"restaurant|cafe|fast_food|food_court|bar|pub"](33.5,134.5,35.8,136.8);

      node["amenity"="library"](33.5,134.5,35.8,136.8);
      node["amenity"="cinema"](33.5,134.5,35.8,136.8);
      node["leisure"="water_park"](33.5,134.5,35.8,136.8);
      node["tourism"="zoo"](33.5,134.5,35.8,136.8);
      node["tourism"="aquarium"](33.5,134.5,35.8,136.8);
      node["tourism"="viewpoint"](33.5,134.5,35.8,136.8);
    );
    out body 150;
    """

    try:
        overpass_url = "http://overpass-api.de/api/interpreter"
        response = requests.post(overpass_url, data={'data': overpass_query}, timeout=30)

        if response.status_code != 200:
            return jsonify({'success': False, 'message': 'Overpass APIからのデータ取得に失敗しました'}), 500

        data = response.json()
        spots_dict = {}

        for element in data.get('elements', []):
            if 'tags' not in element:
                continue

            tags = element['tags']
            element_id = element.get('id')
            lat = element.get('lat') or element.get('center', {}).get('lat')
            lon = element.get('lon') or element.get('center', {}).get('lon')
            name = tags.get('name:ja') or tags.get('name') or tags.get('name:en')

            if not name or name == '名称不明':
                continue
            if len(name) > 40:
                continue

            bad_keywords = ['詰所', '案内', '地図', '乗り場', '駐車場', 'トイレ',
                            '入口', '出口', '受付', '売店', 'ゲート', '記念碑']
            if any(keyword in name for keyword in bad_keywords):
                continue
            if any(keyword in str(value) for value in tags.values() for keyword in bad_keywords):
                continue

            if lat and lon and element_id not in spots_dict:
                spot_type = 'その他'
                if tags.get('historic') == 'castle':
                    spot_type = '城'
                elif tags.get('religion') == 'buddhist':
                    spot_type = '寺院'
                elif tags.get('religion') == 'shinto':
                    spot_type = '神社'
                elif tags.get('tourism') == 'museum':
                    spot_type = '博物館'
                elif tags.get('tourism') == 'gallery':
                    spot_type = '美術館'
                elif tags.get('tourism') == 'theme_park':
                    spot_type = 'テーマパーク'
                elif tags.get('heritage') == '1':
                    spot_type = '世界遺産'
                elif tags.get('leisure') == 'park':
                    spot_type = '公園'
                elif tags.get('amenity') == 'theatre':
                    spot_type = '劇場'
                elif tags.get('amenity') in ['restaurant', 'cafe', 'fast_food', 'food_court', 'bar', 'pub']:
                    spot_type = '飲食店'
                elif tags.get('amenity') == 'library':
                    spot_type = '図書館'
                elif tags.get('amenity') == 'cinema':
                    spot_type = '映画館'
                elif tags.get('leisure') == 'water_park':
                    spot_type = 'ウォーターパーク'
                elif tags.get('tourism') == 'zoo':
                    spot_type = '動物園'
                elif tags.get('tourism') == 'aquarium':
                    spot_type = '水族館'
                elif tags.get('tourism') == 'viewpoint':
                    spot_type = '展望台'
                
                # ✅ websiteを複数の可能性から取得
                website = (tags.get('website') or 
                          tags.get('contact:website') or 
                          tags.get('url') or 
                          tags.get('official_website') or '')

                 # 住所の補完処理
                address = (
                          tags.get('addr:full') or
                          f"{tags.get('addr:city', '')} {tags.get('addr:street', '')} {tags.get('addr:postcode', '')}".strip()
)

                spots_dict[element_id] = {
                         'id': element_id,
                         'name': name,
                         'lat': lat,
                         'lon': lon,
                         'type': spot_type,
                         'address': address,
                         'description': tags.get('description', ''),
                         'website': website,
                         'opening_hours': tags.get('opening_hours', ''),
                         'phone': tags.get('phone', ''),
                         'email': tags.get('contact:email', ''),
                         'facebook': tags.get('contact:facebook', ''),
                         'instagram': tags.get('contact:instagram', '')}


        spots = list(spots_dict.values())
        return jsonify({'success': True, 'count': len(spots), 'spots': spots}), 200

    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'message': 'APIリクエストがタイムアウトしました'}), 504
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500

@app.route('/api/search-combined', methods=['GET'])
def search_combined():
    """複数の検索条件を組み合わせて観光スポットを検索"""
    
    keyword = request.args.get('keyword', '').strip()
    category = request.args.get('category', '').strip()
    prefecture = request.args.get('prefecture', '').strip()
    
    # すべての条件が空の場合はエラー
    if not keyword and not category and not prefecture:
        return jsonify({
            'success': False,
            'message': '少なくとも1つの検索条件を入力してください'
        }), 400
    
    # 都道府県ごとの境界ボックス
    prefecture_bounds = {
        'osaka': ((34.3, 135.2, 34.9, 135.8), '大阪府'),
        'kyoto': ((34.7, 135.0, 35.8, 136.0), '京都府'),
        'hyogo': ((34.2, 134.2, 35.7, 135.5), '兵庫県'),
        'nara': ((33.9, 135.6, 34.8, 136.2), '奈良県'),
        'shiga': ((34.8, 135.8, 35.6, 136.5), '滋賀県'),
        'wakayama': ((33.4, 135.0, 34.4, 135.9), '和歌山県'),
    }
    
    # カテゴリに応じたタグ条件
    category_tags = {
        'castle': ('historic', 'castle', '城'),
        'buddhist': ('religion', 'buddhist', '寺院'),
        'shinto': ('religion', 'shinto', '神社'),
        'museum': ('tourism', 'museum', '博物館'),
        'gallery': ('tourism', 'gallery', '美術館'),
        'theme_park': ('tourism', 'theme_park', 'テーマパーク'),
        'heritage': ('heritage', '1', '世界遺産'),
        'park': ('leisure', 'park', '公園'),
        'theatre': ('amenity', 'theatre', '劇場'),
        'restaurant': ('amenity', 'restaurant', '飲食店'),
        'library': ('amenity', 'library', '図書館'),
        'cinema': ('amenity', 'cinema', '映画館'),
        'water_park': ('leisure', 'water_park', 'ウォーターパーク'),
        'zoo': ('tourism', 'zoo', '動物園'),
        'aquarium': ('tourism', 'aquarium', '水族館'),
        'viewpoint': ('tourism', 'viewpoint', '展望台'),
    }
    
    # 検索範囲を決定
    if prefecture and prefecture in prefecture_bounds:
        bounds, prefecture_name = prefecture_bounds[prefecture]
        min_lat, min_lon, max_lat, max_lon = bounds
    else:
        min_lat, min_lon, max_lat, max_lon = 33.5, 134.5, 35.8, 136.8
        prefecture_name = '近畿地方'
    
    # Overpass APIクエリを構築
    query_parts = []
    
    # キーワード検索の場合
    if keyword:
        # 元のコードのように、Overpass API側でnameフィルタリング
        if category and category in category_tags:
            tag_key, tag_value, category_name = category_tags[category]
            
            if category == 'castle':
                query_parts.append(f'node["historic"="castle"]["name"~"{keyword}",i]({min_lat},{min_lon},{max_lat},{max_lon});')
                query_parts.append(f'way["historic"="castle"]["name"~"{keyword}",i]({min_lat},{min_lon},{max_lat},{max_lon});')
            elif category == 'buddhist':
                query_parts.append(f'node["amenity"="place_of_worship"]["religion"="buddhist"]["name"~"{keyword}",i]({min_lat},{min_lon},{max_lat},{max_lon});')
            elif category == 'shinto':
                query_parts.append(f'node["amenity"="place_of_worship"]["religion"="shinto"]["name"~"{keyword}",i]({min_lat},{min_lon},{max_lat},{max_lon});')
            elif category == 'museum':
                query_parts.append(f'node["tourism"="museum"]["name"~"{keyword}",i]({min_lat},{min_lon},{max_lat},{max_lon});')
                query_parts.append(f'way["tourism"="museum"]["name"~"{keyword}",i]({min_lat},{min_lon},{max_lat},{max_lon});')
            elif category == 'theme_park':
                query_parts.append(f'node["tourism"="theme_park"]["name"~"{keyword}",i]({min_lat},{min_lon},{max_lat},{max_lon});')
                query_parts.append(f'way["tourism"="theme_park"]["name"~"{keyword}",i]({min_lat},{min_lon},{max_lat},{max_lon});')
            elif category == 'restaurant':
                query_parts.append(f'node["amenity"~"restaurant|cafe|fast_food|food_court|bar|pub"]["name"~"{keyword}",i]({min_lat},{min_lon},{max_lat},{max_lon});')
            else:
                query_parts.append(f'node["{tag_key}"="{tag_value}"]["name"~"{keyword}",i]({min_lat},{min_lon},{max_lat},{max_lon});')
        else:
            # カテゴリなしでキーワードのみ（元のsearch-spotsと同じ）
            query_parts.append(f'node["name"~"{keyword}",i]({min_lat},{min_lon},{max_lat},{max_lon});')
            query_parts.append(f'way["name"~"{keyword}",i]({min_lat},{min_lon},{max_lat},{max_lon});')
    
    # カテゴリのみ、または都道府県のみの検索
    elif category and category in category_tags:
        tag_key, tag_value, category_name = category_tags[category]
        
        if category == 'castle':
            query_parts.append(f'node["historic"="castle"]({min_lat},{min_lon},{max_lat},{max_lon});')
            query_parts.append(f'way["historic"="castle"]({min_lat},{min_lon},{max_lat},{max_lon});')
        elif category == 'buddhist':
            query_parts.append(f'node["amenity"="place_of_worship"]["religion"="buddhist"]["wikidata"]({min_lat},{min_lon},{max_lat},{max_lon});')
        elif category == 'shinto':
            query_parts.append(f'node["amenity"="place_of_worship"]["religion"="shinto"]["wikidata"]({min_lat},{min_lon},{max_lat},{max_lon});')
        elif category == 'museum':
            query_parts.append(f'node["tourism"="museum"]({min_lat},{min_lon},{max_lat},{max_lon});')
            query_parts.append(f'way["tourism"="museum"]({min_lat},{min_lon},{max_lat},{max_lon});')
        elif category == 'theme_park':
            query_parts.append(f'node["tourism"="theme_park"]({min_lat},{min_lon},{max_lat},{max_lon});')
            query_parts.append(f'way["tourism"="theme_park"]({min_lat},{min_lon},{max_lat},{max_lon});')
        elif category == 'heritage':
            query_parts.append(f'node["heritage"="1"]({min_lat},{min_lon},{max_lat},{max_lon});')
            query_parts.append(f'way["heritage"="1"]({min_lat},{min_lon},{max_lat},{max_lon});')
        elif category == 'restaurant':
            query_parts.append(f'node["amenity"~"restaurant|cafe|fast_food|food_court|bar|pub"]({min_lat},{min_lon},{max_lat},{max_lon});')
        else:
            query_parts.append(f'node["{tag_key}"="{tag_value}"]({min_lat},{min_lon},{max_lat},{max_lon});')
    
    # 都道府県のみの検索（主要な観光スポットのみ）
    else:
        query_parts.append(f'node["historic"="castle"]({min_lat},{min_lon},{max_lat},{max_lon});')
        query_parts.append(f'way["historic"="castle"]({min_lat},{min_lon},{max_lat},{max_lon});')
        query_parts.append(f'node["amenity"="place_of_worship"]["religion"="buddhist"]["wikidata"]({min_lat},{min_lon},{max_lat},{max_lon});')
        query_parts.append(f'node["amenity"="place_of_worship"]["religion"="shinto"]["wikidata"]({min_lat},{min_lon},{max_lat},{max_lon});')
        query_parts.append(f'node["tourism"="museum"]({min_lat},{min_lon},{max_lat},{max_lon});')
        query_parts.append(f'way["tourism"="museum"]({min_lat},{min_lon},{max_lat},{max_lon});')
        query_parts.append(f'node["tourism"="theme_park"]({min_lat},{min_lon},{max_lat},{max_lon});')
        query_parts.append(f'way["tourism"="theme_park"]({min_lat},{min_lon},{max_lat},{max_lon});')
        query_parts.append(f'node["heritage"="1"]({min_lat},{min_lon},{max_lat},{max_lon});')
        query_parts.append(f'way["heritage"="1"]({min_lat},{min_lon},{max_lat},{max_lon});')
        query_parts.append(f'node["tourism"="attraction"]({min_lat},{min_lon},{max_lat},{max_lon});')
        query_parts.append(f'node["tourism"="zoo"]({min_lat},{min_lon},{max_lat},{max_lon});')
        query_parts.append(f'node["tourism"="aquarium"]({min_lat},{min_lon},{max_lat},{max_lon});')
        query_parts.append(f'node["leisure"="water_park"]({min_lat},{min_lon},{max_lat},{max_lon});')
    
    overpass_query = f"""
    [out:json][timeout:30];
    (
      {' '.join(query_parts)}
    );
    out body;
    >;
    out skel qt;
    """
    
    try:
        overpass_url = "http://overpass-api.de/api/interpreter"
        response = requests.post(overpass_url, data={'data': overpass_query}, timeout=60)
        
        if response.status_code != 200:
            return jsonify({
                'success': False,
                'message': 'Overpass APIからのデータ取得に失敗しました'
            }), 500
        
        data = response.json()
        
        # デバッグ: 取得した要素数
        print(f"取得した全要素数: {len(data.get('elements', []))}")
        
        spots_dict = {}
        rejected_count = 0
        rejection_reasons = {}
        
        for element in data.get('elements', []):
            if 'tags' not in element:
                continue

            tags = element['tags']
            element_id = element.get('id')
            element_type = element.get('type')
            
            # nodeの場合は直接lat/lon
            lat = element.get('lat')
            lon = element.get('lon')
            
            name = tags.get('name:ja') or tags.get('name') or tags.get('name:en')
            
            # デバッグ: 最初の10個の要素名を表示
            if len(spots_dict) < 10:
                print(f"要素 {element_id}: name={name}, type={element_type}, lat={lat}, lon={lon}")
            
            if not name or name == '名称不明':
                rejected_count += 1
                rejection_reasons['名称なし'] = rejection_reasons.get('名称なし', 0) + 1
                continue
            if len(name) > 40:
                rejected_count += 1
                rejection_reasons['名前が長すぎる'] = rejection_reasons.get('名前が長すぎる', 0) + 1
                continue
            
            bad_keywords = ['詰所', '案内', '地図', '乗り場', '駐車場', 'トイレ',
                            '入口', '出口', '受付', '売店', 'ゲート', '記念碑']
            if any(kw in name for kw in bad_keywords):
                rejected_count += 1
                rejection_reasons['除外キーワード'] = rejection_reasons.get('除外キーワード', 0) + 1
                continue

            # wayの場合は座標がないので、スキップせずに保存しておく
            if element_type == 'way':
                if element_id not in spots_dict:
                    spot_type = 'その他'
                    if tags.get('historic') == 'castle':
                        spot_type = '城'
                    elif tags.get('tourism') == 'museum':
                        spot_type = '博物館'
                    elif tags.get('tourism') == 'theme_park':
                        spot_type = 'テーマパーク'
                    
                    website = (tags.get('website') or 
                              tags.get('contact:website') or 
                              tags.get('url') or 
                              tags.get('official_website') or '')

                    address = (tags.get('addr:full') or 
                              f"{tags.get('addr:city', '')} {tags.get('addr:street', '')} {tags.get('addr:postcode', '')}".strip())

                    spots_dict[element_id] = {
                        'id': element_id,
                        'name': name,
                        'type': spot_type,
                        'address': address,
                        'description': tags.get('description', ''),
                        'website': website,
                        'opening_hours': tags.get('opening_hours', ''),
                        'phone': tags.get('phone', ''),
                        'email': tags.get('contact:email', ''),
                        'facebook': tags.get('contact:facebook', ''),
                        'instagram': tags.get('contact:instagram', ''),
                        'nodes': element.get('nodes', []),
                        'lat': None,
                        'lon': None
                    }
            elif element_type == 'node' and lat and lon:
                if element_id not in spots_dict:
                    spot_type = 'その他'
                    if tags.get('historic') == 'castle':
                        spot_type = '城'
                    elif tags.get('religion') == 'buddhist':
                        spot_type = '寺院'
                    elif tags.get('religion') == 'shinto':
                        spot_type = '神社'
                    elif tags.get('tourism') == 'museum':
                        spot_type = '博物館'
                    elif tags.get('tourism') == 'gallery':
                        spot_type = '美術館'
                    elif tags.get('tourism') == 'theme_park':
                        spot_type = 'テーマパーク'
                    elif tags.get('heritage') == '1':
                        spot_type = '世界遺産'
                    elif tags.get('leisure') == 'park':
                        spot_type = '公園'
                    elif tags.get('amenity') == 'theatre':
                        spot_type = '劇場'
                    elif tags.get('amenity') == 'library':
                        spot_type = '図書館'
                    elif tags.get('amenity') == 'cinema':
                        spot_type = '映画館'
                    elif tags.get('leisure') == 'water_park':
                        spot_type = 'ウォーターパーク'
                    elif tags.get('tourism') == 'zoo':
                        spot_type = '動物園'
                    elif tags.get('tourism') == 'aquarium':
                        spot_type = '水族館'
                    elif tags.get('tourism') == 'viewpoint':
                        spot_type = '展望台'
                    elif tags.get('tourism') == 'attraction':
                        spot_type = '観光地'
                    elif tags.get('amenity') in ['restaurant', 'cafe', 'fast_food', 'food_court', 'bar', 'pub']:
                        spot_type = '飲食店'
                    
                    website = (tags.get('website') or 
                              tags.get('contact:website') or 
                              tags.get('url') or 
                              tags.get('official_website') or '')

                    address = (tags.get('addr:full') or 
                              f"{tags.get('addr:city', '')} {tags.get('addr:street', '')} {tags.get('addr:postcode', '')}".strip())

                    spots_dict[element_id] = {
                        'id': element_id,
                        'name': name,
                        'lat': lat,
                        'lon': lon,
                        'type': spot_type,
                        'address': address,
                        'description': tags.get('description', ''),
                        'website': website,
                        'opening_hours': tags.get('opening_hours', ''),
                        'phone': tags.get('phone', ''),
                        'email': tags.get('contact:email', ''),
                        'facebook': tags.get('contact:facebook', ''),
                        'instagram': tags.get('contact:instagram', ''),
                    }
        
        print(f"除外された要素数: {rejected_count}")
        print(f"除外理由: {rejection_reasons}")
        print(f"spots_dictに追加された要素数: {len(spots_dict)}")
        
        # wayの中心座標を計算（ノード情報から）
        node_coords = {}
        for element in data.get('elements', []):
            if element.get('type') == 'node':
                node_id = element.get('id')
                node_coords[node_id] = (element.get('lat'), element.get('lon'))
        
        print(f"ノード座標数: {len(node_coords)}")
        
        # wayの中心を計算
        ways_with_coords = 0
        ways_without_coords = 0
        for spot_id, spot in list(spots_dict.items()):
            if spot.get('lat') is None and 'nodes' in spot:
                lats = []
                lons = []
                for node_id in spot['nodes']:
                    if node_id in node_coords:
                        lat, lon = node_coords[node_id]
                        if lat and lon:
                            lats.append(lat)
                            lons.append(lon)
                
                if lats and lons:
                    spot['lat'] = sum(lats) / len(lats)
                    spot['lon'] = sum(lons) / len(lons)
                    del spot['nodes']
                    ways_with_coords += 1
                    print(f"Way {spot_id} ({spot['name']}): 中心座標計算成功 ({spot['lat']}, {spot['lon']})")
                else:
                    # 座標が計算できない場合は削除
                    ways_without_coords += 1
                    print(f"Way {spot_id} ({spot['name']}): 座標計算失敗")
                    del spots_dict[spot_id]
        
        print(f"座標計算成功したway: {ways_with_coords}")
        print(f"座標計算失敗したway: {ways_without_coords}")
        
        spots = [s for s in spots_dict.values() if s.get('lat') and s.get('lon')]
        
        print(f"最終的なスポット数: {len(spots)}")
        
        # 検索条件の説明文を生成
        conditions = []
        if keyword:
            conditions.append(f'キーワード「{keyword}」')
        if category:
            conditions.append(f'カテゴリ「{category_tags.get(category, ("", "", category))[2]}」')
        if prefecture:
            conditions.append(f'地域「{prefecture_name}」')
        
        condition_text = ' + '.join(conditions)
        
        print(f"統合検索結果: {len(spots)}件（{condition_text}）")
        
        return jsonify({
            'success': True,
            'conditions': condition_text,
            'count': len(spots),
            'spots': spots
        }), 200
        
    except requests.exceptions.Timeout:
        return jsonify({
            'success': False,
            'message': 'APIリクエストがタイムアウトしました'
        }), 504
    except Exception as e:
        print(f"統合検索エラー: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        }), 500
#####################################################################################################
#####################################################################################################





#APIからスポット情報取得し、旅行プラン作成
######################################################################################################
######################################################################################################
def fetch_spots_from_overpass(category_keys: List[str], limit: int = 30) -> List[Dict]:
    """Overpass APIから指定カテゴリーのスポットを取得（分割リクエスト版）"""
    
    # ★ カテゴリーごとに分割したクエリ定義
    category_queries = {
        'relax': """[out:json][timeout:15];
(
  node["leisure"="spa"](34.0,135.0,36.0,136.5);
  node["amenity"="onsen"](34.0,135.0,36.0,136.5);
);
out body 15;""",
        
        'nature': """[out:json][timeout:15];
(
  node["natural"="peak"](34.0,135.0,36.0,136.5);
  node["tourism"="viewpoint"](34.0,135.0,36.0,136.5);
  way["leisure"="park"](34.0,135.0,36.0,136.5);
);
out body 15;""",
        
        'culture': """[out:json][timeout:15];
(
  node["historic"="castle"](34.0,135.0,36.0,136.5);
  way["historic"="castle"](34.0,135.0,36.0,136.5);
  node["tourism"="museum"](34.0,135.0,36.0,136.5);
  way["tourism"="museum"](34.0,135.0,36.0,136.5);
);
out body 15;""",
        
        'gourmet': """[out:json][timeout:15];
(
  node["amenity"="restaurant"](34.5,135.5,35.5,136.0);
);
out body 15;""",
        
        'activity': """[out:json][timeout:15];
(
  node["tourism"="theme_park"](34.0,135.0,36.0,136.5);
  way["tourism"="theme_park"](34.0,135.0,36.0,136.5);
  node["tourism"="zoo"](34.0,135.0,36.0,136.5);
  node["tourism"="aquarium"](34.0,135.0,36.0,136.5);
);
out body 15;""",
        
        'shopping': """[out:json][timeout:15];
(
  node["shop"="mall"](34.0,135.0,36.0,136.5);
  way["shop"="mall"](34.0,135.0,36.0,136.5);
);
out body 15;"""
    }
    
    print(f"\n{'='*60}")
    print(f"🔍 Overpass APIクエリ実行（分割版）")
    print(f"📊 対象カテゴリー: {category_keys}")
    print(f"{'='*60}\n")
    
    all_elements = []
    overpass_url = "http://overpass-api.de/api/interpreter"
    
    # ★ カテゴリーごとに個別リクエスト
    for cat_key in category_keys:
        if cat_key not in category_queries:
            continue
        
        query = category_queries[cat_key]
        
        print(f"🔄 カテゴリー '{cat_key}' を取得中...")
        
        try:
            response = requests.post(
                overpass_url,
                data={'data': query},
                timeout=20
            )
            
            if response.status_code != 200:
                print(f"  ❌ ステータス {response.status_code}")
                continue
            
            data = response.json()
            elements = data.get('elements', [])
            
            print(f"  ✅ {len(elements)}件取得")
            
            if 'remark' in data:
                print(f"  ⚠️ remark: {data['remark']}")
            
            all_elements.extend(elements)
            
        except Exception as e:
            print(f"  ❌ エラー: {e}")
            continue
    
    print(f"\n📦 合計取得: {len(all_elements)}件")
    
    if not all_elements:
        print("⚠️ 全カテゴリーで0件")
        return []
    
    # ★ スポット変換処理
    spots_dict = {}
    stats = {'filtered': 0, 'no_name': 0, 'no_coords': 0}
    
    for element in all_elements:
        tags = element.get('tags', {})
        if not tags:
            continue
        
        element_id = element.get('id')
        lat = element.get('lat') or element.get('center', {}).get('lat')
        lon = element.get('lon') or element.get('center', {}).get('lon')
        
        if not lat or not lon:
            stats['no_coords'] += 1
            continue
        
        name = tags.get('name:ja') or tags.get('name') or tags.get('name:en')
        if not name:
            stats['no_name'] += 1
            continue
        
        if len(name) > 40:
            stats['filtered'] += 1
            continue
        
        bad_keywords = ['詰所', '案内', '駐車場', 'トイレ', '入口', '出口', '売店', 
                       'ゲート', '記念碑', '乗り場', '受付']
        if any(kw in name for kw in bad_keywords):
            stats['filtered'] += 1
            continue
        
        if element_id in spots_dict:
            continue
        
        # スポットタイプ判定
        spot_type = 'その他'
        if tags.get('historic') == 'castle':
            spot_type = '城'
        elif tags.get('religion') == 'buddhist':
            spot_type = '寺院'
        elif tags.get('religion') == 'shinto':
            spot_type = '神社'
        elif tags.get('tourism') == 'museum':
            spot_type = '博物館'
        elif tags.get('tourism') == 'theme_park':
            spot_type = 'テーマパーク'
        elif tags.get('tourism') == 'zoo':
            spot_type = '動物園'
        elif tags.get('tourism') == 'aquarium':
            spot_type = '水族館'
        elif tags.get('tourism') == 'viewpoint':
            spot_type = '展望台'
        elif tags.get('leisure') == 'park':
            spot_type = '公園'
        elif tags.get('leisure') == 'spa':
            spot_type = '温泉'
        elif tags.get('amenity') == 'onsen':
            spot_type = '温泉'
        elif tags.get('amenity') == 'restaurant':
            spot_type = 'レストラン'
        elif tags.get('natural') == 'peak':
            spot_type = '山'
        elif tags.get('shop') == 'mall':
            spot_type = 'ショッピングモール'
        
        category = map_type_to_category(spot_type)
        category_key = determine_category_key(spot_type)
        
        website = (tags.get('website') or tags.get('contact:website') or 
                  tags.get('url') or '')
        
        city = tags.get('addr:city', '')
        street = tags.get('addr:street', '')
        address = f"{city} {street}".strip() or '住所情報なし'
        
        spots_dict[element_id] = {
            'id': f"overpass_{element_id}",
            'name': name,
            'lat': float(lat),
            'lon': float(lon),
            'type': spot_type,
            'category': category,
            'category_key': category_key,
            'address': address,
            'description': generate_description(name, spot_type),
            'image': get_emoji_for_type(spot_type),
            'website': website,
            'tags': generate_tags(tags, spot_type),
            'opening_hours': tags.get('opening_hours', ''),
            'phone': tags.get('phone', ''),
        }
    
    spots = list(spots_dict.values())
    
    print(f"\n✅ 最終スポット数: {len(spots)}件")
    print(f"🚫 統計: フィルタ={stats['filtered']}, 名前なし={stats['no_name']}, 座標なし={stats['no_coords']}")
    
    if spots:
        print(f"\n📋 取得例:")
        for i, spot in enumerate(spots[:5], 1):
            print(f"  {i}. {spot['name']} ({spot['type']}) - {spot['category_key']}")
    
    return spots

def get_recommended_spots_from_api(analysis: Dict, num_spots: int = 6) -> List[Dict]:
    """Overpass APIを使ってスポットを推薦（配分ロジック改善版）"""
    print(f"\n{'='*60}")
    print(f"🎯 推薦処理開始")
    print(f"📊 カテゴリー配分:")
    print(f"  - 主要 (60%): {analysis['primary']}")
    print(f"  - 補助 (30%): {analysis['secondary']}")
    print(f"  - 第三 (10%): {analysis.get('tertiary', [])}")
    print(f"  - 目標スポット数: {num_spots}")
    print(f"{'='*60}\n")
    
    # すべてのカテゴリーを統合
    all_categories = (analysis['primary'] + 
                     analysis['secondary'] + 
                     analysis.get('tertiary', []))
    
    # Overpass APIから取得を試行
    spots = []
    try:
        spots = fetch_spots_from_overpass(all_categories, limit=50)
    except Exception as e:
        print(f"❌ Overpass API呼び出し失敗: {e}")
    
    # 取得成功の場合
    if spots:
        print(f"✅ Overpass APIから{len(spots)}件取得成功")
        
        # カテゴリー別に分類
        primary_spots = [s for s in spots if s.get('category_key') in analysis['primary']]
        secondary_spots = [s for s in spots if s.get('category_key') in analysis['secondary']]
        tertiary_spots = [s for s in spots if s.get('category_key') in analysis.get('tertiary', [])]
        other_spots = [s for s in spots 
                      if s not in primary_spots 
                      and s not in secondary_spots 
                      and s not in tertiary_spots]
        
        print(f"📦 カテゴリー別分類:")
        print(f"  - 主要: {len(primary_spots)}件")
        print(f"  - 補助: {len(secondary_spots)}件")
        print(f"  - 第三: {len(tertiary_spots)}件")
        print(f"  - その他: {len(other_spots)}件")
        
        recommended = []
        
        # 主要カテゴリーから60%
        primary_count = max(1, int(num_spots * 0.6))
        if primary_spots:
            selected = random.sample(primary_spots, min(primary_count, len(primary_spots)))
            recommended.extend(selected)
            print(f"  ✓ 主要から{len(selected)}件選択")
        
        # 補助カテゴリーから30%
        remaining = num_spots - len(recommended)
        secondary_count = max(0, min(int(num_spots * 0.3), remaining))
        if secondary_count > 0 and secondary_spots:
            selected = random.sample(secondary_spots, min(secondary_count, len(secondary_spots)))
            recommended.extend(selected)
            print(f"  ✓ 補助から{len(selected)}件選択")
        
        # 第三カテゴリーから10%
        remaining = num_spots - len(recommended)
        tertiary_count = max(0, min(int(num_spots * 0.1), remaining))
        if tertiary_count > 0 and tertiary_spots:
            selected = random.sample(tertiary_spots, min(tertiary_count, len(tertiary_spots)))
            recommended.extend(selected)
            print(f"  ✓ 第三から{len(selected)}件選択")
        
        # まだ足りない場合は優先順位順に追加
        remaining = num_spots - len(recommended)
        if remaining > 0:
            # 主要 > 補助 > 第三 > その他 の順で追加
            pool = []
            if primary_spots:
                pool.extend([s for s in primary_spots if s not in recommended])
            if secondary_spots:
                pool.extend([s for s in secondary_spots if s not in recommended])
            if tertiary_spots:
                pool.extend([s for s in tertiary_spots if s not in recommended])
            if other_spots:
                pool.extend(other_spots)
            
            if pool:
                selected = random.sample(pool, min(remaining, len(pool)))
                recommended.extend(selected)
                print(f"  ✓ 不足分を補充: {len(selected)}件")
        
        print(f"\n✅ 最終推薦スポット: {len(recommended)}件")
        
        # 選ばれたスポットの詳細をログ出力
        print(f"\n📋 推薦スポット一覧:")
        for i, spot in enumerate(recommended, 1):
            print(f"  {i}. {spot['name']} ({spot['type']}) - {spot.get('category_key', 'unknown')}")
        
        return recommended[:num_spots]
    
    # フォールバック: spots.json から取得
    print("\n⚠️ Overpass API失敗、JSONデータを使用")
    spots_data = load_spots_data()
    
    if not spots_data or not spots_data.get('categories'):
        print("❌ JSONデータも利用不可、ハードコードスポットを使用")
        return get_fallback_hardcoded_spots(analysis, num_spots)
    
    # JSONからスポット収集
    all_json_spots = []
    for category_key, category_data in spots_data['categories'].items():
        for spot in category_data.get('spots', []):
            spot['category_key'] = category_key
            all_json_spots.append(spot)
    
    print(f"📦 JSONから{len(all_json_spots)}件読み込み")
    
    if not all_json_spots:
        print("❌ JSONスポットなし、ハードコードスポットを使用")
        return get_fallback_hardcoded_spots(analysis, num_spots)
    
    # カテゴリーでフィルタリング（優先度付き）
    primary_spots = [s for s in all_json_spots if s.get('category_key') in analysis['primary']]
    secondary_spots = [s for s in all_json_spots if s.get('category_key') in analysis['secondary']]
    tertiary_spots = [s for s in all_json_spots if s.get('category_key') in analysis.get('tertiary', [])]
    
    print(f"🔍 JSON フィルタ後:")
    print(f"  - 主要: {len(primary_spots)}件")
    print(f"  - 補助: {len(secondary_spots)}件")
    print(f"  - 第三: {len(tertiary_spots)}件")
    
    recommended = []
    
    # 主要から60%
    primary_count = max(1, int(num_spots * 0.6))
    if primary_spots:
        recommended.extend(random.sample(primary_spots, min(primary_count, len(primary_spots))))
    
    # 補助から30%
    remaining = num_spots - len(recommended)
    if remaining > 0 and secondary_spots:
        secondary_count = min(int(num_spots * 0.3), remaining)
        recommended.extend(random.sample(secondary_spots, min(secondary_count, len(secondary_spots))))
    
    # 第三から10%
    remaining = num_spots - len(recommended)
    if remaining > 0 and tertiary_spots:
        tertiary_count = min(int(num_spots * 0.1), remaining)
        recommended.extend(random.sample(tertiary_spots, min(tertiary_count, len(tertiary_spots))))
    
    # まだ足りない場合は全体からランダム
    remaining = num_spots - len(recommended)
    if remaining > 0:
        available = [s for s in all_json_spots if s not in recommended]
        if available:
            recommended.extend(random.sample(available, min(remaining, len(available))))
    
    print(f"✅ JSON推薦: {len(recommended)}件")
    return recommended

# APIエンドポイントも修正
@app.route('/api/recommend', methods=['GET'])
def api_recommend():
    """推薦API（プラン生成版）"""
    print("\n" + "="*60)
    print("🚀 /api/recommend リクエスト受信")
    print("="*60)
    
    answers = {
        'mood': request.args.get('mood', ''),
        'purpose': request.args.get('purpose', ''),
        'budget': request.args.get('budget', ''),
        'duration': request.args.get('duration', ''),
        'companion': request.args.get('companion', '')
    }
    
    print(f"📝 回答内容:")
    for key, value in answers.items():
        print(f"  {key}: {value}")
    
    # バリデーション
    if not all(answers.values()):
        print("❌ バリデーションエラー: 未回答あり")
        return jsonify({
            'success': False,
            'message': 'すべての質問に回答してください'
        }), 400
    
    try:
        # 分析
        analysis = analyze_answers(answers)
        print(f"\n📊 分析完了:")
        print(f"  主要: {analysis['primary']}")
        print(f"  補助: {analysis['secondary']}")
        
        # ★★★ ここが変更点！ ★★★
        # 旧: spots = get_recommended_spots_from_api(analysis, num_spots=6)
        # 新: プラン付きで取得
        result = api_recommend_with_plan(answers, analysis)
        
        if not result['success']:
            print("⚠️ スポット取得失敗")
            return jsonify(result), 500
        
        print(f"\n✅ プラン生成成功")
        print("="*60 + "\n")
        
        # ★★★ レスポンス形式も変更 ★★★
        return jsonify(result), 200
        
    except Exception as e:
        print(f"\n❌ 推薦処理エラー: {e}")
        import traceback
        traceback.print_exc()
        print("="*60 + "\n")
        
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        }), 500

def determine_spot_type(tags: Dict) -> str:
    """タグからスポットタイプを判定"""
    if tags.get('historic') == 'castle':
        return '城'
    elif tags.get('religion') == 'buddhist':
        return '寺院'
    elif tags.get('religion') == 'shinto':
        return '神社'
    elif tags.get('tourism') == 'museum':
        return '博物館'
    elif tags.get('tourism') == 'theme_park':
        return 'テーマパーク'
    elif tags.get('tourism') == 'zoo':
        return '動物園'
    elif tags.get('tourism') == 'aquarium':
        return '水族館'
    elif tags.get('tourism') == 'viewpoint':
        return '展望台'
    elif tags.get('natural') in ['peak', 'beach']:
        return '自然'
    elif tags.get('leisure') == 'spa':
        return '温泉'
    elif tags.get('amenity') == 'restaurant':
        return 'レストラン'
    elif tags.get('shop') == 'mall':
        return 'ショッピングモール'
    return '観光地'


def map_type_to_category(spot_type: str) -> str:
    """スポットタイプからカテゴリー名を取得"""
    mapping = {
        '温泉': 'リラクゼーション',
        '自然': '自然・景色',
        '展望台': '自然・景色',
        '城': '文化・歴史',
        '寺院': '文化・歴史',
        '神社': '文化・歴史',
        '博物館': '文化・歴史',
        'レストラン': 'グルメ',
        'ショッピングモール': 'ショッピング',
        'テーマパーク': 'アクティビティ',
        '動物園': 'アクティビティ',
        '水族館': 'アクティビティ',
    }
    return mapping.get(spot_type, 'その他')


def determine_category_key(spot_type: str) -> str:
    """スポットタイプからカテゴリーキーを取得"""
    mapping = {
        '温泉': 'relax',
        '自然': 'nature',
        '展望台': 'nature',
        '山': 'nature',
        'ビーチ': 'nature',
        '城': 'culture',
        '寺院': 'culture',
        '神社': 'culture',
        '博物館': 'culture',
        '美術館': 'culture',
        'レストラン': 'gourmet',
        '飲食店': 'gourmet',
        'ショッピングモール': 'shopping',
        'テーマパーク': 'activity',
        '動物園': 'activity',
        '水族館': 'activity',
        'ウォーターパーク': 'activity',
        '公園': 'nature',
    }
    return mapping.get(spot_type, 'other')
def get_emoji_for_type(spot_type: str) -> str:
    """スポットタイプに応じた絵文字"""
    mapping = {
        '温泉': '♨️',
        '自然': '⛰️',
        '展望台': '🗼',
        '城': '🏰',
        '寺院': '🏯',
        '神社': '⛩️',
        '博物館': '🏛️',
        'レストラン': '🍽️',
        'ショッピングモール': '🛍️',
        'テーマパーク': '🎢',
        '動物園': '🦁',
        '水族館': '🐠',
    }
    return mapping.get(spot_type, '📍')


def generate_description(name: str, spot_type: str) -> str:
    """簡単な説明を生成"""
    desc = {
        '温泉': f'{name}は、関西地方の人気温泉地です。',
        '城': f'{name}は、歴史的価値の高い城郭です。',
        '寺院': f'{name}は、由緒ある仏教寺院です。',
        'テーマパーク': f'{name}は、人気のテーマパークです。',
    }
    return desc.get(spot_type, f'{name}は関西地方の魅力的なスポットです。')


def generate_tags(tags: Dict, spot_type: str) -> List[str]:
    """タグ生成（必ず配列を返す）"""
    result = []
    
    # スポットタイプを追加
    if spot_type:
        result.append(spot_type)
    
    # 都市名を追加
    city = tags.get('addr:city') or tags.get('addr:prefecture')
    if city:
        result.append(city)
    
    # 世界遺産チェック
    if tags.get('heritage') or tags.get('unesco'):
        result.append('世界遺産')
    
    # バリアフリー
    if tags.get('wheelchair') == 'yes':
        result.append('バリアフリー')
    
    # 駐車場
    if tags.get('parking') == 'yes':
        result.append('駐車場あり')
    
    return result[:5] if result else ['観光地']  # 最低1つは返す


def load_spots_data():
    """spots.jsonデータを読み込み"""
    try:
        spots_file = os.path.join(BASE_DIR, 'data', 'spots.json')
        if not os.path.exists(spots_file):
            print(f"警告: spots.jsonが見つかりません: {spots_file}")
            return {'categories': {}}
        
        with open(spots_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"spots.json読み込みエラー: {e}")
        return {'categories': {}}
    



from typing import List, Dict, Tuple
from datetime import datetime, timedelta
import math

from math import radians, sin, cos, sqrt, atan2

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    2地点間の直線距離を計算（Haversine公式）
    
    Args:
        lat1, lon1: 地点1の緯度・経度
        lat2, lon2: 地点2の緯度・経度
    
    Returns:
        float: 距離（km）
    """
    R = 6371  # 地球の半径（km）
    
    # 度数法からラジアンに変換
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    # 差分を計算
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    # Haversine公式
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    distance = R * c
    
    return round(distance, 2)  # 小数点2桁で四捨五入


def calculate_route_distance(spots):
    """
    スポットリストを順番に回った時の合計距離を計算
    
    Args:
        spots: スポットのリスト（各スポットにlat, lonが必要）
    
    Returns:
        float: 合計距離（km）
    """
    if len(spots) < 2:
        return 0.0
    
    total_distance = 0.0
    
    for i in range(len(spots) - 1):
        spot1 = spots[i]
        spot2 = spots[i + 1]
        
        # 緯度経度が存在するか確認
        if 'lat' in spot1 and 'lon' in spot1 and 'lat' in spot2 and 'lon' in spot2:
            distance = calculate_distance(
                spot1['lat'], spot1['lon'],
                spot2['lat'], spot2['lon']
            )
            total_distance += distance
            print(f"  {spot1.get('name', '?')} → {spot2.get('name', '?')}: {distance}km")
    
    return round(total_distance, 2)


def sort_spots_by_distance(base_spot, spots_list, max_distance=60):
    """
    基準スポットから近い順にスポットをソート
    
    Args:
        base_spot: 基準となるスポット（lat, lonが必要）
        spots_list: 並べ替えるスポットのリスト
        max_distance: 最大距離（km）この距離より遠いスポットは除外
    
    Returns:
        list: 距離でソートされたスポットリスト
    """
    base_lat = base_spot.get('lat')
    base_lon = base_spot.get('lon')
    
    if not base_lat or not base_lon:
        print("⚠️ 基準スポットに座標がありません")
        return spots_list
    
    # 各スポットに基準点からの距離を追加
    spots_with_distance = []
    for spot in spots_list:
        if 'lat' in spot and 'lon' in spot:
            distance = calculate_distance(
                base_lat, base_lon,
                spot['lat'], spot['lon']
            )
            
            # 最大距離以内のスポットのみ追加
            if distance <= max_distance:
                spot['distance_from_base'] = distance
                spots_with_distance.append(spot)
                print(f"  📍 {spot.get('name', '?')}: {distance}km")
            else:
                print(f"  ❌ {spot.get('name', '?')}: {distance}km（遠すぎるため除外）")
    
    # 距離でソート（近い順）
    sorted_spots = sorted(spots_with_distance, key=lambda x: x['distance_from_base'])
    
    print(f"\n✅ {len(sorted_spots)}個のスポットを距離順にソート完了")
    
    return sorted_spots

def optimize_daily_route(spots):
    """
    その日のスポットを最短ルートに並び替え（貪欲法）
    
    Args:
        spots: その日のスポットリスト
    
    Returns:
        list: 最適化されたスポットリスト
    """
    if len(spots) <= 1:
        return spots
    
    print(f"\n🔄 {len(spots)}スポットのルート最適化中...")
    
    # 最初のスポットは固定（拠点に近いスポット）
    optimized = [spots[0]]
    remaining = spots[1:].copy()
    
    # 貪欲法: 現在地から最も近いスポットを次に選ぶ
    while remaining:
        current_spot = optimized[-1]
        
        # 現在地から各スポットへの距離を計算
        nearest_spot = None
        nearest_distance = float('inf')
        
        for spot in remaining:
            if 'lat' in spot and 'lon' in spot and 'lat' in current_spot and 'lon' in current_spot:
                distance = calculate_distance(
                    current_spot['lat'], current_spot['lon'],
                    spot['lat'], spot['lon']
                )
                
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest_spot = spot
        
        if nearest_spot:
            optimized.append(nearest_spot)
            remaining.remove(nearest_spot)
            print(f"  {current_spot.get('name', '?')} → {nearest_spot.get('name', '?')}: {nearest_distance}km")
        else:
            # 座標がないスポットは最後に追加
            optimized.extend(remaining)
            break
    
    # 最適化前後の距離を比較
    original_distance = calculate_route_distance(spots)
    optimized_distance = calculate_route_distance(optimized)
    
    print(f"  📉 最適化: {original_distance}km → {optimized_distance}km（{original_distance - optimized_distance:.1f}km削減）")
    
    return optimized



def generate_daily_itinerary(spots: List[Dict], duration_days: int = 1, 
                            start_time: str = "09:00") -> List[Dict]:
    """日ごとの詳細スケジュールを生成（シンプル版）"""
    
    max_spots_per_day = 4  # 1日最大4スポット
    
    itineraries = []
    remaining_spots = spots.copy()
    
    print(f"\n📅 日程配分: {len(spots)}スポット ÷ {duration_days}日")
    
    for day_num in range(1, duration_days + 1):
        if not remaining_spots:
            break
        
        day_schedule = {
            'day': day_num,
            'date': (datetime.now() + timedelta(days=day_num-1)).strftime('%Y年%m月%d日'),
            'activities': []
        }
        
        # 残り日数で均等に分配、ただし最大4スポットまで
        remaining_days = duration_days - day_num + 1
        remaining_spot_count = len(remaining_spots)
        
        if remaining_days == 1:
            day_spot_count = min(max_spots_per_day, remaining_spot_count)
        else:
            ideal_count = (remaining_spot_count + remaining_days - 1) // remaining_days
            day_spot_count = min(max_spots_per_day, ideal_count)
        
        print(f"  {day_num}日目: {day_spot_count}スポット")
        
        # その日のスポットを選択
        day_spots = []
        for _ in range(min(day_spot_count, len(remaining_spots))):
            day_spots.append(remaining_spots.pop(0))
        
        # ★★★ ルート最適化: その日のスポットを効率的な順序に並び替え ★★★
        if len(day_spots) > 1:
            day_spots = optimize_daily_route(day_spots)
        
        # 時刻を簡易計算（2-3時間ごとに配置）
        time_slots = ["09:00", "11:30", "14:00", "16:30"]
        
        for i, spot in enumerate(day_spots):
            if i >= len(time_slots):
                break
            
            # スポット追加
            day_schedule['activities'].append({
                'type': 'spot',
                'time': time_slots[i],
                'name': f"{spot.get('image', '📍')} {spot['name']}",
                'spot_data': spot,
                'description': spot.get('description', ''),
                'address': spot.get('address', '')
            })
    
        
        # 終了時刻（最後のスポット + 1.5時間）
        last_time = time_slots[min(len(day_spots)-1, len(time_slots)-1)]
        hour, minute = map(int, last_time.split(':'))
        end_hour = hour + 2
        day_schedule['end_time'] = f"{end_hour:02d}:{minute:02d}"
        
        # ★★★ 実際の距離を計算 ★★★
        day_schedule['total_distance'] = calculate_route_distance(day_spots)
        print(f"  📊 {day_num}日目の移動距離: {day_schedule['total_distance']}km")
        
        itineraries.append(day_schedule)
    
    return itineraries

def create_travel_plan(spots: List[Dict], answers: Dict) -> Dict:
    """完全な旅行プランを作成（シンプル版）"""
    
    # 期間の決定
    duration_mapping = {
        'short': 1,
        'medium': 3,
        'long': 5
    }
    duration_days = duration_mapping.get(answers.get('duration', 'short'), 1)
    
    print(f"\n📅 旅行期間: {duration_days}日間")
    print(f"📍 スポット総数: {len(spots)}件")
    
    # スポット数が少ない場合は日数を調整
    if len(spots) < duration_days * 3:
        duration_days = max(1, len(spots) // 3)
        print(f"⚠️ スポット数が少ないため、{duration_days}日間に調整")
    
    # 日程作成
    itineraries = generate_daily_itinerary(spots, duration_days)
    
    # プラン全体のサマリー
    total_distance = sum(day['total_distance'] for day in itineraries)
    total_spots = sum(len([a for a in day['activities'] if a['type'] == 'spot']) for day in itineraries)
    
    plan = {
        'title': f"{duration_days}日間の関西旅行プラン",
        'summary': {
            'duration_days': duration_days,
            'total_spots': total_spots,
            'total_distance': round(total_distance, 1),
            'budget_level': answers.get('budget', 'medium'),
            'companion': answers.get('companion', 'solo')
        },
        'itineraries': itineraries,
        #'tips': generate_travel_tips(answers, itineraries)
    }
    
    return plan


#def generate_travel_tips(answers: Dict, itineraries: List[Dict]) -> List[str]:
    """旅のアドバイスを生成"""
    tips = []
    
    # 予算に応じたアドバイス
    if answers.get('budget') == 'low':
        tips.append('💰 交通費節約のため、関西周遊パスの利用がおすすめです')
    elif answers.get('budget') == 'high':
        tips.append('🎫 VIP体験や特別ツアーの事前予約を検討してみてください')
    
    # 同行者に応じたアドバイス
    if answers.get('companion') == 'family':
        tips.append('👨‍👩‍👧‍👦 お子様連れの場合、授乳室やベビーカー貸出のある施設を優先しています')
    elif answers.get('companion') == 'couple':
        tips.append('💑 ロマンティックな夕景スポットでの写真撮影がおすすめです')
    
    # 移動距離に応じたアドバイス
    total_distance = sum(day['total_distance'] for day in itineraries)
    if total_distance > 100:
        tips.append(f'🚗 総移動距離は約{total_distance:.0f}kmです。レンタカー利用が便利です')
    else:
        tips.append('🚃 公共交通機関で効率よく回れるルートになっています')
    
    # 季節のアドバイス
    current_month = datetime.now().month
    if current_month in [3, 4]:
        tips.append('🌸 桜の季節です！各スポットの桜情報を事前にチェックしましょう')
    elif current_month in [7, 8]:
        tips.append('☀️ 暑い季節です。水分補給と日焼け対策をお忘れなく')
    elif current_month in [11, 12]:
        tips.append('🍁 紅葉の季節です！混雑が予想されるため早めの行動がおすすめ')
    
    return tips


# APIエンドポイントに追加する関数
def api_recommend_with_plan(answers: Dict, analysis: Dict) -> Dict:
    """プラン付き推薦APIレスポンスを生成"""
    
    # 期間に応じたスポット数を決定
    duration = answers.get('duration', 'short')
    duration_to_spots = {
        'short': 7,      # 日帰り〜1泊 → 3-4スポット
        'medium': 15,     # 2〜3泊 → 6-8スポット（1日3-4スポット）
        'long': 24       # 4泊以上 → 9-12スポット（1日3-4スポット）
    }
    num_spots = duration_to_spots.get(duration, 4)
    
    print(f"\n🎯 期間「{duration}」に対して{num_spots}スポット取得")
    
    # スポット取得
    spots = get_recommended_spots_from_api(analysis, num_spots=num_spots)
    
    if not spots:
        return {
            'success': False,
            'message': 'スポットを取得できませんでした'
        }
    
    # 旅行プラン生成
    travel_plan = create_travel_plan(spots, answers)
    
    return {
        'success': True,
        'plan': travel_plan,
        'spots': spots,  # 後方互換性のため残す
        'analysis': analysis
    }


# 使用例
if __name__ == "__main__":
    # テストデータ
    test_spots = [
        {'name': '大阪城', 'lat': 34.6873, 'lon': 135.5259, 'type': '城', 'image': '🏯', 'description': '大阪のシンボル', 'address': '大阪市中央区'},
        {'name': '清水寺', 'lat': 34.9949, 'lon': 135.7851, 'type': '寺院', 'image': '⛩️', 'description': '京都の名刹', 'address': '京都市東山区'},
        {'name': 'USJ', 'lat': 34.6654, 'lon': 135.4323, 'type': 'テーマパーク', 'image': '🎢', 'description': '人気テーマパーク', 'address': '大阪市此花区'},
        {'name': '奈良公園', 'lat': 34.6851, 'lon': 135.8431, 'type': '公園', 'image': '🦌', 'description': '鹿と触れ合える', 'address': '奈良市'},
    ]
    
    test_answers = {
        'mood': 'relaxed',
        'purpose': 'culture',
        'budget': 'medium',
        'duration': 'two',
        'companion': 'couple'
    }
    
    plan = create_travel_plan(test_spots, test_answers)
    
    print("=" * 60)
    print(f"📅 {plan['title']}")
    print("=" * 60)
    print(f"期間: {plan['summary']['duration_days']}日間")
    print(f"訪問スポット数: {plan['summary']['total_spots']}箇所")
    print(f"総移動距離: {plan['summary']['total_distance']}km")
    print()
    
    for day in plan['itineraries']:
        print(f"\n【{day['day']}日目】 {day['date']}")
        print(f"終了予定時刻: {day['end_time']}")
        print("-" * 60)
        
        for activity in day['activities']:
            print(f"{activity['time']} - {activity['name']}")
            if activity.get('description'):
                print(f"          {activity['description']}")
        
        print(f"\n📊 1日の移動距離: {day['total_distance']:.1f}km")
    
    print("\n\n💡 旅のアドバイス:")
    for tip in plan['tips']:
        print(f"  • {tip}")


def analyze_answers(answers: Dict) -> Dict:
    """
    アンケート回答を分析してカテゴリー優先度を返す（徹底修正版）
    
    Args:
        answers: アンケート回答辞書
        
    Returns:
        {
            'primary': ['category1', 'category2'],  # 主要カテゴリー (60%)
            'secondary': ['category3'],              # 補助カテゴリー (30%)
            'tertiary': ['category4'],               # 第三カテゴリー (10%)
            'filters': {...}                         # フィルター条件
        }
    """
    mood = answers.get('mood', '')
    purpose = answers.get('purpose', '')
    budget = answers.get('budget', '')
    duration = answers.get('duration', '')
    companion = answers.get('companion', '')
    
    print(f"\n{'='*60}")
    print(f"🔍 回答分析開始")
    print(f"  気分: {mood}")
    print(f"  目的: {purpose}")
    print(f"  予算: {budget}")
    print(f"  期間: {duration}")
    print(f"  同行者: {companion}")
    print(f"{'='*60}\n")
    
    result = {
        'primary': [],
        'secondary': [],
        'tertiary': [],
        'filters': {
            'budget': budget,
            'duration': duration,
            'companion': companion
        }
    }
    
    # ===== ステップ1: 目的からメインカテゴリーを決定 (最優先) =====
    purpose_mapping = {
        'relax': {
            'primary': ['relax', 'nature'],
            'secondary': ['gourmet']
        },
        'adventure': {
            'primary': ['activity', 'nature'],
            'secondary': ['culture']
        },
        'culture': {
            'primary': ['culture'],
            'secondary': ['gourmet', 'nature']
        },
        'gourmet': {
            'primary': ['gourmet'],
            'secondary': ['culture', 'shopping']
        }
    }
    
    if purpose in purpose_mapping:
        purpose_data = purpose_mapping[purpose]
        result['primary'].extend(purpose_data['primary'])
        result['secondary'].extend(purpose_data['secondary'])
        print(f"📌 目的「{purpose}」から:")
        print(f"   主要: {purpose_data['primary']}")
        print(f"   補助: {purpose_data['secondary']}")
    
    # ===== ステップ2: 気分から調整 (補助的) =====
    mood_adjustments = {
        'excited': {
            'boost': ['activity'],      # 強化
            'add': []                   # 追加なし
        },
        'relaxed': {
            'boost': ['relax', 'nature'],
            'add': []
        },
        'adventurous': {
            'boost': ['nature', 'activity'],
            'add': []
        },
        'chilled': {
            'boost': ['relax'],
            'add': ['gourmet']
        }
    }
    
    if mood in mood_adjustments:
        adjustment = mood_adjustments[mood]
        
        # 既存カテゴリーを強化（primaryに移動）
        for cat in adjustment['boost']:
            if cat in result['secondary'] and cat not in result['primary']:
                result['secondary'].remove(cat)
                result['primary'].append(cat)
                print(f"⬆️ 気分「{mood}」により「{cat}」を主要へ昇格")
        
        # 新規カテゴリーを追加
        for cat in adjustment['add']:
            if cat not in result['primary'] and cat not in result['secondary']:
                result['secondary'].append(cat)
                print(f"➕ 気分「{mood}」により「{cat}」を補助に追加")
    
    # ===== ステップ3: 同行者による調整 =====
    companion_adjustments = {
        'solo': {
            'add_secondary': ['nature', 'culture'],  # 一人旅向け
            'remove': ['shopping']                    # ショッピングは優先度下げ
        },
        'couple': {
            'add_secondary': ['gourmet', 'nature'],
            'remove': []
        },
        'family': {
            'add_secondary': ['activity'],
            'add_tertiary': ['shopping'],
            'remove': []
        },
        'friends': {
            'add_secondary': ['activity', 'gourmet'],
            'add_tertiary': ['shopping'],
            'remove': []
        }
    }
    
    if companion in companion_adjustments:
        adj = companion_adjustments[companion]
        
        # 除外カテゴリー処理
        for cat in adj.get('remove', []):
            if cat in result['primary']:
                result['primary'].remove(cat)
                print(f"❌ 同行者「{companion}」により「{cat}」を主要から除外")
            if cat in result['secondary']:
                result['secondary'].remove(cat)
                print(f"❌ 同行者「{companion}」により「{cat}」を補助から除外")
        
        # 補助カテゴリー追加
        for cat in adj.get('add_secondary', []):
            if cat not in result['primary'] and cat not in result['secondary']:
                result['secondary'].append(cat)
                print(f"➕ 同行者「{companion}」により「{cat}」を補助に追加")
        
        # 第三カテゴリー追加
        for cat in adj.get('add_tertiary', []):
            if cat not in result['primary'] and cat not in result['secondary']:
                result['tertiary'].append(cat)
                print(f"➕ 同行者「{companion}」により「{cat}」を第三に追加")
    
    # ===== ステップ4: 予算による調整 =====
    if budget == 'low':
        # 低予算の場合、自然・文化を優先
        if 'nature' not in result['primary']:
            result['secondary'].insert(0, 'nature')
        if 'shopping' in result['primary']:
            result['primary'].remove('shopping')
        print(f"💰 予算「低」により自然・文化を優先")
    
    elif budget == 'high':
        # 高予算の場合、グルメ・ショッピングを追加
        if 'gourmet' not in result['primary'] and 'gourmet' not in result['secondary']:
            result['secondary'].append('gourmet')
            print(f"💎 予算「高」によりグルメを追加")
    
    # ===== 重複削除と整理 =====
    result['primary'] = list(dict.fromkeys(result['primary']))
    result['secondary'] = list(dict.fromkeys(result['secondary']))
    result['tertiary'] = list(dict.fromkeys(result['tertiary']))
    
    # 主要カテゴリーが補助・第三に含まれていたら削除
    result['secondary'] = [c for c in result['secondary'] if c not in result['primary']]
    result['tertiary'] = [c for c in result['tertiary'] if c not in result['primary'] and c not in result['secondary']]
    
    print(f"\n✅ 分析完了:")
    print(f"   主要カテゴリー (60%): {result['primary']}")
    print(f"   補助カテゴリー (30%): {result['secondary']}")
    print(f"   第三カテゴリー (10%): {result['tertiary']}")
    print(f"{'='*60}\n")
    
    return result

def get_recommended_spots_from_api(analysis: Dict, num_spots: int = 6) -> List[Dict]:
    """Overpass APIを使ってスポットを推薦（強化版フォールバック）"""
    print(f"デバッグ: 分析結果 = {analysis}")
    
    all_categories = analysis['primary'] + analysis['secondary']
    print(f"デバッグ: 対象カテゴリー = {all_categories}")
    
    # Overpass APIからスポットを取得（タイムアウト対策）
    spots = []
    try:
        spots = fetch_spots_from_overpass(all_categories, limit=30)
        print(f"デバッグ: Overpass APIから {len(spots)} 件取得")
    except Exception as e:
        print(f"Overpass API 例外: {e}")
        spots = []
    
    # フォールバック処理
    if not spots:
        print("警告: Overpass APIからデータ取得失敗。JSONデータを使用します")
        spots_data = load_spots_data()
        print(f"デバッグ: JSONデータ読み込み = {bool(spots_data)}")
        
        if spots_data and spots_data.get('categories'):
            print(f"デバッグ: JSONカテゴリー数 = {len(spots_data['categories'])}")
            
            # すべてのカテゴリーからスポットを集める
            all_fallback_spots = []
            for category_key, category_data in spots_data['categories'].items():
                for spot in category_data.get('spots', []):
                    # カテゴリーキーをスポットに追加
                    spot['category_key'] = category_key
                    all_fallback_spots.append(spot)
            
            print(f"デバッグ: JSONスポット総数 = {len(all_fallback_spots)}")
            
            if all_fallback_spots:
                # ★★★ JSONデータでも距離ベースの選択を適用 ★★★
                # 拠点スポットを選ぶ
                filtered_spots = [s for s in all_fallback_spots if s.get('category_key') in all_categories]
                
                if not filtered_spots:
                    filtered_spots = all_fallback_spots
                
                base_spot = random.choice(filtered_spots)
                print(f"\n🎯 拠点スポット（JSON）: {base_spot.get('name', '?')}")
                
                # 残りを距離でソート
                other_spots = [s for s in all_fallback_spots if s != base_spot]
                sorted_spots = sort_spots_by_distance(base_spot, other_spots, max_distance=60)
                
                # 近い順から選択
                selected_spots = [base_spot]
                for spot in sorted_spots:
                    if len(selected_spots) >= num_spots:
                        break
                    selected_spots.append(spot)
                
                print(f"デバッグ: 最終選択スポット数 = {len(selected_spots)}")
                return selected_spots
    
    # Overpass APIデータを使用する場合
    if spots:
        # 主要カテゴリーのスポットを優先
        primary_spots = [s for s in spots if s.get('category_key') in analysis['primary']]
        secondary_spots = [s for s in spots if s.get('category_key') in analysis['secondary']]
        other_spots = [s for s in spots if s not in primary_spots and s not in secondary_spots]
        
        # ★★★ ステップ1: 拠点スポットを1つ選ぶ ★★★
        base_spot = None
        if primary_spots:
            base_spot = random.choice(primary_spots)
            print(f"\n🎯 拠点スポット: {base_spot.get('name', '?')}")
        elif secondary_spots:
            base_spot = random.choice(secondary_spots)
            print(f"\n🎯 拠点スポット: {base_spot.get('name', '?')}")
        elif other_spots:
            base_spot = random.choice(other_spots)
            print(f"\n🎯 拠点スポット: {base_spot.get('name', '?')}")
        
        if not base_spot:
            print("❌ 拠点スポットを選択できませんでした")
            return []
        
        # ★★★ ステップ2: 拠点から近い順にソート ★★★
        all_other_spots = [s for s in spots if s != base_spot]
        sorted_spots = sort_spots_by_distance(base_spot, all_other_spots, max_distance=60)
        
        # ★★★ ステップ3: 近い順から必要数だけ選ぶ ★★★
        recommended = [base_spot]  # 拠点を最初に追加
        
        # カテゴリー優先度を考慮しながら選択
        for spot in sorted_spots:
            if len(recommended) >= num_spots:
                break
            
            # 主要カテゴリーを優先
            if spot.get('category_key') in analysis['primary']:
                recommended.append(spot)
            elif len(recommended) < num_spots * 0.8:  # 80%まで埋まってなければ
                if spot.get('category_key') in analysis['secondary']:
                    recommended.append(spot)
            else:  # 残りは何でもOK
                recommended.append(spot)
        
        print(f"\n✅ 最終選択: {len(recommended)}スポット")
        return recommended[:num_spots]
    
    # 両方失敗した場合
    print("エラー: Overpass APIとJSONデータの両方が利用できません")
    return get_fallback_hardcoded_spots(analysis, num_spots)

def get_fallback_hardcoded_spots(analysis: Dict, num_spots: int) -> List[Dict]:
    """最終フォールバック：ハードコードされたスポット"""
    print("警告: ハードコードされたスポットを使用します")
    
    # シンプルなフォールバックスポット
    fallback_spots = [
        {
            'id': 'fallback_1',
            'name': '大阪城公園',
            'lat': 34.6873,
            'lon': 135.5259,
            'category': '文化・歴史',
            'category_key': 'culture',
            'address': '大阪府大阪市中央区大阪城',
            'description': '大阪のシンボルである大阪城を中心とした広大な公園です。',
            'image': '🏯',
            'tags': ['城', '公園', '歴史']
        },
        {
            'id': 'fallback_2', 
            'name': '清水寺',
            'lat': 34.9949,
            'lon': 135.7851,
            'category': '文化・歴史',
            'category_key': 'culture',
            'address': '京都府京都市東山区清水',
            'description': '京都で最も有名な寺院の一つで、舞台からの景色が絶景です。',
            'image': '🏯',
            'tags': ['寺院', '世界遺産']
        },
        {
            'id': 'fallback_3',
            'name': 'ユニバーサル・スタジオ・ジャパン',
            'lat': 34.6654,
            'lon': 135.4323,
            'category': 'アクティビティ', 
            'category_key': 'activity',
            'address': '大阪府大阪市此花区桜島',
            'description': '人気のテーマパークで、ハリウッド映画の世界を体験できます。',
            'image': '🎢',
            'tags': ['テーマパーク', 'アトラクション']
        }
    ]
    
    # 分析結果に基づいてフィルタリング
    all_categories = analysis['primary'] + analysis['secondary']
    filtered = [spot for spot in fallback_spots if spot.get('category_key') in all_categories]
    
    if filtered:
        return random.sample(filtered, min(num_spots, len(filtered)))
    else:
        return random.sample(fallback_spots, min(num_spots, len(fallback_spots)))
# HTMLファイルの配信



@app.route('/questionnaire')

def questionnaire():
    """アンケートページを表示"""
    return send_from_directory(os.path.join(BASE_DIR, 'templates'), 'questionnaire.html')



@app.route('/proposal')
def proposal():
    """
    提案ページを表示（修正版）
    JavaScriptがlocalStorageから読み取るため、単純にHTMLを返す
    """
    print("=== 提案ページリクエスト受信 ===")
    return send_from_directory(os.path.join(BASE_DIR, 'templates'), 'proposal.html')



def generate_simple_proposal_html(answers: Dict, spots: List[Dict], analysis: Dict) -> str:
    """簡易版の提案HTMLを生成（proposal.htmlがない場合のフォールバック）"""
    spots_html = ""
    for spot in spots:
        spots_html += f'''
        <div style="border: 2px solid #e0e0e0; border-radius: 15px; padding: 20px; margin-bottom: 20px;">
            <div style="font-size: 3em; text-align: center;">{spot.get('image', '📍')}</div>
            <h3 style="color: #667eea; text-align: center;">{spot.get('name', '')}</h3>
            <p style="color: #666;">{spot.get('description', '')}</p>
            <p style="color: #999; font-size: 0.9em;">📍 {spot.get('address', '')}</p>
        </div>
        '''
    
    return f'''
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>旅行プラン提案</title>
        <style>
            body {{
                font-family: sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 20px;
                margin: 0;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                padding: 40px;
            }}
            h1 {{
                color: #667eea;
                text-align: center;
            }}
            .spots-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
                margin-top: 30px;
            }}
            .button {{
                display: inline-block;
                padding: 15px 30px;
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
                text-decoration: none;
                border-radius: 10px;
                font-weight: bold;
                margin-top: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✨ あなたにおすすめの旅行プラン</h1>
            <div class="spots-grid">
                {spots_html}
            </div>
            <div style="text-align: center; margin-top: 40px;">
                <a href="/questionnaire" class="button">🔄 もう一度診断する</a>
                <a href="/" class="button">🏠 トップに戻る</a>
            </div>
        </div>
    </body>
    </html>
    ''',500
#####################################################################################################
#####################################################################################################


#レビュー機能
######################################################################################################
######################################################################################################
#レビュー機能ここから下全て変更した11/22

@app.route('/api/check-login', methods=['GET', 'OPTIONS'])
def check_login():
    """ログイン状態を確認"""
    
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response, 200
    
    print(f"\n=== ログイン状態確認 ===")
    print(f"Cookie: {request.cookies}")
    print(f"セッション: {dict(session)}")
    print(f"user_id in session: {'user_id' in session}")
    
    if 'user_id' in session:
        print(f"✅ ログイン中: user_id={session['user_id']}")
        return jsonify({
            'success': True,
            'logged_in': True,
            'user_id': session['user_id']
        }), 200
    else:
        print("❌ 未ログイン")
        return jsonify({
            'success': True,
            'logged_in': False
        }), 200




@app.route('/api/reviews', methods=['POST', 'OPTIONS'])  # ← OPTIONSを追加
def create_review():
    """レビューを投稿（Overpass APIスポット対応）"""
   
    #  OPTIONSリクエスト対応（追加）
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response, 200
   
    #  デバッグログ追加
    print("\n" + "="*60)
    print("【レビュー投稿リクエスト受信】")
    print(f"Cookie: {request.cookies}")
    print(f"セッション内容: {dict(session)}")
    print(f"user_id in session: {'user_id' in session}")
    if 'user_id' in session:
        print(f"user_id値: {session['user_id']}")
    print("="*60)
   
    # セッション確認
    if 'user_id' not in session:
        print("❌ エラー: セッションにuser_idがありません")
        return jsonify({
            'success': False,
            'message': 'ログインが必要です。ページを再読み込みしてください。'
        }), 401
   
    print(f"✅ ログイン確認: user_id={session['user_id']}")
   
    data = request.get_json()
    print(f"受信データ: {data}")
   
    # Overpass APIから取得したスポット情報
    osm_id = data.get('osm_id')
    osm_type = data.get('osm_type', 'node')
    spot_name = data.get('spot_name')
    spot_lat = data.get('spot_lat')
    spot_lon = data.get('spot_lon')
    spot_type = data.get('spot_type', 'その他')
   
    # レビュー内容
    rating = data.get('rating')
    comment = data.get('comment', '')
    visit_date = data.get('visit_date')
   
    # バリデーション
    if not osm_id or not spot_name or not rating:
        print(f"❌ バリデーションエラー: osm_id={osm_id}, spot_name={spot_name}, rating={rating}")
        return jsonify({'success': False, 'message': '必須項目を入力してください'}), 400
   
    if not (1 <= rating <= 5):
        return jsonify({'success': False, 'message': '評価は1-5の範囲で入力してください'}), 400
   
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'データベース接続エラー'}), 500
   
    try:
        cur = conn.cursor()
       
        # 既存レビューの確認
        cur.execute(
            'SELECT id FROM reviews WHERE user_id = %s AND osm_id = %s',
            (session['user_id'], osm_id)
        )
        existing = cur.fetchone()
       
        if existing:
            print(f"⚠️ 既存レビュー検出: review_id={existing['id']}")
            return jsonify({
                'success': False,
                'message': 'このスポットには既にレビューを投稿しています。'
            }), 400
       
        # レビュー投稿
        print(f"📝 レビュー挿入開始...")
        cur.execute(
            '''INSERT INTO reviews
               (user_id, osm_id, osm_type, spot_name, spot_lat, spot_lon, spot_type,
                rating, comment, visit_date, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
               RETURNING id, user_id, osm_id, spot_name, rating, comment, visit_date, created_at''',
            (session['user_id'], osm_id, osm_type, spot_name, spot_lat, spot_lon, spot_type,
             rating, comment, visit_date)
        )
       
        review = cur.fetchone()
        conn.commit()
       
        print(f"✅ レビュー投稿成功: review_id={review['id']}, spot={spot_name}, user_id={session['user_id']}")
       
        return jsonify({
            'success': True,
            'message': 'レビューを投稿しました',
            'review': dict(review)
        }), 201
       
    except Exception as e:
        conn.rollback()
        print(f"❌ レビュー投稿エラー: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'サーバーエラー: {str(e)}'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/api/reviews/spot/<int:osm_id>', methods=['GET', 'OPTIONS'])  # ← OPTIONSを追加
def get_spot_reviews(osm_id):
    """特定スポット（Overpass API）のレビュー一覧を取得"""
   
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response, 200
   
    print(f"\n=== レビュー取得: osm_id={osm_id} ===")
   
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'データベース接続エラー'}), 500
   
    try:
        cur = conn.cursor()
       
        # レビュー取得
        cur.execute(
            '''SELECT r.*, u.name as user_name, u.user_id as username
               FROM reviews r
               JOIN users u ON r.user_id = u.id
               WHERE r.osm_id = %s
               ORDER BY r.created_at DESC''',
            (osm_id,)
        )
       
        reviews = cur.fetchall()
       
        # 平均評価を計算
        avg_rating = 0
        if reviews:
            avg_rating = sum(review['rating'] for review in reviews) / len(reviews)
       
        print(f"✅ レビュー取得成功: {len(reviews)}件")
       
        return jsonify({
            'success': True,
            'osm_id': osm_id,
            'count': len(reviews),
            'average_rating': round(avg_rating, 1),
            'reviews': [dict(review) for review in reviews]
        }), 200
       
    except Exception as e:
        print(f"❌ レビュー取得エラー: {e}")
        return jsonify({'success': False, 'message': 'サーバーエラー'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/api/reviews/<int:review_id>', methods=['PUT', 'OPTIONS'])  # ← OPTIONSを追加
def update_review(review_id):
    """レビューを編集"""
   
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response, 200
   
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'ログインが必要です'}), 401
   
    data = request.get_json()
    rating = data.get('rating')
    comment = data.get('comment')
    visit_date = data.get('visit_date')
   
    if not (1 <= rating <= 5):
        return jsonify({'success': False, 'message': '評価は1-5の範囲で入力してください'}), 400
   
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'データベース接続エラー'}), 500
   
    try:
        cur = conn.cursor()
       
        # レビューの所有者確認
        cur.execute('SELECT * FROM reviews WHERE id = %s AND user_id = %s', (review_id, session['user_id']))
        review = cur.fetchone()
       
        if not review:
            return jsonify({'success': False, 'message': 'レビューが見つからないか、編集権限がありません'}), 404
       
        # レビュー更新
        cur.execute(
            '''UPDATE reviews
               SET rating = %s, comment = %s, visit_date = %s, updated_at = CURRENT_TIMESTAMP
               WHERE id = %s''',
            (rating, comment, visit_date, review_id)
        )
       
        conn.commit()
       
        return jsonify({'success': True, 'message': 'レビューを更新しました'}), 200
       
    except Exception as e:
        conn.rollback()
        print(f"❌ レビュー更新エラー: {e}")
        return jsonify({'success': False, 'message': 'サーバーエラー'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/api/reviews/<int:review_id>', methods=['DELETE', 'OPTIONS'])  # ← OPTIONSを追加
def delete_review(review_id):
    """レビューを削除"""
   
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response, 200
   
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'ログインが必要です'}), 401
   
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'データベース接続エラー'}), 500
   
    try:
        cur = conn.cursor()
       
        # レビューの所有者確認
        cur.execute('SELECT * FROM reviews WHERE id = %s AND user_id = %s', (review_id, session['user_id']))
        review = cur.fetchone()
       
        if not review:
            return jsonify({'success': False, 'message': 'レビューが見つからないか、削除権限がありません'}), 404
       
        # レビュー削除
        cur.execute('DELETE FROM reviews WHERE id = %s', (review_id,))
        conn.commit()
       
        return jsonify({'success': True, 'message': 'レビューを削除しました'}), 200
       
    except Exception as e:
        conn.rollback()
        print(f"❌ レビュー削除エラー: {e}")
        return jsonify({'success': False, 'message': 'サーバーエラー'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/api/reviews/user', methods=['GET', 'OPTIONS'])  # ← OPTIONSを追加
def get_user_reviews():
    """ログイン中のユーザーのレビュー一覧を取得"""
   
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response, 200
   
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'ログインが必要です'}), 401
   
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'データベース接続エラー'}), 500
   
    try:
        cur = conn.cursor()
       
        cur.execute(
            '''SELECT * FROM reviews
               WHERE user_id = %s
               ORDER BY created_at DESC''',
            (session['user_id'],)
        )
       
        reviews = cur.fetchall()
       
        return jsonify({
            'success': True,
            'count': len(reviews),
            'reviews': [dict(review) for review in reviews]
        }), 200
       
    except Exception as e:
        print(f"❌ ユーザーレビュー取得エラー: {e}")
        return jsonify({'success': False, 'message': 'サーバーエラー'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/api/reviews/user/check/<int:osm_id>', methods=['GET', 'OPTIONS'])  # ← OPTIONSを追加
def check_user_review(osm_id):
    """ユーザーが特定スポットにレビュー済みか確認"""
   
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response, 200
   
    print(f"\n=== レビューチェック: osm_id={osm_id} ===")
    print(f"セッション: {dict(session)}")
    print(f"user_id in session: {'user_id' in session}")
   
    if 'user_id' not in session:
        print("❌ 未ログイン")
        return jsonify({'success': True, 'has_review': False, 'logged_in': False}), 200
   
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'データベース接続エラー'}), 500
   
    try:
        cur = conn.cursor()
       
        cur.execute(
            'SELECT * FROM reviews WHERE user_id = %s AND osm_id = %s',
            (session['user_id'], osm_id)
        )
       
        review = cur.fetchone()
       
        if review:
            print(f"✅ 既存レビューあり: review_id={review['id']}")
            return jsonify({
                'success': True,
                'has_review': True,
                'logged_in': True,
                'review': dict(review)
            }), 200
        else:
            print("✅ レビューなし（投稿可能）")
            return jsonify({
                'success': True,
                'has_review': False,
                'logged_in': True
            }), 200
       
    except Exception as e:
        print(f"❌ レビュー確認エラー: {e}")
        return jsonify({'success': False, 'message': 'サーバーエラー'}), 500
    finally:
        cur.close()
        conn.close()
