import os
import sys
import re
import asyncio
import logging
import subprocess
from datetime import datetime
from typing import Dict, List, Optional

# -------------------- مرحله 2: بررسی کتابخانه‌های مورد نیاز -------------------- #
REQUIRED_LIBRARIES = {
    'python-telegram-bot': 'telegram',
    'instagrapi': 'instagrapi',
    'Pillow': 'PIL',
    'python-dotenv': 'dotenv',
    'moviepy': 'moviepy',
    'python-magic': 'magic'
}

def check_and_install_dependencies():
    missing = []
    for pkg, imp in REQUIRED_LIBRARIES.items():
        try:
            __import__(imp)
            logging.info(f"کتابخانه {pkg} نصب شده است.")
        except ImportError:
            missing.append(pkg.split('==')[0])
    if missing:
        logging.info(f"در حال نصب کتابخانه‌های غایب: {', '.join(missing)}")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', *missing])

# -------------------- مرحله 3: مدیریت پوشه دانلود -------------------- #
def prepare_downloads_folder() -> str:
    downloads_path = os.path.join(os.getcwd(), 'downloads')
    if not os.path.exists(downloads_path):
        os.makedirs(downloads_path)
        logging.info("پوشه دانلود ساخته شد.")
    else:
        # پاکسازی پوشه دانلود
        for f in os.listdir(downloads_path):
            file_path = os.path.join(downloads_path, f)
            try:
                os.remove(file_path)
                logging.info(f"فایل حذف شد: {file_path}")
            except Exception as e:
                logging.error(f"خطا در حذف فایل {file_path}: {e}")
    return downloads_path

# -------------------- مرحله 4: خواندن فایل .env -------------------- #
def load_env_variables():
    from dotenv import load_dotenv
    load_dotenv()
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    INSTAGRAM_USER = os.getenv("INSTAGRAM_USER")
    INSTAGRAM_PASS = os.getenv("INSTAGRAM_PASS")
    return TELEGRAM_TOKEN, INSTAGRAM_USER, INSTAGRAM_PASS

# -------------------- مرحله 6: مدیریت اتصال به اینستاگرام -------------------- #
from instagrapi import Client
from instagrapi.exceptions import TwoFactorRequired, ChallengeRequired

class InstagramManager:
    def __init__(self, username: str, password: str, session_file: str = "ig_session.json"):
        self.client = Client()
        self.username = username
        self.password = password
        self.session_file = session_file

    def login(self, code_2fa: str = None) -> tuple:
        try:
            if self.load_session():
                return True, "ورود با سشن موجود انجام شد."
            login_args = {
                "username": self.username,
                "password": self.password,
                "verification_code": code_2fa
            }
            if self.client.login(**{k: v for k, v in login_args.items() if v}):
                self.save_session()
                return True, "اتصال موفق"
            return False, "اتصال ناموفق"
        except TwoFactorRequired:
            return False, "به کد 2FA نیاز است"
        except ChallengeRequired as e:
            return False, f"کد تأیید هویت مورد نیاز است: {str(e)}"
        except Exception as e:
            logging.error(f"خطای اتصال به اینستاگرام: {str(e)}")
            return False, f"خطای سیستم: {str(e)}"

    def load_session(self) -> bool:
        if os.path.exists(self.session_file):
            try:
                self.client.load_settings(self.session_file)
                self.client.get_timeline_feed()  # تست سشن
                return True
            except Exception:
                return False
        return False

    def save_session(self):
        self.client.dump_settings(self.session_file)

# -------------------- مرحله 10: تشخیص نوع فایل -------------------- #
import magic

class FileValidator:
    @staticmethod
    def validate(file_path: str) -> str:
        mime = magic.from_file(file_path, mime=True)
        ext = os.path.splitext(file_path)[1].lower()
        image_extensions = ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']
        video_extensions = ['.mp4', '.avi', '.flv', '.webm', '.mov', '.mkv', '.wmv']
        if ext in image_extensions or mime.startswith('image/'):
            if ext == '.gif' or mime == 'image/gif':
                return 'animation'
            return 'image'
        if ext in video_extensions or mime.startswith('video/'):
            return 'video'
        raise ValueError("فرمت نامعتبر است")

# -------------------- مرحله 11: پردازش عکس با استفاده از Pillow -------------------- #
from PIL import Image

class ImageProcessor:
    @staticmethod
    def process(file_path: str) -> str:
        with Image.open(file_path) as img:
            width, height = img.size
            scale = 1080 / max(width, height)
            new_size = (int(width * scale), int(height * scale))
            resized = img.resize(new_size, Image.Resampling.LANCZOS)
            background = Image.new('RGB', (1080, 1080), (0, 0, 0))
            position = ((1080 - new_size[0]) // 2, (1080 - new_size[1]) // 2)
            background.paste(resized, position)
            output_path = f"{os.path.splitext(file_path)[0]}_processed.jpg"
            background.save(output_path, quality=100, optimize=True)
            logging.info(f"عکس پردازش شد: {output_path}")
            return output_path

# -------------------- مرحله 12: پردازش ویدئو با استفاده از moviepy -------------------- #
import moviepy.editor as mp

class VideoProcessor:
    MAX_DURATION = 60  # ثانیه

    @classmethod
    def process(cls, file_path: str) -> str:
        with mp.VideoFileClip(file_path) as clip:
            if clip.duration > cls.MAX_DURATION:
                raise ValueError(f"زمان ویدئو بیش از {cls.MAX_DURATION} ثانیه")
            if clip.w >= clip.h:
                target_size = (1280, 720)  # افقی
            else:
                target_size = (720, 1280)  # عمودی
            scale = min(target_size[0] / clip.w, target_size[1] / clip.h)
            new_size = (int(clip.w * scale), int(clip.h * scale))
            background = mp.ColorClip(size=target_size, color=(0, 0, 0), duration=clip.duration)
            final_clip = mp.CompositeVideoClip([background, clip.resize(new_size).set_position("center")])
            output_path = f"{os.path.splitext(file_path)[0]}_processed.mp4"
            final_clip.write_videofile(
                output_path,
                codec='libx264',
                preset='slow',
                ffmpeg_params=['-crf', '18'],
                audio_codec='aac' if clip.audio else None,
                threads=8
            )
            logging.info(f"ویدئو پردازش شد: {output_path}")
            return output_path

# -------------------- مرحله 10c: تبدیل GIF به MP4 -------------------- #
class GIFConverter:
    @staticmethod
    def convert(file_path: str) -> str:
        with mp.VideoFileClip(file_path) as clip:
            output_path = f"{os.path.splitext(file_path)[0]}.mp4"
            clip.write_videofile(
                output_path,
                codec='libx264',
                preset='slow',
                ffmpeg_params=['-crf', '18']
            )
            logging.info(f"تبدیل GIF به MP4: {output_path}")
            return output_path

# -------------------- مراحل 5، 7 و 8: راه‌اندازی ربات تلگرام و دریافت فایل‌ها -------------------- #
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputMediaPhoto, InputMediaVideo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes

class MediaBot:
    def __init__(self, token: str, instagram_user: str, instagram_pass: str):
        # مرحله 2 و 3
        check_and_install_dependencies()
        self.downloads_path = prepare_downloads_folder()
        # مرحله 6: راه‌اندازی اینستاگرام
        self.ig = InstagramManager(instagram_user, instagram_pass)
        # مرحله 5: راه‌اندازی تلگرام
        self.app = Application.builder().token(token).build()
        self.STATES = {
            'AUTH': 0,
            'MEDIA_TYPE': 1,
            'RECEIVE_MEDIA': 2,
            'CONFIRM': 3,
            'CAPTION': 4
        }
        self._setup_handlers()

    def _setup_handlers(self):
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self._handle_start)],
            states={
                self.STATES['AUTH']: [MessageHandler(filters.TEXT, self._handle_2fa)],
                self.STATES['MEDIA_TYPE']: [MessageHandler(filters.TEXT, self._handle_media_type)],
                self.STATES['RECEIVE_MEDIA']: [
                    MessageHandler(filters.PHOTO | filters.VIDEO | filters.ANIMATION, self._handle_media),
                    MessageHandler(filters.TEXT & filters.Regex(r'^🏁 اتمام$'), self._process_media)
                ],
                self.STATES['CONFIRM']: [MessageHandler(filters.TEXT, self._handle_confirmation)],
                self.STATES['CAPTION']: [MessageHandler(filters.TEXT, self._handle_caption)]
            },
            fallbacks=[CommandHandler('cancel', self._cancel)],
            conversation_timeout=24 * 60  # [مرحله 14] 24 دقیقه
        )
        self.app.add_handler(conv_handler)

    # -------------------- مرحله 5: فرمان /start -------------------- #
    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("🔄 در حال اتصال...")
        success, msg = self.ig.login()
        if success:
            await update.message.reply_text("🌼🌸🌺🥰 خوش آمدید 🥰🌺🌸🌼 \n\n ✅ اتصال به اینستاگرام موفق بود")
            await self._send_welcome(update)
            return self.STATES['MEDIA_TYPE']
        if "2FA" in msg:
            await update.message.reply_text("🔐 کد 2FA را وارد کنید:")
            return self.STATES['AUTH']
        await update.message.reply_text(f"❌ خطا: {msg}")
        return ConversationHandler.END

    # -------------------- مرحله 7: ارسال پیام خوشامدگویی -------------------- #
    async def _send_welcome(self, update: Update):
        await update.message.reply_text(
            "🤖 نوع ارسال را انتخاب کنید:",
            reply_markup=ReplyKeyboardMarkup([["📤 آلبوم", "📎 تکی"]], resize_keyboard=True)
        )

    # -------------------- مرحله 6d: دریافت کد 2FA -------------------- #
    async def _handle_2fa(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        code = update.message.text.strip()
        if not re.match(r'^\d{6}$', code):
            await update.message.reply_text("❌ فرمت کد نامعتبر! لطفا کد 6 رقمی وارد کنید:")
            return self.STATES['AUTH']
        success, msg = self.ig.login(code_2fa=code)
        if success:
            await update.message.reply_text("🌼🌸🌺🥰 خوش آمدید 🥰🌺🌸🌼 \n\n ✅ اتصال به اینستاگرام موفق بود")
            await self._send_welcome(update)
            return self.STATES['MEDIA_TYPE']
        await update.message.reply_text(f"❌ خطا: {msg}")
        return self.STATES['AUTH']

    # -------------------- مرحله 8: انتخاب نوع ارسال فایل -------------------- #
    async def _handle_media_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        choice = update.message.text.strip()
        context.user_data['mode'] = 'album' if choice == "📤 آلبوم" else 'single'
        instruction = "📤 لطفا حداکثر 10 فایل ارسال کنید" if context.user_data['mode'] == 'album' else "📎 لطفا یک فایل ارسال کنید"
        await update.message.reply_text(instruction, reply_markup=ReplyKeyboardRemove())
        return self.STATES['RECEIVE_MEDIA']

    # -------------------- مرحله 9: دانلود فایل(ها) -------------------- #
    async def _handle_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        # پاکسازی پوشه دانلود تنها در ابتدای دریافت آلبوم (زمانی که فایل قبلی وجود ندارد)
        if 'files' not in context.user_data or not context.user_data['files']:
            prepare_downloads_folder()
            context.user_data['files'] = []
        file_path = await self._download_media(update)
        if not file_path:
            return self.STATES['RECEIVE_MEDIA']
        
        mode = context.user_data.get('mode', 'single')
        if mode == 'album':
            # شماره‌گذاری فایل‌ها در حالت آلبوم
            album_index = len(context.user_data.get('files', [])) + 1
            ext = os.path.splitext(file_path)[1]
            new_name = f"album_{album_index:02d}{ext}"
            new_path = os.path.join(self.downloads_path, new_name)
            os.rename(file_path, new_path)
            file_path = new_path

        context.user_data['files'].append(file_path)
        max_files = 10 if mode == 'album' else 1
        if len(context.user_data['files']) >= max_files:
            return await self._process_media(update, context)
        remaining = max_files - len(context.user_data['files'])
        await update.message.reply_text(
            f"✅ فایل دریافت شد. باقی مانده: {remaining}",
            reply_markup=ReplyKeyboardMarkup([["🏁 اتمام"]], resize_keyboard=True)
        )
        return self.STATES['RECEIVE_MEDIA']

    async def _download_media(self, update: Update) -> Optional[str]:
        try:
            if update.message.photo:
                media = update.message.photo[-1]
                ext = '.jpg'
            elif update.message.video:
                media = update.message.video
                ext = '.mp4'
            elif update.message.animation:
                media = update.message.animation
                ext = '.gif'
            else:
                await update.message.reply_text("⚠️ فرمت فایل معتبر نیست!")
                return None
            file = await media.get_file()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{file.file_id[:8]}{ext}"
            file_path = os.path.join(self.downloads_path, filename)
            await file.download_to_drive(file_path)
            logging.info(f"فایل دانلود شد: {file_path}")
            return file_path
        except Exception as e:
            logging.error(f"خطا در دانلود فایل: {str(e)}")
            await update.message.reply_text("⚠️ خطا در دریافت فایل!")
            return None

    # -------------------- مراحل 10 تا 12: پردازش فایل‌های دریافت شده -------------------- #
    async def _process_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        processed_files = []
        for file_path in context.user_data.get('files', []):
            try:
                file_type = FileValidator.validate(file_path)
                if file_type == 'animation':
                    # تبدیل GIF به MP4 و سپس پردازش به عنوان ویدئو
                    converted_path = await asyncio.to_thread(GIFConverter.convert, file_path)
                    processed = await asyncio.to_thread(VideoProcessor.process, converted_path)
                elif file_type == 'image':
                    processed = await asyncio.to_thread(ImageProcessor.process, file_path)
                elif file_type == 'video':
                    processed = await asyncio.to_thread(VideoProcessor.process, file_path)
                else:
                    raise ValueError("نوع فایل پشتیبانی نمی‌شود")
                processed_files.append(processed)
            except Exception as e:
                logging.error(f"خطا در پردازش فایل: {str(e)}")
                await update.message.reply_text(f"❌ خطا در پردازش فایل: {str(e)}")
                continue
        if not processed_files:
            await update.message.reply_text("⚠️ هیچ فایل معتبری پردازش نشد!")
            await self._send_welcome(update)
            return self.STATES['MEDIA_TYPE']
        context.user_data['processed'] = processed_files
        return await self._send_previews(update, processed_files)

    # -------------------- مراحل 11g و 12g: ارسال پیش‌نمایش فایل‌ها برای تایید -------------------- #
    async def _send_previews(self, update: Update, files: List[str]) -> int:
        media_group = []
        for file in files:
            try:
                if file.endswith('.jpg'):
                    media_group.append(InputMediaPhoto(open(file, 'rb')))
                else:
                    media_group.append(InputMediaVideo(open(file, 'rb')))
            except Exception as e:
                logging.error(f"خطا در باز کردن فایل {file}: {str(e)}")
        await update.message.reply_media_group(media=media_group)
        await update.message.reply_text(
            "آیا می‌خواهید ادامه دهید؟",
            reply_markup=ReplyKeyboardMarkup([["✅ تایید", "❌ لغو"]], resize_keyboard=True)
        )
        return self.STATES['CONFIRM']

    # -------------------- مراحل 11g و 12g: دریافت تایید کاربر -------------------- #
    async def _handle_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if update.message.text.strip() == "✅ تایید":
            await update.message.reply_text("📝 لطفا کپشن را وارد کنید:",
                                            reply_markup=ReplyKeyboardRemove())
            return self.STATES['CAPTION']
        else:
            prepare_downloads_folder()
            context.user_data.clear()
            await update.message.reply_text("♻️ عملیات ریست شد!")
            await self._send_welcome(update)
            return self.STATES['MEDIA_TYPE']

    # -------------------- مرحله 13: آپلود فایل(ها) به اینستاگرام -------------------- #
    async def _handle_caption(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        caption = update.message.text.strip()
        try:
            for file in context.user_data.get('processed', []):
                if file.endswith('.jpg'):
                    self.ig.client.photo_upload(file, caption=caption)
                else:
                    self.ig.client.video_upload(file, caption=caption)
            await update.message.reply_text("✅ آپلود موفقیت‌آمیز در اینستاگرام!")
            prepare_downloads_folder()
            await self._send_welcome(update)
            return self.STATES['MEDIA_TYPE']
        except Exception as e:
            logging.error(f"خطا در آپلود: {str(e)}")
            await update.message.reply_text(f"❌ خطا در آپلود: {str(e)}")
            return ConversationHandler.END

    # -------------------- لغو عملیات -------------------- #
    async def _cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        prepare_downloads_folder()
        context.user_data.clear()
        await update.message.reply_text("عملیات لغو شد!", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

# -------------------- مرحله 1: شروع عملکرد ربات -------------------- #
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()  # رفع مشکلات احتمالی event loop

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler('bot.log', encoding='utf-8'),
                  logging.StreamHandler()]
    )

    TELEGRAM_TOKEN, INSTAGRAM_USER, INSTAGRAM_PASS = load_env_variables()
    if not TELEGRAM_TOKEN or not INSTAGRAM_USER or not INSTAGRAM_PASS:
        logging.error("متغیرهای محیطی تنظیم نشده‌اند. لطفاً فایل .env را بررسی کنید.")
        sys.exit("متغیرهای محیطی ناقص هستند.")

    bot = MediaBot(TELEGRAM_TOKEN, INSTAGRAM_USER, INSTAGRAM_PASS)
    try:
        bot.app.run_polling()
    except KeyboardInterrupt:
        print("\nربات متوقف شد!")