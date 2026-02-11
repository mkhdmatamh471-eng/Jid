def manual_fallback_check_jeddah_pro(clean_text):
    # تحويل النص ليكون متوافقاً مع الفحص
    text = clean_text.lower()

    # 1. فحص المسار الصريح (من ... الين/الى/لـ) - أقوى علامة
    # يسحب: "من الحمدانية للبلد", "من صفا الين المطار"
    route_markers = [" الى", " إلى", " الين", " لين", " لـ", " لحي", " للمطار", " للجامعة"]
    if "من" in text and any(m in text for m in route_markers):
        return True

    # 2. فحص الطلب مع الوجهة
    # يسحب: "ابغا مشوار الصفا", "مين يوديني الردسي"
    has_trigger = any(t in text for t in ORDER_TRIGGERS)
    has_destination = any(d in text for d in JEDDAH_KEYWORDS)
    
    if has_trigger and has_destination:
        return True

    # 3. فحص السؤال عن السعر (خاص بالعملاء)
    # يسحب: "بكم للمطار؟", "بكم مشوار التحلية"
    if "بكم" in text and (has_destination or "مشوار" in text):
        return True

    # 4. فحص "دحين" - حالات الاستعجال غالباً ما تكون عملاء
    if "دحين" in text and (has_destination or "سواق" in text or "كابتن" in text):
        return True

    return False