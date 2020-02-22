"""
Cathy AI Discord Chat Bot

Written in Python 3 using AIML chat library.
"""
import aiml
import asyncio
from datetime import datetime, timedelta
import discord
import os
import pkg_resources
import random
from discord.ext import commands
import logging
import logging.config
import sqlite3


class ChattyCathy:

    STARTUP_FILE = "std-startup.xml"
    BOT_PREFIX = ('?', '!')
    SQL_SCHEMA = [
        'CREATE TABLE IF NOT EXISTS chat_log (time, server_name, user_id, message, response)',
        'CREATE TABLE IF NOT EXISTS users (id, name, first_seen)',
        'CREATE TABLE IF NOT EXISTS servers (id, name, first_seen)',
    ]

    def __init__(self, channel_name, bot_token, log_file, database):
        """
        Initialize the bot using the Discord token and channel name to chat in.

        :param channel_name: Only chats in this channel. No hashtag included.
        :param bot_token: Full secret bot token
        :param log_file: File for logging details
        :param database: Path for sqlite file to use
        """
        # Store configuration values
        self.channel_name = channel_name
        self.token = bot_token
        self.log_file = log_file
        self.database = database
        self.last_reset_time = datetime.now()

        # Log configuration
        self.logger = logging.getLogger('cathy_logger')
        self.setup_logging()
        self.logger.info("[+] Logging initialized")

        # Setup database
        self.db = sqlite3.connect(self.database)
        self.cursor = self.db.cursor()
        self.setup_database_schema()
        self.logger.info('[+] Database initialized')

        # Load AIML kernel
        self.logger.info("[*] Initializing AIML kernel...")
        self.aiml_kernel = aiml.Kernel()
        self.setup_aiml()
        self.logger.info("[+] Done initializing AIML kernel.")

        # Set up Discord
        self.logger.info("[*] Initializing Discord bot...")
        self.discord_bot = commands.Bot(command_prefix=self.BOT_PREFIX)
        self.setup_discord_events()
        self.logger.info("[+] Done initializing Discord bot.")

    def setup_logging(self):
        self.logger.setLevel(logging.INFO)
        log_file_handler = logging.FileHandler(self.log_file)
        log_file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s %(levelname)s - %(message)s')
        log_file_handler.setFormatter(formatter)
        self.logger.addHandler(log_file_handler)

    def setup_database_schema(self):
        for sql_statement in self.SQL_SCHEMA:
            self.cursor.execute(sql_statement)
        self.db.commit()

    def setup_aiml(self):
        initial_dir = os.getcwd()
        os.chdir(pkg_resources.resource_filename(__name__, ''))  # Change directories to load AIML files properly
        startup_filename = pkg_resources.resource_filename(__name__, self.STARTUP_FILE)
        self.aiml_kernel.setBotPredicate("name", "Cathy")
        self.aiml_kernel.learn(startup_filename)
        self.aiml_kernel.respond("LOAD AIML B")
        os.chdir(initial_dir)

    def setup_discord_events(self):
        """
        This method defines all of the bot command and hook callbacks
        :return:
        """

        @self.discord_bot.command()
        async def reset(ctx):
            """
            Allow users to trigger a cathy reset up to once per hour. This can help when the bot quits responding.
            :return:
            """
            now = datetime.now()
            if datetime.now() - self.last_reset_time > timedelta(hours=1):
                self.last_reset_time = now
                await ctx.send('Resetting my brain...')
                self.aiml_kernel.resetBrain()
                self.setup_aiml()
            else:
                await ctx.send(f'Sorry, I can only reset once per hour and I was last reset on {self.last_reset_time} UTC')

        @self.discord_bot.event
        async def on_ready():
            print("Bot Online!")
            self.logger.info("[+] Bot connected to Discord")
            self.logger.info("[*] Name: {}".format(self.discord_bot.user.name))
            self.logger.info("[*] ID: {}".format(self.discord_bot.user.id))
            await self.discord_bot.change_presence(activity=discord.Game(name='Chatting with Humans'))

        @self.discord_bot.event
        async def on_message(message):
            if message.author.bot or str(message.channel) != self.channel_name:
                return

            if message.content is None:
                self.logger.error("[-] Empty message received.")
                return

            now = datetime.now()

            if message.content.startswith(self.BOT_PREFIX):
                # Pass on to rest of the bot commands
                await self.discord_bot.process_commands(message)
                return

            try:
                aiml_response = self.aiml_kernel.respond(message.content)
                aiml_response = aiml_response.replace("://", "")
                aiml_response = "%s: %s" % (message.author.mention, aiml_response)

                self.logger.info("[%s] (%s) %s: %s\nResponse: %s" %
                                 (now.isoformat(), message.guild.name, message.author, message.content, aiml_response))
                self.insert_chat_log(now, message, aiml_response)

                async with message.channel.typing():
                    await asyncio.sleep(random.randint(1, 3))
                    await message.channel.send(aiml_response)

            except discord.HTTPException as e:
                self.logger.error("[-] Discord HTTP Error: %s" % e)
            except Exception as e:
                self.logger.error("[-] General Error: %s" % e)

    def run(self):
        self.logger.info("[*] Attempting to run bot...")
        self.discord_bot.run(self.token)
        self.logger.info("[*] Bot run.")

    def insert_chat_log(self, now, message, aiml_response):
        self.cursor.execute('INSERT INTO chat_log VALUES (?, ?, ?, ?, ?)',
                            (now.isoformat(), message.guild.id, message.author.id,
                             str(message.content), aiml_response))

        # Add user if necessary
        self.cursor.execute('SELECT id FROM users WHERE id=?', (message.author.id,))
        if not self.cursor.fetchone():
            self.cursor.execute(
                'INSERT INTO users VALUES (?, ?, ?)',
                (message.author.id, message.author.name, datetime.now().isoformat()))

        # Add server if necessary
        self.cursor.execute('SELECT id FROM servers WHERE id=?', (message.guild.id,))
        if not self.cursor.fetchone():
            self.cursor.execute(
                'INSERT INTO servers VALUES (?, ?, ?)',
                (message.guild.id, message.guild.name, datetime.now().isoformat()))

        self.db.commit()
