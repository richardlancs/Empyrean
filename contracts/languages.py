"""Shared language vocabulary: language codes, display names and class-label translations.

Every module that speaks or words an answer agrees on these codes. The active
language is the language of audio's confirmed voice (VoiceStatus.language), so
it always matches what the speaker can actually pronounce. Translations here
are fixed and offline; nothing on a speech path looks a word up on the network.
Machine-drafted; a native speaker should review them before any real use.
"""

from __future__ import annotations

# Code -> the language's own name, for the dashboard picker, in menu order.
LANGUAGES: dict[str, str] = {
    "en": "English",
    "zh": "中文",
    "es": "Español",
    "fr": "Français",
    "hi": "हिन्दी",
}
DEFAULT_LANGUAGE = "en"

# Code -> English name of the language, for Grok prompts ("Reply in Spanish").
LANGUAGE_NAMES_EN: dict[str, str] = {
    "en": "English",
    "zh": "Mandarin Chinese (simplified characters)",
    "es": "Spanish",
    "fr": "French",
    "hi": "Hindi (Devanagari script)",
}

# English class label (COCO, plus the demo detector's labels) -> {code: translation}.
# English is the label itself. A label missing here is spoken in English.
CLASS_LABELS: dict[str, dict[str, str]] = {
    "person": {"zh": "人", "es": "persona", "fr": "personne", "hi": "व्यक्ति"},
    "bicycle": {"zh": "自行车", "es": "bicicleta", "fr": "vélo", "hi": "साइकिल"},
    "car": {"zh": "汽车", "es": "coche", "fr": "voiture", "hi": "कार"},
    "motorcycle": {"zh": "摩托车", "es": "motocicleta", "fr": "moto", "hi": "मोटरसाइकिल"},
    "airplane": {"zh": "飞机", "es": "avión", "fr": "avion", "hi": "हवाई जहाज़"},
    "bus": {"zh": "公交车", "es": "autobús", "fr": "bus", "hi": "बस"},
    "train": {"zh": "火车", "es": "tren", "fr": "train", "hi": "रेलगाड़ी"},
    "truck": {"zh": "卡车", "es": "camión", "fr": "camion", "hi": "ट्रक"},
    "boat": {"zh": "船", "es": "barco", "fr": "bateau", "hi": "नाव"},
    "traffic light": {"zh": "红绿灯", "es": "semáforo", "fr": "feu de circulation", "hi": "ट्रैफ़िक लाइट"},
    "fire hydrant": {"zh": "消防栓", "es": "hidrante", "fr": "bouche d'incendie", "hi": "फ़ायर हाइड्रेंट"},
    "stop sign": {"zh": "停车标志", "es": "señal de alto", "fr": "panneau stop", "hi": "रुकने का संकेत"},
    "parking meter": {"zh": "停车计时器", "es": "parquímetro", "fr": "parcmètre", "hi": "पार्किंग मीटर"},
    "bench": {"zh": "长椅", "es": "banco", "fr": "banc", "hi": "बेंच"},
    "bird": {"zh": "鸟", "es": "pájaro", "fr": "oiseau", "hi": "पक्षी"},
    "cat": {"zh": "猫", "es": "gato", "fr": "chat", "hi": "बिल्ली"},
    "dog": {"zh": "狗", "es": "perro", "fr": "chien", "hi": "कुत्ता"},
    "horse": {"zh": "马", "es": "caballo", "fr": "cheval", "hi": "घोड़ा"},
    "sheep": {"zh": "羊", "es": "oveja", "fr": "mouton", "hi": "भेड़"},
    "cow": {"zh": "牛", "es": "vaca", "fr": "vache", "hi": "गाय"},
    "elephant": {"zh": "大象", "es": "elefante", "fr": "éléphant", "hi": "हाथी"},
    "bear": {"zh": "熊", "es": "oso", "fr": "ours", "hi": "भालू"},
    "zebra": {"zh": "斑马", "es": "cebra", "fr": "zèbre", "hi": "ज़ेबरा"},
    "giraffe": {"zh": "长颈鹿", "es": "jirafa", "fr": "girafe", "hi": "जिराफ़"},
    "backpack": {"zh": "背包", "es": "mochila", "fr": "sac à dos", "hi": "बैग"},
    "umbrella": {"zh": "雨伞", "es": "paraguas", "fr": "parapluie", "hi": "छाता"},
    "handbag": {"zh": "手提包", "es": "bolso", "fr": "sac à main", "hi": "हैंडबैग"},
    "tie": {"zh": "领带", "es": "corbata", "fr": "cravate", "hi": "टाई"},
    "suitcase": {"zh": "行李箱", "es": "maleta", "fr": "valise", "hi": "सूटकेस"},
    "frisbee": {"zh": "飞盘", "es": "frisbi", "fr": "frisbee", "hi": "फ़्रिस्बी"},
    "skis": {"zh": "滑雪板", "es": "esquís", "fr": "skis", "hi": "स्की"},
    "snowboard": {"zh": "单板滑雪板", "es": "tabla de snowboard", "fr": "snowboard", "hi": "स्नोबोर्ड"},
    "sports ball": {"zh": "球", "es": "pelota", "fr": "ballon", "hi": "गेंद"},
    "kite": {"zh": "风筝", "es": "cometa", "fr": "cerf-volant", "hi": "पतंग"},
    "baseball bat": {"zh": "棒球棒", "es": "bate de béisbol", "fr": "batte de baseball", "hi": "बेसबॉल बैट"},
    "baseball glove": {"zh": "棒球手套", "es": "guante de béisbol", "fr": "gant de baseball", "hi": "बेसबॉल दस्ताना"},
    "skateboard": {"zh": "滑板", "es": "monopatín", "fr": "skateboard", "hi": "स्केटबोर्ड"},
    "surfboard": {"zh": "冲浪板", "es": "tabla de surf", "fr": "planche de surf", "hi": "सर्फ़बोर्ड"},
    "tennis racket": {"zh": "网球拍", "es": "raqueta de tenis", "fr": "raquette de tennis", "hi": "टेनिस रैकेट"},
    "bottle": {"zh": "瓶子", "es": "botella", "fr": "bouteille", "hi": "बोतल"},
    "wine glass": {"zh": "酒杯", "es": "copa de vino", "fr": "verre à vin", "hi": "वाइन गिलास"},
    "cup": {"zh": "杯子", "es": "taza", "fr": "tasse", "hi": "कप"},
    "fork": {"zh": "叉子", "es": "tenedor", "fr": "fourchette", "hi": "काँटा"},
    "knife": {"zh": "刀", "es": "cuchillo", "fr": "couteau", "hi": "चाकू"},
    "spoon": {"zh": "勺子", "es": "cuchara", "fr": "cuillère", "hi": "चम्मच"},
    "bowl": {"zh": "碗", "es": "cuenco", "fr": "bol", "hi": "कटोरा"},
    "banana": {"zh": "香蕉", "es": "plátano", "fr": "banane", "hi": "केला"},
    "apple": {"zh": "苹果", "es": "manzana", "fr": "pomme", "hi": "सेब"},
    "sandwich": {"zh": "三明治", "es": "sándwich", "fr": "sandwich", "hi": "सैंडविच"},
    "orange": {"zh": "橙子", "es": "naranja", "fr": "orange", "hi": "संतरा"},
    "broccoli": {"zh": "西兰花", "es": "brócoli", "fr": "brocoli", "hi": "ब्रोकोली"},
    "carrot": {"zh": "胡萝卜", "es": "zanahoria", "fr": "carotte", "hi": "गाजर"},
    "hot dog": {"zh": "热狗", "es": "perrito caliente", "fr": "hot-dog", "hi": "हॉट डॉग"},
    "pizza": {"zh": "披萨", "es": "pizza", "fr": "pizza", "hi": "पिज़्ज़ा"},
    "donut": {"zh": "甜甜圈", "es": "dona", "fr": "beignet", "hi": "डोनट"},
    "cake": {"zh": "蛋糕", "es": "pastel", "fr": "gâteau", "hi": "केक"},
    "chair": {"zh": "椅子", "es": "silla", "fr": "chaise", "hi": "कुर्सी"},
    "couch": {"zh": "沙发", "es": "sofá", "fr": "canapé", "hi": "सोफ़ा"},
    "potted plant": {"zh": "盆栽", "es": "planta en maceta", "fr": "plante en pot", "hi": "गमले का पौधा"},
    "bed": {"zh": "床", "es": "cama", "fr": "lit", "hi": "बिस्तर"},
    "dining table": {"zh": "餐桌", "es": "mesa", "fr": "table", "hi": "खाने की मेज़"},
    "toilet": {"zh": "马桶", "es": "inodoro", "fr": "toilettes", "hi": "शौचालय"},
    "tv": {"zh": "电视", "es": "televisor", "fr": "télévision", "hi": "टीवी"},
    "laptop": {"zh": "笔记本电脑", "es": "portátil", "fr": "ordinateur portable", "hi": "लैपटॉप"},
    "mouse": {"zh": "鼠标", "es": "ratón", "fr": "souris", "hi": "माउस"},
    "remote": {"zh": "遥控器", "es": "mando a distancia", "fr": "télécommande", "hi": "रिमोट"},
    "keyboard": {"zh": "键盘", "es": "teclado", "fr": "clavier", "hi": "कीबोर्ड"},
    "cell phone": {"zh": "手机", "es": "teléfono móvil", "fr": "téléphone portable", "hi": "मोबाइल फ़ोन"},
    "microwave": {"zh": "微波炉", "es": "microondas", "fr": "micro-ondes", "hi": "माइक्रोवेव"},
    "oven": {"zh": "烤箱", "es": "horno", "fr": "four", "hi": "ओवन"},
    "toaster": {"zh": "烤面包机", "es": "tostadora", "fr": "grille-pain", "hi": "टोस्टर"},
    "sink": {"zh": "水槽", "es": "fregadero", "fr": "évier", "hi": "सिंक"},
    "refrigerator": {"zh": "冰箱", "es": "nevera", "fr": "réfrigérateur", "hi": "फ़्रिज"},
    "book": {"zh": "书", "es": "libro", "fr": "livre", "hi": "किताब"},
    "clock": {"zh": "钟", "es": "reloj", "fr": "horloge", "hi": "घड़ी"},
    "vase": {"zh": "花瓶", "es": "jarrón", "fr": "vase", "hi": "फूलदान"},
    "scissors": {"zh": "剪刀", "es": "tijeras", "fr": "ciseaux", "hi": "कैंची"},
    "teddy bear": {"zh": "泰迪熊", "es": "osito de peluche", "fr": "ours en peluche", "hi": "टेडी बियर"},
    "hair drier": {"zh": "吹风机", "es": "secador de pelo", "fr": "sèche-cheveux", "hi": "हेयर ड्रायर"},
    "toothbrush": {"zh": "牙刷", "es": "cepillo de dientes", "fr": "brosse à dents", "hi": "टूथब्रश"},
    # Demo detector labels (vision/DEMO.md).
    "water bottle": {"zh": "水瓶", "es": "botella de agua", "fr": "bouteille d'eau", "hi": "पानी की बोतल"},
    "phone": {"zh": "手机", "es": "teléfono", "fr": "téléphone", "hi": "फ़ोन"},
    "watch": {"zh": "手表", "es": "reloj de pulsera", "fr": "montre", "hi": "घड़ी"},
    "charger": {"zh": "充电器", "es": "cargador", "fr": "chargeur", "hi": "चार्जर"},
    "toothpaste": {"zh": "牙膏", "es": "pasta de dientes", "fr": "dentifrice", "hi": "टूथपेस्ट"},
    "keys": {"zh": "钥匙", "es": "llaves", "fr": "clés", "hi": "चाबियाँ"},
    "headphones": {"zh": "耳机", "es": "auriculares", "fr": "casque", "hi": "हेडफ़ोन"},
}


def known_language(code: str | None) -> str:
    """Return code if it is a supported language, else the default ("en")."""
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def translate_label(label: str, language: str) -> str:
    """Return a class label in language, or the English label when no translation exists."""
    if language == DEFAULT_LANGUAGE:
        return label
    return CLASS_LABELS.get(label, {}).get(language, label)
