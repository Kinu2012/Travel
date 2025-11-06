from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
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

@app.route('/api/logout', methods=['POST'])
def logout():
    """ログアウト"""
    session.clear()
    return jsonify({'success': True, 'message': 'ログアウトしました'}), 200

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
#-------------------------------------------------------------------
#11/06チャンが作った

@app.route('/api/overpass-spots', methods=['GET'])
def get_overpass_spots():
    """Overpass APIから近畿地方の主要観光スポットを取得"""
    
    # Overpass API クエリ（バランス版）
    overpass_query = """
    [out:json][timeout:25];
    (
      // 城・史跡
      node["historic"="castle"](34.0,135.0,35.5,136.5);
      way["historic"="castle"](34.0,135.0,35.5,136.5);
      
      // 寺院
      node["amenity"="place_of_worship"]["religion"="buddhist"](34.0,135.0,35.5,136.5);
      
      // 神社
      node["amenity"="place_of_worship"]["religion"="shinto"](34.0,135.0,35.5,136.5);
      
      // 博物館
      node["tourism"="museum"](34.0,135.0,35.5,136.5);
      
      // 主要観光地
      node["tourism"="attraction"](34.0,135.0,35.5,136.5);
      
      // テーマパーク
      node["tourism"="theme_park"](34.0,135.0,35.5,136.5);
    );
    out body 300;
    """
    
    try:
        # Overpass APIにリクエスト
        overpass_url = "http://overpass-api.de/api/interpreter"
        response = requests.post(overpass_url, data={'data': overpass_query}, timeout=30)
        
        if response.status_code != 200:
            return jsonify({
                'success': False,
                'message': 'Overpass APIからのデータ取得に失敗しました'
            }), 500
        
        data = response.json()
        
        # データを整形（重複を除外）
        spots_dict = {}
        for element in data.get('elements', []):
            if 'tags' in element:
                tags = element['tags']
                element_id = element.get('id')
                
                # 座標を取得
                lat = element.get('lat') or (element.get('center', {}).get('lat'))
                lon = element.get('lon') or (element.get('center', {}).get('lon'))
                
                # 名前を取得（日本語名優先）
                name = tags.get('name:ja', tags.get('name', '名称不明'))
                
                if lat and lon and element_id not in spots_dict:
                    # タイプを判定
                    spot_type = 'other'
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
                    elif tags.get('tourism') == 'attraction':
                        spot_type = '観光地'
                    
                    spot = {
                        'id': element_id,
                        'name': name,
                        'lat': lat,
                        'lon': lon,
                        'type': spot_type,
                        'address': tags.get('addr:full', tags.get('addr:city', '')),
                        'description': tags.get('description', ''),
                        'website': tags.get('website', ''),
                    }
                    spots_dict[element_id] = spot
        
        spots = list(spots_dict.values())
        
        print(f"取得したスポット数: {len(spots)}件")
        
        return jsonify({
            'success': True,
            'count': len(spots),
            'spots': spots
        }), 200
        
    except requests.exceptions.Timeout:
        return jsonify({
            'success': False,
            'message': 'APIリクエストがタイムアウトしました'
        }), 504
    except Exception as e:
        print(f"Overpass API エラー: {e}")
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        }), 500
    #----------------------------------------------------------------------------
