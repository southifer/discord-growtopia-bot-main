import json
import requests
import asyncio
import time
import discord
from discord import Activity, ActivityType, Status
from discord.ext import commands
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
from matplotlib.ticker import FuncFormatter
from datetime import datetime
import logging
import os
import sys

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

def retrieveJson(fileName):
    try:
        with open(fileName, 'r') as file:
            jsonData = json.load(file)
        logger.info(f"Successfully retrieved JSON data from {fileName}.")
        return jsonData
    except FileNotFoundError:
        logger.error(f"The file {fileName} does not exist.")
        return None
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from the file {fileName}.")
        return None

def updateJson(file_name, new_data):
    """Update the JSON file with new data and save it."""
    try:
        with open(file_name, 'w') as file:
            json.dump(new_data, file, indent=4)
        return True
    except Exception as e:
        print(f"Failed to update JSON file {file_name}: {e}")
        return False

def storeDatabase(fileName):
    try:
        with open(fileName, 'w') as file:
            json.dump(database, file, indent=4)
        logger.info(f"Database successfully saved to {fileName}.")
    except Exception as e:
        logger.error(f"An error occurred while saving the database: {e}")

def loadDatabase(fileName):
    data = retrieveJson(fileName)
    if data is not None:
        logger.info(f'Retrieved {len(data)} data entries from {fileName}.')
        return data
    return []

config = retrieveJson("config.json")
database = loadDatabase("database.json")

startTime = time.time()

intents = discord.Intents.all()
intents.presences = False
client = commands.Bot(command_prefix='!', intents=intents)

async def changePresence(status: Status, type: str, task: str):
    """
    Changes the bot's presence.

    Parameters:
        status (Status): The status to set (e.g., Status.online).
        type (str): The type of activity (e.g., 'playing', 'watching').
        task (str): The name of the activity.
    """

    # Retrieve the ActivityType dynamically and default to 'playing' if not found
    activity_type = getattr(ActivityType, type, ActivityType.playing)

    # Create the Activity object
    game = Activity(type=activity_type, name=task)

    # Update the bot's presence
    await client.change_presence(status=status, activity=game)
    logger.info(f"Changed presence to {status} - {type}: {task}")

def loadProxy():
    try:
        if config['proxy']['username'] and config['proxy']['password']:
            proxy = f"socks5://{config['proxy']['username']}:{config['proxy']['password']}@{config['proxy']['host']}:{config['proxy']['port']}"
        else:
            proxy = f"socks5://{config['proxy']['host']}:{config['proxy']['port']}"

        logger.info(f"Proxy loaded: {proxy}")
        return {'http': proxy, 'https': proxy}
    except KeyError as e:
        logger.error(f"Proxy configuration key error: {e}")
        return None
    except Exception as e:
        logger.error(f"An error occurred while loading the proxy: {e}")
        return None

async def statusTask():
    """Main task for updating status and handling online player checks."""

    global database
    playerSession = 0  # This will be used for the comparison
    stringNone = ''
    last_message = None
    last_message_time = 0
    message_sent_times = {}

    if config["proxy"]["enable"]:
        try:
            proxyInformation = getProxyInformation()
            if proxyInformation:
                logger.info('=========================================')
                logger.info("IP Info:")
                logger.info(f"* IP: {proxyInformation['ip']}")
                logger.info(f"* City: {proxyInformation['city']}")
                logger.info(f"* Region: {proxyInformation['region']}")
                logger.info(f"* Country: {proxyInformation['country']}")
                logger.info(f"* Org: {proxyInformation['org']}")
                logger.info('=========================================')
        except Exception as e:
            logger.error(f"Error fetching proxy information: {e}")
            return

        try:
            retrieveProxy = loadProxy()
        except Exception as e:
            logger.error(f"Error loading proxy settings: {e}")
            return

    while True:
        try:
            if not config or 'target' not in config:
                raise ValueError("Invalid configuration. 'target' key is missing in config.")

            startTimeRequest = time.time()

            try:
                retrieveData = requests.get(
                    config['target'], 
                    proxies=retrieveProxy if config["proxy"]["enable"] else None, 
                    timeout=15
                )
                retrieveData.raise_for_status()
            except requests.Timeout:
                logger.error("The request timed out.")
                continue
            except requests.RequestException as e:
                logger.error(f"Error during the request: {str(e)}")
                continue

            try:
                data = retrieveData.json()
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON: {str(e)}")
                continue

            try:
                response = data.get('online_user', '0')
                onlineUser = int(response)
            except (KeyError, ValueError) as e:
                logger.error(f"Error retrieving 'online_user' from the response: {str(e)}")
                continue

            finalResult = onlineUser - playerSession
            isMinus = finalResult < -1500

            if isMinus:
                stringNone = f'{onlineUser:,} ({finalResult:,}) online players'
            else:
                if str(finalResult).find('-'):
                    stringNone = f'{onlineUser:,} (+{finalResult:,}) online players'
                else:
                    stringNone = f'{onlineUser:,} ({finalResult:,}) online players'

            if playerSession == 0 or finalResult == 0:
                stringNone = f'{onlineUser:,} online players.'

            if onlineUser <= 1500:
                stringNone = 'SERVER MAINTENANCE!'

            finalString = f'[{time.strftime("%H:%M:%S")}] {stringNone}'
            finishTimeRequest = time.time() - startTimeRequest

            # logger.info("=========================================")
            # logger.info(f"* Status code: {retrieveData.status_code}")
            # logger.info(f"* Online user: {onlineUser}")
            # logger.info(f"* Subtract Result: {finalResult}")
            # logger.info(f"* Is Minus: {isMinus}")
            # logger.info(f"* Proxy: {retrieveProxy['https']}")
            # logger.info(f"* Duration: {finishTimeRequest:.2f} seconds")
            # logger.info("=========================================")


            for server in config['server']:
                messageSent = False

                if playerSession > 0:
                    sessionDropRate = ((onlineUser - playerSession) / playerSession) * 100
                    sessionDropRate = round(sessionDropRate, 2)
                else:
                    sessionDropRate = 0

                target_channel = client.get_channel(server['channelId'])
                notify_channel = client.get_channel(server['channelNotify'])

                currentTime = int(time.time())

                last_sent_time = message_sent_times.get(server['channelId'], 0)
                if last_message == finalString and (currentTime - last_sent_time) < 60:
                    logger.info(f"Skipping duplicate message for channel {server['channelId']}")
                    continue

                try:
                    if onlineUser != 0 and not messageSent:
                        # Sent message to targeted daily channel
                        await target_channel.send(f'{finalString} ({sessionDropRate:+.2f}%)')
                        messageSent = True

                        # Sent message if server is up
                        if database:
                            previousPlayerCount = int(database[-1]['player'].replace(',', ''))
                            if previousPlayerCount < 2000 and onlineUser > 2000:
                                await notify_channel.send(f"[{time.strftime('%H:%M:%S')}] GROWTOPIA SERVER IS UP! <t:{currentTime}:R> <@&{server['role']}>")

                        # Sent message if minues occured
                        if isMinus:
                            await notify_channel.send(f'{finalString} <t:{currentTime}:R> <@&{server['role']}>')

                    last_message = finalString
                    last_message_time = currentTime
                    message_sent_times[server['channelId']] = currentTime

                except AttributeError:
                    logger.error(f"Channel not found: {server['channelId']} or {server['channelNotify']}")
                except discord.HTTPException as e:
                    logger.error(f"Error sending message to Discord channel: {str(e)}")

            try:
                await changePresence(Status.online, 'watching', stringNone)
            except discord.DiscordException as e:
                logger.error(f"Error updating bot presence: {str(e)}")

            try:
                database.append({'player': f'{onlineUser:,}', 'date': time.time()})
                if len(database) > 700:
                    database = database[-700:]

                storeDatabase("database.json")
            except Exception as e:
                logger.error(f"Error updating or saving the database: {str(e)}")

            playerSession = onlineUser  # Update playerSession with the latest online user count

        except Exception as e:
            logger.error(f"An unexpected error occurred: {str(e)}")

        await asyncio.sleep(60)


def formatThousands(x, pos):
    return f'{int(x):,}'

def plotDatabase():
    if not database:
        logger.warning("No data to plot.")
        return

    players = [int(entry['player'].replace(',', '')) for entry in database]
    times = [datetime.fromtimestamp(entry['date']) for entry in database]

    plt.figure(figsize=(10, 6), facecolor='#404570')  # Dark gray-blue background

    # Updated color scheme
    line_color = '#FF8C00'  # Vibrant orange for the line
    marker_color = '#FFD700'  # Gold for markers
    grid_color = '#B0C4DE'  # Light steel blue for grid lines

    plt.plot(times, players, color=line_color, marker='o', markersize=1, linewidth=1.5, label='Online Players')

    plt.title('Player graph in last 12 hours', fontsize=14, fontweight='bold', color='white')

    plt.gca().xaxis.set_major_formatter(DateFormatter('%H:%M'))
    plt.gca().xaxis.set_major_locator(plt.MaxNLocator(12))  # Limit number of x-ticks
    plt.gca().yaxis.set_major_formatter(FuncFormatter(formatThousands))

    plt.grid(True, linestyle='-', linewidth=0.5, color=grid_color)  # Light steel blue grid lines
    plt.box(False)

    plt.gca().tick_params(axis='both', colors='white')  # Customize tick params
    for tick in plt.gca().get_xticklabels() + plt.gca().get_yticklabels():
        tick.set_fontweight('bold')

    plt.tight_layout()  # Adjust layout to fit all elements
    plt.savefig("graph.png", dpi=300, bbox_inches='tight')  # Save the figure with tight bounding box
    plt.close()  # Close the plot to avoid display in some environments
    logger.info("Graph saved as graph.png.")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content == "!db":
        logger.info(f"Database length requested: {len(database)}")

    if message.author.id == config['owner']:
        if message.content == "!restart":
            await message.reply("Restarting bot...")

            os.execv(sys.executable, ['python'] + sys.argv)

    if message.content == "!plr":
        startTimeSent = time.time()  # Track the start time for processing
        embed = None  # Initialize the embed variable here
        try:
            # Check configuration validity
            if not config or 'target' not in config:
                await message.reply('Configuration is not valid...')
                logger.error("Configuration is not valid.")
                return

            # Load proxy settings and make a request
            try:
                # retrieveProxy = loadProxy()
                retrieveData = requests.get(config['target'])
                retrieveData.raise_for_status()  # Raise an error for bad responses

            except requests.Timeout:
                logger.error("The request to the target timed out.")
                await message.reply("Error: The request timed out. Please try again later.")
                return  # Exit the command

            except requests.ConnectionError as e:
                logger.error(f"Connection error occurred: {str(e)}")
                await message.reply("Error: Unable to connect to the target server.")
                return

            except requests.HTTPError as e:
                logger.error(f"HTTP error occurred: {str(e)}")
                await message.reply("Error: Unable to retrieve data from the target server.")
                return

            except Exception as e:
                logger.error(f"An unexpected error occurred during the request: {str(e)}")
                await message.reply("Error: An unexpected error occurred. Please try again later.")
                return

            # Parse the JSON response
            try:
                data = retrieveData.json()
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON response: {str(e)}")
                await message.reply("Error: Unable to decode the data received. Please try again later.")
                return

            # Check for online users
            response = data.get('online_user', '0')
            if response:
                onlineUser = int(response)

                # Check for isMinus occurrences in the last hour
                one_hour_ago = time.time() - 3600
                isMinus_count = 0
                serverStatus = "Normal"

                # Count occurrences of isMinus in the database
                for entry in database:
                    try:
                        player_count = int(entry['player'].replace(',', ''))
                        if player_count < onlineUser - 500 and entry['date'] >= one_hour_ago:
                            isMinus_count += 1
                    except (ValueError, KeyError) as e:
                        logger.warning(f"Skipping invalid entry in database: {str(e)}")

                # Send warning if too many isMinus occurrences
                if isMinus_count > 10:
                    serverStatus = "Server Lagging"
                if onlineUser <= 1500:
                    serverStatus = "Maintenance"

                # Plot and prepare the database
                plotDatabase()

                # Prepare the embed for the response
                embed = discord.Embed(color=0x7b86da)
                embed.set_image(url="attachment://graph.png")

                embed.add_field(name="<:transmog:1292697743386607716> Online Players", value=f"- {onlineUser:,}", inline=True)
                embed.add_field(name="<:bot:1269173357023068242> Server Status", value=f'- {serverStatus}', inline=True)

                embed.timestamp = datetime.fromtimestamp(time.time())

                if message.author.avatar is not None:
                    embed.set_footer(text="Created for Noir", icon_url=f"{message.author.avatar}")
                else:
                    embed.set_footer(text="Created for Noir")

            finishTimeSent = time.time() - startTimeSent
            logger.info(f'Finished sending player count: {finishTimeSent:.2f} seconds')
            await message.reply(file=discord.File("graph.png"), embed=embed)

        except Exception as e:
            logger.error(f'An unexpected error occurred: {str(e)}')
            await message.reply(
                "Error: An unexpected error occurred while processing your request. Please try again later.")

        finally:
            # Cleanup actions
            if embed is not None:
                del embed  # Clear the embed variable if it was created

            # Any other necessary cleanup actions
            logger.info("Cleanup completed after processing '!plr' command.")


def getProxyInformation():
    """Fetch IP information from ipinfo.io using the provided proxies."""
    try:
        retrieveProxy = loadProxy()
        response = requests.get('https://ipinfo.io/json', proxies=retrieveProxy, timeout=15)
        logger.info("Successfully retrieved IP information.")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"An error occurred while fetching IP info: {e}")
        return None
    
@client.event
async def on_ready():
    finishTime = time.time() - startTime

    logger.info(f'Login as {client.user}')
    logger.info(f'Time taken to initialize: {finishTime:.2f} seconds')

    await changePresence(Status.dnd, 'watching', 'Loading config...')
    await statusTask()

client.run(config['token'])