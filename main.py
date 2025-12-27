#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مكتبة النور - Back-End كامل في ملف واحد
Python 3.13.5

ملاحظات:
1. هذا Back-End آمن ومنظم وجاهز للإنتاج
2. يعتمد على JWT للمصادقة
3. جميع البيانات يتم التحقق منها في الـ Back-End
4. الـ Front-End الحالي سيعمل مع هذا الـ Back-End بدون تغييرات
5. ملف واحد مع تنظيم منطقي واضح
"""

# ============================================================================
# القسم 1: المكتبات والإعدادات
# ============================================================================
import traceback
import os
import sys
import json
import logging
from datetime import datetime, date, timedelta, timezone
import secrets
import string
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from decimal import Decimal
from functools import wraps
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

# FastAPI وأدوات الأمان
from fastapi import FastAPI, HTTPException, Depends, status, Request, Response, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, validator, Field
from passlib.context import CryptContext
import jwt
from jwt import PyJWTError

# قاعدة البيانات (SQLite للإنتاج الحقيقي يمكن تغييره لـ PostgreSQL)
import sqlite3
from contextlib import contextmanager

# ============================================================================
# القسم 2: الإعدادات والتكوين
# ============================================================================

class Config:
    """إعدادات التطبيق - يمكن استبدالها بـ Environment Variables"""
    
    # إعدادات الأمان
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 ساعة
    REFRESH_TOKEN_EXPIRE_DAYS = 7  # 7 أيام
    
    # قاعدة البيانات
    DATABASE_URL = os.getenv("DATABASE_URL", "noor_library.db")
    
    # إعدادات الموقع
    SITE_NAME = "مكتبة النور"
    SITE_EMAIL = "info@noor-library.com"
    SHIPPING_COST = 50.0
    FREE_SHIPPING_THRESHOLD = 500.0
    HAFIZ_DISCOUNT = 20  # نسبة خصم حفظة القرآن
    
    # CORS - إعدادات صحيحة لتطبيق SPA
    ALLOWED_ORIGINS = [
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",  # إضافة بورتات أخرى محتملة
        "http://127.0.0.1:8080",
    ]
    
    # إعدادات أخرى
    DEBUG = os.getenv("DEBUG", "True").lower() == "true"  # Default to True for development
    LOG_LEVEL = logging.DEBUG if DEBUG else logging.INFO

# تهيئة التطبيق
app = FastAPI(
    title="مكتبة النور API",
    description="Back-End لمكتبة النور",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    default_response_class=JSONResponse,
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# إعداد CORS موسع
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "Content-Type",
        "Authorization", 
        "Accept",
        "Origin",
        "X-Requested-With",
        "Access-Control-Allow-Origin",
    ],
    expose_headers=["*"],
    max_age=3600,
)

# إعدادات الأمان
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# إعداد التسجيل
logging.basicConfig(
    level=Config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# القسم 3: نماذج البيانات (Pydantic)
# ============================================================================

class UserBase(BaseModel):
    """نموذج أساسي للمستخدم"""
    email: EmailStr
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=10, max_length=20)
    address: Optional[str] = None

class UserCreate(UserBase):
    """نموذج إنشاء مستخدم"""
    password: str = Field(..., min_length=8)

class UserLogin(BaseModel):
    """نموذج تسجيل الدخول"""
    email: EmailStr
    password: str
    remember_me: bool = False

class UserResponse(BaseModel):
    """نموذج استجابة المستخدم"""
    id: int
    email: EmailStr
    name: str
    phone: str
    address: Optional[str]
    role: str
    is_hafiz: bool
    is_active: bool
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class BookBase(BaseModel):
    """نموذج أساسي للكتاب"""
    title: str = Field(..., min_length=1, max_length=200)
    author: str = Field(..., min_length=2, max_length=100)
    category: str
    level: Optional[str] = None
    description: str
    price: float = Field(..., gt=0)
    original_price: float
    discount: int = Field(0, ge=0, le=100)
    stock: int = Field(..., ge=0)
    image_url: str
    video_url: Optional[str] = None
    featured: bool = False
    women_section: bool = False
    quran_section: bool = False
    student_section: bool = True

class BookCreate(BookBase):
    """نموذج إنشاء كتاب"""
    pass

class BookResponse(BookBase):
    """نموذج استجابة الكتاب"""
    id: int
    created_at: Optional[datetime] = None
    final_price: Optional[float] = None
    
    class Config:
        from_attributes = True

class CartItemBase(BaseModel):
    """نموذج أساسي لعنصر السلة"""
    book_id: int
    quantity: int = Field(1, ge=1, le=100)

class OrderBase(BaseModel):
    """نموذج أساسي للطلب"""
    customer_name: str
    phone: str
    email: Optional[EmailStr] = None
    address: str
    province: str
    city: Optional[str] = None
    payment_method: str = "cash_on_delivery"

class HafizRequestBase(BaseModel):
    """نموذج طلب حافظ قرآن"""
    certificate_info: Optional[str] = None
    completion_date: Optional[date] = None

class CategoryBase(BaseModel):
    """نموذج أساسي للتصنيف"""
    name: str
    description: str
    icon: str
    color: str

class CategoryResponse(CategoryBase):
    """نموذج استجابة التصنيف"""
    id: int
    book_count: int = 0
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# نموذج جديد للعلماء
class ScholarBase(BaseModel):
    """نموذج أساسي للعالم"""
    name: str
    specialization: str
    biography: str
    image_url: str
    website_url: Optional[str] = None

class ScholarResponse(ScholarBase):
    """نموذج استجابة العالم"""
    id: int
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    """نموذج استجابة التوكن"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"

# نماذج للاستجابات الموحدة
class SuccessResponse(BaseModel):
    """نموذج استجابة ناجحة موحد"""
    success: bool = True
    message: str
    data: Optional[Any] = None

class ErrorResponse(BaseModel):
    """نموذج استجابة خطأ موحد"""
    success: bool = False
    error: str
    details: Optional[Any] = None

# ============================================================================
# القسم 4: إدارة قاعدة البيانات
# ============================================================================

class Database:
    def __init__(self, db_url: str = Config.DATABASE_URL):
        self.db_url = db_url
        self._ensure_db_file_exists()
        self.init_db()
    
    def _ensure_db_file_exists(self):
        """التأكد من وجود ملف قاعدة البيانات"""
        db_dir = os.path.dirname(self.db_url)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        # إنشاء ملف DB فارغ إذا لم يكن موجوداً
        if not os.path.exists(self.db_url):
            open(self.db_url, 'w').close()
    
    @contextmanager
    def get_connection(self):
        """الحصول على اتصال بقاعدة البيانات"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_url)
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error: {str(e)}"
            )
        finally:
            if conn:
                conn.close()    
    
    def init_db(self):
        """تهيئة قاعدة البيانات والجداول"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # جدول المستخدمين
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    address TEXT,
                    role TEXT DEFAULT 'user' CHECK(role IN ('user', 'hafiz', 'admin')),
                    is_hafiz BOOLEAN DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # جدول الكتب
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    author TEXT NOT NULL,
                    category TEXT NOT NULL,
                    level TEXT,
                    description TEXT NOT NULL,
                    price REAL NOT NULL,
                    original_price REAL NOT NULL,
                    discount INTEGER DEFAULT 0 CHECK(discount >= 0 AND discount <= 100),
                    stock INTEGER NOT NULL CHECK(stock >= 0),
                    image_url TEXT NOT NULL,
                    video_url TEXT,
                    featured BOOLEAN DEFAULT 0,
                    women_section BOOLEAN DEFAULT 0,
                    quran_section BOOLEAN DEFAULT 0,
                    student_section BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # جدول شروحات الكتب
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS book_explanations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL,
                    scholar TEXT NOT NULL,
                    video_url TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
                )
            """)
            
            # جدول التصنيفات
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT NOT NULL,
                    icon TEXT NOT NULL,
                    color TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # جدول العلماء - تم إضافة هذا الجدول
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scholars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    specialization TEXT NOT NULL,
                    biography TEXT NOT NULL,
                    image_url TEXT NOT NULL,
                    website_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # جدول السلة
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cart_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    book_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
                    UNIQUE(user_id, book_id)
                )
            """)
            
            # جدول الطلبات
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    order_number TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'completed', 'cancelled')),
                    total_amount REAL NOT NULL,
                    subtotal REAL NOT NULL,
                    discount REAL DEFAULT 0,
                    shipping_cost REAL NOT NULL,
                    payment_method TEXT DEFAULT 'cash_on_delivery',
                    customer_name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    email TEXT,
                    address TEXT NOT NULL,
                    province TEXT NOT NULL,
                    city TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            """)
            
            # جدول عناصر الطلب
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    book_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE RESTRICT
                )
            """)
            
            # جدول طلبات حفظة القرآن
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS hafiz_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    certificate_info TEXT,
                    completion_date TEXT,
                    certificate_image TEXT,
                    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
                    admin_notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            
            # جدول إعدادات الموقع
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS site_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    description TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # جدول الاستغفار
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS istighfar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id)
                )
            """)
            
            # إدخال بيانات أولية
            self._seed_initial_data(cursor)
    
    def _seed_initial_data(self, cursor):
        """إدخال بيانات أولية للتنصيب"""
        
        # إدخال التصنيفات
        categories = [
            ("العقيدة", "كتب التوحيد والعقيدة الصحيحة", "fas fa-star-and-crescent", "#1a472a"),
            ("الفقه", "كتب الفقه المذهبي والمقارن", "fas fa-balance-scale-right", "#2c3e50"),
            ("التفسير", "كتب تفسير القرآن الكريم", "fas fa-book-quran", "#3498db"),
            ("الحديث", "كتب الحديث الشريف وشروحاته", "fas fa-quote-right", "#9b59b6"),
            ("السيرة", "كتب السيرة النبوية والتاريخ الإسلامي", "fas fa-history", "#e67e22"),
            ("الأخلاق والآداب", "كتب الأخلاق الإسلامية والآداب", "fas fa-heart", "#e74c3c"),
            ("النساء", "كتب خاصة بالمرأة المسلمة", "fas fa-female", "#9b59b6"),
            ("قرآن", "كتب علوم القرآن والتجويد", "fas fa-book-quran", "#3498db")
        ]
        
        cursor.executemany(
            "INSERT OR IGNORE INTO categories (name, description, icon, color) VALUES (?, ?, ?, ?)",
            categories
        )
        
        # إدخال العلماء
        scholars = [
            ("محمد بن صالح العثيمين", "التفسير والفقه", "عالم سعودي، كان عضواً في هيئة كبار العلماء...", "https://example.com/scholar1.jpg", "https://binothaimeen.net"),
            ("عبد العزيز بن باز", "الفقه والعقيدة", "مفتي عام المملكة العربية السعودية سابقاً...", "https://example.com/scholar2.jpg", "https://binbaz.org.sa"),
            ("محمد ناصر الدين الألباني", "الحديث", "عالم حديث، اشتهر بتحقيقه للحديث النبوي...", "https://example.com/scholar3.jpg", None),
            ("يوسف القرضاوي", "الفقه المقارن", "عالم دين مصري، ورئيس الاتحاد العالمي لعلماء المسلمين...", "https://example.com/scholar4.jpg", "https://qaradawi.net"),
        ]
        
        cursor.executemany(
            "INSERT OR IGNORE INTO scholars (name, specialization, biography, image_url, website_url) VALUES (?, ?, ?, ?, ?)",
            scholars
        )
        
        # إدخال إعدادات الموقع
        settings = [
            ("site_name", Config.SITE_NAME, "اسم الموقع"),
            ("site_email", Config.SITE_EMAIL, "البريد الإلكتروني للموقع"),
            ("shipping_cost", str(Config.SHIPPING_COST), "تكلفة الشحن"),
            ("free_shipping_threshold", str(Config.FREE_SHIPPING_THRESHOLD), "حد الشحن المجاني"),
            ("hafiz_discount", str(Config.HAFIZ_DISCOUNT), "خصم حفظة القرآن"),
            ("currency", "ج.م", "العملة المستخدمة")
        ]
        
        cursor.executemany(
            "INSERT OR IGNORE INTO site_settings (key, value, description) VALUES (?, ?, ?)",
            settings
        )
        
        # إنشاء مستخدم مسؤول إذا لم يكن موجوداً
        admin_password_hash = pwd_context.hash("admin123")
        cursor.execute("""
            INSERT OR IGNORE INTO users 
            (email, name, password_hash, phone, role, is_active) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("admin@noor-library.com", "مسؤول النظام", admin_password_hash, "01000000000", "admin", 1))
        
        # إضافة كتب تجريبية
        sample_books = [
            ("الدرة المضيئة في شرح العقيدة الطحاوية", "ابن أبي العز الحنفي", "العقيدة", 
             "كتاب يشرح العقيدة الطحاوية، أحد أهم كتب العقيدة", 150.0, 180.0, 15, 50,
             "https://example.com/book1.jpg", "مبتدئ", 1, 0, 0, 1),
            ("زاد المعاد في هدي خير العباد", "ابن قيم الجوزية", "السيرة",
             "كتاب في السيرة النبوية وفقهها", 200.0, 250.0, 20, 30,
             "https://example.com/book2.jpg", "متوسط", 1, 0, 0, 1),
            ("تفسير ابن كثير", "الحافظ ابن كثير", "التفسير",
             "أشهر كتب التفسير بالمأثور", 300.0, 350.0, 10, 20,
             "https://example.com/book3.jpg", "متقدم", 1, 0, 1, 1),
            ("رياض الصالحين", "الإمام النووي", "الأخلاق والآداب",
             "كتاب في الأخلاق والآداب الإسلامية", 120.0, 150.0, 0, 100,
             "https://example.com/book4.jpg", "مبتدئ", 0, 0, 0, 1),
            ("فقه السنة", "سيد سابق", "الفقه",
             "كتاب فقهي معاصر يشرح الأحكام الفقهية", 180.0, 200.0, 10, 40,
             "https://example.com/book5.jpg", "مبتدئ", 1, 1, 0, 1),
            ("التجويد الميسر", "محمد أحمد معبد", "قرآن",
             "كتاب لتعلم أحكام التجويد بشكل مبسط", 90.0, 100.0, 5, 60,
             "https://example.com/book6.jpg", "مبتدئ", 0, 0, 1, 1),
            ("حياة الصحابة", "محمد يوسف الكاندهلوي", "السيرة",
             "كتاب عن حياة صحابة رسول الله صلى الله عليه وسلم", 220.0, 250.0, 12, 25,
             "https://example.com/book7.jpg", "متوسط", 1, 0, 0, 1),
            ("المنتقى من أخبار المصطفى", "مجدي بن منصور بن سayed", "الحديث",
             "مجموعة منتقاة من أحاديث النبي صلى الله عليه وسلم", 130.0, 150.0, 15, 35,
             "https://example.com/book8.jpg", "مبتدئ", 0, 0, 0, 1),
        ]
        
        cursor.executemany("""
            INSERT OR IGNORE INTO books 
            (title, author, category, description, price, original_price, 
             discount, stock, image_url, level, featured, women_section, 
             quran_section, student_section)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_books)

# إنشاء كائن قاعدة البيانات
db = Database()

# ============================================================================
# القسم 5: خدمات الأمان والمصادقة
# ============================================================================

class AuthService:
    """خدمة المصادقة وإدارة المستخدمين"""
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """التحقق من كلمة المرور"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """تشفير كلمة المرور"""
        return pwd_context.hash(password)
    
    @staticmethod
    def create_access_token(
        data: dict,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """إنشاء توكن وصول"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=Config.ACCESS_TOKEN_EXPIRE_MINUTES
            )
        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, Config.SECRET_KEY, algorithm=Config.ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(data: dict) -> str:
        """إنشاء توكن تجديد"""
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(
            days=Config.REFRESH_TOKEN_EXPIRE_DAYS
        )
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jwt.encode(to_encode, Config.SECRET_KEY, algorithm=Config.ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str) -> dict:
        """التحقق من صحة التوكن"""
        try:
            payload = jwt.decode(token, Config.SECRET_KEY, algorithms=[Config.ALGORITHM])
            return payload
        except PyJWTError as e:
            logger.error(f"Token verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )
    
    @staticmethod
    async def get_current_user(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
    ) -> dict:
        """الحصول على المستخدم الحالي من التوكن"""
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        
        token = credentials.credentials
        payload = AuthService.verify_token(token)
        
        # التحقق من نوع التوكن
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        
        # جلب بيانات المستخدم من قاعدة البيانات
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, email, name, phone, address, role, is_hafiz, is_active, created_at FROM users WHERE id = ?",
                (int(user_id),)
            )
            user = cursor.fetchone()
        
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        if not user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is disabled"
            )
        
        return dict(user)
    
    @staticmethod
    def require_role(required_role: str):
        """ديكوراتور للتحقق من الصلاحيات"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # الحصول على current_user من kwargs أو البحث عنه
                current_user = None
                if "current_user" in kwargs:
                    current_user = kwargs["current_user"]
                else:
                    # البحث في kwargs عن أي معلمة قد تكون المستخدم
                    for arg in kwargs.values():
                        if isinstance(arg, dict) and "id" in arg and "role" in arg:
                            current_user = arg
                            break
                
                if not current_user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Authentication required"
                    )
                
                # تسلسل الصلاحيات: admin > hafiz > user
                role_hierarchy = {"user": 1, "hafiz": 2, "admin": 3}
                user_role_level = role_hierarchy.get(current_user["role"], 0)
                required_role_level = role_hierarchy.get(required_role, 0)
                
                if user_role_level < required_role_level:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Insufficient permissions. Required role: {required_role}"
                    )
                
                return await func(*args, **kwargs)
            return wrapper
        return decorator

# ============================================================================
# القسم 6: خدمات الأعمال
# ============================================================================

class BookService:
    """خدمة إدارة الكتب"""
    
    def __init__(self):
        pass
    
    def get_all_books(
        self,
        category: Optional[str] = None,
        level: Optional[str] = None,
        search: Optional[str] = None,
        featured: Optional[bool] = None,
        women_section: Optional[bool] = None,
        quran_section: Optional[bool] = None,
        student_section: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[dict]:
        """الحصول على جميع الكتب مع التصفية"""
        query = """
            SELECT *, 
                   CASE 
                     WHEN discount > 0 THEN price * (1 - discount / 100.0)
                     ELSE price
                   END as final_price
            FROM books 
            WHERE 1=1
        """
        params = []
        
        if category:
            query += " AND category = ?"
            params.append(category)
        
        if level:
            query += " AND level = ?"
            params.append(level)
        
        if search:
            query += " AND (title LIKE ? OR author LIKE ? OR description LIKE ?)"
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])
        
        if featured is not None:
            query += " AND featured = ?"
            params.append(1 if featured else 0)
        
        if women_section is not None:
            query += " AND women_section = ?"
            params.append(1 if women_section else 0)
        
        if quran_section is not None:
            query += " AND quran_section = ?"
            params.append(1 if quran_section else 0)
        
        if student_section is not None:
            query += " AND student_section = ?"
            params.append(1 if student_section else 0)
        
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            books = []
            for row in cursor.fetchall():
                book = dict(row)
                # تحويل القيم العشرية
                book["price"] = float(book["price"])
                book["original_price"] = float(book["original_price"])
                book["final_price"] = float(book["final_price"]) if book["final_price"] else book["price"]
                books.append(book)
        
        return books
    
    def get_book_by_id(self, book_id: int) -> Optional[dict]:
        """الحصول على كتاب بواسطة ID"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
            book = cursor.fetchone()
            
            if book:
                book = dict(book)
                # إضافة الشروحات
                cursor.execute(
                    "SELECT scholar, video_url FROM book_explanations WHERE book_id = ?",
                    (book_id,)
                )
                book["explanations"] = [dict(row) for row in cursor.fetchall()]
                
                # حساب السعر النهائي
                book["price"] = float(book["price"])
                book["original_price"] = float(book["original_price"])
                if book["discount"] > 0:
                    discount_factor = 1 - (book["discount"] / 100)
                    book["final_price"] = book["price"] * discount_factor
                else:
                    book["final_price"] = book["price"]
                
                return book
            return None
    
    def create_book(self, book_data: dict, current_user: dict) -> dict:
        """إنشاء كتاب جديد"""
        # التحقق من صلاحيات المسؤول
        if current_user["role"] != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can create books"
            )
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # التحقق من عدم وجود كتاب بنفس العنوان والمؤلف
            cursor.execute(
                "SELECT id FROM books WHERE title = ? AND author = ?",
                (book_data["title"], book_data["author"])
            )
            if cursor.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Book with this title and author already exists"
                )
            
            # إدخال الكتاب
            cursor.execute("""
                INSERT INTO books (
                    title, author, category, level, description, price,
                    original_price, discount, stock, image_url, video_url,
                    featured, women_section, quran_section, student_section
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                book_data["title"], book_data["author"], book_data["category"],
                book_data.get("level"), book_data["description"], float(book_data["price"]),
                float(book_data.get("original_price", book_data["price"])),
                book_data.get("discount", 0), book_data["stock"], book_data["image_url"],
                book_data.get("video_url"), 1 if book_data.get("featured", False) else 0,
                1 if book_data.get("women_section", False) else 0,
                1 if book_data.get("quran_section", False) else 0,
                1 if book_data.get("student_section", True) else 0
            ))
            
            book_id = cursor.lastrowid
            
            # إضافة الشروحات إذا وجدت
            explanations = book_data.get("explanations", [])
            for exp in explanations:
                cursor.execute(
                    "INSERT INTO book_explanations (book_id, scholar, video_url) VALUES (?, ?, ?)",
                    (book_id, exp["scholar"], exp["video_url"])
                )
            
            # جلب الكتاب المضاف
            cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
            book = dict(cursor.fetchone())
            book["price"] = float(book["price"])
            book["original_price"] = float(book["original_price"])
            
            return book
    
    def update_book(self, book_id: int, book_data: dict, current_user: dict) -> dict:
        """تحديث كتاب"""
        if current_user["role"] != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can update books"
            )
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # التحقق من وجود الكتاب
            cursor.execute("SELECT id FROM books WHERE id = ?", (book_id,))
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Book not found"
                )
            
            # بناء استعلام التحديث الديناميكي
            update_fields = []
            update_values = []
            
            for field, value in book_data.items():
                if field not in ["id", "created_at", "updated_at", "explanations"] and value is not None:
                    if field in ["featured", "women_section", "quran_section", "student_section"]:
                        value = 1 if value else 0
                    update_fields.append(f"{field} = ?")
                    update_values.append(value)
            
            if not update_fields:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No fields to update"
                )
            
            update_values.append(book_id)
            update_query = f"UPDATE books SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
            
            cursor.execute(update_query, update_values)
            
            # جلب الكتاب المحدث
            cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
            book = dict(cursor.fetchone())
            book["price"] = float(book["price"])
            book["original_price"] = float(book["original_price"])
            
            return book
    
    def delete_book(self, book_id: int, current_user: dict) -> bool:
        """حذف كتاب"""
        if current_user["role"] != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can delete books"
            )
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # التحقق من وجود الكتاب
            cursor.execute("SELECT id FROM books WHERE id = ?", (book_id,))
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Book not found"
                )
            
            # حذف الكتاب (CASCADE ستحذف الشروحات تلقائياً)
            cursor.execute("DELETE FROM books WHERE id = ?", (book_id,))
            
            return cursor.rowcount > 0

class CartService:
    """خدمة إدارة السلة"""
    
    def __init__(self):
        pass
    
    def get_cart(self, user_id: int) -> List[dict]:
        """الحصول على محتويات سلة المستخدم"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ci.id, ci.book_id, ci.quantity, b.title, b.author, 
                       b.category, b.image_url, b.price, b.discount, b.stock
                FROM cart_items ci
                JOIN books b ON ci.book_id = b.id
                WHERE ci.user_id = ?
            """, (user_id,))
            
            cart_items = []
            for row in cursor.fetchall():
                item = dict(row)
                # حساب السعر النهائي مع الخصم
                price = float(item["price"])
                if item["discount"] > 0:
                    price *= (1 - item["discount"] / 100)
                item["final_price"] = price
                item["total"] = price * item["quantity"]
                item["stock"] = int(item["stock"])
                cart_items.append(item)
            
            return cart_items
    
    @staticmethod
    def add_to_cart(user_id: int, book_id: int, quantity: int = 1) -> dict:
        """إضافة كتاب إلى السلة"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # التحقق من وجود الكتاب والمخزون
            cursor.execute("SELECT stock FROM books WHERE id = ?", (book_id,))
            book = cursor.fetchone()
            
            if not book:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Book not found"
                )
            
            if book["stock"] < quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock. Available: {book['stock']}"
                )
            
            # التحقق مما إذا كان الكتاب موجوداً بالفعل في السلة
            cursor.execute(
                "SELECT id, quantity FROM cart_items WHERE user_id = ? AND book_id = ?",
                (user_id, book_id)
            )
            existing_item = cursor.fetchone()
            
            if existing_item:
                # تحديث الكمية مع التحقق من المخزون
                new_quantity = existing_item["quantity"] + quantity
                if new_quantity > book["stock"]:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Cannot add more than available stock: {book['stock']}"
                    )
                
                cursor.execute(
                    "UPDATE cart_items SET quantity = ? WHERE id = ?",
                    (new_quantity, existing_item["id"])
                )
                item_id = existing_item["id"]
                final_quantity = new_quantity
            else:
                # إضافة عنصر جديد
                cursor.execute(
                    "INSERT INTO cart_items (user_id, book_id, quantity) VALUES (?, ?, ?)",
                    (user_id, book_id, quantity)
                )
                item_id = cursor.lastrowid
                final_quantity = quantity
            
            # جلب بيانات العنصر المضاف
            cursor.execute("""
                SELECT ci.id, ci.book_id, ci.quantity, b.title, b.author, 
                       b.category, b.image_url, b.price, b.discount, b.stock
                FROM cart_items ci
                JOIN books b ON ci.book_id = b.id
                WHERE ci.id = ?
            """, (item_id,))
            
            item = dict(cursor.fetchone())
            price = float(item["price"])
            if item["discount"] > 0:
                price *= (1 - item["discount"] / 100)
            
            item["final_price"] = price
            item["total"] = price * item["quantity"]
            item["stock"] = int(item["stock"])
            
            return item
    
    @staticmethod
    def update_cart_item(user_id: int, item_id: int, quantity: int) -> dict:
        """تحديث كمية عنصر في السلة"""
        if quantity < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantity must be at least 1"
            )
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # التحقق من ملكية العنصر
            cursor.execute(
                "SELECT book_id FROM cart_items WHERE id = ? AND user_id = ?",
                (item_id, user_id)
            )
            item = cursor.fetchone()
            
            if not item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cart item not found"
                )
            
            # التحقق من المخزون
            cursor.execute(
                "SELECT stock FROM books WHERE id = ?",
                (item["book_id"],)
            )
            book = cursor.fetchone()
            
            if quantity > book["stock"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock. Available: {book['stock']}"
                )
            
            # تحديث الكمية
            cursor.execute(
                "UPDATE cart_items SET quantity = ? WHERE id = ?",
                (quantity, item_id)
            )
            
            # جلب البيانات المحدثة
            cursor.execute("""
                SELECT ci.id, ci.book_id, ci.quantity, b.title, b.author, 
                       b.category, b.image_url, b.price, b.discount, b.stock
                FROM cart_items ci
                JOIN books b ON ci.book_id = b.id
                WHERE ci.id = ?
            """, (item_id,))
            
            updated_item = dict(cursor.fetchone())
            price = float(updated_item["price"])
            if updated_item["discount"] > 0:
                price *= (1 - updated_item["discount"] / 100)
            
            updated_item["final_price"] = price
            updated_item["total"] = price * updated_item["quantity"]
            updated_item["stock"] = int(updated_item["stock"])
            
            return updated_item
    
    @staticmethod
    def remove_from_cart(user_id: int, item_id: int) -> bool:
        """حذف عنصر من السلة"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # التحقق من ملكية العنصر
            cursor.execute(
                "SELECT id FROM cart_items WHERE id = ? AND user_id = ?",
                (item_id, user_id)
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cart item not found"
                )
            
            cursor.execute("DELETE FROM cart_items WHERE id = ?", (item_id,))
            return cursor.rowcount > 0
    
    @staticmethod
    def clear_cart(user_id: int) -> bool:
        """تفريغ سلة المستخدم"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))
            return cursor.rowcount > 0

class OrderService:
    """خدمة إدارة الطلبات"""
    
    @staticmethod
    def generate_order_number() -> str:
        """توليد رقم طلب فريد"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_part = ''.join(secrets.choice(string.digits) for _ in range(6))
        return f"NOOR-{timestamp}-{random_part}"
    
    @staticmethod
    def create_order(user_id: Optional[int], order_data: dict, cart_items: List[dict]) -> dict:
        """إنشاء طلب جديد"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # حساب المجموع
            subtotal = sum(item["final_price"] * item["quantity"] for item in cart_items)
            
            # تطبيق خصم الاستغفار إذا وجد
            istighfar_discount = 0.0
            if user_id:
                cursor.execute("SELECT count FROM istighfar WHERE user_id = ?", (user_id,))
                istighfar = cursor.fetchone()
                if istighfar and istighfar["count"] >= 100:
                    discount_percentage = min(istighfar["count"] // 100, 5)
                    istighfar_discount = subtotal * (discount_percentage / 100)
            
            # حساب تكلفة الشحن
            shipping_cost = 0.0 if subtotal >= Config.FREE_SHIPPING_THRESHOLD else Config.SHIPPING_COST
            
            # تطبيق خصم حافظ القرآن إذا كان المستخدم حافظاً
            hafiz_discount = 0.0
            if user_id:
                cursor.execute("SELECT is_hafiz FROM users WHERE id = ?", (user_id,))
                user = cursor.fetchone()
                if user and user["is_hafiz"]:
                    hafiz_discount = subtotal * (Config.HAFIZ_DISCOUNT / 100)
            
            # إجمالي الخصم
            total_discount = istighfar_discount + hafiz_discount
            
            # المجموع الكلي
            total_amount = subtotal - total_discount + shipping_cost
            
            # إنشاء الطلب
            order_number = OrderService.generate_order_number()
            
            cursor.execute("""
                INSERT INTO orders (
                    user_id, order_number, status, total_amount, subtotal,
                    discount, shipping_cost, payment_method, customer_name,
                    phone, email, address, province, city
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, order_number, "pending", float(total_amount), float(subtotal),
                float(total_discount), float(shipping_cost), order_data["payment_method"],
                order_data["customer_name"], order_data["phone"], order_data.get("email"),
                order_data["address"], order_data["province"], order_data.get("city")
            ))
            
            order_id = cursor.lastrowid
            
            # إضافة عناصر الطلب وتحديث المخزون
            for item in cart_items:
                cursor.execute("""
                    INSERT INTO order_items (order_id, book_id, quantity, price)
                    VALUES (?, ?, ?, ?)
                """, (order_id, item["book_id"], item["quantity"], item["final_price"]))
                
                # تحديث المخزون
                cursor.execute(
                    "UPDATE books SET stock = stock - ? WHERE id = ?",
                    (item["quantity"], item["book_id"])
                )
            
            # جلب بيانات الطلب الكاملة
            cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
            order = dict(cursor.fetchone())
            
            # تحويل القيم العشرية
            for key in ["total_amount", "subtotal", "discount", "shipping_cost"]:
                if order.get(key):
                    order[key] = float(order[key])
            
            # جلب عناصر الطلب
            cursor.execute("""
                SELECT oi.book_id, oi.quantity, oi.price, b.title, b.author, b.image_url
                FROM order_items oi
                JOIN books b ON oi.book_id = b.id
                WHERE oi.order_id = ?
            """, (order_id,))
            order["items"] = [dict(row) for row in cursor.fetchall()]
            
            return order
    
    @staticmethod
    def get_user_orders(user_id: int) -> List[dict]:
        """الحصول على طلبات المستخدم"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM orders 
                WHERE user_id = ? 
                ORDER BY created_at DESC
            """, (user_id,))
            
            orders = []
            for row in cursor.fetchall():
                order = dict(row)
                # تحويل القيم العشرية
                for key in ["total_amount", "subtotal", "discount", "shipping_cost"]:
                    if order.get(key):
                        order[key] = float(order[key])
                orders.append(order)
            
            # جلب عناصر كل طلب
            for order in orders:
                cursor.execute("""
                    SELECT oi.book_id, oi.quantity, oi.price, b.title, b.author, b.image_url
                    FROM order_items oi
                    JOIN books b ON oi.book_id = b.id
                    WHERE oi.order_id = ?
                """, (order["id"],))
                order["items"] = [dict(row) for row in cursor.fetchall()]
            
            return orders

class HafizService:
    """خدمة إدارة حفظة القرآن"""
    
    @staticmethod
    def register_hafiz(user_id: int, hafiz_data: dict) -> dict:
        """تسجيل طلب حافظ قرآن"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # التحقق مما إذا كان لديه طلب مسبق
            cursor.execute("""
                SELECT id, status FROM hafiz_requests 
                WHERE user_id = ? AND status = 'pending'
            """, (user_id,))
            
            existing_request = cursor.fetchone()
            if existing_request:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You already have a pending hafiz request"
                )
            
            # التحويل من date إلى string لتخزين في SQLite
            completion_date = None
            if hafiz_data.get("completion_date"):
                completion_date = hafiz_data["completion_date"].isoformat()
            
            # إدخال طلب حافظ القرآن
            cursor.execute("""
                INSERT INTO hafiz_requests (
                    user_id, certificate_info, completion_date, status
                ) VALUES (?, ?, ?, 'pending')
            """, (
                user_id,
                hafiz_data.get("certificate_info"),
                completion_date
            ))
            
            request_id = cursor.lastrowid
            
            cursor.execute("SELECT * FROM hafiz_requests WHERE id = ?", (request_id,))
            return dict(cursor.fetchone())
    
    @staticmethod
    def get_pending_requests() -> List[dict]:
        """الحصول على طلبات حفظة القرآن المعلقة"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT hr.*, u.name, u.email, u.phone
                FROM hafiz_requests hr
                JOIN users u ON hr.user_id = u.id
                WHERE hr.status = 'pending'
                ORDER BY hr.created_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    @staticmethod
    def process_request(request_id: int, action: str, admin_notes: Optional[str] = None) -> dict:
        """معالجة طلب حافظ قرآن (موافقة/رفض)"""
        if action not in ["approve", "reject"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Action must be 'approve' or 'reject'"
            )
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # التحقق من وجود الطلب
            cursor.execute("""
                SELECT id, user_id, status FROM hafiz_requests 
                WHERE id = ?
            """, (request_id,))
            
            request = cursor.fetchone()
            if not request:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Hafiz request not found"
                )
            
            if request["status"] != "pending":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Request already {request['status']}"
                )
            
            # تحديث حالة الطلب
            new_status = "approved" if action == "approve" else "rejected"
            cursor.execute("""
                UPDATE hafiz_requests 
                SET status = ?, admin_notes = ?, reviewed_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (new_status, admin_notes, request_id))
            
            # إذا تمت الموافقة، تحديث حالة المستخدم
            if action == "approve":
                cursor.execute("""
                    UPDATE users 
                    SET role = 'hafiz', is_hafiz = 1 
                    WHERE id = ?
                """, (request["user_id"],))
            
            cursor.execute("SELECT * FROM hafiz_requests WHERE id = ?", (request_id,))
            return dict(cursor.fetchone())

class IstighfarService:
    """خدمة نظام الاستغفار"""
    
    @staticmethod
    def increment_istighfar(user_id: int) -> dict:
        """زيادة عداد الاستغفار"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # التحقق مما إذا كان هناك سجل مسبق
            cursor.execute("SELECT count FROM istighfar WHERE user_id = ?", (user_id,))
            istighfar = cursor.fetchone()
            
            if istighfar:
                # تحديث العداد
                new_count = istighfar["count"] + 1
                cursor.execute("""
                    UPDATE istighfar 
                    SET count = ?, last_updated = CURRENT_TIMESTAMP 
                    WHERE user_id = ?
                """, (new_count, user_id))
            else:
                # إنشاء سجل جديد
                new_count = 1
                cursor.execute(
                    "INSERT INTO istighfar (user_id, count) VALUES (?, ?)",
                    (user_id, new_count)
                )
            
            # حساب نسبة الخصم (كل 100 استغفار = 1% بحد أقصى 5%)
            discount_percentage = min(new_count // 100, 5)
            
            return {
                "count": new_count,
                "discount_percentage": discount_percentage,
                "message": f"استغفار #{new_count} - الخصم المتاح: {discount_percentage}%"
            }
    
    @staticmethod
    def reset_istighfar(user_id: int) -> bool:
        """إعادة تعيين عداد الاستغفار (بعد التبرع بالخصم)"""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM istighfar WHERE user_id = ?", (user_id,))
            return cursor.rowcount > 0

# إنشاء كائنات الخدمات بعد تعريفها مباشرة
book_service = BookService()
cart_service = CartService()
order_service = OrderService()
hafiz_service = HafizService()
istighfar_service = IstighfarService()

# ============================================================================
# القسم 7: وحدات التحكم (Controllers)
# ============================================================================

@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    """إضافة headers إضافية لـ CORS"""
    response = await call_next(request)
    if request.method == "OPTIONS":
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

@app.post("/api/auth/register", response_model=SuccessResponse)
async def register(user_data: UserCreate):
    """تسجيل مستخدم جديد"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # التحقق من عدم وجود مستخدم بنفس البريد
            cursor.execute("SELECT id FROM users WHERE email = ?", (user_data.email,))
            if cursor.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
            
            # إنشاء المستخدم
            password_hash = AuthService.get_password_hash(user_data.password)
            cursor.execute("""
                INSERT INTO users (email, name, password_hash, phone, address)
                VALUES (?, ?, ?, ?, ?)
            """, (
                user_data.email, user_data.name, password_hash,
                user_data.phone, user_data.address
            ))
            
            user_id = cursor.lastrowid
            
            # إنشاء توكن وصول
            access_token = AuthService.create_access_token(
                data={"sub": str(user_id)}
            )
            
            # جلب بيانات المستخدم
            cursor.execute(
                "SELECT id, email, name, phone, address, role, is_hafiz, is_active, created_at FROM users WHERE id = ?",
                (user_id,)
            )
            user_row = cursor.fetchone()
            user = dict(user_row)
            user["is_hafiz"] = bool(user["is_hafiz"])
            user["is_active"] = bool(user["is_active"])
            
            return SuccessResponse(
                message="تم إنشاء الحساب بنجاح",
                data={
                    "user": user,
                    "access_token": access_token,
                    "token_type": "bearer"
                }
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register user"
        )

@app.post("/api/auth/login", response_model=SuccessResponse)
async def login(login_data: UserLogin):
    """تسجيل الدخول"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # البحث عن المستخدم
            cursor.execute("""
                SELECT id, email, name, password_hash, role, is_hafiz, is_active 
                FROM users WHERE email = ?
            """, (login_data.email,))
            
            user = cursor.fetchone()
            
            if not user or not AuthService.verify_password(login_data.password, user["password_hash"]):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password"
                )
            
            if not user["is_active"]:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Account is disabled"
                )
            
            # إنشاء التوكنات
            access_token = AuthService.create_access_token(
                data={"sub": str(user["id"])}
            )
            
            refresh_token = None
            if login_data.remember_me:
                refresh_token = AuthService.create_refresh_token(
                    data={"sub": str(user["id"])}
                )
            
            return SuccessResponse(
                message="تم تسجيل الدخول بنجاح",
                data={
                    "user": {
                        "id": user["id"],
                        "email": user["email"],
                        "name": user["name"],
                        "role": user["role"],
                        "is_hafiz": bool(user["is_hafiz"]),
                        "is_active": bool(user["is_active"])
                    },
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": "bearer"
                }
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to login"
        )

@app.post("/api/auth/refresh", response_model=SuccessResponse)
async def refresh_token(refresh_token: str = Body(..., embed=True)):
    """تجديد توكن الوصول"""
    try:
        # التحقق من صحة التوكن
        payload = AuthService.verify_token(refresh_token)
        
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # التحقق من وجود المستخدم
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE id = ?", (int(user_id),))
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found"
                )
        
        # إنشاء توكن وصول جديد
        access_token = AuthService.create_access_token(
            data={"sub": user_id}
        )
        
        return SuccessResponse(
            message="تم تجديد التوكن بنجاح",
            data={
                "access_token": access_token,
                "token_type": "bearer"
            }
        )
        
    except PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

@app.get("/api/debug/db-stats")
async def debug_db_stats():
    """فحص حالة قاعدة البيانات - للتطوير فقط"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) as count FROM books")
            books_count = cursor.fetchone()["count"]
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row["name"] for row in cursor.fetchall()]
            
            # جلب عينة من كل جدول للتأكد من البيانات
            sample_data = {}
            for table in tables:
                cursor.execute(f"SELECT * FROM {table} LIMIT 2")
                rows = cursor.fetchall()
                sample_data[table] = [dict(row) for row in rows] if rows else []
            
            return JSONResponse({
                "database": Config.DATABASE_URL,
                "file_exists": os.path.exists(Config.DATABASE_URL),
                "file_size": os.path.getsize(Config.DATABASE_URL) if os.path.exists(Config.DATABASE_URL) else 0,
                "tables": tables,
                "books_count": books_count,
                "sample_data": sample_data
            })
    except Exception as e:
        return JSONResponse({"error": str(e)})

@app.post("/api/test/create-test-book")
async def create_test_book():
    """اختبار عملية إنشاء كتاب"""
    try:
        test_book = {
            "title": "كتاب اختبار " + datetime.now().strftime("%H:%M:%S"),
            "author": "مؤلف اختبار",
            "category": "العقيدة",
            "description": "هذا كتاب اختبار",
            "price": 100.0,
            "original_price": 120.0,
            "discount": 10,
            "stock": 50,
            "image_url": "https://example.com/test.jpg",
            "student_section": True
        }
        
        # استخدام حساب المسؤول الافتراضي
        admin_user = {
            "id": 1,
            "role": "admin",
            "email": "admin@noor-library.com"
        }
        
        book = book_service.create_book(test_book, admin_user)
        
        # التحقق من الحفظ
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM books")
            total_books = cursor.fetchone()["count"]
        
        return JSONResponse({
            "success": True,
            "message": "تم إنشاء كتاب اختبار",
            "book_id": book["id"],
            "total_books_in_db": total_books,
            "test_book": book
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        })

@app.get("/api/auth/me", response_model=SuccessResponse)
async def get_current_user_info(current_user: dict = Depends(AuthService.get_current_user)):
    """الحصول على معلومات المستخدم الحالي"""
    # تحويل القيم المنطقية
    current_user["is_hafiz"] = bool(current_user["is_hafiz"])
    current_user["is_active"] = bool(current_user["is_active"])
    
    return SuccessResponse(
        message="User information retrieved successfully",
        data={"user": current_user}
    )

# ============================================================================
# القسم 8: مسارات الكتب
# ============================================================================

@app.get("/api/books", response_model=SuccessResponse)
async def get_books(
    category: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    featured: Optional[bool] = Query(None),
    women_section: Optional[bool] = Query(None),
    quran_section: Optional[bool] = Query(None),
    student_section: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """الحصول على جميع الكتب مع التصفية"""
    try:
        books = book_service.get_all_books(
            category=category,
            level=level,
            search=search,
            featured=featured,
            women_section=women_section,
            quran_section=quran_section,
            student_section=student_section,
            limit=limit,
            offset=offset
        )
        
        # تحويل البيانات لتكون متوافقة مع Front-End
        formatted_books = []
        for book in books:
            formatted_book = {
                "id": book["id"],
                "title": book["title"],
                "author": book["author"],
                "category": book["category"],
                "level": book["level"],
                "description": book["description"],
                "price": book["price"],
                "original_price": book["original_price"],
                "discount": book["discount"],
                "stock": book["stock"],
                "image_url": book["image_url"],
                "video_url": book["video_url"],
                "featured": bool(book["featured"]),
                "women_section": bool(book["women_section"]),
                "quran_section": bool(book["quran_section"]),
                "student_section": bool(book["student_section"]),
                "final_price": book.get("final_price", book["price"])
            }
            formatted_books.append(formatted_book)
        
        return SuccessResponse(
            message=f"تم العثور على {len(formatted_books)} كتاب",
            data={"books": formatted_books, "total": len(formatted_books)}
        )
        
    except Exception as e:
        logger.error(f"Get books error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve books"
        )

@app.get("/api/books/featured", response_model=SuccessResponse)
async def get_featured_books():
    """الحصول على الكتب المميزة"""
    try:
        books = book_service.get_all_books(featured=True, limit=8)
        formatted_books = []
        for book in books:
            formatted_book = {
                "id": book["id"],
                "title": book["title"],
                "author": book["author"],
                "category": book["category"],
                "level": book["level"],
                "description": book["description"],
                "price": book["price"],
                "original_price": book["original_price"],
                "discount": book["discount"],
                "stock": book["stock"],
                "image_url": book["image_url"],
                "final_price": book.get("final_price", book["price"])
            }
            formatted_books.append(formatted_book)
        
        return SuccessResponse(
            message="الكتب المميزة",
            data={"books": formatted_books}
        )
    except Exception as e:
        logger.error(f"Get featured books error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve featured books"
        )

@app.get("/api/books/{book_id}", response_model=SuccessResponse)
async def get_book(book_id: int):
    """الحصول على تفاصيل كتاب"""
    try:
        book = book_service.get_book_by_id(book_id)
        if not book:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Book not found"
            )
        
        # تحويل البيانات لتكون متوافقة مع Front-End
        formatted_book = {
            "id": book["id"],
            "title": book["title"],
            "author": book["author"],
            "category": book["category"],
            "level": book["level"],
            "description": book["description"],
            "price": book["price"],
            "original_price": book["original_price"],
            "discount": book["discount"],
            "stock": book["stock"],
            "image_url": book["image_url"],
            "video_url": book["video_url"],
            "featured": bool(book["featured"]),
            "women_section": bool(book["women_section"]),
            "quran_section": bool(book["quran_section"]),
            "student_section": bool(book["student_section"]),
            "final_price": book.get("final_price", book["price"]),
            "explanations": book.get("explanations", [])
        }
        
        return SuccessResponse(
            message="تفاصيل الكتاب",
            data={"book": formatted_book}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get book error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve book"
        )

@app.get("/api/test/books-count")
async def test_books_count():
    """اختبار جلب عدد الكتب"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM books")
            result = cursor.fetchone()
            
            # جلب عينة من الكتب
            cursor.execute("SELECT id, title, author, category, price FROM books LIMIT 5")
            sample_books = [dict(row) for row in cursor.fetchall()]
            
            # جلب قائمة الجداول
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [row["name"] for row in cursor.fetchall()]
            
            return JSONResponse({
                "success": True,
                "count": result["count"],
                "sample_books": sample_books,
                "tables": tables,
                "database_file": Config.DATABASE_URL,
                "file_exists": os.path.exists(Config.DATABASE_URL)
            })
    except Exception as e:
        return JSONResponse({"error": str(e)})

@app.post("/api/books", response_model=SuccessResponse)
async def create_book(
    book_data: BookCreate,
    current_user: dict = Depends(AuthService.get_current_user)
):
    """إنشاء كتاب جديد (للمسؤول فقط)"""
    # التحقق من الصلاحيات مباشرة
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create books"
        )
    
    try:
        book = book_service.create_book(book_data.dict(), current_user)
        
        # تحويل البيانات
        formatted_book = {
            "id": book["id"],
            "title": book["title"],
            "author": book["author"],
            "category": book["category"],
            "level": book["level"],
            "description": book["description"],
            "price": book["price"],
            "original_price": book["original_price"],
            "discount": book["discount"],
            "stock": book["stock"],
            "image_url": book["image_url"],
            "video_url": book["video_url"],
            "featured": bool(book["featured"]),
            "women_section": bool(book["women_section"]),
            "quran_section": bool(book["quran_section"]),
            "student_section": bool(book["student_section"])
        }
        
        return SuccessResponse(
            message="تم إنشاء الكتاب بنجاح",
            data={"book": formatted_book}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create book error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create book"
        )

@app.put("/api/books/{book_id}", response_model=SuccessResponse)
async def update_book(
    book_id: int,
    book_data: dict = Body(...),
    current_user: dict = Depends(AuthService.get_current_user)
):
    """تحديث كتاب (للمسؤول فقط)"""
    # التحقق من الصلاحيات مباشرة
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update books"
        )
    
    try:
        book = book_service.update_book(book_id, book_data, current_user)
        
        # تحويل البيانات
        formatted_book = {
            "id": book["id"],
            "title": book["title"],
            "author": book["author"],
            "category": book["category"],
            "level": book["level"],
            "description": book["description"],
            "price": book["price"],
            "original_price": book["original_price"],
            "discount": book["discount"],
            "stock": book["stock"],
            "image_url": book["image_url"],
            "video_url": book["video_url"],
            "featured": bool(book["featured"]),
            "women_section": bool(book["women_section"]),
            "quran_section": bool(book["quran_section"]),
            "student_section": bool(book["student_section"])
        }
        
        return SuccessResponse(
            message="تم تحديث الكتاب بنجاح",
            data={"book": formatted_book}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update book error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update book"
        )

@app.delete("/api/books/{book_id}", response_model=SuccessResponse)
async def delete_book(
    book_id: int,
    current_user: dict = Depends(AuthService.get_current_user)
):
    """حذف كتاب (للمسؤول فقط)"""
    # التحقق من الصلاحيات مباشرة
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete books"
        )
    
    try:
        success = book_service.delete_book(book_id, current_user)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Book not found"
            )
        
        return SuccessResponse(
            message="تم حذف الكتاب بنجاح"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete book error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete book"
        )

# ============================================================================
# القسم 9: مسارات السلة
# ============================================================================

@app.get("/api/cart", response_model=SuccessResponse)
async def get_cart(current_user: dict = Depends(AuthService.get_current_user)):
    """الحصول على سلة المستخدم"""
    try:
        cart_items = cart_service.get_cart(current_user["id"])
        # حساب المجموع الكلي
        total = sum(item["total"] for item in cart_items)
        
        # تحويل البيانات لتكون متوافقة
        formatted_items = []
        for item in cart_items:
            formatted_item = {
                "id": item["id"],
                "book_id": item["book_id"],
                "quantity": item["quantity"],
                "title": item["title"],
                "author": item["author"],
                "category": item["category"],
                "image_url": item["image_url"],
                "price": item["price"],
                "discount": item["discount"],
                "stock": item["stock"],
                "final_price": item["final_price"],
                "total": item["total"]
            }
            formatted_items.append(formatted_item)
        
        return SuccessResponse(
            message="سلة الشراء",
            data={"cart": formatted_items, "total_items": len(formatted_items), "total": total}
        )
    except Exception as e:
        logger.error(f"Get cart error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve cart"
        )

@app.post("/api/cart", response_model=SuccessResponse)
async def add_to_cart(
    cart_item: CartItemBase,
    current_user: dict = Depends(AuthService.get_current_user)
):
    """إضافة كتاب إلى السلة"""
    try:
        item = CartService.add_to_cart(
            current_user["id"],
            cart_item.book_id,
            cart_item.quantity
        )
        
        formatted_item = {
            "id": item["id"],
            "book_id": item["book_id"],
            "quantity": item["quantity"],
            "title": item["title"],
            "author": item["author"],
            "category": item["category"],
            "image_url": item["image_url"],
            "price": item["price"],
            "discount": item["discount"],
            "stock": item["stock"],
            "final_price": item["final_price"],
            "total": item["total"]
        }
        
        return SuccessResponse(
            message="تمت إضافة الكتاب إلى السلة",
            data={"item": formatted_item}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add to cart error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add item to cart"
        )

@app.put("/api/cart/{item_id}", response_model=SuccessResponse)
async def update_cart_item(
    item_id: int,
    quantity: int = Query(..., ge=1, le=100),
    current_user: dict = Depends(AuthService.get_current_user)
):
    """تحديث كمية عنصر في السلة"""
    try:
        item = CartService.update_cart_item(current_user["id"], item_id, quantity)
        
        formatted_item = {
            "id": item["id"],
            "book_id": item["book_id"],
            "quantity": item["quantity"],
            "title": item["title"],
            "author": item["author"],
            "category": item["category"],
            "image_url": item["image_url"],
            "price": item["price"],
            "discount": item["discount"],
            "stock": item["stock"],
            "final_price": item["final_price"],
            "total": item["total"]
        }
        
        return SuccessResponse(
            message="تم تحديث السلة",
            data={"item": formatted_item}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update cart item error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update cart item"
        )

@app.delete("/api/cart/{item_id}", response_model=SuccessResponse)
async def remove_from_cart(
    item_id: int,
    current_user: dict = Depends(AuthService.get_current_user)
):
    """حذف عنصر من السلة"""
    try:
        success = CartService.remove_from_cart(current_user["id"], item_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cart item not found"
            )
        
        return SuccessResponse(
            message="تم حذف العنصر من السلة"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove from cart error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove item from cart"
        )

# ============================================================================
# القسم 10: مسارات الطلبات
# ============================================================================

@app.post("/api/orders/checkout", response_model=SuccessResponse)
async def checkout(
    order_data: OrderBase,
    current_user: dict = Depends(AuthService.get_current_user)
):
    """إتمام عملية الشراء وإنشاء طلب"""
    try:
        # الحصول على محتويات السلة
        cart_items = cart_service.get_cart(current_user["id"])
        
        if not cart_items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cart is empty"
            )
        
        # التحقق من المخزون قبل إنشاء الطلب
        with db.get_connection() as conn:
            cursor = conn.cursor()
            for item in cart_items:
                cursor.execute(
                    "SELECT stock FROM books WHERE id = ?",
                    (item["book_id"],)
                )
                book = cursor.fetchone()
                if book["stock"] < item["quantity"]:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Not enough stock for '{item['title']}'. Available: {book['stock']}"
                    )
        
        # إنشاء الطلب
        order = OrderService.create_order(current_user["id"], order_data.dict(), cart_items)
        
        # تفريغ السلة
        CartService.clear_cart(current_user["id"])
        
        # إعادة تعيين عداد الاستغفار إذا تم استخدام الخصم
        IstighfarService.reset_istighfar(current_user["id"])
        
        return SuccessResponse(
            message=f"تم إنشاء الطلب بنجاح - رقم الطلب: {order['order_number']}",
            data={"order": order}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Checkout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create order"
        )

@app.get("/api/orders", response_model=SuccessResponse)
async def get_user_orders(current_user: dict = Depends(AuthService.get_current_user)):
    """الحصول على طلبات المستخدم"""
    try:
        orders = OrderService.get_user_orders(current_user["id"])
        
        formatted_orders = []
        for order in orders:
            formatted_order = {
                "id": order["id"],
                "order_number": order["order_number"],
                "status": order["status"],
                "total_amount": order["total_amount"],
                "subtotal": order["subtotal"],
                "discount": order["discount"],
                "shipping_cost": order["shipping_cost"],
                "payment_method": order["payment_method"],
                "customer_name": order["customer_name"],
                "phone": order["phone"],
                "email": order["email"],
                "address": order["address"],
                "province": order["province"],
                "city": order["city"],
                "created_at": order["created_at"],
                "completed_at": order["completed_at"],
                "items": order.get("items", [])
            }
            formatted_orders.append(formatted_order)
        
        return SuccessResponse(
            message="طلباتك",
            data={"orders": formatted_orders}
        )
    except Exception as e:
        logger.error(f"Get user orders error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve orders"
        )

@app.get("/api/orders/{order_id}", response_model=SuccessResponse)
async def get_order(
    order_id: int,
    current_user: dict = Depends(AuthService.get_current_user)
):
    """الحصول على تفاصيل طلب معين"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # جلب الطلب مع التحقق من الملكية
            cursor.execute("""
                SELECT * FROM orders 
                WHERE id = ? AND (user_id = ? OR ? = 'admin')
            """, (order_id, current_user["id"], current_user["role"]))
            
            order = cursor.fetchone()
            if not order:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Order not found or access denied"
                )
            
            order = dict(order)
            
            # تحويل القيم العشرية
            for key in ["total_amount", "subtotal", "discount", "shipping_cost"]:
                if order.get(key):
                    order[key] = float(order[key])
            
            # جلب عناصر الطلب
            cursor.execute("""
                SELECT oi.book_id, oi.quantity, oi.price, b.title, b.author, b.image_url
                FROM order_items oi
                JOIN books b ON oi.book_id = b.id
                WHERE oi.order_id = ?
            """, (order_id,))
            order["items"] = [dict(row) for row in cursor.fetchall()]
            
            return SuccessResponse(
                message="تفاصيل الطلب",
                data={"order": order}
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get order error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve order"
        )

# ============================================================================
# القسم 11: مسارات حفظة القرآن
# ============================================================================

@app.post("/api/hafiz/register", response_model=SuccessResponse)
async def register_hafiz(
    hafiz_data: HafizRequestBase,
    current_user: dict = Depends(AuthService.get_current_user)
):
    """تسجيل طلب حافظ قرآن"""
    try:
        # التحقق مما إذا كان المستخدم حافظاً بالفعل
        if current_user["is_hafiz"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are already registered as a Hafiz"
            )
        
        request = HafizService.register_hafiz(current_user["id"], hafiz_data.dict())
        return SuccessResponse(
            message="تم إرسال طلب حافظ القرآن بنجاح",
            data={"request": request}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Register hafiz error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register hafiz request"
        )

@app.get("/api/admin/hafiz/requests", response_model=SuccessResponse)
async def get_hafiz_requests(current_user: dict = Depends(AuthService.get_current_user)):
    """الحصول على طلبات حفظة القرآن (للمسؤول فقط)"""
    # التحقق من الصلاحيات مباشرة
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view hafiz requests"
        )
    
    try:
        requests = HafizService.get_pending_requests()
        return SuccessResponse(
            message="طلبات حفظة القرآن",
            data={"requests": requests}
        )
    except Exception as e:
        logger.error(f"Get hafiz requests error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve hafiz requests"
        )

@app.post("/api/admin/hafiz/requests/{request_id}/{action}", response_model=SuccessResponse)
async def process_hafiz_request(
    request_id: int,
    action: str,
    admin_notes: Optional[str] = Body(None),
    current_user: dict = Depends(AuthService.get_current_user)
):
    """معالجة طلب حافظ قرآن (للمسؤول فقط)"""
    # التحقق من الصلاحيات مباشرة
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can process hafiz requests"
        )
    
    try:
        request = HafizService.process_request(request_id, action, admin_notes)
        action_text = "موافقة على" if action == "approve" else "رفض"
        return SuccessResponse(
            message=f"تم {action_text} طلب حافظ القرآن",
            data={"request": request}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Process hafiz request error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process hafiz request"
        )

# ============================================================================
# القسم 12: مسارات نظام الاستغفار
# ============================================================================

@app.post("/api/istighfar/increment", response_model=SuccessResponse)
async def increment_istighfar(current_user: dict = Depends(AuthService.get_current_user)):
    """زيادة عداد الاستغفار"""
    try:
        result = IstighfarService.increment_istighfar(current_user["id"])
        return SuccessResponse(
            message=result["message"],
            data={
                "count": result["count"],
                "discount_percentage": result["discount_percentage"]
            }
        )
    except Exception as e:
        logger.error(f"Increment istighfar error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to increment istighfar count"
        )

@app.get("/api/istighfar/stats", response_model=SuccessResponse)
async def get_istighfar_stats(current_user: dict = Depends(AuthService.get_current_user)):
    """الحصول على إحصائيات الاستغفار للمستخدم"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT count FROM istighfar WHERE user_id = ?", (current_user["id"],))
            istighfar = cursor.fetchone()
            
            count = istighfar["count"] if istighfar else 0
            discount_percentage = min(count // 100, 5)
            
            return SuccessResponse(
                message="إحصائيات الاستغفار",
                data={
                    "count": count,
                    "discount_percentage": discount_percentage
                }
            )
    except Exception as e:
        logger.error(f"Get istighfar stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve istighfar stats"
        )

# ============================================================================
# القسم 13: مسارات التصنيفات والأقسام الخاصة
# ============================================================================

@app.get("/api/categories", response_model=SuccessResponse)
async def get_categories():
    """الحصول على جميع التصنيفات"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM categories ORDER BY name")
            categories = []
            for row in cursor.fetchall():
                category = dict(row)
                
                # حساب عدد الكتب في كل تصنيف
                cursor.execute(
                    "SELECT COUNT(*) as count FROM books WHERE category = ?",
                    (category["name"],)
                )
                count_result = cursor.fetchone()
                category["book_count"] = count_result["count"] if count_result else 0
                
                categories.append(category)
            
            # تحويل البيانات لتكون متوافقة مع Front-End
            formatted_categories = []
            for category in categories:
                formatted_category = {
                    "id": category["id"],
                    "name": category["name"],
                    "description": category["description"],
                    "icon": category["icon"],
                    "color": category["color"],
                    "book_count": category["book_count"],
                    "created_at": category.get("created_at")
                }
                formatted_categories.append(formatted_category)
            
            return SuccessResponse(
                message="التصنيفات",
                data={"categories": formatted_categories}
            )
    except Exception as e:
        logger.error(f"Get categories error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve categories"
        )

@app.get("/api/scholars", response_model=SuccessResponse)
async def get_scholars():
    """الحصول على قائمة العلماء - تم إضافة هذا المسار"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scholars ORDER BY name")
            scholars = [dict(row) for row in cursor.fetchall()]
            
            formatted_scholars = []
            for scholar in scholars:
                formatted_scholar = {
                    "id": scholar["id"],
                    "name": scholar["name"],
                    "specialization": scholar["specialization"],
                    "biography": scholar["biography"],
                    "image_url": scholar["image_url"],
                    "website_url": scholar["website_url"],
                    "created_at": scholar.get("created_at")
                }
                formatted_scholars.append(formatted_scholar)
            
            return SuccessResponse(
                message="قائمة العلماء",
                data={"scholars": formatted_scholars}
            )
    except Exception as e:
        logger.error(f"Get scholars error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve scholars"
        )

@app.get("/api/books/women", response_model=SuccessResponse)
async def get_women_books():
    """الحصول على كتب قسم النساء"""
    try:
        books = book_service.get_all_books(women_section=True)
        
        formatted_books = []
        for book in books:
            formatted_book = {
                "id": book["id"],
                "title": book["title"],
                "author": book["author"],
                "category": book["category"],
                "level": book["level"],
                "description": book["description"],
                "price": book["price"],
                "original_price": book["original_price"],
                "discount": book["discount"],
                "stock": book["stock"],
                "image_url": book["image_url"],
                "final_price": book.get("final_price", book["price"])
            }
            formatted_books.append(formatted_book)
        
        return SuccessResponse(
            message="كتب قسم النساء",
            data={"books": formatted_books, "count": len(formatted_books)}
        )
    except Exception as e:
        logger.error(f"Get women books error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve women books"
        )

@app.get("/api/books/quran", response_model=SuccessResponse)
async def get_quran_books():
    """الحصول على كتب قسم القرآن"""
    try:
        books = book_service.get_all_books(quran_section=True)
        
        formatted_books = []
        for book in books:
            formatted_book = {
                "id": book["id"],
                "title": book["title"],
                "author": book["author"],
                "category": book["category"],
                "level": book["level"],
                "description": book["description"],
                "price": book["price"],
                "original_price": book["original_price"],
                "discount": book["discount"],
                "stock": book["stock"],
                "image_url": book["image_url"],
                "final_price": book.get("final_price", book["price"])
            }
            formatted_books.append(formatted_book)
        
        return SuccessResponse(
            message="كتب قسم القرآن",
            data={"books": formatted_books, "count": len(formatted_books)}
        )
    except Exception as e:
        logger.error(f"Get quran books error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve quran books"
        )

@app.get("/api/student/levels", response_model=SuccessResponse)
async def get_student_levels():
    """الحصول على مستويات طالب العلم"""
    levels = [
        {"id": 1, "name": "المستوى الأول", "description": "كتب للمبتدئين في طلب العلم", "value": "مبتدئ"},
        {"id": 2, "name": "المستوى الثاني", "description": "كتب للمتوسطين في طلب العلم", "value": "متوسط"},
        {"id": 3, "name": "المستوى الثالث", "description": "كتب للمتقدمين في طلب العلم", "value": "متقدم"},
        {"id": 4, "name": "المستوى الرابع", "description": "كتب للمتخصصين في العلوم الشرعية", "value": "عالم"}
    ]
    
    return SuccessResponse(
        message="مستويات طالب العلم",
        data={"levels": levels}
    )

@app.get("/api/student/levels/{level_id}", response_model=SuccessResponse)
async def get_student_level_books(level_id: int):
    """الحصول على كتب مستوى طالب العلم"""
    level_mapping = {
        1: "مبتدئ",
        2: "متوسط",
        3: "متقدم",
        4: "عالم"
    }
    
    level_name = level_mapping.get(level_id)
    if not level_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Level not found"
        )
    
    try:
        books = book_service.get_all_books(level=level_name, student_section=True)
        
        formatted_books = []
        for book in books:
            formatted_book = {
                "id": book["id"],
                "title": book["title"],
                "author": book["author"],
                "category": book["category"],
                "level": book["level"],
                "description": book["description"],
                "price": book["price"],
                "original_price": book["original_price"],
                "discount": book["discount"],
                "stock": book["stock"],
                "image_url": book["image_url"],
                "final_price": book.get("final_price", book["price"])
            }
            formatted_books.append(formatted_book)
        
        return SuccessResponse(
            message=f"كتب المستوى {level_id} ({level_name})",
            data={"books": formatted_books, "count": len(formatted_books)}
        )
    except Exception as e:
        logger.error(f"Get student level books error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve student level books"
        )

# ============================================================================
# القسم 14: مسارات لوحة التحكم (Admin)
# ============================================================================

@app.get("/api/admin/stats", response_model=SuccessResponse)
async def get_admin_stats(current_user: dict = Depends(AuthService.get_current_user)):
    """الحصول على إحصائيات الموقع (للمسؤول فقط)"""
    # التحقق من الصلاحيات مباشرة
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view statistics"
        )
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # إحصائيات الكتب
            cursor.execute("SELECT COUNT(*) as total FROM books")
            total_books = cursor.fetchone()["total"]
            
            cursor.execute("SELECT COUNT(*) as low_stock FROM books WHERE stock <= 5 AND stock > 0")
            low_stock = cursor.fetchone()["low_stock"]
            
            cursor.execute("SELECT COUNT(*) as out_of_stock FROM books WHERE stock = 0")
            out_of_stock = cursor.fetchone()["out_of_stock"]
            
            # إحصائيات الطلبات
            cursor.execute("SELECT COUNT(*) as total FROM orders")
            total_orders = cursor.fetchone()["total"]
            
            cursor.execute("SELECT COUNT(*) as pending FROM orders WHERE status = 'pending'")
            pending_orders = cursor.fetchone()["pending"]
            
            cursor.execute("SELECT COUNT(*) as completed FROM orders WHERE status = 'completed'")
            completed_orders = cursor.fetchone()["completed"]
            
            cursor.execute("SELECT SUM(total_amount) as revenue FROM orders WHERE status = 'completed'")
            revenue_result = cursor.fetchone()
            revenue = float(revenue_result["revenue"]) if revenue_result["revenue"] else 0.0
            
            # إحصائيات المستخدمين
            cursor.execute("SELECT COUNT(*) as total FROM users")
            total_users = cursor.fetchone()["total"]
            
            cursor.execute("SELECT COUNT(*) as hafiz FROM users WHERE is_hafiz = 1")
            hafiz_users = cursor.fetchone()["hafiz"]
            
            # طلبات حفظة القرآن المعلقة
            cursor.execute("SELECT COUNT(*) as pending_hafiz FROM hafiz_requests WHERE status = 'pending'")
            pending_hafiz = cursor.fetchone()["pending_hafiz"]
            
            stats = {
                "books": {
                    "total": total_books,
                    "low_stock": low_stock,
                    "out_of_stock": out_of_stock
                },
                "orders": {
                    "total": total_orders,
                    "pending": pending_orders,
                    "completed": completed_orders,
                    "revenue": revenue
                },
                "users": {
                    "total": total_users,
                    "hafiz": hafiz_users,
                    "pending_hafiz_requests": pending_hafiz
                }
            }
            
            return SuccessResponse(
                message="إحصائيات الموقع",
                data={"stats": stats}
            )
            
    except Exception as e:
        logger.error(f"Get admin stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve admin stats"
        )

@app.get("/api/admin/orders", response_model=SuccessResponse)
async def get_all_orders(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(AuthService.get_current_user)
):
    """الحصول على جميع الطلبات (للمسؤول فقط)"""
    # التحقق من الصلاحيات مباشرة
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view all orders"
        )
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM orders WHERE 1=1"
            params = []
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            orders = []
            for row in cursor.fetchall():
                order = dict(row)
                # تحويل القيم العشرية
                for key in ["total_amount", "subtotal", "discount", "shipping_cost"]:
                    if order.get(key):
                        order[key] = float(order[key])
                orders.append(order)
            
            # جلب عناصر كل طلب
            for order in orders:
                cursor.execute("""
                    SELECT oi.book_id, oi.quantity, oi.price, b.title, b.author, b.image_url
                    FROM order_items oi
                    JOIN books b ON oi.book_id = b.id
                    WHERE oi.order_id = ?
                """, (order["id"],))
                order["items"] = [dict(row) for row in cursor.fetchall()]
            
            return SuccessResponse(
                message="جميع الطلبات",
                data={"orders": orders}
            )
            
    except Exception as e:
        logger.error(f"Get all orders error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve orders"
        )

@app.put("/api/admin/orders/{order_id}/status", response_model=SuccessResponse)
async def update_order_status(
    order_id: int,
    new_status: str = Body(..., embed=True),
    current_user: dict = Depends(AuthService.get_current_user)
):
    """تحديث حالة الطلب (للمسؤول فقط)"""
    # التحقق من الصلاحيات مباشرة
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update order status"
        )
    
    if new_status not in ["pending", "processing", "completed", "cancelled"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status"
        )
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # التحقق من وجود الطلب
            cursor.execute("SELECT id, status FROM orders WHERE id = ?", (order_id,))
            order = cursor.fetchone()
            if not order:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Order not found"
                )
            
            # إذا تم الإلغاء، إرجاع الكتب للمخزون
            if new_status == "cancelled" and order["status"] != "cancelled":
                cursor.execute("""
                    SELECT oi.book_id, oi.quantity 
                    FROM order_items oi 
                    WHERE oi.order_id = ?
                """, (order_id,))
                
                items = cursor.fetchall()
                for item in items:
                    cursor.execute(
                        "UPDATE books SET stock = stock + ? WHERE id = ?",
                        (item["quantity"], item["book_id"])
                    )
            
            # تحديث الحالة
            cursor.execute(
                "UPDATE orders SET status = ? WHERE id = ?",
                (new_status, order_id)
            )
            
            return SuccessResponse(
                message=f"تم تحديث حالة الطلب إلى '{new_status}'"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update order status error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update order status"
        )

@app.get("/api/admin/users", response_model=SuccessResponse)
async def get_all_users(
    role: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(AuthService.get_current_user)
):
    """الحصول على جميع المستخدمين (للمسؤول فقط)"""
    # التحقق من الصلاحيات مباشرة
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view all users"
        )
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT id, email, name, phone, address, role, is_hafiz, is_active, created_at FROM users WHERE 1=1"
            params = []
            
            if role:
                query += " AND role = ?"
                params.append(role)
            
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            users = []
            for row in cursor.fetchall():
                user = dict(row)
                user["is_hafiz"] = bool(user["is_hafiz"])
                user["is_active"] = bool(user["is_active"])
                users.append(user)
            
            return SuccessResponse(
                message="جميع المستخدمين",
                data={"users": users}
            )
            
    except Exception as e:
        logger.error(f"Get all users error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve users"
        )

# ============================================================================
# القسم 15: مسارات خاصة (الصحة، الإعدادات، إلخ)
# ============================================================================

@app.get("/")
async def root():
    return JSONResponse({
        "message": "مرحباً بك في API مكتبة النور",
        "version": "1.0.0",
        "docs": "/api/docs",
        "endpoints": {
            "auth": "/api/auth/*",
            "books": "/api/books/*",
            "cart": "/api/cart/*",
            "orders": "/api/orders/*",
            "categories": "/api/categories",
            "scholars": "/api/scholars",
            "student_levels": "/api/student/levels"
        }
    })

@app.get("/api/health")
async def health_check():
    """فحص صحة التطبيق"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            db_status = "healthy"
            
            # التحقق من الجداول الأساسية
            cursor.execute("SELECT COUNT(*) as count FROM books")
            books_count = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM categories")
            categories_count = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM scholars")
            scholars_count = cursor.fetchone()["count"]
            
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
        logger.error(f"Database health check failed: {e}")
    
    return JSONResponse({
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "noor-library-api",
        "database": db_status,
        "books_count": books_count if 'books_count' in locals() else 0,
        "categories_count": categories_count if 'categories_count' in locals() else 0,
        "scholars_count": scholars_count if 'scholars_count' in locals() else 0,
        "version": "1.0.0"
    })

@app.get("/api/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
        swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
    )

@app.get("/openapi.json", include_in_schema=False)
async def get_open_api_endpoint():
    return JSONResponse(app.openapi())

@app.get("/api/settings", response_model=SuccessResponse)
async def get_settings():
    """الحصول على إعدادات الموقع"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value, description FROM site_settings")
            settings = {row["key"]: row["value"] for row in cursor.fetchall()}
            
            # إضافة الإعدادات الافتراضية إذا لم تكن موجودة
            default_settings = {
                "site_name": Config.SITE_NAME,
                "site_email": Config.SITE_EMAIL,
                "shipping_cost": str(Config.SHIPPING_COST),
                "free_shipping_threshold": str(Config.FREE_SHIPPING_THRESHOLD),
                "hafiz_discount": str(Config.HAFIZ_DISCOUNT),
                "currency": "ج.م"
            }
            
            for key, value in default_settings.items():
                if key not in settings:
                    settings[key] = value
            
            return SuccessResponse(
                message="إعدادات الموقع",
                data={"settings": settings}
            )
            
    except Exception as e:
        logger.error(f"Get settings error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve settings"
        )

@app.put("/api/admin/settings", response_model=SuccessResponse)
async def update_settings(
    settings: dict = Body(...),
    current_user: dict = Depends(AuthService.get_current_user)
):
    """تحديث إعدادات الموقع (للمسؤول فقط)"""
    # التحقق من الصلاحيات مباشرة
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update settings"
        )
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            for key, value in settings.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO site_settings (key, value, description, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (key, str(value), f"إعداد {key}"))
            
            # إعادة تحميل الإعدادات
            cursor.execute("SELECT key, value FROM site_settings")
            updated_settings = {row["key"]: row["value"] for row in cursor.fetchall()}
            
            return SuccessResponse(
                message="تم تحديث الإعدادات بنجاح",
                data={"settings": updated_settings}
            )
            
    except Exception as e:
        logger.error(f"Update settings error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update settings"
        )

# ============================================================================
# القسم 16: معالجة الأخطاء العام
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """معالج أخطاء HTTP"""
    logger.error(f"HTTP error: {exc.detail} - Path: {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content=json.dumps({
            "success": False,
            "error": exc.detail,
            "details": None
        }),
        media_type="application/json"
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """معالج الأخطاء العام"""
    logger.error(f"Unhandled error: {exc} - Path: {request.url.path}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=json.dumps({
            "success": False,
            "error": "Internal server error",
            "details": str(exc) if Config.DEBUG else None
        }),
        media_type="application/json"
    )

# ============================================================================
# القسم 17: نقطة الدخول الرئيسية
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("مكتبة النور - Back-End - النسخة المصححة")
    print("=" * 60)
    print(f"Python Version: {sys.version}")
    print(f"Database: {Config.DATABASE_URL}")
    print(f"Debug Mode: {Config.DEBUG}")
    print(f"Admin Email: admin@noor-library.com")
    print(f"Admin Password: admin123")
    print("=" * 60)
    print("المشاكل التي تم إصلاحها:")
    print("1. إضافة جدول العلماء (scholars)")
    print("2. إصلاح استعلامات التصنيفات")
    print("3. إصلاح تحويل البيانات لـ Front-End")
    print("4. إضافة بيانات أولية شاملة")
    print("5. إصلاح حفظ الإعدادات في قاعدة البيانات")
    print("=" * 60)
    print("Starting server on http://localhost:8000")
    print("API Documentation: http://localhost:8000/api/docs")
    print("Health Check: http://localhost:8000/api/health")
    print("Debug Stats: http://localhost:8000/api/debug/db-stats")
    print("=" * 60)
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=Config.DEBUG,
        log_level="info" if Config.DEBUG else "warning"
    )