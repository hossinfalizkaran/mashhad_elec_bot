import Rubika

# Initialize the bot
bot = Rubika.Bot(token='YOUR_BOT_TOKEN')

@bot.on_message()
def handle_message(message):
    # Respond to user messages automatically
    bot.send_message(chat_id=message.chat_id, text='Automated response: {}'.format(message.text))

@bot.on_command('start')
def start_command(message):
    bot.send_message(chat_id=message.chat_id, text='Welcome to the Rubika Bot!')

@bot.on_command('help')
def help_command(message):
    bot.send_message(chat_id=message.chat_id, text='Available commands: /start, /help, /ping')

@bot.on_command('ping')
def ping_command(message):
    bot.send_message(chat_id=message.chat_id, text='Pong!')

# Start the bot
if __name__ == '__main__':
    bot.run()