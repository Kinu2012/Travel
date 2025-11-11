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
import random
from typing import Dict, List
import re


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

# CORS設定
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
# ========== Overpass API関連関数（calculate_age()の後に追加）==========

def fetch_spots_from_overpass(category_keys: List[str], limit: int = 100) -> List[Dict]:
    """Overpass APIから指定カテゴリーのスポットを取得"""
    
    category_queries = {
        'relax': [
            'node["leisure"="spa"](33.5,134.5,35.8,136.8);',
            'node["amenity"="hot_spring"](33.5,134.5,35.8,136.8);',
            'node["tourism"="hot_spring"](33.5,134.5,35.8,136.8);',
        ],
        'nature': [
            'node["natural"="peak"](33.5,134.5,35.8,136.8);',
            'node["natural"="beach"](33.5,134.5,35.8,136.8);',
            'node["tourism"="viewpoint"](33.5,134.5,35.8,136.8);',
            'way["leisure"="park"]["name"](33.5,134.5,35.8,136.8);',
        ],
        'culture': [
            'node["historic"="castle"](33.5,134.5,35.8,136.8);',
            'way["historic"="castle"](33.5,134.5,35.8,136.8);',
            'node["amenity"="place_of_worship"]["religion"="buddhist"](33.5,134.5,35.8,136.8);',
            'node["amenity"="place_of_worship"]["religion"="shinto"](33.5,134.5,35.8,136.8);',
            'node["tourism"="museum"](33.5,134.5,35.8,136.8);',
        ],
        'gourmet': [
            'node["amenity"="restaurant"](33.5,134.5,35.8,136.8);',
            'node["amenity"="marketplace"](33.5,134.5,35.8,136.8);',
        ],
        'activity': [
            'node["tourism"="theme_park"](33.5,134.5,35.8,136.8);',
            'way["tourism"="theme_park"](33.5,134.5,35.8,136.8);',
            'node["tourism"="zoo"](33.5,134.5,35.8,136.8);',
            'node["tourism"="aquarium"](33.5,134.5,35.8,136.8);',
            'node["leisure"="water_park"](33.5,134.5,35.8,136.8);',
        ],
        'shopping': [
            'node["shop"="mall"](33.5,134.5,35.8,136.8);',
            'way["shop"="mall"](33.5,134.5,35.8,136.8);',
        ]
    }
    
    query_parts = []
    for cat_key in category_keys:
        if cat_key in category_queries:
            query_parts.extend(category_queries[cat_key])
    
    if not query_parts:
        print("警告: 有効なカテゴリーが指定されていません")
        return []
    
    # ★ クエリ構文を修正
    overpass_query = f"""
    [out:json][timeout:30];
    (
      {''.join(query_parts)}
    );
    out body {limit};
    """
    
    print(f"生成されたクエリ:\n{overpass_query}")  # デバッグ用
    
    try:
        overpass_url = "http://overpass-api.de/api/interpreter"
        print(f"Overpass APIリクエスト送信中... (カテゴリー: {category_keys})")
        
        response = requests.post(overpass_url, data={'data': overpass_query}, timeout=30)
        
        if response.status_code != 200:
            print(f"Overpass APIエラー: {response.status_code}")
            print(f"レスポンス: {response.text[:500]}")  # エラー詳細
            return []
        
        data = response.json()
        spots_dict = {}
        
        for element in data.get('elements', []):
            if 'tags' not in element:
                continue
            
            tags = element['tags']
            element_id = element.get('id')
            lat = element.get('lat') or element.get('center', {}).get('lat')
            lon = element.get('lon') or element.get('center', {}).get('lon')
            name = tags.get('name:ja') or tags.get('name')
            
            if not name or len(name) > 30:
                continue
            
            bad_keywords = ['詰所', '案内', '駐車場', 'トイレ', '入口', '出口', '売店']
            if any(kw in name for kw in bad_keywords):
                continue
            
            if not lat or not lon or element_id in spots_dict:
                continue
            
            spot_type = determine_spot_type(tags)
            category = map_type_to_category(spot_type)
            emoji = get_emoji_for_type(spot_type)
            
            website = (tags.get('website') or tags.get('contact:website') or 
                      tags.get('url') or '')
            
            address = (tags.get('addr:full') or 
                      f"{tags.get('addr:city', '')} {tags.get('addr:street', '')}".strip() or
                      tags.get('addr:city', '住所情報なし'))
            
            spots_dict[element_id] = {
                'id': f"overpass_{element_id}",
                'name': name,
                'lat': lat,
                'lon': lon,
                'type': spot_type,
                'category': category,
                'category_key': determine_category_key(spot_type),
                'address': address,
                'description': generate_description(name, spot_type),
                'image': emoji,
                'website': website,
                'tags': generate_tags(tags, spot_type)  # ★ 必ず配列を返す
            }
        
        spots = list(spots_dict.values())
        print(f"Overpass APIから{len(spots)}件取得")
        return spots
        
    except Exception as e:
        print(f"Overpass API エラー: {e}")
        import traceback
        traceback.print_exc()
        return []


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
        '城': 'culture',
        '寺院': 'culture',
        '神社': 'culture',
        '博物館': 'culture',
        'レストラン': 'gourmet',
        'ショッピングモール': 'shopping',
        'テーマパーク': 'activity',
        '動物園': 'activity',
        '水族館': 'activity',
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

def analyze_answers(answers: Dict) -> Dict:
    """
    アンケート回答を分析してカテゴリー優先度を返す
    
    Args:
        answers: アンケート回答辞書
        
    Returns:
        {
            'primary': ['category1', 'category2'],  # 主要カテゴリー
            'secondary': ['category3'],              # 補助カテゴリー
            'filters': {...}                         # フィルター条件
        }
    """
    mood = answers.get('mood', '')
    purpose = answers.get('purpose', '')
    budget = answers.get('budget', '')
    duration = answers.get('duration', '')
    companion = answers.get('companion', '')
    
    result = {
        'primary': [],
        'secondary': [],
        'filters': {
            'budget': budget,
            'duration': duration,
            'companion': companion
        }
    }
    
    # 目的からカテゴリーを決定
    purpose_mapping = {
        'relax': ['relax', 'nature'],
        'adventure': ['activity', 'nature'],
        'culture': ['culture', 'gourmet'],
        'gourmet': ['gourmet', 'culture']
    }
    
    # 気分からカテゴリーを調整
    mood_mapping = {
        'excited': ['activity', 'shopping'],
        'relaxed': ['relax', 'nature'],
        'adventurous': ['nature', 'activity'],
        'chilled': ['relax', 'gourmet']
    }
    
    # 主要カテゴリー決定
    if purpose in purpose_mapping:
        result['primary'].extend(purpose_mapping[purpose])
    
    # 補助カテゴリー決定
    if mood in mood_mapping:
        for cat in mood_mapping[mood]:
            if cat not in result['primary']:
                result['secondary'].append(cat)
    
    # 重複削除
    result['primary'] = list(dict.fromkeys(result['primary']))
    result['secondary'] = list(dict.fromkeys(result['secondary']))
    
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
                # 分析に基づいてスポットをフィルタリング
                filtered_spots = []
                for spot in all_fallback_spots:
                    spot_category = spot.get('category_key', '')
                    if spot_category in all_categories:
                        filtered_spots.append(spot)
                
                print(f"デバッグ: フィルタリング後スポット数 = {len(filtered_spots)}")
                
                # フィルタリングされたスポットから選択、なければ全スポットから
                if filtered_spots:
                    selected_spots = random.sample(filtered_spots, min(num_spots, len(filtered_spots)))
                else:
                    selected_spots = random.sample(all_fallback_spots, min(num_spots, len(all_fallback_spots)))
                
                print(f"デバッグ: 最終選択スポット数 = {len(selected_spots)}")
                return selected_spots
    
    # Overpass APIデータを使用する場合
    if spots:
        # 主要カテゴリーのスポットを優先
        primary_spots = [s for s in spots if s.get('category_key') in analysis['primary']]
        secondary_spots = [s for s in spots if s.get('category_key') in analysis['secondary']]
        other_spots = [s for s in spots if s not in primary_spots and s not in secondary_spots]
        
        recommended = []
        
        # 主要カテゴリーから60%
        primary_count = int(num_spots * 0.6)
        if primary_spots:
            recommended.extend(random.sample(primary_spots, min(primary_count, len(primary_spots))))
        
        # 補助カテゴリーから残り
        remaining = num_spots - len(recommended)
        if remaining > 0 and secondary_spots:
            recommended.extend(random.sample(secondary_spots, min(remaining, len(secondary_spots))))
        
        # まだ足りない場合は他から
        remaining = num_spots - len(recommended)
        if remaining > 0 and other_spots:
            recommended.extend(random.sample(other_spots, min(remaining, len(other_spots))))
        
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
    """スポットデータを取得（更新版）"""
    try:
        if not SPOTS_DATA or not SPOTS_DATA.get('categories'):
            return jsonify({
                'success': False,
                'message': 'スポットデータが見つかりません'
            }), 404
        
        return jsonify({
            'success': True,
            'data': SPOTS_DATA
        }), 200
        
    except Exception as e:
        print(f"スポットデータ取得エラー: {e}")
        return jsonify({
            'success': False,
            'message': 'データの読み込みに失敗しました'
        }), 500


@app.route('/api/spot/<spot_id>')
def api_spot_detail(spot_id):
    """
    特定のスポット詳細を返すAPI
    
    Args:
        spot_id: スポットID
    
    Returns:
        JSON: スポット詳細情報
    """
    try:
        categories = SPOTS_DATA.get('categories', {})
        
        for category_key, category_data in categories.items():
            for spot in category_data.get('spots', []):
                if spot.get('id') == spot_id:
                    # カテゴリー情報を追加
                    spot_detail = spot.copy()
                    spot_detail['category'] = category_data.get('name')
                    spot_detail['category_key'] = category_key
                    
                    return jsonify({
                        'success': True,
                        'spot': spot_detail
                    }), 200
        
        return jsonify({
            'success': False,
            'message': 'スポットが見つかりません'
        }), 404
        
    except Exception as e:
        print(f"スポット詳細取得エラー: {e}")
        return jsonify({
            'success': False,
            'message': 'エラーが発生しました'
        }), 500
    
@app.route('/questionnaire')
def questionnaire():
    """アンケートページを表示"""
    return send_from_directory(os.path.join(BASE_DIR, 'templates'), 'questionnaire.html')


@app.route('/api/recommend', methods=['GET'])
def api_recommend():
    """
    推薦API
    
    Query Parameters:
        mood: excited/relaxed/adventurous/chilled
        purpose: relax/adventure/culture/gourmet
        budget: low/medium/high
        duration: short/medium/long
        companion: solo/couple/family/friends
    
    Returns:
        JSON: {
            'success': True,
            'answers': {...},
            'analysis': {...},
            'spots': [...]
        }
    """
    print("=== 推薦APIリクエスト受信 ===")
    
    answers = {
        'mood': request.args.get('mood', ''),
        'purpose': request.args.get('purpose', ''),
        'budget': request.args.get('budget', ''),
        'duration': request.args.get('duration', ''),
        'companion': request.args.get('companion', '')
    }
    
    print(f"回答内容: {answers}")
    
    # バリデーション
    if not all(answers.values()):
        return jsonify({
            'success': False,
            'message': 'すべての質問に回答してください'
        }), 400
    
    try:
        # 分析と推薦
        analysis = analyze_answers(answers)
        spots = get_recommended_spots_from_api(analysis)
        
        print(f"推薦スポット数: {len(spots)}件")
        
        return jsonify({
            'success': True,
            'answers': answers,
            'analysis': analysis,
            'spots': spots
        }), 200
        
    except Exception as e:
        print(f"推薦処理エラー: {e}")
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        }), 500


@app.route('/proposal')
def proposal():
    """
    提案ページを表示
    アンケート回答からスポットを推薦して表示
    """
    print("=== 提案ページリクエスト受信 ===")
    
    answers = {
        'mood': request.args.get('mood', ''),
        'purpose': request.args.get('purpose', ''),
        'budget': request.args.get('budget', ''),
        'duration': request.args.get('duration', ''),
        'companion': request.args.get('companion', '')
    }
    
    print(f"回答内容: {answers}")
    
    # バリデーション
    if not all(answers.values()):
        # エラーページまたはアンケートページにリダイレクト
        return '''
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>エラー</title>
            <style>
                body {
                    font-family: sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .error-box {
                    background: white;
                    padding: 40px;
                    border-radius: 20px;
                    text-align: center;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                }
                .error-icon { font-size: 3em; margin-bottom: 20px; }
                h1 { color: #667eea; margin-bottom: 20px; }
                a {
                    display: inline-block;
                    margin-top: 20px;
                    padding: 15px 30px;
                    background: linear-gradient(135deg, #667eea, #764ba2);
                    color: white;
                    text-decoration: none;
                    border-radius: 10px;
                    font-weight: bold;
                }
            </style>
        </head>
        <body>
            <div class="error-box">
                <div class="error-icon">⚠️</div>
                <h1>アンケート未回答</h1>
                <p>アンケートに回答してください</p>
                <a href="/questionnaire">アンケートに回答する</a>
            </div>
        </body>
        </html>
        ''', 400
    
    try:
        # 分析と推薦
        analysis = analyze_answers(answers)
        spots = get_recommended_spots_from_api(analysis)
        
        print(f"推薦スポット数: {len(spots)}件")
        
        # HTMLテンプレートを生成（render_templateの代わりに直接HTML生成）
        # または render_template('proposal.html', ...) を使用
        # ここでは簡単のため、proposal.htmlを読み込んで変数を埋め込む
        
        # proposal.htmlが存在する場合
        proposal_path = os.path.join(BASE_DIR, 'templates', 'proposal.html')
        if os.path.exists(proposal_path):
            # Flaskのrender_templateを使用するため、Jinjaテンプレートとして読み込み
            from flask import render_template
            return render_template('proposal.html', 
                                 answers=answers,
                                 spots=spots,
                                 analysis=analysis)
        else:
            # proposal.htmlがない場合は簡易版を返す
            return generate_simple_proposal_html(answers, spots, analysis)
        
    except Exception as e:
        print(f"提案ページ生成エラー: {e}")
        import traceback
        traceback.print_exc()
        return f'''
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <title>エラー</title>
            <style>
                body {{
                    font-family: sans-serif;
                    padding: 40px;
                    background: #f5f5f5;
                }}
                .error {{ 
                    background: #ff4444;
                    color: white;
                    padding: 20px;
                    border-radius: 10px;
                }}
            </style>
        </head>
        <body>
            <div class="error">
                <h1>エラーが発生しました</h1>
                <p>{str(e)}</p>
                <a href="/questionnaire" style="color: white;">アンケートに戻る</a>
            </div>
        </body>
        </html>
        ''', 500


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
    '''



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
    
    
# @app.route('/api/overpass-spots', methods=['GET'])
# def get_overpass_spots():
#     """Overpass APIから厳選された観光スポットのみを取得"""

#     overpass_query = """
#     [out:json][timeout:25];
#     (
#       node["historic"="castle"](33.5,134.5,35.8,136.8);
#       way["historic"="castle"](33.5,134.5,35.8,136.8);

#       node["amenity"="place_of_worship"]["religion"="buddhist"]["wikidata"](33.5,134.5,35.8,136.8);
#       node["amenity"="place_of_worship"]["religion"="shinto"]["wikidata"](33.5,134.5,35.8,136.8);

#       node["tourism"="museum"](33.5,134.5,35.8,136.8);
#       way["tourism"="museum"](33.5,134.5,35.8,136.8);
#       node["tourism"="gallery"](33.5,134.5,35.8,136.8);

#       node["tourism"="theme_park"](33.5,134.5,35.8,136.8);
#       way["tourism"="theme_park"](33.5,134.5,35.8,136.8);

#       node["heritage"="1"](33.5,134.5,35.8,136.8);
#       way["heritage"="1"](33.5,134.5,35.8,136.8);
#       relation["heritage"="1"](33.5,134.5,35.8,136.8);

#       node["leisure"="park"]["operator"~"国"](33.5,134.5,35.8,136.8);

#       node["amenity"="theatre"](33.5,134.5,35.8,136.8);

#       node["amenity"~"restaurant|cafe|fast_food|food_court|bar|pub"](33.5,134.5,35.8,136.8);

#       node["amenity"="library"](33.5,134.5,35.8,136.8);
#       node["amenity"="cinema"](33.5,134.5,35.8,136.8);
#       node["leisure"="water_park"](33.5,134.5,35.8,136.8);
#       node["tourism"="zoo"](33.5,134.5,35.8,136.8);
#       node["tourism"="aquarium"](33.5,134.5,35.8,136.8);
#       node["tourism"="viewpoint"](33.5,134.5,35.8,136.8);
#     );
#     out body 150;
#     """

#     try:
#         overpass_url = "http://overpass-api.de/api/interpreter"
#         response = requests.post(overpass_url, data={'data': overpass_query}, timeout=30)

#         if response.status_code != 200:
#             return jsonify({'success': False, 'message': 'Overpass APIからのデータ取得に失敗しました'}), 500

#         data = response.json()
#         spots_dict = {}

#         for element in data.get('elements', []):
#             if 'tags' not in element:
#                 continue

#             tags = element['tags']
#             element_id = element.get('id')
#             lat = element.get('lat') or element.get('center', {}).get('lat')
#             lon = element.get('lon') or element.get('center', {}).get('lon')
#             name = tags.get('name:ja') or tags.get('name') or tags.get('name:en')

#             if not name or name == '名称不明':
#                 continue
#             if len(name) > 20:
#                 continue

#             bad_keywords = ['詰所', '案内', '地図', '乗り場', '駐車場', 'トイレ',
#                             '入口', '出口', '受付', '売店', 'ゲート', '記念碑']
#             if any(keyword in name for keyword in bad_keywords):
#                 continue
#             if any(keyword in str(value) for value in tags.values() for keyword in bad_keywords):
#                 continue

#             if lat and lon and element_id not in spots_dict:
#                 spot_type = 'その他'
#                 if tags.get('historic') == 'castle':
#                     spot_type = '城'
#                 elif tags.get('religion') == 'buddhist':
#                     spot_type = '寺院'
#                 elif tags.get('religion') == 'shinto':
#                     spot_type = '神社'
#                 elif tags.get('tourism') == 'museum':
#                     spot_type = '博物館'
#                 elif tags.get('tourism') == 'gallery':
#                     spot_type = '美術館'
#                 elif tags.get('tourism') == 'theme_park':
#                     spot_type = 'テーマパーク'
#                 elif tags.get('heritage') == '1':
#                     spot_type = '世界遺産'
#                 elif tags.get('leisure') == 'park':
#                     spot_type = '公園'
#                 elif tags.get('amenity') == 'theatre':
#                     spot_type = '劇場'
#                 elif tags.get('amenity') in ['restaurant', 'cafe', 'fast_food', 'food_court', 'bar', 'pub']:
#                     spot_type = '飲食店'
#                 elif tags.get('amenity') == 'library':
#                     spot_type = '図書館'
#                 elif tags.get('amenity') == 'cinema':
#                     spot_type = '映画館'
#                 elif tags.get('leisure') == 'water_park':
#                     spot_type = 'ウォーターパーク'
#                 elif tags.get('tourism') == 'zoo':
#                     spot_type = '動物園'
#                 elif tags.get('tourism') == 'aquarium':
#                     spot_type = '水族館'
#                 elif tags.get('tourism') == 'viewpoint':
#                     spot_type = '展望台'
                
#                 # ✅ websiteを複数の可能性から取得
#                 website = (tags.get('website') or 
#                           tags.get('contact:website') or 
#                           tags.get('url') or 
#                           tags.get('official_website') or '')

#                  # 住所の補完処理
#                 address = (
#                           tags.get('addr:full') or
#                           f"{tags.get('addr:city', '')} {tags.get('addr:street', '')} {tags.get('addr:postcode', '')}".strip()
# )

#                 spots_dict[element_id] = {
#     'id': element_id,
#     'name': name,
#     'lat': lat,
#     'lon': lon,
#     'type': spot_type,
#     'address': address,
#     'description': tags.get('description', ''),
#     'website': website,
#     'opening_hours': tags.get('opening_hours', ''),
#     'phone': tags.get('phone', ''),
#     'email': tags.get('contact:email', ''),
#     'facebook': tags.get('contact:facebook', ''),
#     'instagram': tags.get('contact:instagram', '')
# }


#         spots = list(spots_dict.values())
#         return jsonify({'success': True, 'count': len(spots), 'spots': spots}), 200

#     except requests.exceptions.Timeout:
#         return jsonify({'success': False, 'message': 'APIリクエストがタイムアウトしました'}), 504
#     except Exception as e:
#         return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500

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




