from flask import Flask, request, jsonify, session, send_from_directory
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

# 環境変数の読み込み
load_dotenv()

# ベースディレクトリ（C:\travel）を取得
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__, 
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'mysecretkey123')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)

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

# HTMLファイルの配信
@app.route('/')
def index():
    """ログインページを表示"""
    return send_from_directory(os.path.join(BASE_DIR, 'templates'), 'login.html')

@app.route('/<path:path>')
def serve_static(path):
    """静的ファイルを配信"""
    return send_from_directory(os.path.join(BASE_DIR, 'templates'), path)

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
    
import re
import requests
from flask import jsonify, request

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
            if len(name) > 20:
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
    'instagram': tags.get('contact:instagram', '')
}


        spots = list(spots_dict.values())
        return jsonify({'success': True, 'count': len(spots), 'spots': spots}), 200

    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'message': 'APIリクエストがタイムアウトしました'}), 504
    except Exception as e:
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500

@app.route('/api/search-spots', methods=['GET'])
def search_spots():
    """検索クエリに基づいて観光スポットを検索"""    
    
    query = request.args.get('query', '').strip()
    
    if not query:
        return jsonify({
            'success': False,
            'message': '検索キーワードを入力してください'
        }), 400
    
    overpass_query = f"""
    [out:json][timeout:30];
    (
      node["name"~"{query}",i](34.4,135.2,34.9,135.8);
      way["name"~"{query}",i](34.4,135.2,34.9,135.8);
      node["name"~"{query}",i](34.8,135.5,35.3,136.0);
      way["name"~"{query}",i](34.8,135.5,35.3,136.0);
      node["name"~"{query}",i](34.4,135.6,34.9,136.1);
      way["name"~"{query}",i](34.4,135.6,34.9,136.1);
    );
    out body 100;
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
        spots_dict = {}
        
        for element in data.get('elements', []):
            if 'tags' not in element:
                continue

            tags = element['tags']
            element_id = element.get('id')
            lat = element.get('lat') or element.get('center', {}).get('lat')
            lon = element.get('lon') or element.get('center', {}).get('lon')
            name = tags.get('name:ja') or tags.get('name') or '名称不明'

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
                elif tags.get('tourism') == 'aquarium':
                    spot_type = '水族館'
                elif tags.get('tourism') == 'theme_park':
                    spot_type = 'テーマパーク'
                elif tags.get('tourism') == 'attraction':
                    spot_type = '観光地'
                elif tags.get('tourism') == 'viewpoint':
                    spot_type = '展望台'
                elif tags.get('tourism') == 'zoo':
                    spot_type = '動物園'
                elif tags.get('leisure') == 'water_park':
                    spot_type = 'ウォーターパーク'
                elif tags.get('leisure') == 'park':
                    spot_type = '公園'
                elif tags.get('amenity') == 'place_of_worship':
                    spot_type = '寺社'
                elif tags.get('amenity') == 'theatre':
                    spot_type = '劇場'
                elif tags.get('amenity') == 'library':
                    spot_type = '図書館'
                elif tags.get('amenity') == 'cinema':
                    spot_type = '映画館'
                elif tags.get('amenity') in ['restaurant', 'cafe', 'fast_food', 'food_court', 'bar', 'pub']:
                    spot_type = '飲食店'
                
                # ✅ websiteを複数の可能性から取得
                website = (tags.get('website') or 
                          tags.get('contact:website') or 
                          tags.get('url') or 
                          tags.get('official_website') or '')

                # 住所の補完処理
                address = (tags.get('addr:full') or f"{tags.get('addr:city', '')} {tags.get('addr:street', '')} {tags.get('addr:postcode', '')}".strip()
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
    'instagram': tags.get('contact:instagram', '')
}

        
        spots = list(spots_dict.values())
        print(f"検索結果: {len(spots)}件（キーワード: {query}）")
        
        return jsonify({
            'success': True,
            'query': query,
            'count': len(spots),
            'spots': spots
        }), 200
        
    except requests.exceptions.Timeout:
        print(f"タイムアウト: キーワード「{query}」")
        return jsonify({
            'success': False,
            'message': 'APIリクエストがタイムアウトしました'
        }), 504
    except Exception as e:
        print(f"検索エラー: {e}")
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        }), 500




@app.route('/api/search-by-category', methods=['GET'])
def search_by_category():
    """カテゴリで観光スポットを検索"""
    
    category = request.args.get('category', '').strip()
    
    if not category:
        return jsonify({
            'success': False,
            'message': 'カテゴリを選択してください'
        }), 400
    
    # カテゴリに応じたOverpass APIクエリを生成
    category_queries = {
        'castle': ('node["historic"="castle"](33.5,134.5,35.8,136.8); way["historic"="castle"](33.5,134.5,35.8,136.8);', '城'),
        'buddhist': ('node["amenity"="place_of_worship"]["religion"="buddhist"]["wikidata"](33.5,134.5,35.8,136.8);', '寺院'),
        'shinto': ('node["amenity"="place_of_worship"]["religion"="shinto"]["wikidata"](33.5,134.5,35.8,136.8);', '神社'),
        'museum': ('node["tourism"="museum"](33.5,134.5,35.8,136.8); way["tourism"="museum"](33.5,134.5,35.8,136.8);', '博物館'),
        'gallery': ('node["tourism"="gallery"](33.5,134.5,35.8,136.8);', '美術館'),
        'theme_park': ('node["tourism"="theme_park"](33.5,134.5,35.8,136.8); way["tourism"="theme_park"](33.5,134.5,35.8,136.8);', 'テーマパーク'),
        'heritage': ('node["heritage"="1"](33.5,134.5,35.8,136.8); way["heritage"="1"](33.5,134.5,35.8,136.8); relation["heritage"="1"](33.5,134.5,35.8,136.8);', '世界遺産'),
        'park': ('node["leisure"="park"](33.5,134.5,35.8,136.8);', '公園'),
        'theatre': ('node["amenity"="theatre"](33.5,134.5,35.8,136.8);', '劇場'),
        'restaurant': ('node["amenity"~"restaurant|cafe|fast_food|food_court|bar|pub"](33.5,134.5,35.8,136.8);', '飲食店'),
        'library': ('node["amenity"="library"](33.5,134.5,35.8,136.8);', '図書館'),
        'cinema': ('node["amenity"="cinema"](33.5,134.5,35.8,136.8);', '映画館'),
        'water_park': ('node["leisure"="water_park"](33.5,134.5,35.8,136.8);', 'ウォーターパーク'),
        'zoo': ('node["tourism"="zoo"](33.5,134.5,35.8,136.8);', '動物園'),
        'aquarium': ('node["tourism"="aquarium"](33.5,134.5,35.8,136.8);', '水族館'),
        'viewpoint': ('node["tourism"="viewpoint"](33.5,134.5,35.8,136.8);', '展望台'),
    }
    
    if category not in category_queries:
        return jsonify({
            'success': False,
            'message': '無効なカテゴリです'
        }), 400
    
    query_part, category_name = category_queries[category]
    
    overpass_query = f"""
    [out:json][timeout:30];
    (
      {query_part}
    );
    out body 100;
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
        spots_dict = {}
        
        for element in data.get('elements', []):
            if 'tags' not in element:
                continue

            tags = element['tags']
            element_id = element.get('id')
            lat = element.get('lat') or element.get('center', {}).get('lat')
            lon = element.get('lon') or element.get('center', {}).get('lon')
            name = tags.get('name:ja') or tags.get('name') or '名称不明'
            
            if not name or name == '名称不明':
                continue
            if len(name) > 20:
                continue
            
            bad_keywords = ['詰所', '案内', '地図', '乗り場', '駐車場', 'トイレ',
                            '入口', '出口', '受付', '売店', 'ゲート', '記念碑']
            if any(keyword in name for keyword in bad_keywords):
                continue

            # ✅ websiteを複数の可能性から取得
            website = (tags.get('website') or 
                    tags.get('contact:website') or 
                    tags.get('url') or 
                    tags.get('official_website') or '')
            if lat and lon and element_id not in spots_dict:
                spots_dict[element_id] = {
                    'id': element_id,
                    'name': name,
                    'lat': lat,
                    'lon': lon,
                    'type': category_name,
                    'address': tags.get('addr:full', tags.get('addr:city', '')),
                    'description': tags.get('description', ''),
                    'website': website ,
                    'opening_hours': tags.get('opening_hours', ''),
                    'phone': tags.get('phone', ''),
                    'email': tags.get('contact:email', ''),
                    'facebook': tags.get('contact:facebook', ''),
                    'instagram': tags.get('contact:instagram', ''),

                }
        
        spots = list(spots_dict.values())
        print(f"カテゴリ検索結果: {len(spots)}件（カテゴリ: {category_name}）")
        
        return jsonify({
            'success': True,
            'category': category,
            'category_name': category_name,
            'count': len(spots),
            'spots': spots
        }), 200
        
    except requests.exceptions.Timeout:
        print(f"タイムアウト: カテゴリ「{category}」")
        return jsonify({
            'success': False,
            'message': 'APIリクエストがタイムアウトしました'
        }), 504
    except Exception as e:
        print(f"カテゴリ検索エラー: {e}")
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        }), 500
