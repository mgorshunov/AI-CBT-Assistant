import logging
import os
import subprocess
import time
import requests
from sqlalchemy import create_engine, Column, Integer, JSON, exc, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import random
from datetime import datetime, timezone

# Set up environment variables and constants
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


telegram_token = os.getenv("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

with open('system_prompt.txt', 'r', encoding='utf-8') as file:
    system_prompt = file.read()

with open('start_message.txt', 'r', encoding='utf-8') as file:
    start_message = file.read()

# Word limit constants
MAX_CONVERSATION_WORDS = 500
MAX_USER_INPUT_WORDS = 3000
MAX_SUMMARIZATION_TOKENS = 100
MAX_GROQ_RESPONSE_TOKENS = 100

# Database setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Conversation(Base):
    __tablename__ = 'conversations'
    user_id = Column(Integer, primary_key=True, index=True)
    conversation = Column(JSON, nullable=False)
    created = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_visit = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    message_count = Column(Integer, default=0)  # New column for message count
    audio_message_count = Column(Integer, default=0)  # New column for audio message count

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    except exc.SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()

def save_conversation(db, user_id, conversation, is_audio=False):
    try:
        db_conversation = db.query(Conversation).filter(Conversation.user_id == user_id).first()
        if db_conversation:
            db_conversation.conversation = conversation
            db_conversation.message_count += 1  # Increment total message count
            if is_audio:
                db_conversation.audio_message_count += 1  # Increment audio message count if the message is audio
            db_conversation.last_visit = datetime.now(timezone.utc)
        else:
            db_conversation = Conversation(
                user_id=user_id,
                conversation=conversation,
                created=datetime.now(timezone.utc),
                last_visit=datetime.now(timezone.utc),
                message_count=1,  # Initialize total message count
                audio_message_count=1 if is_audio else 0  # Initialize audio message count
            )
            db.add(db_conversation)
        db.commit()
    except exc.SQLAlchemyError as e:
        logger.error(f"Failed to save conversation: {e}")
        raise


def load_conversation(db, user_id):
    try:
        db_conversation = db.query(Conversation).filter(Conversation.user_id == user_id).first()
        if db_conversation:
            # Ensure system prompt is the first message in the conversation history
            if db_conversation.conversation[0]['role'] != 'system':
                db_conversation.conversation.insert(0, {"role": "system", "content": system_prompt})
            return db_conversation
        else:
            return None
    except exc.SQLAlchemyError as e:
        logger.error(f"Failed to load conversation: {e}")
        raise

def clear_conversation(db, user_id):
    try:
        db_conversation = db.query(Conversation).filter(Conversation.user_id == user_id).first()
        if db_conversation:
            db.delete(db_conversation)
            db.commit()
    except exc.SQLAlchemyError as e:
        logger.error(f"Failed to clear conversation: {e}")
        raise

def calculate_total_words(messages):
    return sum(len(message['content'].split()) for message in messages)

def summarize_messages(messages):
    concatenated_messages = " ".join(message['content'] for message in messages)
    summarization_prompt = f"Summarize the following conversation to get the main idea: {concatenated_messages}"
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_API_KEY}"}
    data = {"messages": [{"role": "system", "content": summarization_prompt}], "model": "llama3-70b-8192", "temperature": 0.0, "max_tokens": MAX_SUMMARIZATION_TOKENS, "top_p": 1, "stream": False}

    try:
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        completion = response.json()
        summarized_content = completion['choices'][0]['message']['content']
        logger.info("Summarized content: %s", summarized_content)
        return summarized_content
    except Exception as e:
        logger.error(f"Error while summarizing messages: {e}")
        raise Exception("An unexpected error occurred while summarizing the conversation. Probably, the server is too busy. Please wait a bit before continuing.")

def trim_conversation_history(conversation_history, max_words=MAX_CONVERSATION_WORDS):
    total_words = calculate_total_words(conversation_history)
    if total_words > max_words:
        system_message = conversation_history[0]  # Keep the system prompt
        summarized_content = summarize_messages(conversation_history[1:])  # Summarize user and system responses except the system prompt
        conversation_history = [system_message, {"role": "system", "content": summarized_content}]
    return conversation_history

# Dictionary to store message timestamps
message_timestamps = {}

def check_rate_limit(user_id):
    current_time = time.time()
    if user_id not in message_timestamps:
        message_timestamps[user_id] = []
    
    # Remove timestamps older than 60 seconds
    message_timestamps[user_id] = [timestamp for timestamp in message_timestamps[user_id] if current_time - timestamp < 60]
    
    if len(message_timestamps[user_id]) >= 15:
        return False  # Rate limit exceeded
    else:
        message_timestamps[user_id].append(current_time)
        return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(start_message)
    if 'conversation_history' not in context.user_data:
        context.user_data['conversation_history'] = [{"role": "system", "content": system_prompt}]  # Initialize conversation history with system prompt

def check_message_length(user_input, max_words=MAX_USER_INPUT_WORDS):
    user_input_words = len(user_input.split())
    if user_input_words > max_words:
        return f"Your message is too long. Please limit your message to {max_words} words. Your message had {user_input_words} words."
    return None

def convert_audio_to_supported_format(input_file):
    output_file = input_file.rsplit('.', 1)[0] + '.mp3'
    command = [
        'ffmpeg', '-i', input_file,
        '-ar', '16000', '-ac', '1',
        output_file
    ]
    subprocess.run(command, check=True)
    return output_file

def check_file_size(file_path):
    file_size = os.path.getsize(file_path) / (1024 * 1024)  # Convert to MB
    return file_size <= 25

def transcribe_audio(file_path):
    try:
        # Convert audio to a supported format
        converted_file_path = convert_audio_to_supported_format(file_path)
        
        if not check_file_size(converted_file_path):
            raise Exception("The audio file duration exceeds 13 minute limit.")
        
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
        files = {"file": open(converted_file_path, "rb")}
        data = {"model": "whisper-large-v3", "response_format": "verbose_json"}

        response = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files=files, data=data)
        response.raise_for_status()
        transcription = response.json()
        transcribed_text = transcription['text']
        logger.info("Transcribed text: %s", transcribed_text)
        return transcribed_text
    except subprocess.CalledProcessError as e:
        logger.error(f"Error during audio conversion: {e}")
        raise Exception("An error occurred while converting the audio file.")
    except Exception as e:
        logger.error(f"Error while transcribing audio: {e}")
        raise Exception("An unexpected error occurred while transcribing the audio. Probably, the server is too busy. Please wait a bit before continuing.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    is_audio = False
    if update.message.voice or update.message.audio:
        is_audio = True
        file_id = update.message.voice.file_id if update.message.voice else update.message.audio.file_id
        file = await context.bot.get_file(file_id)
        file_path = f"./{file_id}.oga"
        
        await file.download_to_drive(file_path)
        
        try:
            user_input = transcribe_audio(file_path)
        except Exception as e:
            logger.error(f"Error while transcribing audio: {e}")
            await update.message.reply_text(str(e))
            return
    else:
        user_input = update.message.text

    user_id = update.message.from_user.id
    logger.info("User says: %s", user_input)

    length_warning = check_message_length(user_input)
    if length_warning:
        await update.message.reply_text(length_warning)
        return 

    if not check_rate_limit(user_id):
        await update.message.reply_text("You've sent too many requests in a short period. Please wait a minute before sending another message.")
        return 

    try:
        db = next(get_db())
    except StopIteration:
        await update.message.reply_text("Database connection error. Please try again later.")
        return  

    if 'conversation_history' not in context.user_data:
        db_conversation = load_conversation(db, user_id)
        context.user_data['conversation_history'] = db_conversation.conversation if db_conversation else [{"role": "system", "content": system_prompt}]

    context.user_data['conversation_history'].append({"role": "user", "content": user_input})

    try:
        total_words = calculate_total_words(context.user_data['conversation_history'])
        if total_words > MAX_CONVERSATION_WORDS:
            summarized_content = summarize_messages(context.user_data['conversation_history'][1:])
            context.user_data['conversation_history'] = [
                context.user_data['conversation_history'][0],  # System prompt
                {"role": "system", "content": summarized_content}
            ]
    except Exception as e:
        await update.message.reply_text(str(e))
        return  

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_API_KEY}"}
    data = {"messages": context.user_data['conversation_history'], "model": "llama3-70b-8192", "temperature": 0.7, "max_tokens": MAX_GROQ_RESPONSE_TOKENS, "top_p": 1, "stream": False}

    try:
        logger.info("Sending request to Groq API with data: %s", data)
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        completion = response.json()
        response_text = completion['choices'][0]['message']['content']
        logger.info("Response text: %s", response_text)

        if response_text.strip():
            context.user_data['conversation_history'].append({"role": "system", "content": response_text})
            save_conversation(db, user_id, context.user_data['conversation_history'], is_audio)
            await update.message.reply_text(response_text)
        else:
            logger.error("Received empty response from Groq API")
            await update.message.reply_text("Received an empty response from the server. Please try again.")
    except requests.RequestException as e:
        logger.error(f"Error while handling message: {e}")
        await update.message.reply_text("An error occurred while processing your request. Please try again later.")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    logger.info("User %s reset the conversation.", update.message.from_user.first_name)
    
    try:
        db = next(get_db())
        
        # Load the existing conversation for the user
        db_conversation = load_conversation(db, user_id)
        
        if db_conversation:
            # Reset the conversation field to only include the system prompt
            db_conversation.conversation = [{"role": "system", "content": system_prompt}]
            db.commit()
            logger.info("Reset conversation for user_id: %s", user_id)
        else:
            # Initialize the conversation field if not found
            db_conversation = Conversation(user_id=user_id, conversation=[{"role": "system", "content": system_prompt}])
            db.add(db_conversation)
            db.commit()
            logger.info("Initialized conversation for user_id: %s", user_id)
        
    except StopIteration:
        await update.message.reply_text("Database connection error. Please try again later.")
        return
    except exc.SQLAlchemyError as e:
        logger.error(f"Failed to reset conversation: {e}")
        await update.message.reply_text("Failed to reset your conversation. Please try again later.")
        return
    
    # Clear the user data in the context except for the conversation history with the system prompt
    context.user_data.clear()
    context.user_data['conversation_history'] = [{"role": "system", "content": system_prompt}]
    
    await update.message.reply_text("Your conversation history has been reset. To start a new conversation, just send a message.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if update:
        await update.message.reply_text("An error occurred while processing your request. Please try again later.")

def main():
    application = Application.builder().token(telegram_token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND | filters.VOICE | filters.AUDIO, handle_message))
    application.add_handler(CommandHandler("reset", reset))
    application.add_error_handler(error_handler)
    application.run_polling()

if __name__ == "__main__":
    main()
