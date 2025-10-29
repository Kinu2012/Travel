const express = require('express');
const bcrypt = require('bcrypt');
const session = require('express-session');
const { Pool } = require('pg');
const cors = require('cors');

const app = express();
const PORT = 3000;

// PostgreSQL接続設定
const pool = new Pool({
  user: 'postgres',
  host: 'localhost',
  database: 'travel',
  password: 'kashiwa0001',
  port: 5432,
});

// ミドルウェア設定
app.use(cors({
  origin: 'http://localhost:8080', // フロントエンドのURL
  credentials: true
}));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(session({
  secret: 'your-secret-key-change-this',
  resave: false,
  saveUninitialized: false,
  cookie: {
    secure: false, // 本番環境ではtrueに設定（HTTPS必須）
    httpOnly: true,
    maxAge: 24 * 60 * 60 * 1000 // 24時間
  }
}));

// ユーザー登録エンドポイント
app.post('/api/register', async (req, res) => {
  const { username, email, password, fullname, birthdate, gender } = req.body;
  
  try {
    // 入力バリデーション
    if (!username || !email || !password) {
      return res.status(400).json({ 
        success: false, 
        message: '必須項目を入力してください' 
      });
    }

    // メールアドレスの重複チェック
    const emailCheck = await pool.query(
      'SELECT * FROM users WHERE email = $1',
      [email]
    );
    
    if (emailCheck.rows.length > 0) {
      return res.status(400).json({ 
        success: false, 
        message: 'このメールアドレスは既に登録されています' 
      });
    }

    // ユーザーIDの重複チェック
    const userIdCheck = await pool.query(
      'SELECT * FROM users WHERE user_id = $1',
      [username]
    );
    
    if (userIdCheck.rows.length > 0) {
      return res.status(400).json({ 
        success: false, 
        message: 'このユーザー名は既に使用されています' 
      });
    }

    // パスワードのハッシュ化
    const saltRounds = 10;
    const hashedPassword = await bcrypt.hash(password, saltRounds);

    // 年齢計算
    let age = null;
    if (birthdate) {
      const today = new Date();
      const birth = new Date(birthdate);
      age = today.getFullYear() - birth.getFullYear();
      const monthDiff = today.getMonth() - birth.getMonth();
      if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
        age--;
      }
    }

    // ユーザー登録
    const result = await pool.query(
      `INSERT INTO users (user_id, password, name, email, age, created_at, updated_at) 
       VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) 
       RETURNING id, user_id, name, email, age, created_at`,
      [username, hashedPassword, fullname || username, email, age]
    );

    res.status(201).json({
      success: true,
      message: '登録が完了しました',
      user: {
        id: result.rows[0].id,
        user_id: result.rows[0].user_id,
        name: result.rows[0].name,
        email: result.rows[0].email,
        age: result.rows[0].age
      }
    });

  } catch (error) {
    console.error('登録エラー:', error);
    res.status(500).json({ 
      success: false, 
      message: 'サーバーエラーが発生しました' 
    });
  }
});

// ログインエンドポイント
app.post('/api/login', async (req, res) => {
  const { email, password } = req.body;
  
  try {
    // 入力バリデーション
    if (!email || !password) {
      return res.status(400).json({ 
        success: false, 
        message: 'メールアドレスとパスワードを入力してください' 
      });
    }

    // ユーザー検索
    const result = await pool.query(
      'SELECT * FROM users WHERE email = $1',
      [email]
    );

    if (result.rows.length === 0) {
      return res.status(401).json({ 
        success: false, 
        message: 'メールアドレスまたはパスワードが正しくありません' 
      });
    }

    const user = result.rows[0];

    // パスワード検証
    const validPassword = await bcrypt.compare(password, user.password);

    if (!validPassword) {
      return res.status(401).json({ 
        success: false, 
        message: 'メールアドレスまたはパスワードが正しくありません' 
      });
    }

    // セッションにユーザー情報を保存
    req.session.userId = user.id;
    req.session.userEmail = user.email;

    // 最終ログイン時刻を更新
    await pool.query(
      'UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE id = $1',
      [user.id]
    );

    res.json({
      success: true,
      message: 'ログインに成功しました',
      user: {
        id: user.id,
        user_id: user.user_id,
        name: user.name,
        email: user.email,
        age: user.age
      }
    });

  } catch (error) {
    console.error('ログインエラー:', error);
    res.status(500).json({ 
      success: false, 
      message: 'サーバーエラーが発生しました' 
    });
  }
});

// ログアウトエンドポイント
app.post('/api/logout', (req, res) => {
  req.session.destroy((err) => {
    if (err) {
      return res.status(500).json({ 
        success: false, 
        message: 'ログアウトに失敗しました' 
      });
    }
    res.json({ 
      success: true, 
      message: 'ログアウトしました' 
    });
  });
});

// 認証チェック用ミドルウェア
const requireAuth = (req, res, next) => {
  if (!req.session.userId) {
    return res.status(401).json({ 
      success: false, 
      message: '認証が必要です' 
    });
  }
  next();
};

// ユーザー情報取得エンドポイント（認証必須）
app.get('/api/user', requireAuth, async (req, res) => {
  try {
    const result = await pool.query(
      'SELECT id, user_id, name, email, age, created_at FROM users WHERE id = $1',
      [req.session.userId]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ 
        success: false, 
        message: 'ユーザーが見つかりません' 
      });
    }

    res.json({
      success: true,
      user: result.rows[0]
    });

  } catch (error) {
    console.error('ユーザー情報取得エラー:', error);
    res.status(500).json({ 
      success: false, 
      message: 'サーバーエラーが発生しました' 
    });
  }
});

// サーバー起動
app.listen(PORT, () => {
  console.log(`サーバーがポート${PORT}で起動しました`);
});

// データベース接続確認
pool.query('SELECT NOW()', (err, res) => {
  if (err) {
    console.error('データベース接続エラー:', err);
  } else {
    console.log('データベースに接続しました');
  }
});