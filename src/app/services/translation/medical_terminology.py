"""
Medical terminology mapping service for semantic translations.
"""

from typing import Dict, Any, Optional
from src.app.common.constants.languages import LanguageCode

class MedicalTerminologyService:
    """
    Service for mapping medical terminology to different languages with semantic accuracy.
    """
    
    def __init__(self):
        self.terminology_maps = {
            LanguageCode.SPANISH: {
                # Diabetes and related terms
                "diabetes": "diabetes",
                "borderline diabetes": "diabetes limítrofe",
                "type 2 diabetes": "diabetes tipo 2",
                "gestational diabetes": "diabetes gestacional",
                "diabetic": "diabético",
                
                # Blood pressure
                "high blood pressure": "presión arterial alta",
                "hypertension": "hipertensión",
                "low blood pressure": "presión arterial baja",
                "hypotension": "hipotensión",
                "blood pressure": "presión arterial",
                
                # Heart and cardiovascular
                "chest pain": "dolor en el pecho",
                "angina": "angina",
                "heart attack": "ataque cardíaco",
                "cardiac": "cardíaco",
                "cardiovascular": "cardiovascular",
                
                # Medications
                "medication": "medicamento",
                "prescription": "receta",
                "dosage": "dosis",
                "frequency": "frecuencia",
                "daily": "diario",
                "twice daily": "dos veces al día",
                "three times daily": "tres veces al día",
                "weekly": "semanal",
                "monthly": "mensual",
                
                # Common medications
                "hydrochlorothiazide": "hidroclorotiazida",
                "metformin": "metformina",
                "insulin": "insulina",
                "aspirin": "aspirina",
                "paracetamol": "paracetamol",
                "ibuprofen": "ibuprofeno",
                
                # Medical procedures
                "follow-up": "seguimiento",
                "appointment": "cita",
                "consultation": "consulta",
                "examination": "examen",
                "test": "prueba",
                "surgery": "cirugía",
                
                # Symptoms
                "pain": "dolor",
                "fever": "fiebre",
                "cough": "tos",
                "headache": "dolor de cabeza",
                "nausea": "náusea",
                "vomiting": "vómito",
                "dizziness": "mareo",
                "fatigue": "fatiga",
                
                # Lifestyle
                "exercise": "ejercicio",
                "diet": "dieta",
                "lifestyle": "estilo de vida",
                "weight": "peso",
                "obesity": "obesidad",
                "smoking": "tabaquismo",
                "alcohol": "alcohol",
                
                # Measurements
                "mg": "mg",
                "ml": "ml",
                "kg": "kg",
                "cm": "cm",
                "mm": "mm",
                
                # Time periods
                "weeks": "semanas",
                "months": "meses",
                "years": "años",
                "immediately": "inmediatamente",
                "as needed": "según sea necesario",
                
                # Instructions
                "take": "tomar",
                "avoid": "evitar",
                "monitor": "monitorear",
                "check": "revisar",
                "report": "reportar",
                "contact": "contactar",
                
                # Severity levels
                "mild": "leve",
                "moderate": "moderado",
                "severe": "grave",
                "critical": "crítico",
                "emergency": "emergencia",
            },
            
            LanguageCode.PORTUGUESE: {
                # Diabetes and related terms
                "diabetes": "diabetes",
                "borderline diabetes": "diabetes limítrofe",
                "type 2 diabetes": "diabetes tipo 2",
                "gestational diabetes": "diabetes gestacional",
                "diabetic": "diabético",
                
                # Blood pressure
                "high blood pressure": "pressão arterial alta",
                "hypertension": "hipertensão",
                "low blood pressure": "pressão arterial baixa",
                "hypotension": "hipotensão",
                "blood pressure": "pressão arterial",
                
                # Heart and cardiovascular
                "chest pain": "dor no peito",
                "angina": "angina",
                "heart attack": "ataque cardíaco",
                "cardiac": "cardíaco",
                "cardiovascular": "cardiovascular",
                
                # Medications
                "medication": "medicamento",
                "prescription": "prescrição",
                "dosage": "dosagem",
                "frequency": "frequência",
                "daily": "diário",
                "twice daily": "duas vezes ao dia",
                "three times daily": "três vezes ao dia",
                "weekly": "semanal",
                "monthly": "mensal",
                
                # Common medications
                "hydrochlorothiazide": "hidroclorotiazida",
                "metformin": "metformina",
                "insulin": "insulina",
                "aspirin": "aspirina",
                "paracetamol": "paracetamol",
                "ibuprofen": "ibuprofeno",
                
                # Medical procedures
                "follow-up": "acompanhamento",
                "appointment": "consulta",
                "consultation": "consulta",
                "examination": "exame",
                "test": "teste",
                "surgery": "cirurgia",
                
                # Symptoms
                "pain": "dor",
                "fever": "febre",
                "cough": "tosse",
                "headache": "dor de cabeça",
                "nausea": "náusea",
                "vomiting": "vômito",
                "dizziness": "tontura",
                "fatigue": "fadiga",
                
                # Lifestyle
                "exercise": "exercício",
                "diet": "dieta",
                "lifestyle": "estilo de vida",
                "weight": "peso",
                "obesity": "obesidade",
                "smoking": "tabagismo",
                "alcohol": "álcool",
                
                # Measurements
                "mg": "mg",
                "ml": "ml",
                "kg": "kg",
                "cm": "cm",
                "mm": "mm",
                
                # Time periods
                "weeks": "semanas",
                "months": "meses",
                "years": "anos",
                "immediately": "imediatamente",
                "as needed": "conforme necessário",
                
                # Instructions
                "take": "tomar",
                "avoid": "evitar",
                "monitor": "monitorar",
                "check": "verificar",
                "report": "relatar",
                "contact": "contatar",
                
                # Severity levels
                "mild": "leve",
                "moderate": "moderado",
                "severe": "grave",
                "critical": "crítico",
                "emergency": "emergência",
            },
            
            LanguageCode.MANDARIN: {
                # Diabetes and related terms
                "diabetes": "糖尿病",
                "borderline diabetes": "临界糖尿病",
                "type 2 diabetes": "2型糖尿病",
                "gestational diabetes": "妊娠糖尿病",
                "diabetic": "糖尿病患者",
                
                # Blood pressure
                "high blood pressure": "高血压",
                "hypertension": "高血压",
                "low blood pressure": "低血压",
                "hypotension": "低血压",
                "blood pressure": "血压",
                
                # Heart and cardiovascular
                "chest pain": "胸痛",
                "angina": "心绞痛",
                "heart attack": "心脏病发作",
                "cardiac": "心脏的",
                "cardiovascular": "心血管的",
                
                # Medications
                "medication": "药物",
                "prescription": "处方",
                "dosage": "剂量",
                "frequency": "频率",
                "daily": "每日",
                "twice daily": "每日两次",
                "three times daily": "每日三次",
                "weekly": "每周",
                "monthly": "每月",
                
                # Common medications
                "hydrochlorothiazide": "氢氯噻嗪",
                "metformin": "二甲双胍",
                "insulin": "胰岛素",
                "aspirin": "阿司匹林",
                "paracetamol": "扑热息痛",
                "ibuprofen": "布洛芬",
                
                # Medical procedures
                "follow-up": "随访",
                "appointment": "预约",
                "consultation": "咨询",
                "examination": "检查",
                "test": "测试",
                "surgery": "手术",
                
                # Symptoms
                "pain": "疼痛",
                "fever": "发烧",
                "cough": "咳嗽",
                "headache": "头痛",
                "nausea": "恶心",
                "vomiting": "呕吐",
                "dizziness": "头晕",
                "fatigue": "疲劳",
                
                # Lifestyle
                "exercise": "运动",
                "diet": "饮食",
                "lifestyle": "生活方式",
                "weight": "体重",
                "obesity": "肥胖",
                "smoking": "吸烟",
                "alcohol": "酒精",
                
                # Measurements
                "mg": "毫克",
                "ml": "毫升",
                "kg": "公斤",
                "cm": "厘米",
                "mm": "毫米",
                
                # Time periods
                "weeks": "周",
                "months": "月",
                "years": "年",
                "immediately": "立即",
                "as needed": "按需",
                
                # Instructions
                "take": "服用",
                "avoid": "避免",
                "monitor": "监测",
                "check": "检查",
                "report": "报告",
                "contact": "联系",
                
                # Severity levels
                "mild": "轻度",
                "moderate": "中度",
                "severe": "重度",
                "critical": "危重",
                "emergency": "紧急",
            },
            
            LanguageCode.HINDI: {
                # Diabetes and related terms
                "diabetes": "मधुमेह",
                "borderline diabetes": "सीमारेखा मधुमेह",
                "type 2 diabetes": "टाइप 2 मधुमेह",
                "gestational diabetes": "गर्भावस्था मधुमेह",
                "diabetic": "मधुमेह रोगी",

                # Blood pressure
                "high blood pressure": "उच्च रक्तचाप",
                "hypertension": "उच्च रक्तचाप",
                "low blood pressure": "निम्न रक्तचाप",
                "hypotension": "निम्न रक्तचाप",
                "blood pressure": "रक्तचाप",

                # Heart and cardiovascular
                "chest pain": "छाती में दर्द",
                "angina": "एनजाइना",
                "heart attack": "दिल का दौरा",
                "cardiac": "हृदय संबंधी",
                "cardiovascular": "हृदय-वाहिकीय",

                # Medications
                "medication": "दवाई",
                "prescription": "नुस्खा",
                "dosage": "खुराक",
                "frequency": "आवृत्ति",
                "daily": "प्रतिदिन",
                "twice daily": "दिन में दो बार",
                "three times daily": "दिन में तीन बार",
                "weekly": "साप्ताहिक",
                "monthly": "मासिक",

                # Common medications
                "hydrochlorothiazide": "हाइड्रोक्लोरोथियाज़ाइड",
                "metformin": "मेटफॉर्मिन",
                "insulin": "इंसुलिन",
                "aspirin": "एस्पिरिन",
                "paracetamol": "पेरासिटामोल",
                "ibuprofen": "इबुप्रोफेन",

                # Medical procedures
                "follow-up": "अनुवर्ती",
                "appointment": "नियुक्ति",
                "consultation": "परामर्श",
                "examination": "परीक्षण",
                "test": "जाँच",
                "surgery": "शल्य चिकित्सा",

                # Symptoms
                "pain": "दर्द",
                "fever": "बुखार",
                "cough": "खाँसी",
                "headache": "सिरदर्द",
                "nausea": "मतली",
                "vomiting": "उल्टी",
                "dizziness": "चक्कर",
                "fatigue": "थकान",

                # Lifestyle
                "exercise": "व्यायाम",
                "diet": "आहार",
                "lifestyle": "जीवनशैली",
                "weight": "वजन",
                "obesity": "मोटापा",
                "smoking": "धूम्रपान",
                "alcohol": "शराब",

                # Measurements
                "mg": "मिलीग्राम",
                "ml": "मिलीलीटर",
                "kg": "किलोग्राम",
                "cm": "सेंटीमीटर",
                "mm": "मिलीमीटर",

                # Time periods
                "weeks": "सप्ताह",
                "months": "महीने",
                "years": "साल",
                "immediately": "तुरंत",
                "as needed": "आवश्यकतानुसार",

                # Instructions
                "take": "लें",
                "avoid": "बचें",
                "monitor": "निगरानी करें",
                "check": "जाँचें",
                "report": "रिपोर्ट करें",
                "contact": "संपर्क करें",

                # Severity levels
                "mild": "हल्का",
                "moderate": "मध्यम",
                "severe": "गंभीर",
                "critical": "जटिल",
                "emergency": "आपातकाल",
            },

            LanguageCode.ARABIC: {
                # Diabetes and related terms
                "diabetes": "السكري",
                "borderline diabetes": "مقدمات السكري",
                "type 2 diabetes": "السكري من النوع الثاني",
                "gestational diabetes": "سكري الحمل",
                "diabetic": "مريض السكري",

                # Blood pressure
                "high blood pressure": "ارتفاع ضغط الدم",
                "hypertension": "ارتفاع ضغط الدم",
                "low blood pressure": "انخفاض ضغط الدم",
                "hypotension": "انخفاض ضغط الدم",
                "blood pressure": "ضغط الدم",

                # Heart and cardiovascular
                "chest pain": "ألم في الصدر",
                "angina": "الذبحة الصدرية",
                "heart attack": "النوبة القلبية",
                "cardiac": "قلبي",
                "cardiovascular": "قلبي وعائي",

                # Medications
                "medication": "دواء",
                "prescription": "وصفة طبية",
                "dosage": "جرعة",
                "frequency": "تكرار الجرعة",
                "daily": "يومياً",
                "twice daily": "مرتين يومياً",
                "three times daily": "ثلاث مرات يومياً",
                "weekly": "أسبوعياً",
                "monthly": "شهرياً",

                # Common medications
                "hydrochlorothiazide": "هيدروكلوروثيازيد",
                "metformin": "ميتفورمين",
                "insulin": "الأنسولين",
                "aspirin": "الأسبرين",
                "paracetamol": "باراسيتامول",
                "ibuprofen": "إيبوبروفين",

                # Medical procedures
                "follow-up": "متابعة",
                "appointment": "موعد",
                "consultation": "استشارة",
                "examination": "فحص",
                "test": "اختبار",
                "surgery": "جراحة",

                # Symptoms
                "pain": "ألم",
                "fever": "حمى",
                "cough": "سعال",
                "headache": "صداع",
                "nausea": "غثيان",
                "vomiting": "قيء",
                "dizziness": "دوار",
                "fatigue": "إرهاق",

                # Lifestyle
                "exercise": "تمرين",
                "diet": "نظام غذائي",
                "lifestyle": "نمط الحياة",
                "weight": "وزن",
                "obesity": "سمنة",
                "smoking": "تدخين",
                "alcohol": "كحول",

                # Measurements
                "mg": "ملغ",
                "ml": "مل",
                "kg": "كغ",
                "cm": "سم",
                "mm": "مم",

                # Time periods
                "weeks": "أسابيع",
                "months": "أشهر",
                "years": "سنوات",
                "immediately": "فوراً",
                "as needed": "عند الحاجة",

                # Instructions
                "take": "تناول",
                "avoid": "تجنب",
                "monitor": "راقب",
                "check": "تحقق",
                "report": "أبلغ",
                "contact": "تواصل",

                # Severity levels
                "mild": "خفيف",
                "moderate": "متوسط",
                "severe": "شديد",
                "critical": "حرج",
                "emergency": "طارئ",
            },

            LanguageCode.BENGALI: {
                # Diabetes and related terms
                "diabetes": "ডায়াবেটিস",
                "borderline diabetes": "সীমারেখার ডায়াবেটিস",
                "type 2 diabetes": "টাইপ ২ ডায়াবেটিস",
                "gestational diabetes": "গর্ভাবস্থার ডায়াবেটিস",
                "diabetic": "ডায়াবেটিক রোগী",
                
                # Blood pressure
                "high blood pressure": "উচ্চ রক্তচাপ",
                "hypertension": "উচ্চ রক্তচাপ",
                "low blood pressure": "নিম্ন রক্তচাপ",
                "hypotension": "নিম্ন রক্তচাপ",
                "blood pressure": "রক্তচাপ",
                
                # Heart and cardiovascular
                "chest pain": "বুকের ব্যথা",
                "angina": "এনজাইনা",
                "heart attack": "হার্ট অ্যাটাক",
                "cardiac": "হৃদয়সংক্রান্ত",
                "cardiovascular": "হৃদয়সংবহনতন্ত্রীয়",
                
                # Medications
                "medication": "ওষুধ",
                "prescription": "প্রেসক্রিপশন",
                "dosage": "মাত্রা",
                "frequency": "ফ্রিকোয়েন্সি",
                "daily": "দৈনিক",
                "twice daily": "দিনে দুবার",
                "three times daily": "দিনে তিনবার",
                "weekly": "সাপ্তাহিক",
                "monthly": "মাসিক",
                
                # Common medications
                "hydrochlorothiazide": "হাইড্রোক্লোরোথায়াজাইড",
                "metformin": "মেটফরমিন",
                "insulin": "ইনসুলিন",
                "aspirin": "অ্যাসপিরিন",
                "paracetamol": "প্যারাসিটামল",
                "ibuprofen": "আইবুপ্রোফেন",
                
                # Medical procedures
                "follow-up": "পুনরায় দেখা",
                "appointment": "অ্যাপয়েন্টমেন্ট",
                "consultation": "পরামর্শ",
                "examination": "পরীক্ষা",
                "test": "টেস্ট",
                "surgery": "অস্ত্রোপচার",
                
                # Symptoms
                "pain": "ব্যথা",
                "fever": "জ্বর",
                "cough": "কাশি",
                "headache": "মাথাব্যথা",
                "nausea": "বমি বমি ভাব",
                "vomiting": "বমি",
                "dizziness": "মাথা ঘোরা",
                "fatigue": "ক্লান্তি",
                
                # Lifestyle
                "exercise": "ব্যায়াম",
                "diet": "খাদ্যাভ্যাস",
                "lifestyle": "জীবনধারা",
                "weight": "ওজন",
                "obesity": "স্থূলতা",
                "smoking": "ধূমপান",
                "alcohol": "মদ",
                
                # Measurements
                "mg": "মিলিগ্রাম",
                "ml": "মিলিলিটার",
                "kg": "কিলোগ্রাম",
                "cm": "সেন্টিমিটার",
                "mm": "মিলিমিটার",
                
                # Time periods
                "weeks": "সপ্তাহ",
                "months": "মাস",
                "years": "বছর",
                "immediately": "তাৎক্ষণিকভাবে",
                "as needed": "প্রয়োজন অনুযায়ী",
                
                # Instructions
                "take": "গ্রহণ করুন",
                "avoid": "এড়িয়ে চলুন",
                "monitor": "নিরীক্ষণ করুন",
                "check": "পরীক্ষা করুন",
                "report": "রিপোর্ট করুন",
                "contact": "যোগাযোগ করুন",
                
                # Severity levels
                "mild": "হালকা",
                "moderate": "মাঝারি",
                "severe": "গুরুতর",
                "critical": "সমালোচনামূলক",
                "emergency": "জরুরি",
            }
        }
    
    def get_medical_terminology(self, language_code: str) -> Dict[str, str]:
        """
        Get medical terminology mapping for a specific language.
        
        Args:
            language_code: The language code (e.g., 'hi', 'es', 'fr')
            
        Returns:
            Dictionary mapping English terms to target language terms
        """
        return self.terminology_maps.get(language_code, {})
    
    def translate_medical_term(self, term: str, language_code: str) -> Optional[str]:
        """
        Translate a specific medical term to the target language.
        
        Args:
            term: The medical term to translate
            language_code: The target language code
            
        Returns:
            Translated term or None if not found
        """
        terminology_map = self.get_medical_terminology(language_code)
        return terminology_map.get(term.lower())
    
    def get_semantic_context(self, language_code: str) -> Dict[str, Any]:
        """
        Get semantic context information for a language.
        
        Args:
            language_code: The language code
            
        Returns:
            Dictionary with semantic context information
        """
        context_maps = {
            LanguageCode.SPANISH: {
                "sentence_structure": "Subject-Verb-Object (SVO)",
                "formality_levels": ["usted", "tú"],
                "medical_honorifics": ["doctor", "doctora"],
                "measurement_preferences": "metric",
                "date_format": "DD/MM/YYYY",
                "time_format": "24-hour"
            },
            LanguageCode.PORTUGUESE: {
                "sentence_structure": "Subject-Verb-Object (SVO)",
                "formality_levels": ["você", "tu"],
                "medical_honorifics": ["doutor", "doutora"],
                "measurement_preferences": "metric",
                "date_format": "DD/MM/YYYY",
                "time_format": "24-hour"
            },
            LanguageCode.MANDARIN: {
                "sentence_structure": "Subject-Verb-Object (SVO)",
                "formality_levels": ["您", "你"],
                "medical_honorifics": ["医生", "大夫"],
                "measurement_preferences": "metric",
                "date_format": "YYYY-MM-DD",
                "time_format": "24-hour"
            },
            LanguageCode.BENGALI: {
                "sentence_structure": "Subject-Object-Verb (SOV)",
                "formality_levels": ["আপনি", "তুমি", "তুই"],
                "medical_honorifics": ["ডাক্তার", "চিকিৎসক"],
                "measurement_preferences": "metric",
                "date_format": "DD/MM/YYYY",
                "time_format": "12-hour with AM/PM"
            },
            LanguageCode.HINDI: {
                "sentence_structure": "Subject-Object-Verb (SOV)",
                "formality_levels": ["आप", "तुम", "तू"],
                "medical_honorifics": ["डॉक्टर", "चिकित्सक"],
                "measurement_preferences": "metric",
                "date_format": "DD/MM/YYYY",
                "time_format": "12-hour with AM/PM"
            },
            LanguageCode.ARABIC: {
                "sentence_structure": "Verb-Subject-Object (VSO) in formal; Subject-Verb-Object (SVO) in modern medical",
                "formality_levels": ["حضرتك", "أنت"],
                "medical_honorifics": ["الدكتور", "الدكتورة"],
                "measurement_preferences": "metric",
                "date_format": "DD/MM/YYYY",
                "time_format": "12-hour",
                "script_direction": "right-to-left (RTL)"
            },
        }

        return context_maps.get(language_code, {})
    
    def enhance_translation_prompt(self, language_code: str) -> str:
        """
        Generate enhanced translation prompt with semantic context.
        
        Args:
            language_code: The target language code
            
        Returns:
            Enhanced prompt string
        """
        context = self.get_semantic_context(language_code)
        terminology = self.get_medical_terminology(language_code)
        
        prompt_enhancements = {
            LanguageCode.SPANISH: f"""
            SPANISH SEMANTIC CONTEXT:
            - Use natural Spanish sentence structure (SVO)
            - Use appropriate formality (usted for medical context)
            - Use metric measurements
            - Use 24-hour time format
            - Use DD/MM/YYYY date format
            
            KEY MEDICAL TERMS:
            {chr(10).join([f"- {eng}: {spanish}" for eng, spanish in list(terminology.items())[:10]])}
            
            SEMANTIC EXAMPLES:
            - "Borderline diabetes" → "diabetes limítrofe" (medical terminology)
            - "High blood pressure" → "presión arterial alta" (natural Spanish)
            - "Take medication daily" → "tome el medicamento diariamente" (formal medical)
            """,
            
            LanguageCode.PORTUGUESE: f"""
            PORTUGUESE SEMANTIC CONTEXT:
            - Use natural Portuguese sentence structure (SVO)
            - Use appropriate formality (você for medical context)
            - Use metric measurements
            - Use 24-hour time format
            - Use DD/MM/YYYY date format
            
            KEY MEDICAL TERMS:
            {chr(10).join([f"- {eng}: {portuguese}" for eng, portuguese in list(terminology.items())[:10]])}
            
            SEMANTIC EXAMPLES:
            - "Borderline diabetes" → "diabetes limítrofe" (medical terminology)
            - "High blood pressure" → "pressão arterial alta" (natural Portuguese)
            - "Take medication daily" → "tome o medicamento diariamente" (formal medical)
            """,
            
            LanguageCode.MANDARIN: f"""
            MANDARIN SEMANTIC CONTEXT:
            - Use natural Mandarin sentence structure (SVO)
            - Use appropriate formality (您 for medical context)
            - Use metric measurements
            - Use 24-hour time format
            - Use YYYY-MM-DD date format
            
            KEY MEDICAL TERMS:
            {chr(10).join([f"- {eng}: {mandarin}" for eng, mandarin in list(terminology.items())[:10]])}
            
            SEMANTIC EXAMPLES:
            - "Borderline diabetes" → "临界糖尿病" (medical terminology)
            - "High blood pressure" → "高血压" (natural Mandarin)
            - "Take medication daily" → "每日服用药物" (formal medical)
            """,
            
            LanguageCode.BENGALI: f"""
            BENGALI SEMANTIC CONTEXT:
            - Use natural Bengali sentence structure (SOV)
            - Use appropriate honorifics (ডাক্তার, চিকিৎসক)
            - Use metric measurements (mg, ml, kg)
            - Use 12-hour time format with AM/PM
            - Use DD/MM/YYYY date format

            KEY MEDICAL TERMS:
            {chr(10).join([f"- {eng}: {bengali}" for eng, bengali in list(terminology.items())[:10]])}

            SEMANTIC EXAMPLES:
            - "Borderline diabetes" → "সীমারেখার ডায়াবেটিস" (not word-for-word)
            - "High blood pressure" → "উচ্চ রক্তচাপ" (medical terminology)
            - "Take medication daily" → "ওষুধ দৈনিক গ্রহণ করুন" (natural Bengali)
            """,

            LanguageCode.HINDI: f"""
            HINDI SEMANTIC CONTEXT:
            - Use natural Hindi sentence structure (SOV)
            - Use appropriate formality (आप for medical context)
            - Use metric measurements (mg, ml, kg)
            - Use 12-hour time format with AM/PM
            - Use DD/MM/YYYY date format

            KEY MEDICAL TERMS:
            {chr(10).join([f"- {eng}: {hindi}" for eng, hindi in list(terminology.items())[:10]])}

            SEMANTIC EXAMPLES:
            - "Borderline diabetes" → "सीमारेखा मधुमेह" (medical terminology)
            - "High blood pressure" → "उच्च रक्तचाप" (natural Hindi)
            - "Take medication daily" → "दवाई प्रतिदिन लें" (formal medical)
            """,

            LanguageCode.ARABIC: f"""
            ARABIC SEMANTIC CONTEXT:
            - Use Modern Standard Arabic (MSA) appropriate for medical contexts
            - Script direction is right-to-left (RTL) — ensure proper text flow
            - Use appropriate honorifics (الدكتور / الدكتورة)
            - Use metric measurements (ملغ, مل, كغ)
            - Use 12-hour time format
            - Use DD/MM/YYYY date format

            KEY MEDICAL TERMS:
            {chr(10).join([f"- {eng}: {arabic}" for eng, arabic in list(terminology.items())[:10]])}

            SEMANTIC EXAMPLES:
            - "Borderline diabetes" → "مقدمات السكري" (medical terminology)
            - "High blood pressure" → "ارتفاع ضغط الدم" (natural Arabic)
            - "Take medication daily" → "تناول الدواء يومياً" (formal medical)
            """,
        }

        return prompt_enhancements.get(language_code, "")

# Global instance
medical_terminology_service = MedicalTerminologyService()
