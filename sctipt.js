// アンケート画面の機能（questionnaire.htmlで使用）
if (document.getElementById('questionnaire-form')) {
    const questions = document.querySelectorAll('.question-area');
    const progressText = document.getElementById('progress-text');
    const progressFill = document.getElementById('progress-fill');
    const nextBtn = document.getElementById('next-btn');
    const prevBtn = document.getElementById('prev-btn');
    const submitBtn = document.getElementById('submit-btn');
    
    let currentQuestion = 0;
    const totalQuestions = questions.length;
    
    // イベントリスナー
    nextBtn.addEventListener('click', nextQuestion);
    prevBtn.addEventListener('click', prevQuestion);
    
    // オプション選択の処理
    document.querySelectorAll('.mood-option input').forEach(radio => {
        radio.addEventListener('change', function() {
            updateNavigation();
        });
    });
    
    // 質問表示関数
    function showQuestion(index) {
        questions.forEach((q, i) => {
            q.classList.toggle('active', i === index);
        });
        
        // 進捗更新
        const progressPercent = ((index + 1) / totalQuestions) * 100;
        progressText.textContent = `質問${index + 1}／${totalQuestions}`;
        progressFill.style.width = `${progressPercent}%`;
        
        // ナビゲーション更新
        updateNavigation();
    }
    
    // ナビゲーション更新
    function updateNavigation() {
        const currentQuestionElement = questions[currentQuestion];
        const isAnswered = currentQuestionElement.querySelector('input:checked');
        
        // 前へボタン
        prevBtn.disabled = currentQuestion === 0;
        
        // 次へ/送信ボタン
        if (currentQuestion === totalQuestions - 1) {
            nextBtn.style.display = 'none';
            submitBtn.style.display = isAnswered ? 'flex' : 'none';
        } else {
            nextBtn.style.display = 'flex';
            submitBtn.style.display = 'none';
            nextBtn.style.opacity = isAnswered ? '1' : '0.7';
            nextBtn.style.cursor = isAnswered ? 'pointer' : 'not-allowed';
        }
    }
    
    function nextQuestion() {
        const currentQuestionElement = questions[currentQuestion];
        const isAnswered = currentQuestionElement.querySelector('input:checked');
        
        if (!isAnswered) {
            alert('選択してください！');
            return;
        }
        
        if (currentQuestion < totalQuestions - 1) {
            currentQuestion++;
            showQuestion(currentQuestion);
        }
    }
    
    function prevQuestion() {
        if (currentQuestion > 0) {
            currentQuestion--;
            showQuestion(currentQuestion);
        }
    }
    
    // 初期表示
    showQuestion(0);
}

// プラン生成機能（proposal.htmlで使用）
function generatePlans(answers) {
    const plansContainer = document.getElementById('plans-container');
    if (!plansContainer) return;
    
    plansContainer.innerHTML = '';
    
    // プランデータ
    const planTemplates = {
        excited: {
            title: "エキサイティング冒険プラン",
            price: "58,000円〜",
            description: "ワクワクする体験が満載のアクティブな旅",
            features: [
                "スリリングなアクティビティ",
                "絶景スポット巡り",
                "ローカルガイド付き",
                "写真撮影サービス"
            ]
        },
        relaxed: {
            title: "のんびりリラックスプラン",
            price: "42,000円〜",
            description: "心と体を癒すゆったりとした時間",
            features: [
                "温泉宿泊",
                "スパトリートメント",
                "自然散策",
                "朝食バイキング"
            ]
        },
        adventurous: {
            title: "本格アドベンチャープラン",
            price: "65,000円〜",
            description: "大自然を満喫する本格的な冒険",
            features: [
                "トレッキングツアー",
                "アウトドア体験",
                "専門ガイド同行",
                "装備レンタル"
            ]
        },
        chilled: {
            title: "まったり滞在プラン",
            price: "38,000円〜",
            description: "自分のペースで楽しむゆったり旅",
            features: [
                "自由なスケジュール",
                "カフェ巡り",
                "読書タイム",
                "地元体験"
            ]
        }
    };
    
    // メインプラン（気分に基づく）
    const mainPlan = planTemplates[answers.mood];
    if (mainPlan) {
        const planElement = createPlanElement(mainPlan, true);
        plansContainer.appendChild(planElement);
    }
    
    // 代替プラン（他の気分）
    Object.entries(planTemplates).forEach(([key, plan]) => {
        if (key !== answers.mood) {
            const planElement = createPlanElement(plan, false);
            plansContainer.appendChild(planElement);
        }
    });
}

function createPlanElement(plan, isMain) {
    const planDiv = document.createElement('div');
    planDiv.className = 'plan-card';
    if (isMain) {
        planDiv.classList.add('selected');
    }
    
    planDiv.innerHTML = `
        <div class="plan-header">
            <div class="plan-title">${plan.title}</div>
            <div class="plan-price">${plan.price}</div>
        </div>
        <div class="plan-description">${plan.description}</div>
        <ul class="plan-features">
            ${plan.features.map(feature => `<li>${feature}</li>`).join('')}
        </ul>
        <button class="select-btn" onclick="selectPlan(this)">
            ${isMain ? 'おすすめプランを選択' : 'このプランを選択'}
        </button>
    `;
    
    return planDiv;
}

function selectPlan(button) {
    const planCard = button.closest('.plan-card');
    const planTitle = planCard.querySelector('.plan-title').textContent;
    
    alert(`「${planTitle}」が選択されました！\nご利用ありがとうございます。`);
}