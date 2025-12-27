// ملف التكوين
const DefaultConfig = {
    API_BASE_URL: 'http://localhost:8000',
    SITE_NAME: 'مكتبة النور',
    CURRENCY: 'ج.م',
    DEFAULT_SHIPPING_COST: 50,
    FREE_SHIPPING_THRESHOLD: 500,
    HAFIZ_DISCOUNT: 20,
    ISTIGHFAR_DISCOUNT_PER_100: 1,
    MAX_ISTIGHFAR_DISCOUNT: 5
};

class ConfigManager {
    constructor() {
        this.config = { ...DefaultConfig };
        this.storageKey = 'app_config';
        this.initialize();
    }

    initialize() {
        // محاولة تحميل الإعدادات المحفوظة
        const savedConfig = this.loadFromStorage();
        
        if (savedConfig) {
            // دمج الإعدادات المحفوظة مع الافتراضية
            this.config = { ...DefaultConfig, ...savedConfig };
        } else {
            // حفظ الإعدادات الافتراضية لأول مرة
            this.saveToStorage();
        }
    }

    // تحميل الإعدادات من localStorage
    loadFromStorage() {
        try {
            const saved = localStorage.getItem(this.storageKey);
            return saved ? JSON.parse(saved) : null;
        } catch (error) {
            console.error('خطأ في تحميل الإعدادات:', error);
            return null;
        }
    }

    // حفظ الإعدادات في localStorage
    saveToStorage() {
        try {
            localStorage.setItem(this.storageKey, JSON.stringify(this.config));
            return true;
        } catch (error) {
            console.error('خطأ في حفظ الإعدادات:', error);
            return false;
        }
    }

    // الحصول على قيمة إعداد
    get(key) {
        return this.config[key];
    }

    // تعيين قيمة إعداد
    set(key, value) {
        this.config[key] = value;
        return this.saveToStorage();
    }

    // تحديث عدة إعدادات مرة واحدة
    updateMultiple(settings) {
        Object.assign(this.config, settings);
        return this.saveToStorage();
    }

    // إعادة تعيين الإعدادات إلى الافتراضية
    reset() {
        this.config = { ...DefaultConfig };
        localStorage.removeItem(this.storageKey);
        return true;
    }

    // الحصول على نسخة من جميع الإعدادات
    getAll() {
        return { ...this.config };
    }

    // مزامنة مع Back-End (اختياري)
    async syncWithBackend(apiUrl = this.config.API_BASE_URL) {
        try {
            const response = await fetch(`${apiUrl}/api/config`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(this.config)
            });
            
            if (response.ok) {
                console.log('تمت المزامنة مع الخادم بنجاح');
                return true;
            }
            return false;
        } catch (error) {
            console.error('خطأ في المزامنة مع الخادم:', error);
            return false;
        }
    }

    // تحميل من Back-End (اختياري)
    async loadFromBackend(apiUrl = this.config.API_BASE_URL) {
        try {
            const response = await fetch(`${apiUrl}/api/config`);
            
            if (response.ok) {
                const serverConfig = await response.json();
                this.config = { ...DefaultConfig, ...serverConfig };
                this.saveToStorage();
                return true;
            }
            return false;
        } catch (error) {
            console.error('خطأ في تحميل الإعدادات من الخادم:', error);
            return false;
        }
    }
}

// إنشاء نسخة عامة من مدير الإعدادات
const configManager = new ConfigManager();

// للحفاظ على التوافق مع الكود القديم
const Config = new Proxy({}, {
    get(target, prop) {
        return configManager.get(prop);
    },
    set(target, prop, value) {
        return configManager.set(prop, value);
    }
});

// تصدير المدير للاستخدام المتقدم
export { configManager, Config, DefaultConfig };