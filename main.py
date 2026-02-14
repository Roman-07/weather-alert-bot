import sqlite3
from datetime import datetime, time
import requests
import pytz
import logging
from time import sleep
import re
from deep_translator import GoogleTranslator
from timezonefinder import TimezoneFinder
from geopy.geocoders import Nominatim
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackContext,
    CallbackQueryHandler,
    InlineQueryHandler,
)

# LOGGING FOR DEBUGGING OF THE BOT
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

# DATABASE CONNECTION
conn = sqlite3.connect("User_data.db",  check_same_thread=False)
cursor = conn.cursor()

# DECLARATION OF VARIABLE AND CONSTANT
current_w_preferences_list = ['0'] * 10
current_data = {
    'user_id': None,
    'name': '',
    'location': '',
    'w_preferences': '',
    'timezone': '',
    'a_schedule': '',
    'gmt_schedule': ''
    }
W_METRICS = ['Общее описание', 'Температура', 'Ветер', 'Осадки', 'Облака', 'Снег', 'Давление', 'Влажность', 'Видимость', 'Солнечная радиация', 'Предупреждени о погоде']
translator = GoogleTranslator(source='en', target='ru')

def translate_to_russian(text):
    translation = translator.translate(text)
    return translation

# TIMEZONE & LOCATION FUNCTION. Initialize the timezone finder and geolocator for the following function
tf = TimezoneFinder()
geolocator = Nominatim(user_agent="timezone_finder")

def get_gmt_offset(query):
    city, country = query.split(',')
    location = geolocator.geocode(f"{city}, {country}", exactly_one=True)  # add later country_codes=code; so need to ask for country also
    if location is None:
        return "City not found", None, None, None
    lat, lng = location.latitude, location.longitude
    timezone_name = tf.timezone_at(lng=lng, lat=lat)
    timezone = pytz.timezone(timezone_name)
    current_time = datetime.now(timezone)
    utc_offset = current_time.utcoffset().total_seconds() / 3600
    return f'GMT{utc_offset:+.0f}', lat, lng, timezone

# FUNCTION TO CONVERT FROM LOCAL USER'S TIME INTO GMT (for the bot)
def local_to_gmt(local_time, timezone):
    difference = - int(timezone[3:])
    local_hours = int(local_time[:2])
    new_hours = local_hours + difference
    if new_hours in range(0, 25):
        if new_hours in range(0, 10):
            gmt_time = '0' + str(new_hours) + local_time[2:]
        else:
            gmt_time = str(new_hours) + local_time[2:]
    elif new_hours < 0:
        new_hours = 24 - abs(new_hours)
        if new_hours in range(0, 10):
            gmt_time = '0' + str(new_hours) + local_time[2:]
        else:
            gmt_time = str(new_hours) + local_time[2:]
    else:
        new_hours = new_hours - 24
        if new_hours in range(0, 10):
            gmt_time = '0' + str(new_hours) + local_time[2:]
        else:
            gmt_time = str(new_hours) + local_time[2:]
    return gmt_time

def gmt_to_local(gmt_time, timezone):
    difference = int(timezone[3:])
    gmt_hours = int(gmt_time[:2])
    new_hours = gmt_hours + difference
    if new_hours in range(0, 25):
        if new_hours in range(0, 10):
            local_time = '0' + str(new_hours) + gmt_time[2:]
        else:
            local_time = str(new_hours) + gmt_time[2:]
    elif new_hours < 0:
        new_hours = 24 - abs(new_hours)
        if new_hours in range(0, 10):
            local_time = '0' + str(new_hours) + gmt_time[2:]
        else:
            local_time = str(new_hours) + gmt_time[2:]
    else:
        new_hours = new_hours - 24
        if new_hours in range(0, 10):
            local_time = '0' + str(new_hours) + gmt_time[2:]
        else:
            local_time = str(new_hours) + gmt_time[2:]
    return local_time

# TELEGRAM BOT CODE START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я очень хочу помочь сделать вашу жизнь проще. Чтобы начать работу, мне потребуется немного "
                                    "информации о Вас. Спасибо!")
    await update.message.reply_text("Как мне Вас называть?")
    return 2


async def get_consent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text
    if answer == "Да!":
        await update.message.reply_text("Отлично, давайте начнем! Какое имя вы предпочитаете?", reply_markup=ReplyKeyboardRemove())
        return 2
    elif answer == "Нет...":
        await update.message.reply_text("Увы, я не могу нормально функционировать без этой информации. Если вы передумаете, просто перезапустите бота, набрав /start",
                                        reply_markup=ReplyKeyboardRemove())
        context.user_data.clear()
        return ConversationHandler.END
    else:
        await update.message.reply_text("Пожалуйста, используйте кнопки!")
        return 1
    

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_data['name'] = update.message.text
    if '/' in update.message.text:
            await update.message.reply_text("Введите корректное имя.")
            return 2
    else:
        current_data['user_id'] = update.message.chat.id
        cursor.execute("SELECT id FROM Users WHERE id=?", (current_data['user_id'],))
        if not cursor.fetchone():
            cursor.execute("""INSERT INTO Users (id, name) VALUES (?, ?)""",
                            (current_data['user_id'], current_data['name']))
        else:
            cursor.execute("UPDATE Users SET name=? WHERE id=?",
                            (current_data['name'],current_data['user_id']))
        conn.commit()
        await update.message.reply_text("Для какого населенного пункта и из какой страны вы хотите получать информацию о погоде? Пожалуйста, укажите ближайший узнаваемый город. Введите город и страну через запятую, например, 'Москва, Россия'")
        return 3


async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_data['location'] = update.message.text
    pattern = r'^([а-яА-ЯёЁa-zA-Z]+),\s*([а-яА-ЯёЁa-zA-Z]+)$'
    match = re.match(pattern, current_data['location'])
    if ', ' not in current_data['location']:
            await update.message.reply_text("Введите корректное название, соответствующее форматированию.")
            return 3
    else:
        gmt_offset = get_gmt_offset(current_data['location'])[0]
        if gmt_offset == "City not found":
            await update.message.reply_text("Мне не удалось найти ваш город. Пожалуйста, попробуйте ввести более узнаваемый город поблизости.")
            return 3
        current_data['timezone'] = gmt_offset
        current_data['user_id'] = update.message.chat.id
        cursor.execute("""UPDATE Users SET location=?, timezone=? WHERE id=?""",
                            (current_data['location'], current_data['timezone'], current_data['user_id']))
        conn.commit()
        keyboard = [
        [InlineKeyboardButton("Общее описание", callback_data="1"), InlineKeyboardButton("Температура", callback_data="2")],
        [InlineKeyboardButton("Ветер", callback_data="3"), InlineKeyboardButton("Осадки", callback_data="4")],
        [InlineKeyboardButton("Облака", callback_data="5"), InlineKeyboardButton("Снег", callback_data="6")],
        [InlineKeyboardButton("Давление", callback_data="7"), InlineKeyboardButton("Влажность", callback_data="8")],
        [InlineKeyboardButton("Видимость", callback_data="9"), InlineKeyboardButton("Солнечная радиация", callback_data="10")],
        [InlineKeyboardButton("Всё вышеперечисленное", callback_data="all")],
        [InlineKeyboardButton("Готово", callback_data="done")]
    ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Каковы ваши предпочтения о показываемых данных о погоде?", reply_markup=reply_markup)
        return 4

    
async def get_w_preferences(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    output =''
    global current_w_preferences_list

    if data == "all":
        for j in range(10):
            current_w_preferences_list[j] = '1'
    elif data =="done":
        for j in range(10):
            if current_w_preferences_list[j] == '1':
                output += W_METRICS[j]+'\n'
        
        current_data['user_id'] = query.message.chat.id
        await query.edit_message_text(f"Ваши предпочтения о погоде:\n{output}")
        current_data['w_preferences'] = ' '.join(current_w_preferences_list)
        cursor.execute("""UPDATE Users SET w_preferences=? WHERE id=?""",
                            (current_data['w_preferences'], current_data['user_id']))
        conn.commit()

        await context.bot.send_message(context._chat_id,"Когда вы хотите получать оповещения? Я буду писать вам каждый день, поэтому выберите "
                                "время для сообщений (часовой пояс будет тот, который действует в вашей выбранной локации). Введите свой ответ в формате 'одно время в 24-часовой системе "
                                "с двоеточием', например '09:30'."
                                        )
        current_data['w_preferences'] = ''
        
        current_w_preferences_list = ['0'] * 10
        return 5
    else:
        current_w_preferences_list[int(data) - 1] = '1'


async def get_a_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    current_data['a_schedule'] = update.message.text
    if not ((len(current_data['a_schedule']) == 5) and (current_data['a_schedule'][2] == ':') and ('0' <= current_data['a_schedule'][0] <= '9') and ('0' <= current_data['a_schedule'][1] <= '9') and ('0' <= current_data['a_schedule'][3] <= '9') and ('0' <= current_data['a_schedule'][4] <= '9') and ('00' <= current_data['a_schedule'][:2] <= '24') and ('00' <= current_data['a_schedule'][3:] <= '59')):
        await update.message.reply_text("Пожалуйста, введите время в соответствии с инструкциями. Часы - это 00-24, посередине ставится двоеточие (:), а минуты - 00-59. "
                                        "Другой пример: '11:05'. Попробуйте еще раз!")
        return 5
    current_data['gmt_schedule'] = local_to_gmt(current_data['a_schedule'], current_data['timezone'])
    current_data['user_id'] = update.message.chat_id
    
    cursor.execute("""UPDATE Users SET gmt_schedule=? WHERE id=?""",
                        (current_data['gmt_schedule'], current_data['user_id']))
    conn.commit()
    
    # Setting the daily alert function
    context.job_queue.run_daily(daily_alert, time(hour=int(current_data['gmt_schedule'][:2]), minute=int(current_data['gmt_schedule'][3:])), chat_id=current_data['user_id'])
    
    await update.message.reply_text("Спасибо, что предоставили мне всю необходимую информацию. Я обязательно оповещу вас!\n\n"
                                    "Тем временем вы можете изменить свою информацию для меня, нажав на кнопку меню и далее нужную команду "
                                    "(например, если вы путешествуете, вы можете изменить местоположение). А также, вы можете посмотреть и введенные данные я использую для работы.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Действие отменено.')
    try:
        del context.user_data['asked']
        return ConversationHandler.END
    except Exception as e:
        return ConversationHandler.END

# Keyboard for giving consent
# reply_keyboard1 = [['Да!', 'Нет...']]
# markup1 = ReplyKeyboardMarkup(reply_keyboard1, one_time_keyboard=False)


# async def update_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     # Check if the user is responding to the question
#     if 'asked' not in context.user_data:
#         context.user_data['asked'] = True
#         await update.message.reply_text("Каким будет ваше новое имя?", reply_markup=markup3)
#         return 1
#     else:
#         # Handle the user's response
#         current_data['name'] = update.message.text
#         if '/' in update.message.text and update.message.text != '/cancel':
#             await update.message.reply_text("Введите корректное имя.")
#             return 1
#         elif update.message.text == '/cancel':
#             await update.message.reply_text("Действие отменено.", reply_markup=ReplyKeyboardRemove())
#             del context.user_data['asked']
#             return ConversationHandler.END
#         else:
#             cursor.execute("""UPDATE Users SET name=? WHERE id=?""",
#                         (current_data['name'], current_data['user_id']))
#             conn.commit()
#             await update.message.reply_text(f"Здравствуйте, {current_data['name']}!", reply_markup=ReplyKeyboardRemove())
#             del context.user_data['asked']
#             return ConversationHandler.END


async def update_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'asked' not in context.user_data:
        context.user_data['asked'] = True
        await update.message.reply_text("По какой новой локации вы будете получать уведомления? Пожалуйста, укажите ближайший узнаваемый город. (Например, 'Минск, Беларусь')", reply_markup=markup3)
        return 1
    else:
        current_data['location'] = update.message.text
        pattern = r'^([а-яА-ЯёЁa-zA-Z]+),\s*([а-яА-ЯёЁa-zA-Z]+)$'
    
    # Проверка сообщения по регулярному выражению
        match = re.match(pattern, current_data['location'])
        if ', ' not in current_data['location']:
            if '/' in update.message.text and update.message.text!= '/cancel':
                await update.message.reply_text("Введите корректное название, соответствующее форматированию.")
                return 1
            elif update.message.text == '/cancel':
                await update.message.reply_text("Действие отменено.", reply_markup=ReplyKeyboardRemove())
                del context.user_data['asked']
                return ConversationHandler.END
        else:
            
            gmt_offset = get_gmt_offset(current_data['location'])[0]
            if gmt_offset == "City not found":
                await update.message.reply_text("Мне не удалось найти ваш город. Пожалуйста, попробуйте ввести более узнаваемый город поблизости в том же формате (город, страна).")
                return 1
            current_data['timezone'] = gmt_offset
            cursor.execute("""UPDATE Users SET location=?, timezone=? WHERE id=?""",
                            (current_data['location'], current_data['timezone'], current_data['user_id']))
            conn.commit()
            await update.message.reply_text(f"Теперь ваше местоположение установлено на {current_data['location']}!", reply_markup=ReplyKeyboardRemove())
            del context.user_data['asked']
            return ConversationHandler.END

async def get_w_preferences2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    global current_w_preferences_list
    current_data = {
    'user_id': None,
    'name': '',
    'location': '',
    'w_preferences': '',
    'timezone': '',
    'a_schedule': '',
    'gmt_schedule': ''
    }
    
    output =''
    if data == "all":
        for j in range(10):
            current_w_preferences_list[j] = '1'
    elif data =="done":
        for j in range(10):
            if current_w_preferences_list[j] == '1':
                output += W_METRICS[j]+'\n'
         
        
        current_data['user_id'] = query.message.chat.id
        current_data['w_preferences'] = ' '.join(current_w_preferences_list)
        cursor.execute("SELECT id FROM Users WHERE id=?", (current_data['user_id'],))
        cursor.execute("""UPDATE Users SET w_preferences=? WHERE id=?""",
                        (current_data['w_preferences'], current_data['user_id']))
        conn.commit()
        
        await query.edit_message_text('Предпочтения по погоде успешно изменены!')
        #global current_w_preferences_list
        
        current_data['w_preferences'] = ''
        await context.bot.send_message(current_data['user_id'],f"Вы выбрали:\n{output}")
        current_w_preferences_list = ['0'] * 10
        return ConversationHandler.END
    
    else:
        current_w_preferences_list[int(data) - 1] = '1'

async def update_w_preferences(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ('/' in update.message.text) and (update.message.text != '/cancel' and update.message.text !='/update_preferences'):
        await update.message.reply_text("Пожалуйста, не вводите другие комманды"
                                    )
        return 1
    elif update.message.text == '/cancel':
        await update.message.reply_text("Действие отменено.")
        return ConversationHandler.END
    elif update.message.text == '/update_preferences':
        keyboard = [
        [InlineKeyboardButton("Общее описание", callback_data="1"), InlineKeyboardButton("Температура", callback_data="2")],
        [InlineKeyboardButton("Ветер", callback_data="3"), InlineKeyboardButton("Осадки", callback_data="4")],
        [InlineKeyboardButton("Облака", callback_data="5"), InlineKeyboardButton("Снег", callback_data="6")],
        [InlineKeyboardButton("Давление", callback_data="7"), InlineKeyboardButton("Влажность", callback_data="8")],
        [InlineKeyboardButton("Видимость", callback_data="9"), InlineKeyboardButton("Солнечная радиация", callback_data="10")],
        [InlineKeyboardButton("Всё вышеперечисленное", callback_data="all")],
        [InlineKeyboardButton("Готово", callback_data="done")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Каковы ваши предпочтения о показываемых данных о погоде?", reply_markup=reply_markup)
        return 2

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pref ='\n'
    location = cursor.execute("SELECT location FROM Users WHERE id=?", (context._chat_id,)).fetchone()[0]
    pref1 = cursor.execute("SELECT w_preferences FROM Users WHERE id=?", (context._chat_id,)).fetchone()[0].split()
    for j in range(10):
        if pref1[j] == '1':
            pref += W_METRICS[j]+'\n'
    time = cursor.execute("SELECT gmt_schedule FROM Users WHERE id=?", (context._chat_id,)).fetchone()[0]
    name = cursor.execute("SELECT name FROM Users WHERE id=?", (context._chat_id,)).fetchone()[0]
    timezone = cursor.execute("SELECT timezone FROM Users WHERE id=?", (context._chat_id,)).fetchone()[0]
    await context.bot.send_message(context._chat_id, f"Ваши данные:\nИмя: {name}\nГород: {location}\nПредпочтения по погоде: {pref}\nВремя оповещений: {gmt_to_local(time, timezone)}\n")
    
async def update_a_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'asked' not in context.user_data:
        context.user_data['asked'] = True
        await context.bot.send_message(context._chat_id,"Когда вы хотите получать оповещения? Я буду писать вам каждый день, поэтому выберите "
                                "время для сообщений (часовой пояс будет тот, который действует в вашей выбранной локации). Введите свой ответ в формате 'одно время в 24-часовой системе "
                                "с двоеточием', например '09:30'.", reply_markup=markup3)
        return 1
    else:
        current_data['user_id'] = update.message.chat.id
        current_data['a_schedule'] = update.message.text
        if not ((len(current_data['a_schedule']) == 5) and (current_data['a_schedule'][2] == ':') and ('0' <= current_data['a_schedule'][0] <= '9') and ('0' <= current_data['a_schedule'][1] <= '9') and ('0' <= current_data['a_schedule'][3] <= '9') and ('0' <= current_data['a_schedule'][4] <= '9') and ('00' <= current_data['a_schedule'][:2] <= '24') and ('00' <= current_data['a_schedule'][3:] <= '59')):
            if update.message.text == '/cancel':
                await update.message.reply_text("Действие отменено.", reply_markup=ReplyKeyboardRemove())
                del context.user_data['asked']
                return ConversationHandler.END
            else:
                await update.message.reply_text("Пожалуйста, введите время в соответствии с инструкциями. Часы - это 00-24, посередине ставится двоеточие (:), а минуты - 00-60. "
                                            "Другой пример: '11:45'. Попробуйте еще раз!")
                return 1
        else:
            timezone = cursor.execute("SELECT timezone FROM Users WHERE id=?",(current_data['user_id'],)).fetchone()[0]
            current_gmt_schedule = local_to_gmt(current_data['a_schedule'], timezone)
            cursor.execute("""UPDATE Users SET gmt_schedule=? WHERE id=?""",
                            (current_gmt_schedule, current_data['user_id']))
            conn.commit()
            # Setting the daily alert function\
            for job in context.job_queue.jobs():
                if job.chat_id == current_data['user_id']:
                    job.schedule_removal()
            
            context.job_queue.run_daily(daily_alert, time(hour=int(current_gmt_schedule[:2]), minute=int(current_gmt_schedule[3:])), chat_id=current_data['user_id'])
            
            await update.message.reply_text(f"Теперь ваше время оповещений установлено на {current_data['a_schedule'].strip()}!", reply_markup=ReplyKeyboardRemove())
            del context.user_data['asked']
            return ConversationHandler.END

# Keyboard for updating name, location, preferences, and schedule
# reply_keyboard2 = [['/update_preferences', '/update_location'],
#                   ['/update_schedule', '/update_name'],
#                   ['/profile'],]
# markup2 = ReplyKeyboardMarkup(reply_keyboard2, one_time_keyboard=False)

# TELEGRAM BOT CODE END
reply_keyboard3 = [['/cancel'],]
markup3 = ReplyKeyboardMarkup(reply_keyboard3, one_time_keyboard=True)



# WEATHER EXTRACTION FUNCTION
def fetch_weather(current_location, current_w_preferences, current_name):
    lat, lng, timezone = get_gmt_offset(current_location)[1:]
    api_key = open('Weather_key.txt', 'r').read()
    now = datetime.now(timezone)
    today_str = now.strftime("%Y-%m-%d")
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lng}/{today_str}?key={api_key}&unitGroup=metric&include=days,alerts"
    response = requests.get(url)
    data = response.json()
    current_w_preferences_list = current_w_preferences.split()
    personalised_data = f'Здравствуйте, {current_name}! Информация о прогнозе погоды в локации {current_location} сегодня ({today_str})!\n' +  ' \n'
    # Adding the alert
    if len(data['alerts']) > 0:
        personalised_data += 'Предупреждения от правительства: '
        for elem in data['alerts']:
            personalised_data += f"'{elem['event']}'. "
    else:
        personalised_data += "На сегодня нет официальных предупреждений. "
    if data['days'][0]['severerisk'] < 30:
        level = 'низкий'
    elif 30 <= data['days'][0]['severerisk'] <= 70:
        level = 'умеренный'
    else:
        level = 'высокий'
    personalised_data += f'Также, существует {level} уровень риска конвективных бурь (например, гроз, града и торнадо).\n' + ' \n'
    # Adding other metrics
    if current_w_preferences_list[0] == '1':
        personalised_data += 'Описание: ' + translate_to_russian(data['days'][0]['description']) + '\n'
    if current_w_preferences_list[1] == '1':
        personalised_data += f"Температура: Максимум {data['days'][0]['tempmax']}°C, Минимум {data['days'][0]['tempmin']}°C, Средняя {data['days'][0]['temp']}°C, и Точка росы {data['days'][0]['dew']}°C.\n"
    if current_w_preferences_list[2] == '1':
        personalised_data += f"Вете: Порыв ветра {data['days'][0]['windgust']}км/ч, Средняя скорость ветра {data['days'][0]['windspeed']}км/ч.\n"
    if current_w_preferences_list[3] == '1':
        personalised_data += f"Осадки: Жидкие Осадки {data['days'][0]['precip']}мм, Вероятность {data['days'][0]['precipprob']}%, Ненулевые осадки для {data['days'][0]['precipcover']} часов, и "
        if data['days'][0]['preciptype'] == None:
            personalised_data += "никаких осадков"
        elif len(data['days'][0]['preciptype']) == 1:
            personalised_data += f"Тип Осадков {translate_to_russian(data['days'][0]['preciptype'][0])}"
        elif len(data['days'][0]['preciptype']) == 2:
            personalised_data += f"Виды Осадков {translate_to_russian(data['days'][0]['preciptype'][0])} и {translate_to_russian(data['days'][0]['preciptype'][1])}"
        else:
            personalised_data += 'Виды Осадков '
            for i in range(len(data['days'][0]['preciptype']) - 1):
                personalised_data += data['days'][0]['preciptype'][i] + ', '
            personalised_data += 'и ' + data['days'][0]['preciptype'][-1]
        personalised_data += '.\n'
    if current_w_preferences_list[4] == '1':
        personalised_data += f"Облака: Небо будет покрыто на {data['days'][0]['cloudcover']}%.\n"
    if current_w_preferences_list[5] == '1':
        if data['days'][0]['snow'] == 0:
            personalised_data += f"Снег: Сегодня снега нет. Глубина снежного покрова {data['days'][0]['snowdepth']}см.\n"
        else:
            personalised_data += f"Снег: {data['days'][0]['snow']}см выпадет, и глубина снежного покрова {data['days'][0]['snowdepth']}см.\n"
    if current_w_preferences_list[6] == '1':
        personalised_data += f"Давление: {data['days'][0]['pressure']}ГПа.\n"
    if current_w_preferences_list[7] == '1':
        personalised_data += f"Влажность: {data['days'][0]['humidity']}%.\n"
    if current_w_preferences_list[8] == '1':
        personalised_data += f"Видимость: {data['days'][0]['visibility']}км.\n"
    if current_w_preferences_list[9] == '1':
        personalised_data += f"Солнечная радиация: Полная энергия солнца за день составит {data['days'][0]['solarenergy']}МДж/м^2. Максимальный УФ-индекс составит {data['days'][0]['uvindex']}.\n"
    personalised_data += ' \n' + 'Берегите себя. Увидимся завтра!'
    return personalised_data

# DAILY NOTIFICATION FUNCTION
async def daily_alert(context: ContextTypes.DEFAULT_TYPE) -> None:
    location =cursor.execute("SELECT location FROM Users WHERE id =?", (context._chat_id,)).fetchone()[0]
    w_preferences = cursor.execute("SELECT w_preferences FROM Users WHERE id =?", (context._chat_id,)).fetchone()[0]
    name =cursor.execute("SELECT name FROM Users WHERE id =?", (context._chat_id,)).fetchone()[0]
    await context.bot.send_message(context._chat_id, text=fetch_weather(location, w_preferences, name))

# MAIN FUNCTION THAT EXECUTES EVERYTHING
def main():
    # Initializing
    TOKEN = open('Token_bot.txt', 'r').read()
    
    application = Application.builder().token(TOKEN).build()
    
    # Handler for the initial information-gathering conversation
    conv_handler0 = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_consent)],
            2: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            3: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_location)],
            4: [CallbackQueryHandler(get_w_preferences, pattern="^[1-9]|all|done")],
            5: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_a_schedule)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(conv_handler0)
    
    # Handler for updating the name
    # conv_handler1 = ConversationHandler(
    #         entry_points=[CommandHandler('update_name', update_name)],
    #         states={
    #             1: [MessageHandler(filters.TEXT, update_name)],
    #         },
    #         fallbacks=[CommandHandler('cancel', cancel)]
    #     )
    # Handler for updating the location
    conv_handler2 = ConversationHandler(
            entry_points=[CommandHandler('update_location', update_location)],
            states={
                1: [MessageHandler(filters.TEXT, update_location)],
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
    # Handler for updating the preferences
    conv_handler3 = ConversationHandler(
            entry_points=[CommandHandler('update_preferences', update_w_preferences)],
            states={
                1: [MessageHandler(filters.TEXT, update_w_preferences,)],
                2: [CallbackQueryHandler(get_w_preferences2, pattern="^[1-9]|all|done")],
                
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
    # Handler for updating the schedule
    conv_handler4 = ConversationHandler(
            entry_points=[CommandHandler('update_schedule', update_a_schedule)],
            states={
                1: [MessageHandler(filters.TEXT, update_a_schedule)],
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        
    application.add_handler(CommandHandler('profile', profile))
    
      # Adding the handler to the bot
  #  application.add_handler(conv_handler1)
    application.add_handler(conv_handler2)
    application.add_handler(conv_handler3)
    application.add_handler(conv_handler4)
    
    # START POOLING THE BOT
    application.run_polling()


if __name__ == '__main__':
    main()