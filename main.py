import telebot
from telebot import types
import requests
import json
import hashlib
import hmac
import time
from urllib.parse import quote
import sqlite3
from datetime import datetime


import os

# ========== إعدادات البوت ==========
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

# ========== إعدادات AliExpress API ==========
APP_KEY = os.environ.get('APP_KEY', 'YOUR_APP_KEY')
APP_SECRET = os.environ.get('APP_SECRET', 'YOUR_APP_SECRET')
TRACKING_ID = os.environ.get('TRACKING_ID', 'YOUR_TRACKING_ID')
bot = telebot.TeleBot(BOT_TOKEN)

# ========== قاعدة البيانات ==========
def init_db():
    conn = sqlite3.connect('affiliate_bot.db')
    c = conn.cursor()
    
    # جدول المستخدمين
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  join_date TEXT,
                  total_clicks INTEGER DEFAULT 0,
                  language TEXT DEFAULT 'ar')''')
    
    # جدول النقرات
    c.execute('''CREATE TABLE IF NOT EXISTS clicks
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  product_id TEXT,
                  product_title TEXT,
                  click_date TEXT,
                  FOREIGN KEY (user_id) REFERENCES users (user_id))''')
    
    # جدول المنتجات المفضلة
    c.execute('''CREATE TABLE IF NOT EXISTS favorites
                 (user_id INTEGER,
                  product_id TEXT,
                  product_title TEXT,
                  product_image TEXT,
                  product_price TEXT,
                  added_date TEXT,
                  PRIMARY KEY (user_id, product_id))''')
    
    conn.commit()
    conn.close()

init_db()

# ========== دوال AliExpress API ==========
def generate_signature(params, secret):
    """توليد التوقيع للطلبات"""
    sorted_params = sorted(params.items())
    string_to_sign = secret + ''.join([f'{k}{v}' for k, v in sorted_params]) + secret
    return hmac.new(secret.encode(), string_to_sign.encode(), hashlib.md5).hexdigest().upper()

def call_api(method, params):
    """استدعاء AliExpress API"""
    system_params = {
        'app_key': APP_KEY,
        'sign_method': 'md5',
        'timestamp': str(int(time.time() * 1000)),
        'format': 'json',
        'v': '2.0',
        'method': method
    }
    
    all_params = {**system_params, **params}
    all_params['sign'] = generate_signature(all_params, APP_SECRET)
    
    try:
        response = requests.post(API_GATEWAY, data=all_params, timeout=30)
        return response.json()
    except Exception as e:
        print(f"API Error: {e}")
        return None

def search_products(keywords, page=1, page_size=10, category_id=None, min_price=None, max_price=None, sort='default'):
    """البحث عن المنتجات"""
    params = {
        'keywords': keywords,
        'page_no': str(page),
        'page_size': str(page_size),
        'tracking_id': TRACKING_ID,
        'sort': sort,
        'target_currency': 'USD',
        'target_language': 'AR'
    }
    
    if category_id:
        params['category_ids'] = str(category_id)
    if min_price:
        params['min_sale_price'] = str(min_price)
    if max_price:
        params['max_sale_price'] = str(max_price)
    
    return call_api('aliexpress.affiliate.product.query', params)

def get_product_details(product_ids):
    """الحصول على تفاصيل المنتجات"""
    params = {
        'product_ids': ','.join(map(str, product_ids)),
        'tracking_id': TRACKING_ID,
        'target_currency': 'USD',
        'target_language': 'AR'
    }
    
    return call_api('aliexpress.affiliate.productdetail.get', params)

def generate_promotion_link(source_values):
    """توليد روابط الترويج"""
    params = {
        'promotion_link_type': '0',
        'source_values': source_values,
        'tracking_id': TRACKING_ID
    }
    
    return call_api('aliexpress.affiliate.link.generate', params)

def get_hot_products(category_id=None):
    """الحصول على المنتجات الرائجة"""
    params = {
        'tracking_id': TRACKING_ID,
        'target_currency': 'USD',
        'target_language': 'AR'
    }
    
    if category_id:
        params['category_id'] = str(category_id)
    
    return call_api('aliexpress.affiliate.hotproduct.query', params)

def get_categories():
    """الحصول على الفئات"""
    params = {}
    return call_api('aliexpress.affiliate.category.get', params)

# ========== دوال قاعدة البيانات ==========
def add_user(user_id, username, first_name):
    conn = sqlite3.connect('affiliate_bot.db')
    c = conn.cursor()
    c.execute('''INSERT OR IGNORE INTO users (user_id, username, first_name, join_date)
                 VALUES (?, ?, ?, ?)''', (user_id, username, first_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def track_click(user_id, product_id, product_title):
    conn = sqlite3.connect('affiliate_bot.db')
    c = conn.cursor()
    c.execute('''INSERT INTO clicks (user_id, product_id, product_title, click_date)
                 VALUES (?, ?, ?, ?)''', (user_id, product_id, product_title, datetime.now().isoformat()))
    c.execute('UPDATE users SET total_clicks = total_clicks + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def add_favorite(user_id, product_id, title, image, price):
    conn = sqlite3.connect('affiliate_bot.db')
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO favorites (user_id, product_id, product_title, product_image, product_price, added_date)
                     VALUES (?, ?, ?, ?, ?, ?)''', 
                  (user_id, product_id, title, image, price, datetime.now().isoformat()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_favorites(user_id):
    conn = sqlite3.connect('affiliate_bot.db')
    c = conn.cursor()
    c.execute('SELECT * FROM favorites WHERE user_id = ? ORDER BY added_date DESC', (user_id,))
    favorites = c.fetchall()
    conn.close()
    return favorites

def remove_favorite(user_id, product_id):
    conn = sqlite3.connect('affiliate_bot.db')
    c = conn.cursor()
    c.execute('DELETE FROM favorites WHERE user_id = ? AND product_id = ?', (user_id, product_id))
    conn.commit()
    conn.close()

# ========== معالجات البوت ==========
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    add_user(user_id, username, first_name)
    
    welcome_text = f"""
🎉 مرحباً {first_name}!

أنا بوت التسوق الذكي من AliExpress 🛍️

✨ ماذا أستطيع أن أفعل؟
• 🔍 البحث عن أي منتج تريده
• 🔥 عرض المنتجات الأكثر مبيعاً
• 🏷️ تصفح الفئات المختلفة
• ⭐ حفظ المنتجات المفضلة
• 💰 الحصول على أفضل الأسعار والخصومات

👇 اختر من القائمة أدناه للبدء
    """
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('🔍 بحث', '🔥 منتجات رائجة')
    markup.add('🏷️ الفئات', '⭐ المفضلة')
    markup.add('📊 إحصائياتي', 'ℹ️ مساعدة')
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.message_handler(commands=['search'])
def search_command(message):
    msg = bot.send_message(message.chat.id, "🔍 أدخل اسم المنتج الذي تبحث عنه:")
    bot.register_next_step_handler(msg, process_search)

def process_search(message, page=1):
    search_term = message.text
    
    loading_msg = bot.send_message(message.chat.id, "⏳ جاري البحث...")
    
    result = search_products(search_term, page=page, page_size=5)
    
    bot.delete_message(message.chat.id, loading_msg.message_id)
    
    if result and 'aliexpress_affiliate_product_query_response' in result:
        response = result['aliexpress_affiliate_product_query_response']
        
        if 'resp_result' in response:
            resp_result = json.loads(response['resp_result']['resp_msg'])
            products = resp_result.get('result', {}).get('products', [])
            total_results = resp_result.get('result', {}).get('total_results', 0)
            
            if products:
                bot.send_message(message.chat.id, f"✅ تم العثور على {total_results} منتج\n\n📦 أفضل النتائج:")
                
                for product in products:
                    send_product_card(message.chat.id, product)
                
                # أزرار التنقل
                if total_results > page * 5:
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("➡️ الصفحة التالية", 
                                                         callback_data=f"search_{search_term}_{page+1}"))
                    bot.send_message(message.chat.id, "👇 المزيد من النتائج:", reply_markup=markup)
            else:
                bot.send_message(message.chat.id, "❌ لم يتم العثور على منتجات. جرب كلمات بحث أخرى.")
        else:
            bot.send_message(message.chat.id, "❌ حدث خطأ في البحث. حاول مرة أخرى.")
    else:
        bot.send_message(message.chat.id, "❌ تعذر الاتصال بالخدمة. حاول لاحقاً.")

def send_product_card(chat_id, product):
    """إرسال بطاقة المنتج"""
    title = product.get('product_title', 'بدون عنوان')
    price = product.get('target_sale_price', product.get('target_original_price', 'N/A'))
    image = product.get('product_main_image_url', '')
    product_id = product.get('product_id', '')
    product_url = product.get('promotion_link', product.get('product_detail_url', ''))
    
    # حساب نسبة الخصم
    original_price = float(product.get('target_original_price', 0))
    sale_price = float(product.get('target_sale_price', original_price))
    discount = 0
    if original_price > sale_price:
        discount = int(((original_price - sale_price) / original_price) * 100)
    
    rating = product.get('evaluate_rate', 'N/A')
    orders = product.get('30days_sold_count', product.get('lastest_volume', 0))
    
    caption = f"""
🛍️ **{title[:100]}**

💰 السعر: **${sale_price}**
"""
    
    if discount > 0:
        caption += f"🏷️ خصم: **{discount}%** (كان ${original_price})\n"
    
    caption += f"""
⭐ التقييم: {rating}
📦 المبيعات: {orders}+

🔗 رابط المنتج 👇
"""
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # توليد رابط الترويج
    promo_result = generate_promotion_link(product_url)
    if promo_result and 'aliexpress_affiliate_link_generate_response' in promo_result:
        promo_resp = promo_result['aliexpress_affiliate_link_generate_response']
        if 'resp_result' in promo_resp:
            promo_data = json.loads(promo_resp['resp_result']['resp_msg'])
            if promo_data.get('resp_code') == 200:
                promo_link = promo_data['result']['promotion_links'][0]['promotion_link']
                markup.add(types.InlineKeyboardButton("🛒 اشتري الآن", url=promo_link))
                markup.add(types.InlineKeyboardButton("⭐ أضف للمفضلة", 
                                                     callback_data=f"fav_{product_id}"))
    
    try:
        if image:
            bot.send_photo(chat_id, image, caption=caption, parse_mode='Markdown', reply_markup=markup)
        else:
            bot.send_message(chat_id, caption, parse_mode='Markdown', reply_markup=markup)
    except:
        caption_text = caption.replace('**', '').replace('*', '')
        bot.send_message(chat_id, caption_text, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == '🔥 منتجات رائجة')
def hot_products_command(message):
    loading_msg = bot.send_message(message.chat.id, "⏳ جاري تحميل المنتجات الرائجة...")
    
    result = get_hot_products()
    
    bot.delete_message(message.chat.id, loading_msg.message_id)
    
    if result and 'aliexpress_affiliate_hotproduct_query_response' in result:
        response = result['aliexpress_affiliate_hotproduct_query_response']
        
        if 'resp_result' in response:
            resp_result = json.loads(response['resp_result']['resp_msg'])
            products = resp_result.get('result', {}).get('products', [])
            
            if products:
                bot.send_message(message.chat.id, "🔥 **المنتجات الأكثر مبيعاً:**", parse_mode='Markdown')
                
                for product in products[:10]:
                    send_product_card(message.chat.id, product)
            else:
                bot.send_message(message.chat.id, "❌ لا توجد منتجات رائجة حالياً.")

@bot.message_handler(func=lambda m: m.text == '🏷️ الفئات')
def categories_command(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    categories = [
        ('📱 إلكترونيات', '44'),
        ('👗 ملابس نسائية', '100003109'),
        ('👔 ملابس رجالية', '100003070'),
        ('🏠 منزل وحديقة', '15'),
        ('⌚ ساعات', '1511'),
        ('💄 جمال وصحة', '66'),
        ('🎮 ألعاب', '26'),
        ('👶 أطفال', '1501'),
        ('⚽ رياضة', '18'),
        ('💍 مجوهرات', '36'),
        ('👜 حقائب', '1524'),
        ('👠 أحذية', '322'),
    ]
    
    for name, cat_id in categories:
        markup.add(types.InlineKeyboardButton(name, callback_data=f'cat_{cat_id}'))
    
    bot.send_message(message.chat.id, "🏷️ اختر الفئة:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('cat_'))
def category_callback(call):
    category_id = call.data.replace('cat_', '')
    
    bot.answer_callback_query(call.id, "⏳ جاري التحميل...")
    
    result = search_products('', category_id=category_id, page_size=10)
    
    if result and 'aliexpress_affiliate_product_query_response' in result:
        response = result['aliexpress_affiliate_product_query_response']
        
        if 'resp_result' in response:
            resp_result = json.loads(response['resp_result']['resp_msg'])
            products = resp_result.get('result', {}).get('products', [])
            
            if products:
                bot.send_message(call.message.chat.id, "✅ منتجات الفئة:")
                
                for product in products:
                    send_product_card(call.message.chat.id, product)

@bot.callback_query_handler(func=lambda call: call.data.startswith('fav_'))
def add_favorite_callback(call):
    product_id = call.data.replace('fav_', '')
    user_id = call.from_user.id
    
    # هنا يجب جلب تفاصيل المنتج
    result = get_product_details([product_id])
    
    if result:
        # حفظ المنتج في المفضلة
        success = add_favorite(user_id, product_id, "منتج", "", "")
        
        if success:
            bot.answer_callback_query(call.id, "⭐ تمت الإضافة للمفضلة!")
        else:
            bot.answer_callback_query(call.id, "❌ المنتج موجود مسبقاً في المفضلة")

@bot.message_handler(func=lambda m: m.text == '⭐ المفضلة')
def favorites_command(message):
    user_id = message.from_user.id
    favorites = get_favorites(user_id)
    
    if favorites:
        bot.send_message(message.chat.id, f"⭐ لديك {len(favorites)} منتج في المفضلة:")
        # عرض المنتجات المفضلة
    else:
        bot.send_message(message.chat.id, "❌ لا توجد منتجات في المفضلة بعد.")

@bot.message_handler(func=lambda m: m.text == '📊 إحصائياتي')
def stats_command(message):
    user_id = message.from_user.id
    
    conn = sqlite3.connect('affiliate_bot.db')
    c = conn.cursor()
    c.execute('SELECT total_clicks, join_date FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    
    c.execute('SELECT COUNT(*) FROM favorites WHERE user_id = ?', (user_id,))
    fav_count = c.fetchone()[0]
    conn.close()
    
    if result:
        total_clicks, join_date = result
        stats_text = f"""
📊 **إحصائياتك**

👤 المستخدم: {message.from_user.first_name}
📅 تاريخ الانضمام: {join_date[:10]}
🔗 عدد النقرات: {total_clicks}
⭐ المنتجات المفضلة: {fav_count}

شكراً لاستخدامك البوت! 💙
        """
        bot.send_message(message.chat.id, stats_text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '🔍 بحث')
def quick_search(message):
    search_command(message)

@bot.message_handler(func=lambda m: m.text == 'ℹ️ مساعدة')
def help_command(message):
    help_text = """
ℹ️ **دليل الاستخدام**

🔍 **البحث:**
استخدم زر "بحث" وأدخل اسم المنتج

🏷️ **الفئات:**
تصفح المنتجات حسب الفئات المختلفة

🔥 **المنتجات الرائجة:**
شاهد الأكثر مبيعاً

⭐ **المفضلة:**
احفظ منتجاتك المفضلة للرجوع إليها

📊 **الإحصائيات:**
تابع نشاطك على البوت

💡 **نصيحة:** جميع الروابط تحتوي على أفضل الأسعار!

للدعم: @YOUR_SUPPORT
    """
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    # البحث التلقائي
    msg = bot.send_message(message.chat.id, f"🔍 هل تبحث عن: {message.text}?")
    bot.register_next_step_handler(msg, lambda m: process_search(message))

if __name__ == '__main__':
    print("🤖 البوت يعمل الآن...")
    print("📊 قاعدة البيانات جاهزة...")
    bot.infinity_polling()
